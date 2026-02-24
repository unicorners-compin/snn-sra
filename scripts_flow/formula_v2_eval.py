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
from scripts_flow.paper_stat_eval import bootstrap_ci, parse_int_ranges, sign_flip_pvalue
from scripts_flow.snn_node import SNNQueueNode
from scripts_flow.snn_router import SNNRouter
from scripts_flow.snn_simulator import SNNSimulator
from scripts_flow.traffic import TrafficGenerator


def choose_failure_edges_multi(graph, k):
    g = graph.copy()
    out = []
    for _ in range(k):
        if g.number_of_edges() <= 0:
            break
        edge_bc = nx.edge_betweenness_centrality(g)
        edge = max(edge_bc.items(), key=lambda kv: kv[1])[0]
        edge = (int(edge[0]), int(edge[1]))
        out.append(edge)
        if g.has_edge(*edge):
            g.remove_edge(*edge)
    return out


def failure_steps_from_profile(profile, fail_step, steps):
    if profile == "single":
        fs = [int(fail_step)]
    elif profile == "frequent":
        fs = [int(fail_step - 30), int(fail_step), int(fail_step + 30), int(fail_step + 60)]
    else:
        raise ValueError(f"Unsupported failure profile: {profile}")
    return sorted({x for x in fs if 0 <= x < steps})


def run_snn_case(
    formula_mode,
    topo,
    seed,
    num_nodes,
    steps,
    fail_step,
    failure_profile,
    er_p,
    ba_m,
    snn_mode,
    beta_s=8.0,
):
    random.seed(seed)
    np.random.seed(seed)

    graph0 = generate_topology(kind=topo, num_nodes=num_nodes, seed=seed, er_p=er_p, ba_m=ba_m)
    n_actual = int(graph0.number_of_nodes())
    flow_cfg = build_flow_config(num_nodes=n_actual, seed=seed)

    fail_steps = failure_steps_from_profile(failure_profile, fail_step, steps)
    if len(fail_steps) <= 1:
        e = choose_failure_edge(graph0)
        fail_edges = [e] if e is not None else []
    else:
        fail_edges = choose_failure_edges_multi(graph0, len(fail_steps))

    cfg = build_snn_runtime_config(topo, snn_mode, formula_mode=formula_mode)
    router_kwargs = dict(cfg.get("router", {}))
    router_kwargs["beta_s"] = beta_s
    router = SNNRouter(**router_kwargs)

    graph = copy.deepcopy(graph0)
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
        for i in range(n_actual)
    }
    sim_kwargs = dict(cfg.get("sim", {}))
    sim_kwargs["known_destinations"] = [f["dst"] for f in flow_cfg]
    sim = SNNSimulator(nodes, graph, router, routing_mode=snn_mode, **sim_kwargs)
    traffic = TrafficGenerator(flow_cfg)

    history = []
    fi = 0
    for k in range(steps):
        while fi < len(fail_steps) and k == fail_steps[fi]:
            if fi < len(fail_edges):
                e = fail_edges[fi]
                if e is not None and graph.has_edge(*e):
                    graph.remove_edge(*e)
            fi += 1

        metrics = sim.run_step(k, traffic.generate(k))
        metrics["step"] = k
        history.append(metrics)

    df = pd.DataFrame(history)
    final = df.iloc[-1]
    if fail_steps:
        last_fail = fail_steps[-1]
        post = df[(df.step >= last_fail + 20) & (df.step <= min(steps - 1, last_fail + 80))]
        if post.empty:
            post = df.tail(min(60, len(df)))
    else:
        post = df.tail(min(60, len(df)))

    return {
        "formula_mode": formula_mode,
        "topo": topo,
        "size": int(n_actual),
        "failure_profile": failure_profile,
        "seed": int(seed),
        "pdr_final": float(final.pdr),
        "delay_final": float(final.avg_delay),
        "hop_final": float(final.avg_hop),
        "loss_final": float(final.loss),
        "pdr_post": float(post.pdr.mean()),
        "delay_post": float(post.avg_delay.mean()),
    }


def build_group_summary(runs_df, rng):
    metric_cols = ["pdr_final", "delay_final", "hop_final", "loss_final", "pdr_post", "delay_post"]
    rows = []
    keys = ["topo", "size", "failure_profile", "formula_mode"]
    for key, group in runs_df.groupby(keys):
        row = {keys[i]: key[i] for i in range(len(keys))}
        row["n"] = int(len(group))
        for m in metric_cols:
            vals = group[m].to_numpy(dtype=float)
            row[f"{m}_mean"] = float(np.mean(vals))
            row[f"{m}_std"] = float(np.std(vals, ddof=1)) if len(vals) > 1 else 0.0
            lo, hi = bootstrap_ci(vals, rng=rng, n_boot=1000, alpha=0.05)
            row[f"{m}_ci95_lo"] = lo
            row[f"{m}_ci95_hi"] = hi
        rows.append(row)
    return pd.DataFrame(rows)


