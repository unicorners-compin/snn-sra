import argparse
"""
Analyze spike causality in SNN (Spiking Neural Network) routing under network failures.

This module simulates network behavior under fault conditions using an SNN-based router
and identifies high-pressure spike events that correlate with network stress. It measures
the relationship between spike events and subsequent changes in route configurations,
packet delivery rates, and traffic flow patterns.

Key metrics computed:
- Event detection: High-stress spike events identified by neuron firing above quantile threshold
- Route change correlation: Ratio and delta of routing protocol activity before/after events
- Flow impact: Drop rates and flow deltas at nodes experiencing spike events
- Recovery metrics: PDR (Packet Delivery Rate) recovery slope and gain post-failure

The analysis varies topology types (e.g., Erdős-Rényi, Barabási-Albert) and random seeds,
generating per-run statistics and aggregated mean statistics across runs.

Main entry point: main() - Parses CLI arguments and orchestrates simulation runs,
outputting results to CSV files for further analysis.
"""
import copy
import random
import sys
from pathlib import Path

import numpy as np
import pandas as pd

# Path patch for local package imports.
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from scripts.topo_manager import generate_topology
from scripts_flow.main_snn import build_flow_config, build_snn_runtime_config, choose_failure_edge
from scripts_flow.snn_node import SNNQueueNode
from scripts_flow.snn_router import SNNRouter
from scripts_flow.snn_simulator import SNNSimulator
from scripts_flow.traffic import TrafficGenerator


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


def _safe_mean(values):
    if not values:
        return float("nan")
    return float(np.mean(values))


def run_case(
    topo,
    seed,
    steps=240,
    fail_step=150,
    er_p=0.06,
    ba_m=3,
    high_q=0.85,
    min_event_gap=5,
    min_base_flow=0.5,
):
    random.seed(seed)
    np.random.seed(seed)

    num_nodes = 100
    graph0 = generate_topology(kind=topo, num_nodes=num_nodes, seed=seed, er_p=er_p, ba_m=ba_m)
    flow_cfg = build_flow_config(num_nodes=num_nodes, seed=seed)
    traffic = TrafficGenerator(flow_cfg)
    failure_edge = choose_failure_edge(graph0)

    graph = copy.deepcopy(graph0)
    nodes = build_nodes(num_nodes, beta=8.0)
    cfg = build_snn_runtime_config(topo, "snn_spike_native")
    router_kwargs = dict(cfg.get("router", {}))
    router_kwargs["beta_s"] = 8.0
    sim_kwargs = dict(cfg.get("sim", {}))
    sim_kwargs["known_destinations"] = [f["dst"] for f in flow_cfg]
    router = SNNRouter(**router_kwargs)
    sim = SNNSimulator(nodes, graph, router, routing_mode="snn_spike_native", **sim_kwargs)

    inbound_hist = []
    routechg_hist = []
    pdr_hist = []
    step_pdr_hist = []
    last_event_step = {}
    events = []
    prev_generated = 0.0
    prev_delivered = 0.0

    for k in range(steps):
        if k == fail_step and failure_edge is not None and graph.has_edge(*failure_edge):
            graph.remove_edge(*failure_edge)

        metrics = sim.run_step(k, traffic.generate(k))
        pdr_hist.append(float(metrics["pdr"]))
        routechg_hist.append(int(sim.last_step_route_change_increase))
        generated = float(metrics.get("generated", 0.0))
        delivered = float(metrics.get("delivered", 0.0))
        gen_inc = generated - prev_generated
        del_inc = delivered - prev_delivered
        if gen_inc > 1e-9:
            step_pdr = del_inc / gen_inc
        else:
            step_pdr = 0.0
        step_pdr_hist.append(float(step_pdr))
        prev_generated = generated
        prev_delivered = delivered

        inbound_counts = {n: 0.0 for n in nodes}
        for (_, v), cnt in sim.last_step_edge_forward_counts.items():
            inbound_counts[v] += float(cnt)
        inbound_hist.append(inbound_counts)

        stress_vals = [float(nodes[n].S) for n in nodes]
        threshold = float(np.quantile(stress_vals, high_q))
        for nid, node in nodes.items():
            if int(getattr(node, "last_spike", 0)) <= 0:
                continue
            if float(node.S) < threshold:
                continue
            prev_t = last_event_step.get(nid, -10**9)
            if k - prev_t < min_event_gap:
                continue
            events.append((k, int(nid), float(node.S)))
            last_event_step[nid] = k

    route_change_rate_ratios = []
    route_change_rate_deltas = []
    through_node_drop_rates = []
    through_node_flow_deltas = []
    event_stresses = []
    flow_valid_events = 0

    for t, nid, stress in events:
        if t - 5 < 0 or t + 20 >= steps:
            continue

        base_in = _safe_mean([inbound_hist[i][nid] for i in range(t - 5, t)])
        fut_in = _safe_mean([inbound_hist[i][nid] for i in range(t + 5, t + 21)])
        flow_delta = base_in - fut_in

        base_rc = _safe_mean(routechg_hist[t - 5 : t])
        fut_rc = _safe_mean(routechg_hist[t + 5 : t + 21])
        rc_ratio = fut_rc / max(base_rc, 0.2)
        rc_delta = fut_rc - base_rc

        if base_in >= min_base_flow:
            drop_rate = flow_delta / max(base_in, 1e-6)
            through_node_drop_rates.append(float(drop_rate))
            flow_valid_events += 1
        through_node_flow_deltas.append(float(flow_delta))
        route_change_rate_ratios.append(float(rc_ratio))
        route_change_rate_deltas.append(float(rc_delta))
        event_stresses.append(float(stress))

    start = fail_step + 1
    end = min(steps - 1, fail_step + 20)
    if end > start:
        pdr_recovery_slope = float((step_pdr_hist[end] - step_pdr_hist[start]) / float(end - start))
        pdr_recovery_gain = float(step_pdr_hist[end] - step_pdr_hist[start])
    else:
        pdr_recovery_slope = float("nan")
        pdr_recovery_gain = float("nan")

    return {
        "topo": topo,
        "seed": seed,
        "events_total": int(len(events)),
        "events_valid": int(len(event_stresses)),
        "events_flow_valid": int(flow_valid_events),
        "event_stress_mean": _safe_mean(event_stresses),
        "route_change_rate_ratio": _safe_mean(route_change_rate_ratios),
        "route_change_rate_delta": _safe_mean(route_change_rate_deltas),
        "through_node_drop_rate": _safe_mean(through_node_drop_rates),
        "through_node_flow_delta": _safe_mean(through_node_flow_deltas),
        "pdr_recovery_slope": pdr_recovery_slope,
        "pdr_recovery_gain": pdr_recovery_gain,
    }


