import argparse
import copy
import random
import sys
from pathlib import Path

import networkx as nx
import numpy as np
import pandas as pd

# Path patch for local package imports.
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from scripts.topo_manager import generate_topology
from scripts_flow.main_snn import build_flow_config, build_snn_runtime_config, choose_failure_edge
from scripts_flow.ppo_lite import PPOLitePolicy
from scripts_flow.snn_node import SNNQueueNode
from scripts_flow.snn_router import SNNRouter
from scripts_flow.snn_simulator import SNNSimulator
from scripts_flow.traffic import TrafficGenerator


class OSPFSimulator:
    """Hop-count shortest path routing with the same queueing model."""

    def __init__(self, node_dict, physical_graph, hop_limit=64):
        self.nodes = node_dict
        self.G = physical_graph
        self.hop_limit = hop_limit
        self.inflight_packets = []
        self.total_generated = 0
        self.total_delivered = 0
        self.total_delay = 0.0
        self.total_delivered_hops = 0
        self.delivered_delay_samples = []
        self.delivered_step_samples = []
        self.delivered_hop_samples = []
        self.delivered_shortest_hop_samples = []
        self.delivered_extra_hop_samples = []
        self.delivered_queue_delay_samples = []
        self._sp_cache = {}
        self._sp_cache_edge_count = None

    def _shortest_hop_len(self, src, dst):
        edge_count = self.G.number_of_edges()
        if self._sp_cache_edge_count != edge_count:
            self._sp_cache.clear()
            self._sp_cache_edge_count = edge_count
        key = (src, dst)
        if key in self._sp_cache:
            return self._sp_cache[key]
        try:
            val = int(nx.shortest_path_length(self.G, source=src, target=dst))
        except nx.NetworkXNoPath:
            val = None
        self._sp_cache[key] = val
        return val

    def _on_packet_delivered(self, packet, step_k):
        delay = int(step_k - packet.creation_step)
        hops = int(getattr(packet, "hops", 0))
        shortest = self._shortest_hop_len(packet.src, packet.dst)
        if shortest is None:
            shortest = hops
        extra_hop = max(0, int(hops - shortest))
        queue_delay = max(0, int(delay - hops))

        self.total_delivered += 1
        self.total_delay += float(delay)
        self.total_delivered_hops += hops

        self.delivered_delay_samples.append(delay)
        self.delivered_step_samples.append(int(step_k))
        self.delivered_hop_samples.append(hops)
        self.delivered_shortest_hop_samples.append(int(shortest))
        self.delivered_extra_hop_samples.append(extra_hop)
        self.delivered_queue_delay_samples.append(queue_delay)

    def _pick_next_hop(self, node_id, packet, dst_dist_cache):
        try:
            path = nx.shortest_path(self.G, source=node_id, target=packet.dst)
            if len(path) > 1:
                return path[1]
        except nx.NetworkXNoPath:
            return None
        return None

    def run_step(self, step_k, new_packets):
        dst_dist_cache = {}
        for pkt in new_packets:
            if not hasattr(pkt, "hops"):
                pkt.hops = 0
            self.total_generated += 1
            self.nodes[pkt.src].receive_packet(pkt)

        for node_id, node in self.nodes.items():
            pkts = node.process_and_forward(step_k)
            for p in pkts:
                if p.dst == node_id:
                    self._on_packet_delivered(p, step_k)
                    continue

                if p.hops >= self.hop_limit:
                    node.notify_link_failure_drop()
                    continue

                next_hop = self._pick_next_hop(node_id, p, dst_dist_cache)

                if next_hop is not None:
                    p.hops += 1
                    self.inflight_packets.append((p, next_hop, step_k + 1, node_id))
                else:
                    node.notify_link_failure_drop()

        remaining = []
        for p, nxt, arr_t, last_node in self.inflight_packets:
            if step_k >= arr_t:
                if self.G.has_edge(last_node, nxt):
                    self.nodes[nxt].receive_packet(p)
                else:
                    self.nodes[last_node].notify_link_failure_drop()
            else:
                remaining.append((p, nxt, arr_t, last_node))
        self.inflight_packets = remaining

        total_loss = sum(n.total_dropped for n in self.nodes.values())
        pdr = self.total_delivered / self.total_generated if self.total_generated else 0.0
        avg_delay = self.total_delay / self.total_delivered if self.total_delivered else 0.0
        avg_hop = self.total_delivered_hops / self.total_delivered if self.total_delivered else 0.0
        return {"loss": total_loss, "pdr": pdr, "avg_delay": avg_delay, "avg_hop": avg_hop}


