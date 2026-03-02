import argparse
import copy
import csv
import random
import time
from dataclasses import dataclass
from pathlib import Path
import sys

import networkx as nx
import numpy as np
import redis

root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from scripts_flow.snn_node import SNNQueueNode
from scripts_flow.snn_router import SNNRouter
from scripts_flow.snn_simulator import SNNSimulator
from scripts_flow.traffic import TrafficGenerator


@dataclass
class StepMetrics:
    step: int
    algo: str
    pdr: float
    avg_delay: float
    avg_hop: float
    loss: float
    route_changes: float
    table_updates: float
    broadcasts: float


class OSPFSyncLite:
    """Minimal OSPF-sync baseline without external pandas dependency."""

    def __init__(self, node_dict, physical_graph, hop_limit=64, sync_period=12, spf_delay=4):
        self.nodes = node_dict
        self.G = physical_graph
        self.hop_limit = hop_limit
        self.sync_period = max(1, int(sync_period))
        self.spf_delay = max(0, int(spf_delay))

        self.inflight_packets = []
        self.total_generated = 0
        self.total_delivered = 0
        self.total_delay = 0.0
        self.total_delivered_hops = 0

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

    def sync_physical_graph(self):
        self.G = self.G

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
            else:
                if not self.effective_graph.has_edge(u, v):
                    self.effective_graph.add_edge(u, v, cost=1.0)
                    changed = True
        self.pending_changes = keep
        return changed

    def _pick_next_hop(self, node_id, dst):
        return self.routing_table.get(node_id, {}).get(dst)

    def _on_delivered(self, pkt, step_k):
        delay = int(step_k - pkt.creation_step)
        hops = int(getattr(pkt, "hops", 0))
        self.total_delivered += 1
        self.total_delay += float(delay)
        self.total_delivered_hops += hops

    def run_step(self, step_k, new_packets):
        if step_k % self.sync_period == 0:
            self._schedule_topology_changes(step_k)
        changed = self._apply_due_changes(step_k)
        if changed and step_k % self.sync_period == 0:
            self._recompute_routes()
        elif step_k % self.sync_period == 0:
            self.broadcast_count += self.effective_graph.number_of_nodes()

        for pkt in new_packets:
            if not hasattr(pkt, "hops"):
                pkt.hops = 0
            self.total_generated += 1
            self.nodes[pkt.src].receive_packet(pkt)

        for node_id, node in self.nodes.items():
            pkts = node.process_and_forward(step_k)
            for p in pkts:
                if p.dst == node_id:
                    self._on_delivered(p, step_k)
                    continue
                if p.hops >= self.hop_limit:
                    node.notify_link_failure_drop()
                    continue
                nxt = self._pick_next_hop(node_id, p.dst)
                if nxt is not None and self.effective_graph.has_edge(node_id, nxt):
                    p.hops += 1
                    self.inflight_packets.append((p, nxt, step_k + 1, node_id))
                else:
                    node.notify_link_failure_drop()

        remain = []
        for p, nxt, arr_t, last_node in self.inflight_packets:
            if step_k >= arr_t:
                if self.G.has_edge(last_node, nxt):
                    self.nodes[nxt].receive_packet(p)
                else:
                    self.nodes[last_node].notify_link_failure_drop()
            else:
                remain.append((p, nxt, arr_t, last_node))
        self.inflight_packets = remain

        total_loss = sum(n.total_dropped for n in self.nodes.values())
        pdr = self.total_delivered / self.total_generated if self.total_generated else 0.0
        avg_delay = self.total_delay / self.total_delivered if self.total_delivered else 0.0
        avg_hop = self.total_delivered_hops / self.total_delivered if self.total_delivered else 0.0
        return {
            "loss": float(total_loss),
            "pdr": float(pdr),
            "avg_delay": float(avg_delay),
            "avg_hop": float(avg_hop),
            "table_updates": float(self.table_updates),
            "broadcasts": float(self.broadcast_count),
        }


