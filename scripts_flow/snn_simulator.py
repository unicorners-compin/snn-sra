import copy
import networkx as nx


class SNNSimulator:
    def __init__(
        self,
        node_dict,
        physical_graph,
        router,
        routing_mode="snn_local",
        hop_limit=64,
        event_base_period=6,
        event_max_period=20,
        event_delta_threshold=0.03,
        switch_hysteresis=0.25,
        native_min_switch_interval=3,
        native_min_hold_steps=6,
        native_emergency_improvement=2.0,
        route_ttl=40,
        burst_decay=0.86,
        burst_low_threshold=0.18,
        burst_high_threshold=0.45,
        burst_scale=0.22,
        burst_max_pulses=5,
        enable_lif_burst=True,
        enable_dst_beacon=True,
        dst_beacon_decay=0.88,
        dst_beacon_gain=1.0,
        dst_beacon_weight=1.0,
        known_destinations=None,
    ):
        self.nodes = node_dict
        self.G = physical_graph
        self.router = router
        self.routing_mode = routing_mode
        self.hop_limit = hop_limit

        self.inflight_packets = []
        self.routing_tables = {n: {dest: (None, float("inf")) for dest in node_dict} for n in node_dict}
        for u in self.nodes:
            self.routing_tables[u][u] = (u, 0.0)

        self.last_next_hop = {}
        self.route_changes = 0
        self.table_updates = 0

        self.total_generated = 0
        self.total_delivered = 0
        self.total_delay = 0.0
        self.total_delivered_hops = 0
        self.total_forwarded = 0
        self.delivered_delay_samples = []
        self.delivered_step_samples = []
        self.delivered_hop_samples = []
        self.delivered_shortest_hop_samples = []
        self.delivered_extra_hop_samples = []
        self.delivered_queue_delay_samples = []
        self._sp_cache = {}
        self._sp_cache_edge_count = None

        # Event-driven control-plane state.
        self.event_base_period = event_base_period
        self.event_max_period = event_max_period
        self.event_delta_threshold = event_delta_threshold
        self.switch_hysteresis = switch_hysteresis
        self.native_min_switch_interval = native_min_switch_interval
        self.native_min_hold_steps = native_min_hold_steps
        self.native_emergency_improvement = native_emergency_improvement
        self.route_ttl = route_ttl
        self.burst_decay = burst_decay
        self.burst_low_threshold = burst_low_threshold
        self.burst_high_threshold = burst_high_threshold
        self.burst_scale = burst_scale
        self.burst_max_pulses = burst_max_pulses
        self.enable_lif_burst = enable_lif_burst
        self.enable_dst_beacon = enable_dst_beacon
        self.dst_beacon_decay = dst_beacon_decay
        self.dst_beacon_gain = dst_beacon_gain
        self.dst_beacon_weight = dst_beacon_weight
        self.known_destinations = set(known_destinations or [])
        self.broadcast_count = 0
        self.next_broadcast_step = {u: 0 for u in self.nodes}
        self.last_broadcast_metric = {u: 0.0 for u in self.nodes}
        self.advertised_tables = copy.deepcopy(self.routing_tables)
        self.route_age = {u: {dest: -10**9 for dest in self.nodes} for u in self.nodes}
        self.neighbor_burst_view = {u: {} for u in self.nodes}
        self.dst_beacon = {u: {dst: 0.0 for dst in self.known_destinations} for u in self.nodes}
        self.last_switch_step = {}
        self.last_step_edge_forward_counts = {}
        self.last_step_route_change_increase = 0
        for u in self.nodes:
            self.route_age[u][u] = 0

    def trace_policy_path(self, src, dst, max_hops=None):
        """Trace a policy path using current local SNN routing decisions."""
        if max_hops is None:
            max_hops = self.hop_limit
        path = [src]
        visited = {src}
        prev = None
        curr = src
        for _ in range(max_hops):
            if curr == dst:
                return path, True
            if self.routing_mode in ("distance_vector", "snn_event_dv"):
                res = self.routing_tables.get(curr, {}).get(dst)
                nxt = res[0] if res else None
            else:
                nxt = self.router.choose_next_hop(
                    self.G,
                    self.nodes,
                    curr=curr,
                    dst=dst,
                    avoid=prev,
                    visited=visited,
                )
            if nxt is None:
                return path, False
            path.append(nxt)
            if nxt in visited:
                return path, False
            visited.add(nxt)
            prev, curr = curr, nxt
        return path, False

    def get_node_snapshot(self):
        node_ids = sorted(self.nodes.keys())
        stress = []
        spikes = []
        queue_load = []
        for nid in node_ids:
            node = self.nodes[nid]
            stress.append(float(node.S))
            spikes.append(float(getattr(node, "spike_rate_ema", 0.0)))
            q = len(node.input_queue) / max(node.buffer_size, 1)
            queue_load.append(float(q))
        return {"node_ids": node_ids, "stress": stress, "spike_rate": spikes, "queue_load": queue_load}

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

    def update_control_plane(self):
        self.router.update_link_costs(self.G, self.nodes)
        new_tables = copy.deepcopy(self.routing_tables)

        for u in self.nodes:
            active_neighbors = list(self.G.neighbors(u))

            for dest in self.routing_tables[u]:
                nxt, _ = self.routing_tables[u][dest]
                if nxt is not None and nxt != u and nxt not in active_neighbors:
                    new_tables[u][dest] = (None, float("inf"))

            for v in active_neighbors:
                edge_cost = self.router.edge_cost(self.G, self.nodes, u, v)
                for dest, (v_next, v_dist) in self.routing_tables[v].items():
                    if v_next == u:
                        continue
                    new_dist = edge_cost + v_dist
                    curr_next, curr_dist = self.routing_tables[u][dest]
                    if new_dist < curr_dist or v == curr_next:
                        if curr_next != v:
                            self.table_updates += 1
                        new_tables[u][dest] = (v, new_dist)

        self.routing_tables = new_tables

    def _should_broadcast(self, node_id, step_k):
        node = self.nodes[node_id]
        metric = float(node.S + node.spike_rate_ema + 0.5 * node.recent_loss_ratio)
        delta = abs(metric - self.last_broadcast_metric.get(node_id, 0.0))
        due = step_k >= self.next_broadcast_step.get(node_id, 0)
        triggered = delta >= self.event_delta_threshold
        strength = max(0.0, node.spike_rate_ema + node.S)
        period = int(round(self.event_base_period / max(0.08, strength)))
        period = max(1, min(self.event_max_period, period))
        return due or triggered, period, metric

    def _expire_stale_routes(self, step_k, tables):
        for u in self.nodes:
            for dest in self.nodes:
                if u == dest:
                    continue
                nxt, _ = tables[u][dest]
                if nxt is None:
                    continue
                if step_k - self.route_age[u][dest] > self.route_ttl:
                    tables[u][dest] = (None, float("inf"))

    def update_control_plane_event(self, step_k):
        self.router.update_link_costs(self.G, self.nodes, step_k=step_k)
        new_tables = copy.deepcopy(self.routing_tables)

        # Remove invalid next hops if physical links disappeared.
        for u in self.nodes:
            active_neighbors = set(self.G.neighbors(u))
            for dest, (nxt, _) in self.routing_tables[u].items():
                if nxt is not None and nxt != u and nxt not in active_neighbors:
                    new_tables[u][dest] = (None, float("inf"))

        broadcasters = []
        for u in self.nodes:
            should, period, metric = self._should_broadcast(u, step_k)
            if should:
                broadcasters.append((u, metric, period))

        for b, _, _ in broadcasters:
            adv_table = self.advertised_tables[b]
            for u in self.G.neighbors(b):
                edge_cost = self.router.edge_cost(self.G, self.nodes, u, b)
                for dest, (b_next, b_dist) in adv_table.items():
                    if dest == u:
                        continue
                    if b_next == u:
                        # Split horizon.
                        continue
                    if b_dist == float("inf"):
                        continue

                    new_dist = edge_cost + b_dist
                    curr_next, curr_dist = new_tables[u][dest]
                    same_next = curr_next == b
                    better_enough = new_dist + self.switch_hysteresis < curr_dist

                    if same_next or curr_next is None or better_enough:
                        if curr_next != b:
                            self.table_updates += 1
                        new_tables[u][dest] = (b, new_dist)
                        self.route_age[u][dest] = step_k

        self._expire_stale_routes(step_k, new_tables)
        self.routing_tables = new_tables

        for u, metric, period in broadcasters:
            self.advertised_tables[u] = copy.deepcopy(self.routing_tables[u])
            self.last_broadcast_metric[u] = metric
            self.next_broadcast_step[u] = step_k + period
            self.broadcast_count += 1

    def _decay_burst_plane(self):
        for recv in self.neighbor_burst_view:
            for src in list(self.neighbor_burst_view[recv].keys()):
                self.neighbor_burst_view[recv][src] *= self.burst_decay
                if self.neighbor_burst_view[recv][src] < 1e-4:
                    del self.neighbor_burst_view[recv][src]

    def _update_burst_plane(self):
        if not self.enable_lif_burst:
            self._decay_burst_plane()
            return
        self._decay_burst_plane()
        for src, node in self.nodes.items():
            # Burst emission is event-driven by the node's LIF firing event.
            # LIF threshold crossing + reset is implemented inside SNNQueueNode.
            pulses = 1 if int(getattr(node, "last_spike", 0)) > 0 else 0
            if pulses <= 0:
                continue
            self.broadcast_count += pulses
            for recv in self.G.neighbors(src):
                prev = self.neighbor_burst_view[recv].get(src, 0.0)
                self.neighbor_burst_view[recv][src] = prev + float(pulses)

    def _update_dst_beacons(self, observed_destinations):
        if not self.enable_dst_beacon:
            return

        active_dsts = set(self.known_destinations) | set(observed_destinations)
        if not active_dsts:
            return

        for u in self.nodes:
            slot = self.dst_beacon.setdefault(u, {})
            for dst in active_dsts:
                slot.setdefault(dst, 0.0)

        prev = {
            u: {dst: self.dst_beacon[u].get(dst, 0.0) for dst in active_dsts}
            for u in self.nodes
        }

        for u in self.nodes:
            for dst in active_dsts:
                if u == dst:
                    self.dst_beacon[u][dst] = max(self.dst_beacon_gain, prev[u][dst])
                else:
                    neigh_vals = [prev[v][dst] for v in self.G.neighbors(u)]
                    relay = max(neigh_vals) if neigh_vals else 0.0
                    self.dst_beacon[u][dst] = max(
                        prev[u][dst] * self.dst_beacon_decay,
                        relay * self.dst_beacon_decay,
                    )

    def _choose_native_next_hop(self, node_id, packet, step_k):
        neighbors = list(self.G.neighbors(node_id))
        if not neighbors:
            return None

        score_map = {}
        extra_penalty_map = {
            n: self.neighbor_burst_view.get(node_id, {}).get(n, 0.0) for n in neighbors
        }
        base_score_map = {}
        for n in neighbors:
            base_score_map[n] = self.router.score_neighbor(
                self.G,
                self.nodes,
                curr=node_id,
                dst=packet.dst,
                neighbor=n,
                visited=packet.visited,
                extra_penalty=extra_penalty_map.get(n, 0.0),
            )
            score_map[n] = base_score_map[n]

        if self.enable_dst_beacon:
            self_val = float(self.dst_beacon.get(node_id, {}).get(packet.dst, 0.0))
            beacon_delta = {}
            max_delta = 0.0
            for n in neighbors:
                neigh_val = float(self.dst_beacon.get(n, {}).get(packet.dst, 0.0))
                delta = max(0.0, neigh_val - self_val)
                beacon_delta[n] = delta
                if delta > max_delta:
                    max_delta = delta

            if max_delta > 1e-9:
                base_vals = list(base_score_map.values())
                base_span = max(base_vals) - min(base_vals)
                score_scale = max(1.0, 0.5 * base_span)
                for n in neighbors:
                    ratio = beacon_delta[n] / max_delta
                    score_map[n] -= self.dst_beacon_weight * score_scale * ratio

        best_hop = min(score_map, key=score_map.get)
        best_score = score_map[best_hop]
        key = (node_id, packet.dst)
        prev_hop = self.last_next_hop.get(key)
        if prev_hop is not None and prev_hop in score_map and prev_hop != best_hop:
            prev_score = score_map[prev_hop]
            improvement = prev_score - best_score
            last_sw = self.last_switch_step.get(key, -10**9)
            in_hold = step_k - last_sw < self.native_min_hold_steps
            emergency = improvement >= self.native_emergency_improvement
            if in_hold and not emergency:
                return prev_hop
            if improvement < self.switch_hysteresis:
                return prev_hop
            if step_k - last_sw < self.native_min_switch_interval:
                return prev_hop
            self.last_switch_step[key] = step_k
        elif prev_hop is None or prev_hop != best_hop:
            # First decision for this (node,dst) pair.
            self.last_switch_step.setdefault(key, step_k)
        return best_hop

    def run_step(self, step_k, new_packets):
        self.last_step_edge_forward_counts = {}
        self.last_step_route_change_increase = 0

        if self.routing_mode == "distance_vector":
            self.update_control_plane()
        elif self.routing_mode == "snn_event_dv":
            self.update_control_plane_event(step_k)
        elif self.routing_mode == "snn_spike_native":
            self.router.update_link_costs(self.G, self.nodes, step_k=step_k)
            self._update_burst_plane()
            observed_dsts = [pkt.dst for pkt in new_packets]
            self._update_dst_beacons(observed_dsts)
        else:
            self.router.update_link_costs(self.G, self.nodes, step_k=step_k)

        for pkt in new_packets:
            if not hasattr(pkt, "hops"):
                pkt.hops = 0
            if not hasattr(pkt, "visited"):
                pkt.visited = set()
            if not hasattr(pkt, "prev_node"):
                pkt.prev_node = None
            self.total_generated += 1
            self.nodes[pkt.src].receive_packet(pkt)

        for node_id, node in self.nodes.items():
            pkts = node.process_and_forward(step_k)
            for p in pkts:
                if p.dst == node_id:
                    self._on_packet_delivered(p, step_k)
                    continue

                if self.routing_mode in ("distance_vector", "snn_event_dv"):
                    res = self.routing_tables[node_id].get(p.dst)
                    next_hop = res[0] if res else None
                elif self.routing_mode == "snn_spike_native":
                    if p.hops >= self.hop_limit:
                        node.notify_link_failure_drop()
                        continue
                    next_hop = self._choose_native_next_hop(node_id, p, step_k)
                else:
                    if p.hops >= self.hop_limit:
                        node.notify_link_failure_drop()
                        continue
                    next_hop = self.router.choose_next_hop(
                        self.G,
                        self.nodes,
                        curr=node_id,
                        dst=p.dst,
                        avoid=p.prev_node,
                        visited=p.visited,
                    )
                if next_hop is not None:
                    key = (node_id, p.dst)
                    prev_nh = self.last_next_hop.get(key)
                    if prev_nh is not None and prev_nh != next_hop:
                        self.route_changes += 1
                        self.last_step_route_change_increase += 1
                    self.last_next_hop[key] = next_hop
                    p.hops += 1
                    p.visited.add(node_id)
                    p.prev_node = node_id
                    self.total_forwarded += 1
                    edge_key = (node_id, next_hop)
                    prev_edge = self.last_step_edge_forward_counts.get(edge_key, 0)
                    self.last_step_edge_forward_counts[edge_key] = prev_edge + 1
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

        v_s = 0.5 * sum(n.S**2 for n in self.nodes.values())
        total_loss = sum(n.total_dropped for n in self.nodes.values())
        pdr = self.total_delivered / self.total_generated if self.total_generated > 0 else 0.0
        avg_delay = self.total_delay / self.total_delivered if self.total_delivered > 0 else 0.0
        avg_hop = self.total_delivered_hops / self.total_delivered if self.total_delivered > 0 else 0.0

        return {
            "step": step_k,
            "v_s": v_s,
            "loss": total_loss,
            "pdr": pdr,
            "avg_delay": avg_delay,
            "avg_hop": avg_hop,
            "route_changes": self.route_changes,
            "table_updates": self.table_updates,
            "broadcasts": self.broadcast_count,
            "generated": self.total_generated,
            "delivered": self.total_delivered,
        }
