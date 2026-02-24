import argparse
import copy
import random
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import pandas as pd

# Path patch for local package imports.
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from scripts.topo_manager import generate_topology
from scripts_flow.compare_snn_vs_ospf import ECMPSimulator, OSPFSimulator, OSPFSyncSimulator, PPOSimulator, build_nodes
from scripts_flow.main_snn import build_flow_config, build_snn_runtime_config, choose_failure_edge
from scripts_flow.paper_stat_eval import (
    bootstrap_ci,
    choose_failure_edges_multi,
    failure_steps_from_profile,
    parse_int_ranges,
    scale_flow_config,
    sign_flip_pvalue,
)
from scripts_flow.snn_router import SNNRouter
from scripts_flow.snn_simulator import SNNSimulator
from scripts_flow.traffic import TrafficGenerator


def make_sim(algo, topo, graph, flow_cfg):
    n = graph.number_of_nodes()
    if algo == "ospf":
        return OSPFSimulator(build_nodes(n, 0.0), graph, hop_limit=64)
    if algo == "ospf_sync":
        return OSPFSyncSimulator(build_nodes(n, 0.0), graph, hop_limit=64, sync_period=12, spf_delay=4)
    if algo == "ecmp":
        return ECMPSimulator(build_nodes(n, 0.0), graph, hop_limit=64)
    if algo == "ppo":
        return PPOSimulator(build_nodes(n, 0.0), graph, hop_limit=64, seed=7, train=True)
    if algo == "snn":
        cfg = build_snn_runtime_config(topo, "snn_spike_native")
        router_kwargs = dict(cfg.get("router", {}))
        router_kwargs["beta_s"] = 8.0
        router = SNNRouter(**router_kwargs)
        sim_kwargs = dict(cfg.get("sim", {}))
        sim_kwargs["known_destinations"] = [f["dst"] for f in flow_cfg]
        return SNNSimulator(build_nodes(n, 8.0), graph, router, routing_mode="snn_spike_native", **sim_kwargs)
    raise ValueError(f"Unsupported algo: {algo}")


def run_case(
    algo,
    topo,
    seed,
    num_nodes,
    steps,
    fail_step,
    failure_profile,
    er_p,
    ba_m,
    background_scale=1.0,
):
    random.seed(seed)
    np.random.seed(seed)

    graph0 = generate_topology(kind=topo, num_nodes=num_nodes, seed=seed, er_p=er_p, ba_m=ba_m)
    flow_cfg = scale_flow_config(build_flow_config(num_nodes=num_nodes, seed=seed), background_scale)
    traffic = TrafficGenerator(flow_cfg)

    fail_steps = failure_steps_from_profile(failure_profile, fail_step, steps)
    if len(fail_steps) <= 1:
        edge = choose_failure_edge(graph0)
        fail_edges = [edge] if edge is not None else []
    else:
        fail_edges = choose_failure_edges_multi(graph0, len(fail_steps))

    graph = copy.deepcopy(graph0)
    sim = make_sim(algo, topo, graph, flow_cfg)

    step_wall_ms = []
    step_ctrl_msgs = []
    prev_broadcast = 0.0
    prev_table_updates = 0.0
    history = []

    fi = 0
    for k in range(steps):
        while fi < len(fail_steps) and k == fail_steps[fi]:
            if fi < len(fail_edges):
                e = fail_edges[fi]
                if e is not None and graph.has_edge(*e):
                    graph.remove_edge(*e)
            fi += 1

        t0 = time.perf_counter()
        metrics = sim.run_step(k, traffic.generate(k))
        dt_ms = (time.perf_counter() - t0) * 1000.0
        step_wall_ms.append(float(dt_ms))

        b_now = float(metrics.get("broadcasts", prev_broadcast))
        t_now = float(metrics.get("table_updates", prev_table_updates))
        b_delta = max(0.0, b_now - prev_broadcast)
        t_delta = max(0.0, t_now - prev_table_updates)
        step_ctrl_msgs.append(float(b_delta + t_delta))
        prev_broadcast = b_now
        prev_table_updates = t_now

        metrics["step"] = k
        history.append(metrics)

    if hasattr(sim, "finalize"):
        sim.finalize()

    df = pd.DataFrame(history)
    final = df.iloc[-1]

    wall_arr = np.asarray(step_wall_ms, dtype=float)
    ctrl_arr = np.asarray(step_ctrl_msgs, dtype=float)

    return {
        "algo": algo,
        "topo": topo,
        "size": int(num_nodes),
        "failure_profile": failure_profile,
        "seed": int(seed),
        "pdr_final": float(final.pdr),
        "loss_final": float(final.loss),
        "delay_final": float(final.avg_delay),
        "wall_ms_total": float(np.sum(wall_arr)),
        "wall_ms_mean": float(np.mean(wall_arr)),
        "wall_ms_p95": float(np.quantile(wall_arr, 0.95)),
        "wall_ms_p99": float(np.quantile(wall_arr, 0.99)),
        "ctrl_msgs_total": float(np.sum(ctrl_arr)),
        "ctrl_msgs_mean": float(np.mean(ctrl_arr)),
        "ctrl_msgs_p95": float(np.quantile(ctrl_arr, 0.95)),
        "ctrl_msgs_p99": float(np.quantile(ctrl_arr, 0.99)),
        "broadcasts_final": float(final.get("broadcasts", 0.0)),
        "table_updates_final": float(final.get("table_updates", 0.0)),
        "route_changes_final": float(final.get("route_changes", 0.0)),
        "generated_final": float(getattr(sim, "total_generated", 0.0)),
        "delivered_final": float(getattr(sim, "total_delivered", 0.0)),
    }