def build_significance(runs_df, rng):
    metric_cols = ["pdr_final", "delay_final", "hop_final", "loss_final", "pdr_post", "delay_post"]
    rows = []
    keys = ["topo", "size", "failure_profile"]
    for key, group in runs_df.groupby(keys):
        v1 = group[group.formula_mode == "v1"]
        v2 = group[group.formula_mode == "v2"]
        if v1.empty or v2.empty:
            continue
        merged = v2.merge(v1, on=["seed", "topo", "size", "failure_profile"], suffixes=("_v2", "_v1"))
        if merged.empty:
            continue
        for m in metric_cols:
            diffs = (merged[f"{m}_v2"] - merged[f"{m}_v1"]).to_numpy(dtype=float)
            mean_diff = float(np.mean(diffs))
            lo, hi = bootstrap_ci(diffs, rng=rng, n_boot=2000, alpha=0.05)
            p = sign_flip_pvalue(diffs, rng=rng, n_perm=10000)
            rows.append(
                {
                    "topo": key[0],
                    "size": key[1],
                    "failure_profile": key[2],
                    "metric": m,
                    "n_pairs": int(len(diffs)),
                    "mean_diff_v2_minus_v1": mean_diff,
                    "ci95_lo": lo,
                    "ci95_hi": hi,
                    "p_value_two_sided": p,
                }
            )
    return pd.DataFrame(rows)


def main():
    parser = argparse.ArgumentParser(description="Formula v2 vs v1 paired statistical evaluation for SNN.")
    parser.add_argument("--topos", default="ba,er")
    parser.add_argument("--sizes", default="50,100")
    parser.add_argument("--seeds", default="1-20")
    parser.add_argument("--steps", type=int, default=240)
    parser.add_argument("--fail-step", type=int, default=150)
    parser.add_argument("--failure-profiles", default="single,frequent")
    parser.add_argument("--er-p", type=float, default=0.06)
    parser.add_argument("--ba-m", type=int, default=3)
    parser.add_argument("--snn-mode", default="snn_event_dv")
    parser.add_argument("--beta-s", type=float, default=8.0)
    parser.add_argument("--out-prefix", default="run_dir/issue9_formula_v2")
    parser.add_argument("--random-seed", type=int, default=20260224)
    args = parser.parse_args()

    rng = np.random.default_rng(args.random_seed)
    topos = [x.strip() for x in args.topos.split(",") if x.strip()]
    sizes = parse_int_ranges(args.sizes)
    seeds = parse_int_ranges(args.seeds)
    failure_profiles = [x.strip() for x in args.failure_profiles.split(",") if x.strip()]

    rows = []
    total = len(topos) * len(sizes) * len(failure_profiles) * len(seeds) * 2
    done = 0
    for topo in topos:
        for size in sizes:
            for profile in failure_profiles:
                for seed in seeds:
                    for mode in ("v1", "v2"):
                        done += 1
                        print(
                            f"[{done:04d}/{total:04d}] topo={topo} size={size} profile={profile} seed={seed} mode={mode}",
                            flush=True,
                        )
                        rows.append(
                            run_snn_case(
                                formula_mode=mode,
                                topo=topo,
                                seed=seed,
                                num_nodes=size,
                                steps=args.steps,
                                fail_step=args.fail_step,
                                failure_profile=profile,
                                er_p=args.er_p,
                                ba_m=args.ba_m,
                                snn_mode=args.snn_mode,
                                beta_s=args.beta_s,
                            )
                        )

    runs_df = pd.DataFrame(rows)
    summary_df = build_group_summary(runs_df, rng)
    sig_df = build_significance(runs_df, rng)

    runs_path = f"{args.out_prefix}_runs.csv"
    summary_path = f"{args.out_prefix}_summary.csv"
    sig_path = f"{args.out_prefix}_significance.csv"

    runs_df.to_csv(runs_path, index=False)
    summary_df.to_csv(summary_path, index=False)
    sig_df.to_csv(sig_path, index=False)

    print("\n=== summary (head) ===")
    print(summary_df.head(20).to_string(index=False))
    print("\n=== significance (head) ===")
    print(sig_df.head(30).to_string(index=False))
    print(f"\nSaved: {runs_path}")
    print(f"Saved: {summary_path}")
    print(f"Saved: {sig_path}")


if __name__ == "__main__":
    main()