class OSPFSyncSimulator(OSPFSimulator):
    """OSPF with periodic sync and delayed SPF recomputation."""

    def __init__(self, node_dict, physical_graph, hop_limit=64, sync_period=12, spf_delay=4):
        super().__init__(node_dict, physical_graph, hop_limit=hop_limit)
        self.sync_period = max(1, int(sync_period))
        self.spf_delay = max(0, int(spf_delay))
        self.broadcast_count = 0
        self.table_updates = 0

        self.effective_graph = self.G.copy()
        self.routing_table = {u: {d: None for d in self.nodes} for u in self.nodes}
        self.pending_changes = []
        self.pending_keys = set()
        self._recompute_routes()

    @staticmethod
    def _edge_key(u, v):
        return (u, v) if u < v else (v, u)

    def _route_next_hop(self, src, dst):
        if src == dst:
            return src
        try:
            path = nx.shortest_path(self.effective_graph, source=src, target=dst)
            if len(path) > 1:
                return path[1]
        except nx.NetworkXNoPath:
            return None
        return None

    def _recompute_routes(self):
        updates = 0
        for u in self.nodes:
            for d in self.nodes:
                nxt = self._route_next_hop(u, d)
                if self.routing_table[u][d] != nxt:
                    updates += 1
                    self.routing_table[u][d] = nxt
        self.table_updates += updates
        self.broadcast_count += self.effective_graph.number_of_nodes()

    def _schedule_topology_changes(self, step_k):
        actual = {self._edge_key(u, v) for u, v in self.G.edges()}
        effective = {self._edge_key(u, v) for u, v in self.effective_graph.edges()}

        to_remove = effective - actual
        to_add = actual - effective

        apply_step = int(step_k + self.spf_delay)
        for e in to_remove:
            key = ("remove", e[0], e[1])
            if key in self.pending_keys:
                continue
            self.pending_keys.add(key)
            self.pending_changes.append((apply_step, "remove", e[0], e[1]))
        for e in to_add:
            key = ("add", e[0], e[1])
            if key in self.pending_keys:
                continue
            self.pending_keys.add(key)
            self.pending_changes.append((apply_step, "add", e[0], e[1]))

    def _apply_due_changes(self, step_k):
        if not self.pending_changes:
            return False
        changed = False
        keep = []
        for apply_step, action, u, v in self.pending_changes:
            if apply_step > step_k:
                keep.append((apply_step, action, u, v))
                continue
            self.pending_keys.discard((action, u, v))
            if action == "remove":
                if self.effective_graph.has_edge(u, v):
                    self.effective_graph.remove_edge(u, v)
                    changed = True
            elif action == "add":
                if not self.effective_graph.has_edge(u, v):
                    self.effective_graph.add_edge(u, v)
                    self.effective_graph[u][v]["cost"] = 1.0
                    changed = True
        self.pending_changes = keep
        return changed

    def _pick_next_hop(self, node_id, packet, dst_dist_cache):
        return self.routing_table.get(node_id, {}).get(packet.dst)

    def run_step(self, step_k, new_packets):
        if step_k % self.sync_period == 0:
            self._schedule_topology_changes(step_k)
        changed = self._apply_due_changes(step_k)
        if changed and step_k % self.sync_period == 0:
            self._recompute_routes()
        elif step_k % self.sync_period == 0:
            self.broadcast_count += self.effective_graph.number_of_nodes()

        dst_dist_cache = {}
        for pkt in new_packets:
            if not hasattr(pkt, "hops"):
                pkt.hops = 0
            self.total_generated += 1
            self.nodes[pkt.src].receive_packet(pkt)

        for node_id, node in self.nodes.items():
            pkts = node.process_and_forward(step_k)
            for p in pkts:
                if p.dst == node_id:
                    self._on_packet_delivered(p, step_k)
                    continue

                if p.hops >= self.hop_limit:
                    node.notify_link_failure_drop()
                    continue

                next_hop = self._pick_next_hop(node_id, p, dst_dist_cache)
                if next_hop is not None and self.effective_graph.has_edge(node_id, next_hop):
                    p.hops += 1
                    self.inflight_packets.append((p, next_hop, step_k + 1, node_id))
                else:
                    node.notify_link_failure_drop()

        remaining = []
        for p, nxt, arr_t, last_node in self.inflight_packets:
            if step_k >= arr_t:
                if self.G.has_edge(last_node, nxt):
                    self.nodes[nxt].receive_packet(p)
                else:
                    self.nodes[last_node].notify_link_failure_drop()
            else:
                remaining.append((p, nxt, arr_t, last_node))
        self.inflight_packets = remaining

        total_loss = sum(n.total_dropped for n in self.nodes.values())
        pdr = self.total_delivered / self.total_generated if self.total_generated else 0.0
        avg_delay = self.total_delay / self.total_delivered if self.total_delivered else 0.0
        avg_hop = self.total_delivered_hops / self.total_delivered if self.total_delivered else 0.0
        return {
            "loss": total_loss,
            "pdr": pdr,
            "avg_delay": avg_delay,
            "avg_hop": avg_hop,
            "broadcasts": float(self.broadcast_count),
            "table_updates": float(self.table_updates),
        }