def build_flow_config(num_nodes=100, seed=7):
    preset = [
        {"src": 0, "dst": max(1, num_nodes - 1), "base_rate": 9, "burst_start": 110, "burst_end": 170, "burst_rate": 30},
        {"src": min(9, num_nodes - 2), "dst": max(1, num_nodes - 10), "base_rate": 9, "burst_start": 110, "burst_end": 170, "burst_rate": 30},
        {"src": min(4, num_nodes - 2), "dst": max(1, num_nodes - 5), "base_rate": 10, "burst_start": 110, "burst_end": 170, "burst_rate": 34},
        {"src": min(40, num_nodes - 2), "dst": min(59, num_nodes - 1), "base_rate": 8, "burst_start": 80, "burst_end": 200, "burst_rate": 28},
        {"src": min(50, num_nodes - 2), "dst": min(49, num_nodes - 1), "base_rate": 8, "burst_start": 80, "burst_end": 200, "burst_rate": 28},
    ]
    cfg = [f for f in preset if f["src"] < num_nodes and f["dst"] < num_nodes and f["src"] != f["dst"]]
    if len(cfg) >= 4:
        return cfg

    rng = random.Random(seed + num_nodes * 19)
    nodes = list(range(num_nodes))
    pairs = set()
    target = min(7, max(3, num_nodes // 30))
    while len(pairs) < target:
        s, d = rng.sample(nodes, 2)
        pairs.add((s, d))

    cfg = []
    for i, (s, d) in enumerate(sorted(pairs)):
        cfg.append(
            {
                "src": s,
                "dst": d,
                "base_rate": 6 + (i % 5),
                "burst_start": 80 + (i % 4) * 10,
                "burst_end": 180 + (i % 4) * 10,
                "burst_rate": 18 + (i % 5) * 4,
            }
        )
    return cfg


def build_snn_runtime_config():
    router_kwargs = {
        "base_cost": 1.0,
        "beta_s": 8.0,
        "beta_h": 0.55,
        "beta_f": 0.8,
        "beta_burst": 0.9,
        "trace_decay": 0.92,
        "eta_stdp": 0.12,
        "eta_loss": 0.65,
        "stdp_window": 10,
        "stdp_tau": 3.0,
        "syn_decay": 0.996,
        "syn_min": 0.0,
        "syn_max": 6.0,
        "score_norm_mode": "none",
        "softmin_temperature": 0.0,
    }
    sim_kwargs = {
        "hop_limit": 64,
        "event_base_period": 6,
        "event_max_period": 20,
        "event_delta_threshold": 0.03,
        "switch_hysteresis": 0.25,
        "native_min_switch_interval": 3,
        "native_min_hold_steps": 6,
        "native_emergency_improvement": 2.0,
        "route_ttl": 40,
        "burst_decay": 0.86,
        "burst_low_threshold": 0.18,
        "burst_high_threshold": 0.45,
        "burst_scale": 0.22,
        "burst_max_pulses": 5,
        "enable_dst_beacon": True,
        "dst_beacon_decay": 0.88,
        "dst_beacon_gain": 1.0,
        "dst_beacon_weight": 1.1,
    }
    return {"router": router_kwargs, "sim": sim_kwargs}


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


def fetch_edges_from_redis(client, key, node_count):
    edges = set()
    for i in range(node_count):
        row = client.hget(key, str(i))
        if not row:
            continue
        # Avoid json import in loop.
        import json

        arr = json.loads(row)
        for item in arr:
            if int(item.get("status", 0)) != 1:
                continue
            j = int(item["target"])
            if i == j:
                continue
            u, v = (i, j) if i < j else (j, i)
            edges.add((u, v))
    return sorted(edges)


def apply_edges(graph, node_count, edges):
    graph.clear()
    graph.add_nodes_from(range(node_count))
    graph.add_edges_from(edges, cost=1.0)


def write_step_csv(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "step",
                "algo",
                "pdr",
                "avg_delay",
                "avg_hop",
                "loss",
                "route_changes",
                "table_updates",
                "broadcasts",
            ],
        )
        writer.writeheader()
        for r in rows:
            writer.writerow(r.__dict__)


def write_summary_csv(path, rows):
    by_algo = {}
    for r in rows:
        by_algo.setdefault(r.algo, []).append(r)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "algo",
                "pdr_final",
                "avg_delay_final",
                "avg_hop_final",
                "loss_final",
                "route_changes_total",
                "table_updates_total",
                "broadcasts_total",
            ],
        )
        writer.writeheader()
        for algo, arr in sorted(by_algo.items()):
            last = arr[-1]
            writer.writerow(
                {
                    "algo": algo,
                    "pdr_final": f"{last.pdr:.6f}",
                    "avg_delay_final": f"{last.avg_delay:.6f}",
                    "avg_hop_final": f"{last.avg_hop:.6f}",
                    "loss_final": f"{last.loss:.0f}",
                    "route_changes_total": f"{sum(x.route_changes for x in arr):.0f}",
                    "table_updates_total": f"{sum(x.table_updates for x in arr):.0f}",
                    "broadcasts_total": f"{sum(x.broadcasts for x in arr):.0f}",
                }
            )