def build_summary(runs_df, rng):
    metric_cols = [
        "pdr_final",
        "loss_final",
        "delay_final",
        "wall_ms_total",
        "wall_ms_mean",
        "wall_ms_p95",
        "wall_ms_p99",
        "ctrl_msgs_total",
        "ctrl_msgs_mean",
        "ctrl_msgs_p95",
        "ctrl_msgs_p99",
        "broadcasts_final",
        "table_updates_final",
        "route_changes_final",
        "generated_final",
        "delivered_final",
    ]
    rows = []
    keys = ["topo", "size", "failure_profile", "algo"]
    for key, group in runs_df.groupby(keys):
        row = {keys[i]: key[i] for i in range(len(keys))}
        row["n"] = int(len(group))
        for m in metric_cols:
            vals = group[m].to_numpy(dtype=float)
            row[f"{m}_mean"] = float(np.mean(vals))
            row[f"{m}_std"] = float(np.std(vals, ddof=1)) if vals.size > 1 else 0.0
            lo, hi = bootstrap_ci(vals, rng=rng, n_boot=1000, alpha=0.05)
            row[f"{m}_ci95_lo"] = lo
            row[f"{m}_ci95_hi"] = hi
        rows.append(row)
    return pd.DataFrame(rows)


def build_significance(runs_df, rng):
    metric_cols = [
        "pdr_final",
        "loss_final",
        "delay_final",
        "wall_ms_mean",
        "wall_ms_p95",
        "wall_ms_p99",
        "ctrl_msgs_mean",
        "ctrl_msgs_p95",
        "ctrl_msgs_p99",
    ]
    rows = []
    keys = ["topo", "size", "failure_profile"]
    for key, group in runs_df.groupby(keys):
        snn = group[group.algo == "snn"]
        if snn.empty:
            continue
        for base_algo in ["ospf", "ospf_sync", "ecmp", "ppo"]:
            base = group[group.algo == base_algo]
            if base.empty:
                continue
            merged = snn.merge(base, on=["seed", "topo", "size", "failure_profile"], suffixes=("_snn", "_base"))
            if merged.empty:
                continue
            for m in metric_cols:
                diffs = (merged[f"{m}_snn"] - merged[f"{m}_base"]).to_numpy(dtype=float)
                lo, hi = bootstrap_ci(diffs, rng=rng, n_boot=2000, alpha=0.05)
                rows.append(
                    {
                        "topo": key[0],
                        "size": key[1],
                        "failure_profile": key[2],
                        "base_algo": base_algo,
                        "metric": m,
                        "n_pairs": int(diffs.size),
                        "mean_diff_snn_minus_base": float(np.mean(diffs)),
                        "ci95_lo": lo,
                        "ci95_hi": hi,
                        "p_value_two_sided": sign_flip_pvalue(diffs, rng=rng, n_perm=10000),
                    }
                )
    return pd.DataFrame(rows)