class ECMPSimulator(OSPFSimulator):
    """Hop-count ECMP routing with equal-cost next-hop splitting."""

    def _pick_next_hop(self, node_id, packet, dst_dist_cache):
        if packet.dst not in dst_dist_cache:
            dst_dist_cache[packet.dst] = nx.single_source_shortest_path_length(self.G, packet.dst)
        dist_map = dst_dist_cache[packet.dst]
        curr_dist = dist_map.get(node_id)
        if curr_dist is None or curr_dist <= 0:
            return None

        target_dist = curr_dist - 1
        candidates = [n for n in self.G.neighbors(node_id) if dist_map.get(n) == target_dist]
        if not candidates:
            return None
        return random.choice(candidates)


class BackpressureSimulator(OSPFSimulator):
    """Destination-aware backpressure (MaxWeight-like) routing baseline."""

    def __init__(self, node_dict, physical_graph, hop_limit=64, dist_bias=0.25, hold_threshold=0.0):
        super().__init__(node_dict, physical_graph, hop_limit=hop_limit)
        self.dist_bias = dist_bias
        self.hold_threshold = hold_threshold

    def _build_dst_queue_counts(self):
        counts = {u: {} for u in self.nodes}
        for u, node in self.nodes.items():
            slot = counts[u]
            for pkt in node.input_queue:
                slot[pkt.dst] = slot.get(pkt.dst, 0) + 1
        return counts

    def _pick_next_hop(self, node_id, packet, dst_dist_cache, dst_queue_counts):
        if packet.dst not in dst_dist_cache:
            dst_dist_cache[packet.dst] = nx.single_source_shortest_path_length(self.G, packet.dst)
        dist_map = dst_dist_cache[packet.dst]
        curr_dist = dist_map.get(node_id)
        if curr_dist is None:
            return None

        q_curr = float(dst_queue_counts[node_id].get(packet.dst, 0))
        best_weight = None
        best_neighbors = []
        for n in self.G.neighbors(node_id):
            neigh_dist = dist_map.get(n)
            if neigh_dist is None:
                continue
            q_neigh = float(dst_queue_counts[n].get(packet.dst, 0))
            dist_gain = float(curr_dist - neigh_dist)
            weight = (q_curr - q_neigh) + self.dist_bias * dist_gain
            if best_weight is None or weight > best_weight + 1e-12:
                best_weight = weight
                best_neighbors = [n]
            elif abs(weight - best_weight) <= 1e-12:
                best_neighbors.append(n)

        if not best_neighbors or best_weight is None:
            return None
        if best_weight <= self.hold_threshold:
            return None

        # Prefer non-regressive neighbors when max weights tie.
        better = [n for n in best_neighbors if dist_map.get(n, curr_dist + 1) <= curr_dist]
        choices = better if better else best_neighbors
        return random.choice(choices)

    def run_step(self, step_k, new_packets):
        dst_dist_cache = {}
        for pkt in new_packets:
            if not hasattr(pkt, "hops"):
                pkt.hops = 0
            self.total_generated += 1
            self.nodes[pkt.src].receive_packet(pkt)

        dst_queue_counts = self._build_dst_queue_counts()
        for node_id, node in self.nodes.items():
            pkts = node.process_and_forward(step_k)
            for p in pkts:
                slot = dst_queue_counts[node_id]
                slot[p.dst] = max(0, int(slot.get(p.dst, 0)) - 1)

                if p.dst == node_id:
                    self._on_packet_delivered(p, step_k)
                    continue

                if p.hops >= self.hop_limit:
                    node.notify_link_failure_drop()
                    continue

                next_hop = self._pick_next_hop(node_id, p, dst_dist_cache, dst_queue_counts)
                if next_hop is not None:
                    p.hops += 1
                    self.inflight_packets.append((p, next_hop, step_k + 1, node_id))
                else:
                    # Hold packet for future scheduling opportunity.
                    if node.receive_packet(p):
                        slot[p.dst] = int(slot.get(p.dst, 0)) + 1
                    else:
                        node.notify_link_failure_drop()

        remaining = []
        for p, nxt, arr_t, last_node in self.inflight_packets:
            if step_k >= arr_t:
                if self.G.has_edge(last_node, nxt):
                    self.nodes[nxt].receive_packet(p)
                else:
                    self.nodes[last_node].notify_link_failure_drop()
            else:
                remaining.append((p, nxt, arr_t, last_node))
        self.inflight_packets = remaining

        total_loss = sum(n.total_dropped for n in self.nodes.values())
        pdr = self.total_delivered / self.total_generated if self.total_generated else 0.0
        avg_delay = self.total_delay / self.total_delivered if self.total_delivered else 0.0
        avg_hop = self.total_delivered_hops / self.total_delivered if self.total_delivered else 0.0
        return {"loss": total_loss, "pdr": pdr, "avg_delay": avg_delay, "avg_hop": avg_hop}


