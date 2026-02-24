import networkx as nx
import math
import random


class SNNRouter:
    """Edge plasticity and stress-aware edge cost provider."""

    def __init__(
        self,
        base_cost=1.0,
        beta_s=10.0,
        beta_h=0.6,
        beta_f=0.8,
        beta_burst=0.9,
        trace_decay=0.92,
        eta_stdp=0.12,
        eta_loss=0.60,
        stdp_window=10,
        stdp_tau=3.0,
        syn_decay=0.995,
        syn_min=0.0,
        syn_max=8.0,
        score_norm_mode="none",
        softmin_temperature=0.0,
        softmin_eps=1e-9,
    ):
        self.base_cost = base_cost
        self.beta_s = beta_s
        self.beta_h = beta_h
        self.beta_f = beta_f
        self.beta_burst = beta_burst
        self.trace_decay = trace_decay
        self.eta_stdp = eta_stdp
        self.eta_loss = eta_loss
        self.stdp_window = stdp_window
        self.stdp_tau = stdp_tau
        self.syn_decay = syn_decay
        self.syn_min = syn_min
        self.syn_max = syn_max
        self.score_norm_mode = score_norm_mode
        self.softmin_temperature = softmin_temperature
        self.softmin_eps = softmin_eps

        self.node_trace = {}
        self.syn_penalty = {}
        self.last_spike_step = {}
        self.hop_hint_cache = {}
        self.hop_hint_edge_count = None

    @staticmethod
    def _edge_key(u, v):
        return (u, v) if u < v else (v, u)

    def update_link_costs(self, graph, nodes, step_k=None):
        if step_k is not None:
            for n, node in nodes.items():
                if getattr(node, "last_spike", 0):
                    self.last_spike_step[n] = int(step_k)

        for n, node in nodes.items():
            prev = self.node_trace.get(n, 0.0)
            self.node_trace[n] = self.trace_decay * prev + float(getattr(node, "last_spike", 0))

        for u, v in graph.edges():
            key = self._edge_key(u, v)
            prev_penalty = self.syn_penalty.get(key, 0.0) * self.syn_decay
            pre = self.node_trace.get(u, 0.0)
            post = self.node_trace.get(v, 0.0)
            loss_term = 0.5 * (nodes[u].recent_loss_ratio + nodes[v].recent_loss_ratio)

            temporal = 0.0
            if step_k is not None:
                tu = self.last_spike_step.get(u)
                tv = self.last_spike_step.get(v)
                if tu is not None and tv is not None:
                    dt = abs(tu - tv)
                    if dt <= self.stdp_window:
                        temporal = 1.0 / (1.0 + dt / max(self.stdp_tau, 1e-6))

            delta = self.eta_stdp * (0.7 * pre * post + 0.3 * temporal) + self.eta_loss * loss_term
            penalty = min(self.syn_max, max(self.syn_min, prev_penalty + delta))
            self.syn_penalty[key] = penalty

            neural_cost = self.beta_s * (nodes[u].S + nodes[v].S)
            graph[u][v]["snn_cost"] = self.base_cost + neural_cost + penalty

    def edge_cost(self, graph, nodes, u, v):
        if graph.has_edge(u, v):
            return graph[u][v].get("snn_cost", self.base_cost + self.beta_s * (nodes[u].S + nodes[v].S))
        return float("inf")

    def _hop_hint(self, graph, src, dst):
        edge_count = graph.number_of_edges()
        if self.hop_hint_edge_count != edge_count:
            self.hop_hint_cache.clear()
            self.hop_hint_edge_count = edge_count

        key = (src, dst)
        if key in self.hop_hint_cache:
            return self.hop_hint_cache[key]

        try:
            hint = nx.shortest_path_length(graph, source=src, target=dst)
        except nx.NetworkXNoPath:
            hint = 10**6
        self.hop_hint_cache[key] = float(hint)
        return float(hint)

    def score_neighbor(self, graph, nodes, curr, dst, neighbor, visited=None, extra_penalty=0.0):
        loop_penalty = 5.0 if visited is not None and neighbor in visited else 0.0
        link_cost = self.edge_cost(graph, nodes, curr, neighbor)
        spike_term = nodes[neighbor].spike_rate_ema
        h_term = self._hop_hint(graph, neighbor, dst)
        if self.score_norm_mode == "bounded":
            link_scale = max(1.0, self.base_cost + 2.0 * self.beta_s + self.syn_max)
            link_cost = link_cost / link_scale
            h_term = h_term / (h_term + 1.0)
            spike_term = min(1.0, max(0.0, spike_term))
            extra_penalty = min(1.0, max(0.0, float(extra_penalty)))
            loop_penalty = 1.0 if loop_penalty > 0 else 0.0
        return (
            link_cost
            + self.beta_h * h_term
            + self.beta_f * spike_term
            + self.beta_burst * float(extra_penalty)
            + loop_penalty
        )

    def choose_next_hop(
        self,
        graph,
        nodes,
        curr,
        dst,
        avoid=None,
        visited=None,
        extra_penalty_map=None,
        return_score=False,
    ):
        """Pure SNN local routing: choose among 1-hop neighbors only."""
        neighbors = list(graph.neighbors(curr))
        if not neighbors:
            return (None, float("inf")) if return_score else None

        best_hop = None
        best_score = float("inf")
        scored = []

        for v in neighbors:
            if avoid is not None and v == avoid:
                continue
            extra = 0.0
            if extra_penalty_map is not None:
                extra = float(extra_penalty_map.get(v, 0.0))
            score = self.score_neighbor(
                graph,
                nodes,
                curr=curr,
                dst=dst,
                neighbor=v,
                visited=visited,
                extra_penalty=extra,
            )
            scored.append((v, score))
            if score < best_score:
                best_score = score
                best_hop = v

        if best_hop is None:
            return (None, float("inf")) if return_score else None

        if self.softmin_temperature > 0.0 and len(scored) > 1:
            min_score = min(s for _, s in scored)
            temp = max(self.softmin_temperature, self.softmin_eps)
            weights = []
            total_w = 0.0
            for v, s in scored:
                w = math.exp(-(s - min_score) / temp)
                weights.append((v, s, w))
                total_w += w
            if total_w > 0:
                r = random.random() * total_w
                acc = 0.0
                for v, s, w in weights:
                    acc += w
                    if r <= acc:
                        return (v, s) if return_score else v

        return (best_hop, best_score) if return_score else best_hop