def build_benefit_cost(runs_df):
    rows = []
    keys = ["topo", "size", "failure_profile"]
    for key, group in runs_df.groupby(keys):
        snn = group[group.algo == "snn"]
        if snn.empty:
            continue
        for base_algo in ["ospf", "ospf_sync", "ecmp", "ppo"]:
            base = group[group.algo == base_algo]
            if base.empty:
                continue
            merged = snn.merge(base, on=["seed", "topo", "size", "failure_profile"], suffixes=("_snn", "_base"))
            if merged.empty:
                continue

            dpdr = merged["pdr_final_snn"].to_numpy(dtype=float) - merged["pdr_final_base"].to_numpy(dtype=float)
            dloss = merged["loss_final_snn"].to_numpy(dtype=float) - merged["loss_final_base"].to_numpy(dtype=float)
            dwall = merged["wall_ms_mean_snn"].to_numpy(dtype=float) - merged["wall_ms_mean_base"].to_numpy(dtype=float)
            dctrl = merged["ctrl_msgs_mean_snn"].to_numpy(dtype=float) - merged["ctrl_msgs_mean_base"].to_numpy(dtype=float)

            pdr_per_ms = np.full_like(dpdr, np.nan, dtype=float)
            loss_reduction_per_ctrl = np.full_like(dpdr, np.nan, dtype=float)
            wall_mask = np.abs(dwall) > 1e-9
            ctrl_mask = np.abs(dctrl) > 1e-9
            pdr_per_ms[wall_mask] = dpdr[wall_mask] / np.abs(dwall[wall_mask])
            loss_reduction_per_ctrl[ctrl_mask] = (-dloss[ctrl_mask]) / np.abs(dctrl[ctrl_mask])

            rows.append(
                {
                    "topo": key[0],
                    "size": key[1],
                    "failure_profile": key[2],
                    "base_algo": base_algo,
                    "n_pairs": int(merged.shape[0]),
                    "delta_pdr_mean": float(np.mean(dpdr)),
                    "delta_loss_mean": float(np.mean(dloss)),
                    "delta_wall_ms_mean": float(np.mean(dwall)),
                    "delta_ctrl_msgs_mean": float(np.mean(dctrl)),
                    "pdr_gain_per_ms_overhead": float(np.nanmean(pdr_per_ms))
                    if np.any(np.isfinite(pdr_per_ms))
                    else float("nan"),
                    "loss_reduction_per_ctrl_msg": float(np.nanmean(loss_reduction_per_ctrl))
                    if np.any(np.isfinite(loss_reduction_per_ctrl))
                    else float("nan"),
                }
            )

    df = pd.DataFrame(rows)
    if df.empty:
        return df

    global_df = (
        df.groupby("base_algo", as_index=False)[
            [
                "delta_pdr_mean",
                "delta_loss_mean",
                "delta_wall_ms_mean",
                "delta_ctrl_msgs_mean",
                "pdr_gain_per_ms_overhead",
                "loss_reduction_per_ctrl_msg",
                "n_pairs",
            ]
        ]
        .mean()
        .sort_values("base_algo")
        .reset_index(drop=True)
    )
    global_df["topo"] = "all"
    global_df["size"] = -1
    global_df["failure_profile"] = "all"
    global_df["scope"] = "global"

    local_df = df.copy()
    local_df["scope"] = "group"
    return pd.concat([global_df, local_df], ignore_index=True, sort=False)


