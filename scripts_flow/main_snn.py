import os
import random
import sys
import json
from pathlib import Path
import copy

import networkx as nx
import numpy as np
import pandas as pd

# Path patch for local package imports.
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from scripts.topo_manager import build_layout_positions, generate_topology
from scripts_flow.snn_node import SNNQueueNode
from scripts_flow.snn_router import SNNRouter
from scripts_flow.snn_simulator import SNNSimulator
from scripts_flow.traffic import TrafficGenerator


def build_flow_config(num_nodes=100, seed=7):
    # Preset probes for 100-node experiments.
    preset = [
        {"src": 0, "dst": 99, "base_rate": 9, "burst_start": 110, "burst_end": 170, "burst_rate": 30},
        {"src": 9, "dst": 90, "base_rate": 9, "burst_start": 110, "burst_end": 170, "burst_rate": 30},
        {"src": 4, "dst": 95, "base_rate": 10, "burst_start": 110, "burst_end": 170, "burst_rate": 34},
        {"src": 40, "dst": 59, "base_rate": 8, "burst_start": 80, "burst_end": 200, "burst_rate": 28},
        {"src": 50, "dst": 49, "base_rate": 8, "burst_start": 80, "burst_end": 200, "burst_rate": 28},
        {"src": 1, "dst": 98, "base_rate": 7, "burst_start": 130, "burst_end": 170, "burst_rate": 22},
        {"src": 10, "dst": 89, "base_rate": 7, "burst_start": 130, "burst_end": 170, "burst_rate": 22},
    ]
    cfg = [f for f in preset if f["src"] < num_nodes and f["dst"] < num_nodes]
    if len(cfg) >= 5:
        return cfg

    rng = random.Random(seed + num_nodes * 19)
    nodes = list(range(num_nodes))
    pairs = set()
    while len(pairs) < min(7, max(3, num_nodes // 12)):
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


def _round_list(values, ndigits=6):
    return [round(float(v), ndigits) for v in values]


def _flow_key(src, dst):
    return f"{src}->{dst}"


def build_topology_payload(graph, positions, kind):
    nodes = [
        {"id": int(i), "x": float(positions[i][0]), "y": float(positions[i][1])}
        for i in sorted(graph.nodes())
    ]
    edges = [[int(u), int(v)] for u, v in graph.edges()]
    return {"kind": kind, "nodes": nodes, "edges": edges}


def choose_failure_edge(graph):
    if graph.number_of_edges() == 0:
        return None
    edge_bc = nx.edge_betweenness_centrality(graph)
    edge = max(edge_bc.items(), key=lambda kv: kv[1])[0]
    return (int(edge[0]), int(edge[1]))


def build_snn_runtime_config(topo_kind, routing_mode, formula_mode="v1"):
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

    if (topo_kind or "").lower() == "er":
        # ER random graph needs stronger anti-oscillation and less burst aggressiveness.
        router_kwargs.update(
            {
                "beta_h": 0.95,
                "beta_f": 0.55,
                "beta_burst": 0.35,
                "eta_loss": 0.50,
                "syn_decay": 0.997,
            }
        )
        sim_kwargs.update(
            {
                "event_base_period": 8,
                "event_max_period": 24,
                "event_delta_threshold": 0.05,
                "switch_hysteresis": 0.45,
                "native_min_switch_interval": 6,
                "native_min_hold_steps": 8,
                "native_emergency_improvement": 2.6,
                "route_ttl": 55,
                "burst_decay": 0.90,
                "burst_low_threshold": 0.24,
                "burst_high_threshold": 0.58,
                "burst_scale": 0.30,
                "burst_max_pulses": 3,
                "dst_beacon_decay": 0.91,
                "dst_beacon_weight": 1.45,
            }
        )

    if routing_mode == "snn_event_dv":
        # Disable burst related influence for DV-based control mode.
        router_kwargs["beta_burst"] = 0.0

    if formula_mode == "v2":
        router_kwargs.update(
            {
                "score_norm_mode": "bounded",
                "softmin_temperature": 0.08,
            }
        )

    return {"router": router_kwargs, "sim": sim_kwargs}


def run_experiment(
    tag,
    beta_s,
    base_graph,
    flow_cfg,
    failure_edge=None,
    seed=7,
    steps=300,
    fail_step=180,
    routing_mode="snn_local",
    capture_viz=True,
    probe_flows=None,
    runtime_cfg=None,
    formula_mode="v1",
):
    random.seed(seed)
    np.random.seed(seed)

    graph = copy.deepcopy(base_graph)
    num_nodes = graph.number_of_nodes()
    nodes = {
        i: SNNQueueNode(
            node_id=i,
            service_rate=22,
            buffer_size=180,
            alpha=0.22,
            beta_I=beta_s,
            T_d=1,
            tau_m=4.0,
            v_th=1.0,
            stress_mode="v2_sigmoid" if formula_mode == "v2" else "v1",
            stress_smooth_gain=7.0,
            stress_smooth_center=0.45,
        )
        for i in range(num_nodes)
    }
    cfg = runtime_cfg or build_snn_runtime_config("ba", routing_mode)
    router_kwargs = dict(cfg.get("router", {}))
    router_kwargs["beta_s"] = beta_s
    router = SNNRouter(**router_kwargs)
    sim_kwargs = dict(cfg.get("sim", {}))
    sim_kwargs["known_destinations"] = [f["dst"] for f in flow_cfg]
    sim = SNNSimulator(nodes, graph, router, routing_mode=routing_mode, **sim_kwargs)
    tg = TrafficGenerator(flow_cfg)
    if probe_flows is None:
        probe_flows = [(f["src"], f["dst"]) for f in flow_cfg]

    rows = []
    snapshots = []
    failure_events = []
    prev_paths = {}
    for k in range(steps):
        if k == fail_step and failure_edge is not None and graph.has_edge(*failure_edge):
            graph.remove_edge(*failure_edge)
            failure_events.append({"step": int(k), "edge": [int(failure_edge[0]), int(failure_edge[1])]})
            print(f"[{tag}] step={k:03d} inject link failure {failure_edge}")

        metrics = sim.run_step(k, tg.generate(k))
        metrics["tag"] = tag
        rows.append(metrics)

        if capture_viz:
            node_snap = sim.get_node_snapshot()
            flow_paths = {}
            changed = []
            for src, dst in probe_flows:
                path, ok = sim.trace_policy_path(src, dst, max_hops=64)
                key = _flow_key(src, dst)
                flow_paths[key] = {"path": [int(p) for p in path], "ok": bool(ok)}
                if prev_paths.get(key) != flow_paths[key]["path"]:
                    changed.append(key)
                prev_paths[key] = flow_paths[key]["path"]

            snapshots.append(
                {
                    "step": int(k),
                    "v_s": round(float(metrics["v_s"]), 8),
                    "loss": int(metrics["loss"]),
                    "pdr": round(float(metrics["pdr"]), 8),
                    "avg_delay": round(float(metrics["avg_delay"]), 8),
                    "avg_hop": round(float(metrics["avg_hop"]), 8),
                    "route_changes": int(metrics["route_changes"]),
                    "table_updates": int(metrics["table_updates"]),
                    "broadcasts": int(metrics.get("broadcasts", 0)),
                    "stress": _round_list(node_snap["stress"], 6),
                    "spike_rate": _round_list(node_snap["spike_rate"], 6),
                    "queue_load": _round_list(node_snap["queue_load"], 6),
                    "flow_paths": flow_paths,
                    "changed_flows": changed,
                }
            )

        if k % 25 == 0:
            print(
                f"[{tag}] step={k:03d} V={metrics['v_s']:.4f} "
                f"PDR={metrics['pdr']:.3f} delay={metrics['avg_delay']:.2f} "
                f"loss={metrics['loss']} reroute={metrics['route_changes']} "
                f"broadcast={metrics.get('broadcasts', 0)}"
            )

    return pd.DataFrame(rows), {
        "tag": tag,
        "beta_s": float(beta_s),
        "routing_mode": routing_mode,
        "probe_flows": [{"id": _flow_key(s, d), "src": int(s), "dst": int(d)} for s, d in probe_flows],
        "flow_config": flow_cfg,
        "failure_events": failure_events,
        "snapshots": snapshots,
    }


def summarize(df):
    final = df.iloc[-1]
    return {
        "tag": final["tag"],
        "final_v_s": float(final["v_s"]),
        "final_loss": int(final["loss"]),
        "final_pdr": float(final["pdr"]),
        "final_avg_delay": float(final["avg_delay"]),
        "final_avg_hop": float(final["avg_hop"]),
        "route_changes": int(final["route_changes"]),
        "table_updates": int(final["table_updates"]),
        "broadcasts": int(final.get("broadcasts", 0)),
        "generated": int(final["generated"]),
        "delivered": int(final["delivered"]),
    }


def main():
    print(">>> [SNN] 启动全网神经路由仿真 (A/B: beta_s=0 vs beta_s>0)")
    run_dir = os.getenv("EXPERIMENT_RUN_DIR", "run_dir")
    os.makedirs(run_dir, exist_ok=True)

    topo_kind = os.getenv("SNN_TOPOLOGY", "ba").lower()
    num_nodes = int(os.getenv("SNN_NUM_NODES", "100"))
    topo_seed = int(os.getenv("SNN_TOPO_SEED", "17"))
    er_p = float(os.getenv("SNN_ER_P", "0.06"))
    ba_m = int(os.getenv("SNN_BA_M", "3"))
    layout_kind = os.getenv("SNN_LAYOUT", "spring")
    routing_mode = os.getenv("SNN_ROUTING_MODE", "snn_event_dv")
    formula_mode = os.getenv("SNN_FORMULA_MODE", "v1").lower()
    steps = int(os.getenv("SNN_STEPS", "300"))
    fail_step = int(os.getenv("SNN_FAIL_STEP", "180"))

    base_graph = generate_topology(
        kind=topo_kind,
        num_nodes=num_nodes,
        seed=topo_seed,
        grid_dim=int(num_nodes ** 0.5),
        er_p=er_p,
        ba_m=ba_m,
    )
    layout_positions = build_layout_positions(base_graph, layout=layout_kind, seed=topo_seed)
    failure_edge = choose_failure_edge(base_graph)
    print(
        f">>> [SNN] topology={topo_kind} nodes={base_graph.number_of_nodes()} "
        f"edges={base_graph.number_of_edges()} failure_edge={failure_edge} mode={routing_mode} formula={formula_mode}"
    )
    runtime_cfg = build_snn_runtime_config(topo_kind, routing_mode, formula_mode=formula_mode)

    flow_cfg = build_flow_config(num_nodes=num_nodes, seed=topo_seed)
    probe_flows = [(f["src"], f["dst"]) for f in flow_cfg]
    baseline_df, baseline_viz = run_experiment(
        tag="baseline_beta0",
        beta_s=0.0,
        base_graph=base_graph,
        flow_cfg=flow_cfg,
        failure_edge=failure_edge,
        routing_mode=routing_mode,
        capture_viz=True,
        probe_flows=probe_flows,
        runtime_cfg=runtime_cfg,
        formula_mode=formula_mode,
        steps=steps,
        fail_step=fail_step,
    )
    snn_df, snn_viz = run_experiment(
        tag="snn_beta8",
        beta_s=8.0,
        base_graph=base_graph,
        flow_cfg=flow_cfg,
        failure_edge=failure_edge,
        routing_mode=routing_mode,
        capture_viz=True,
        probe_flows=probe_flows,
        runtime_cfg=runtime_cfg,
        formula_mode=formula_mode,
        steps=steps,
        fail_step=fail_step,
    )
    all_df = pd.concat([baseline_df, snn_df], ignore_index=True)

    summary_df = pd.DataFrame([summarize(baseline_df), summarize(snn_df)])
    all_path = Path(run_dir) / "snn_metrics.csv"
    summary_path = Path(run_dir) / "snn_ablation_summary.csv"
    viz_path = Path(run_dir) / "snn_route_viz.json"
    all_df.to_csv(all_path, index=False)
    summary_df.to_csv(summary_path, index=False)
    viz_payload = {
        "meta": {
            "steps": int(len(baseline_df)),
            "generated_at": "local_run",
            "description": "Pure SNN local-routing visualization payload",
            "topology_kind": topo_kind,
            "num_nodes": int(base_graph.number_of_nodes()),
            "num_edges": int(base_graph.number_of_edges()),
            "routing_mode": routing_mode,
            "formula_mode": formula_mode,
        },
        "topology": build_topology_payload(base_graph, layout_positions, topo_kind),
        "scenarios": {
            baseline_viz["tag"]: baseline_viz,
            snn_viz["tag"]: snn_viz,
        },
    }
    with open(viz_path, "w", encoding="utf-8") as f:
        json.dump(viz_payload, f, ensure_ascii=False)

    print(">>> [SNN] 指标文件已生成:")
    print(f"    - {all_path}")
    print(f"    - {summary_path}")
    print(f"    - {viz_path}")
    print(summary_df.to_string(index=False))


if __name__ == "__main__":
    main()