class PPOSimulator(OSPFSimulator):
    """PPO-Lite adaptive next-hop routing baseline (pure numpy, masked discrete action)."""

    def __init__(self, node_dict, physical_graph, hop_limit=64, seed=7, train=True):
        super().__init__(node_dict, physical_graph, hop_limit=hop_limit)
        self.train = bool(train)
        self.policy = PPOLitePolicy(
            n_features=6,
            seed=int(seed),
            lr=0.03,
            clip_eps=0.2,
            update_interval=256,
            epochs=3,
            max_grad_norm=1.0,
        )

    def _build_feature(self, node_id, neigh_id, dst, dist_map):
        node = self.nodes[node_id]
        neigh = self.nodes[neigh_id]
        q_curr = float(len(node.input_queue)) / max(float(node.buffer_size), 1.0)
        q_neigh = float(len(neigh.input_queue)) / max(float(neigh.buffer_size), 1.0)
        curr_dist = float(dist_map.get(node_id, 1e6))
        neigh_dist = float(dist_map.get(neigh_id, 1e6))
        dist_gain = max(-2.0, min(2.0, curr_dist - neigh_dist)) / 2.0
        s_curr = float(getattr(node, "S", 0.0))
        s_neigh = float(getattr(neigh, "S", 0.0))
        return np.asarray([1.0, q_curr, q_neigh, dist_gain, s_curr, s_neigh], dtype=float), dist_gain

    def _pick_next_hop(self, node_id, packet, dst_dist_cache):
        if packet.dst not in dst_dist_cache:
            dst_dist_cache[packet.dst] = nx.single_source_shortest_path_length(self.G, packet.dst)
        dist_map = dst_dist_cache[packet.dst]
        curr_dist = dist_map.get(node_id)
        if curr_dist is None:
            return None

        neighbors = list(self.G.neighbors(node_id))
        if not neighbors:
            return None

        finite = [n for n in neighbors if n in dist_map]
        if not finite:
            return None

        non_regress = [n for n in finite if dist_map[n] <= curr_dist]
        candidates = non_regress if non_regress else finite
        feat_rows = []
        gains = []
        for n in candidates:
            feat, gain = self._build_feature(node_id, n, packet.dst, dist_map)
            feat_rows.append(feat)
            gains.append(gain)
        feat_mat = np.vstack(feat_rows)

        a, old_logp, _ = self.policy.select_action(feat_mat, greedy=(not self.train))
        if a is None:
            return None
        next_hop = candidates[a]

        if self.train:
            # Immediate shaping reward: progress to dst while avoiding local congestion.
            q_curr = feat_mat[a][1]
            q_neigh = feat_mat[a][2]
            s_neigh = feat_mat[a][5]
            reward = 0.60 * float(gains[a]) - 0.25 * q_neigh - 0.10 * q_curr - 0.15 * s_neigh
            self.policy.record(feat_mat, a, old_logp, reward)
        return next_hop

    def run_step(self, step_k, new_packets):
        dst_dist_cache = {}
        for pkt in new_packets:
            if not hasattr(pkt, "hops"):
                pkt.hops = 0
            self.total_generated += 1
            self.nodes[pkt.src].receive_packet(pkt)

        for node_id, node in self.nodes.items():
            pkts = node.process_and_forward(step_k)
            for p in pkts:
                if p.dst == node_id:
                    self._on_packet_delivered(p, step_k)
                    continue

                if p.hops >= self.hop_limit:
                    node.notify_link_failure_drop()
                    continue

                next_hop = self._pick_next_hop(node_id, p, dst_dist_cache)
                if next_hop is not None:
                    p.hops += 1
                    self.inflight_packets.append((p, next_hop, step_k + 1, node_id))
                else:
                    node.notify_link_failure_drop()

        remaining = []
        for p, nxt, arr_t, last_node in self.inflight_packets:
            if step_k >= arr_t:
                if self.G.has_edge(last_node, nxt):
                    self.nodes[nxt].receive_packet(p)
                else:
                    self.nodes[last_node].notify_link_failure_drop()
            else:
                remaining.append((p, nxt, arr_t, last_node))
        self.inflight_packets = remaining

        total_loss = sum(n.total_dropped for n in self.nodes.values())
        pdr = self.total_delivered / self.total_generated if self.total_generated else 0.0
        avg_delay = self.total_delay / self.total_delivered if self.total_delivered else 0.0
        avg_hop = self.total_delivered_hops / self.total_delivered if self.total_delivered else 0.0
        return {"loss": total_loss, "pdr": pdr, "avg_delay": avg_delay, "avg_hop": avg_hop}

    def finalize(self):
        self.policy.finalize()