def main():
    parser = argparse.ArgumentParser(description="Complexity and overhead evaluation for routing algorithms.")
    parser.add_argument("--algos", default="ospf,ecmp,ppo,snn")
    parser.add_argument("--topos", default="ba,er")
    parser.add_argument("--sizes", default="50,100,200")
    parser.add_argument("--seeds", default="1-20")
    parser.add_argument("--steps", type=int, default=240)
    parser.add_argument("--fail-step", type=int, default=150)
    parser.add_argument("--failure-profiles", default="single,frequent")
    parser.add_argument("--er-p", type=float, default=0.06)
    parser.add_argument("--ba-m", type=int, default=3)
    parser.add_argument("--background-scale", type=float, default=2.0)
    parser.add_argument("--workers", type=int, default=20)
    parser.add_argument("--out-prefix", default="run_dir/issue18_overhead")
    parser.add_argument("--random-seed", type=int, default=20260223)
    args = parser.parse_args()

    algos = [x.strip() for x in args.algos.split(",") if x.strip()]
    topos = [x.strip() for x in args.topos.split(",") if x.strip()]
    sizes = parse_int_ranges(args.sizes)
    seeds = parse_int_ranges(args.seeds)
    profiles = [x.strip() for x in args.failure_profiles.split(",") if x.strip()]

    valid_algos = {"ospf", "ospf_sync", "ecmp", "ppo", "snn"}
    invalid = [a for a in algos if a not in valid_algos]
    if invalid:
        raise ValueError(f"Unsupported algos: {invalid}")

    tasks = []
    for topo in topos:
        for size in sizes:
            for profile in profiles:
                for seed in seeds:
                    for algo in algos:
                        tasks.append(
                            {
                                "algo": algo,
                                "topo": topo,
                                "seed": seed,
                                "num_nodes": size,
                                "steps": args.steps,
                                "fail_step": args.fail_step,
                                "failure_profile": profile,
                                "er_p": args.er_p,
                                "ba_m": args.ba_m,
                                "background_scale": args.background_scale,
                            }
                        )

    total = len(tasks)
    rows = []
    done = 0
    with ProcessPoolExecutor(max_workers=int(args.workers)) as ex:
        fut2task = {ex.submit(run_case, **t): t for t in tasks}
        for fut in as_completed(fut2task):
            rows.append(fut.result())
            done += 1
            if done % 20 == 0 or done == total:
                print(f"[{done:04d}/{total:04d}] done", flush=True)

    runs_df = pd.DataFrame(rows)
    runs_df = runs_df.sort_values(["topo", "size", "failure_profile", "seed", "algo"]).reset_index(drop=True)

    rng = np.random.default_rng(args.random_seed)
    summary_df = build_summary(runs_df, rng)
    sig_df = build_significance(runs_df, rng)
    bc_df = build_benefit_cost(runs_df)

    runs_path = f"{args.out_prefix}_runs.csv"
    summary_path = f"{args.out_prefix}_summary.csv"
    sig_path = f"{args.out_prefix}_significance.csv"
    bc_path = f"{args.out_prefix}_benefit_cost.csv"

    runs_df.to_csv(runs_path, index=False)
    summary_df.to_csv(summary_path, index=False)
    sig_df.to_csv(sig_path, index=False)
    bc_df.to_csv(bc_path, index=False)

    print("\n=== summary (head) ===")
    print(summary_df.head(20).to_string(index=False))
    print("\n=== significance (head) ===")
    print(sig_df.head(30).to_string(index=False))
    print("\n=== benefit_cost (global) ===")
    if bc_df.empty:
        print("(empty)")
    else:
        print(bc_df[bc_df.scope == "global"].to_string(index=False))

    print(f"\nSaved: {runs_path}")
    print(f"Saved: {summary_path}")
    print(f"Saved: {sig_path}")
    print(f"Saved: {bc_path}")


if __name__ == "__main__":
    main()