def main():
    parser = argparse.ArgumentParser(description="Analyze high-pressure spike causality in SNN routing.")
    parser.add_argument("--topos", default="er,ba", help="Comma-separated topology list, e.g. er,ba")
    parser.add_argument("--seeds", default="11,17,23", help="Comma-separated seeds")
    parser.add_argument("--steps", type=int, default=240)
    parser.add_argument("--fail-step", type=int, default=150)
    parser.add_argument("--er-p", type=float, default=0.06)
    parser.add_argument("--ba-m", type=int, default=3)
    parser.add_argument("--high-q", type=float, default=0.85, help="Stress quantile for high-pressure spikes")
    parser.add_argument("--min-event-gap", type=int, default=5, help="Minimum step gap between events per node")
    parser.add_argument("--min-base-flow", type=float, default=0.5, help="Min baseline in-flow for drop-rate stats")
    parser.add_argument("--out", default="run_dir/issue6_spike_causality.csv")
    parser.add_argument("--out-agg", default="run_dir/issue6_spike_causality_agg.csv")
    args = parser.parse_args()

    topos = [t.strip() for t in args.topos.split(",") if t.strip()]
    seeds = [int(s.strip()) for s in args.seeds.split(",") if s.strip()]

    rows = []
    for topo in topos:
        for seed in seeds:
            rows.append(
                run_case(
                    topo=topo,
                    seed=seed,
                    steps=args.steps,
                    fail_step=args.fail_step,
                    er_p=args.er_p,
                    ba_m=args.ba_m,
                    high_q=args.high_q,
                    min_event_gap=args.min_event_gap,
                    min_base_flow=args.min_base_flow,
                )
            )

    runs_df = pd.DataFrame(rows)
    agg_df = runs_df.groupby(["topo"], as_index=False).mean(numeric_only=True)
    runs_df.to_csv(args.out, index=False)
    agg_df.to_csv(args.out_agg, index=False)

    print("=== per-run ===")
    print(runs_df.to_string(index=False))
    print("\n=== mean ===")
    print(agg_df.to_string(index=False))
    print(f"\nSaved: {args.out}")
    print(f"Saved: {args.out_agg}")


if __name__ == "__main__":
    main()