def build_nodes(num_nodes, beta):
    return {
        i: SNNQueueNode(
            node_id=i,
            service_rate=22,
            buffer_size=180,
            alpha=0.22,
            beta_I=beta,
            T_d=1,
            tau_m=4.0,
            v_th=1.0,
        )
        for i in range(num_nodes)
    }


def run_case(algo, topo, seed, steps=260, fail_step=160, er_p=0.06, ba_m=3, snn_mode="snn_event_dv"):
    random.seed(seed)
    np.random.seed(seed)

    num_nodes = 100
    graph0 = generate_topology(kind=topo, num_nodes=num_nodes, seed=seed, er_p=er_p, ba_m=ba_m)
    flow_cfg = build_flow_config(num_nodes=num_nodes, seed=seed)
    traffic = TrafficGenerator(flow_cfg)
    failure_edge = choose_failure_edge(graph0)

    graph = copy.deepcopy(graph0)
    if algo == "ospf":
        sim = OSPFSimulator(build_nodes(num_nodes, 0.0), graph, hop_limit=64)
    elif algo == "ospf_sync":
        sim = OSPFSyncSimulator(
            build_nodes(num_nodes, 0.0),
            graph,
            hop_limit=64,
            sync_period=12,
            spf_delay=4,
        )
    elif algo == "ecmp":
        sim = ECMPSimulator(build_nodes(num_nodes, 0.0), graph, hop_limit=64)
    elif algo == "backpressure":
        sim = BackpressureSimulator(build_nodes(num_nodes, 0.0), graph, hop_limit=64)
    elif algo == "ppo":
        sim = PPOSimulator(build_nodes(num_nodes, 0.0), graph, hop_limit=64, seed=seed, train=True)
    elif algo == "snn":
        cfg = build_snn_runtime_config(topo, snn_mode)
        router_kwargs = dict(cfg.get("router", {}))
        router_kwargs["beta_s"] = 8.0
        router = SNNRouter(**router_kwargs)
        sim_kwargs = dict(cfg.get("sim", {}))
        sim_kwargs["known_destinations"] = [f["dst"] for f in flow_cfg]
        sim = SNNSimulator(
            build_nodes(num_nodes, 8.0),
            graph,
            router,
            routing_mode=snn_mode,
            **sim_kwargs,
        )
    else:
        raise ValueError(f"Unsupported algo: {algo}")

    history = []
    for k in range(steps):
        if k == fail_step and failure_edge is not None and graph.has_edge(*failure_edge):
            graph.remove_edge(*failure_edge)
        metrics = sim.run_step(k, traffic.generate(k))
        metrics["step"] = k
        history.append(metrics)
    if hasattr(sim, "finalize"):
        sim.finalize()

    df = pd.DataFrame(history)
    final = df.iloc[-1]
    post = df[(df.step >= fail_step + 20) & (df.step <= min(steps - 1, fail_step + 80))]
    return {
        "algo": algo,
        "topo": topo,
        "seed": seed,
        "pdr_final": float(final.pdr),
        "delay_final": float(final.avg_delay),
        "hop_final": float(final.avg_hop),
        "loss_final": int(final.loss),
        "pdr_post": float(post.pdr.mean()),
        "delay_post": float(post.avg_delay.mean()),
    }