def main():
    parser = argparse.ArgumentParser(description="Live routing compare on current new_huan topology matrix.")
    parser.add_argument("--redis-host", default="172.17.0.1")
    parser.add_argument("--redis-port", type=int, default=6379)
    parser.add_argument("--redis-db", type=int, default=0)
    parser.add_argument("--matrix-key", default="net:topology:matrix")
    parser.add_argument("--nodes", type=int, default=300)
    parser.add_argument("--steps", type=int, default=120)
    parser.add_argument("--dt", type=float, default=1.0)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--snn-mode", default="snn_event_dv")
    parser.add_argument("--sync-period", type=int, default=12)
    parser.add_argument("--spf-delay", type=int, default=4)
    parser.add_argument("--out", default="run_dir/new_huan_live_steps.csv")
    parser.add_argument("--out-agg", default="run_dir/new_huan_live_summary.csv")
    args = parser.parse_args()

    random.seed(args.seed)
    np.random.seed(args.seed)

    r = redis.Redis(host=args.redis_host, port=args.redis_port, db=args.redis_db, decode_responses=True)
    if not r.ping():
        raise RuntimeError("redis ping failed")
    if r.hlen(args.matrix_key) < args.nodes:
        raise RuntimeError(f"matrix key {args.matrix_key} has fewer than {args.nodes} rows")

    flow_cfg = build_flow_config(num_nodes=args.nodes, seed=args.seed)
    traffic = TrafficGenerator(flow_cfg)

    graph_snn = nx.Graph()
    graph_ospf = nx.Graph()
    apply_edges(graph_snn, args.nodes, [])
    apply_edges(graph_ospf, args.nodes, [])

    cfg = build_snn_runtime_config()
    router_kwargs = dict(cfg.get("router", {}))
    router_kwargs["beta_s"] = 8.0
    router = SNNRouter(**router_kwargs)
    sim_kwargs = dict(cfg.get("sim", {}))
    sim_kwargs["known_destinations"] = [f["dst"] for f in flow_cfg]

    snn = SNNSimulator(build_nodes(args.nodes, 8.0), graph_snn, router, routing_mode=args.snn_mode, **sim_kwargs)
    ospf = OSPFSyncLite(
        build_nodes(args.nodes, 0.0),
        graph_ospf,
        hop_limit=64,
        sync_period=args.sync_period,
        spf_delay=args.spf_delay,
    )

    rows = []
    for step in range(args.steps):
        edges = fetch_edges_from_redis(r, args.matrix_key, args.nodes)
        apply_edges(graph_snn, args.nodes, edges)
        apply_edges(graph_ospf, args.nodes, edges)

        packets = traffic.generate(step)
        snn_m = snn.run_step(step, copy.deepcopy(packets))
        ospf_m = ospf.run_step(step, copy.deepcopy(packets))

        rows.append(
            StepMetrics(
                step=step,
                algo="snn",
                pdr=float(snn_m.get("pdr", 0.0)),
                avg_delay=float(snn_m.get("avg_delay", 0.0)),
                avg_hop=float(snn_m.get("avg_hop", 0.0)),
                loss=float(snn_m.get("loss", 0.0)),
                route_changes=float(snn_m.get("route_changes", 0.0)),
                table_updates=float(snn_m.get("table_updates", 0.0)),
                broadcasts=float(snn_m.get("broadcasts", 0.0)),
            )
        )
        rows.append(
            StepMetrics(
                step=step,
                algo="ospf_sync",
                pdr=float(ospf_m.get("pdr", 0.0)),
                avg_delay=float(ospf_m.get("avg_delay", 0.0)),
                avg_hop=float(ospf_m.get("avg_hop", 0.0)),
                loss=float(ospf_m.get("loss", 0.0)),
                route_changes=0.0,
                table_updates=float(ospf_m.get("table_updates", 0.0)),
                broadcasts=float(ospf_m.get("broadcasts", 0.0)),
            )
        )
        if args.dt > 0:
            time.sleep(args.dt)

    out = Path(args.out)
    out_agg = Path(args.out_agg)
    write_step_csv(out, rows)
    write_summary_csv(out_agg, rows)
    print(f"steps -> {out}")
    print(f"summary -> {out_agg}")


if __name__ == "__main__":
    main()