def main():
    parser = argparse.ArgumentParser(description="Compare SNN against OSPF/ECMP baselines.")
    parser.add_argument(
        "--algos",
        default="ospf,ecmp,backpressure,snn",
        help="Comma-separated algos from: ospf,ospf_sync,ecmp,backpressure,ppo,snn",
    )
    parser.add_argument("--topos", default="ba,er", help="Comma-separated topology list, e.g. ba,er")
    parser.add_argument("--seeds", default="11,17,23,29,31", help="Comma-separated seeds")
    parser.add_argument("--steps", type=int, default=260)
    parser.add_argument("--fail-step", type=int, default=160)
    parser.add_argument("--er-p", type=float, default=0.06)
    parser.add_argument("--ba-m", type=int, default=3)
    parser.add_argument("--snn-mode", default="snn_event_dv", help="snn_event_dv | snn_spike_native")
    parser.add_argument("--out", default="run_dir/ospf_compare_runs.csv")
    parser.add_argument("--out-agg", default="run_dir/ospf_compare_agg.csv")
    args = parser.parse_args()

    algos = [a.strip() for a in args.algos.split(",") if a.strip()]
    valid_algos = {"ospf", "ospf_sync", "ecmp", "backpressure", "ppo", "snn"}
    invalid = [a for a in algos if a not in valid_algos]
    if invalid:
        raise ValueError(f"Unsupported algos in --algos: {invalid}")

    topos = [t.strip() for t in args.topos.split(",") if t.strip()]
    seeds = [int(s.strip()) for s in args.seeds.split(",") if s.strip()]

    rows = []
    for topo in topos:
        for seed in seeds:
            for algo in algos:
                rows.append(
                    run_case(
                        algo=algo,
                        topo=topo,
                        seed=seed,
                        steps=args.steps,
                        fail_step=args.fail_step,
                        er_p=args.er_p,
                        ba_m=args.ba_m,
                        snn_mode=args.snn_mode,
                    )
                )

    runs_df = pd.DataFrame(rows)
    agg_df = runs_df.groupby(["topo", "algo"], as_index=False).mean(numeric_only=True)
    runs_df.to_csv(args.out, index=False)
    agg_df.to_csv(args.out_agg, index=False)

    print("=== per-run ===")
    print(runs_df.to_string(index=False))
    print("\n=== mean ===")
    print(
        agg_df[
            ["topo", "algo", "pdr_final", "delay_final", "hop_final", "loss_final", "pdr_post", "delay_post"]
        ].to_string(index=False)
    )

    if "snn" in algos:
        for base_algo in ["ospf", "ecmp", "backpressure", "ppo"]:
            if base_algo not in algos:
                continue
            print(f"\n=== delta snn-{base_algo} ===")
            for topo in topos:
                base = agg_df[(agg_df.topo == topo) & (agg_df.algo == base_algo)]
                snn = agg_df[(agg_df.topo == topo) & (agg_df.algo == "snn")]
                if base.empty or snn.empty:
                    continue
                b = base.iloc[0]
                s = snn.iloc[0]
                print(
                    topo,
                    {
                        "pdr_final": round(float(s.pdr_final - b.pdr_final), 4),
                        "delay_final": round(float(s.delay_final - b.delay_final), 3),
                        "hop_final": round(float(s.hop_final - b.hop_final), 3),
                        "loss_final": round(float(s.loss_final - b.loss_final), 1),
                        "pdr_post": round(float(s.pdr_post - b.pdr_post), 4),
                        "delay_post": round(float(s.delay_post - b.delay_post), 3),
                    },
                )

    print(f"\nSaved: {args.out}")
    print(f"Saved: {args.out_agg}")


if __name__ == "__main__":
    main()
