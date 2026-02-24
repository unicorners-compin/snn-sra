import argparse
import copy
import random
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import pandas as pd

# Path patch for local package imports.
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from scripts.topo_manager import generate_topology
from scripts_flow.compare_snn_vs_ospf import (
    ECMPSimulator,
    OSPFSimulator,
    OSPFSyncSimulator,
    PPOSimulator,
    build_nodes,
)
from scripts_flow.main_snn import build_flow_config, build_snn_runtime_config, choose_failure_edge
from scripts_flow.paper_stat_eval import (
    bootstrap_ci,
    build_group_summary,
    build_significance,
    choose_failure_edges_multi,
    failure_steps_from_profile,
    parse_int_ranges,
    scale_flow_config,
    sign_flip_pvalue,
)
from scripts_flow.snn_router import SNNRouter
from scripts_flow.snn_simulator import SNNSimulator
from scripts_flow.traffic import TrafficGenerator


def _quantile(arr, q):
    if len(arr) <= 0:
        return float("nan")
    return float(np.quantile(np.asarray(arr, dtype=float), q))


def _summary_from_samples(sim, post_start=None, post_end=None):
    delays = np.asarray(getattr(sim, "delivered_delay_samples", []), dtype=float)
    steps = np.asarray(getattr(sim, "delivered_step_samples", []), dtype=float)
    queue_delays = np.asarray(getattr(sim, "delivered_queue_delay_samples", []), dtype=float)
    extra_hops = np.asarray(getattr(sim, "delivered_extra_hop_samples", []), dtype=float)

    out = {
        "delay_p50_final": _quantile(delays, 0.50),
        "delay_p95_final": _quantile(delays, 0.95),
        "delay_p99_final": _quantile(delays, 0.99),
        "queue_delay_mean_final": float(np.mean(queue_delays)) if queue_delays.size > 0 else float("nan"),
        "extra_hop_mean_final": float(np.mean(extra_hops)) if extra_hops.size > 0 else float("nan"),
    }

    if post_start is None or post_end is None or delays.size <= 0 or steps.size != delays.size:
        out.update(
            {
                "delay_p50_post": float("nan"),
                "delay_p95_post": float("nan"),
                "delay_p99_post": float("nan"),
                "queue_delay_mean_post": float("nan"),
                "extra_hop_mean_post": float("nan"),
                "n_delivered_post": 0,
            }
        )
        return out

    mask = (steps >= float(post_start)) & (steps <= float(post_end))
    post_delays = delays[mask]
    post_queue = queue_delays[mask] if queue_delays.size == delays.size else np.asarray([], dtype=float)
    post_extra = extra_hops[mask] if extra_hops.size == delays.size else np.asarray([], dtype=float)

    out.update(
        {
            "delay_p50_post": _quantile(post_delays, 0.50),
            "delay_p95_post": _quantile(post_delays, 0.95),
            "delay_p99_post": _quantile(post_delays, 0.99),
            "queue_delay_mean_post": float(np.mean(post_queue)) if post_queue.size > 0 else float("nan"),
            "extra_hop_mean_post": float(np.mean(post_extra)) if post_extra.size > 0 else float("nan"),
            "n_delivered_post": int(post_delays.size),
        }
    )
    return out


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

    if hasattr(sim, "finalize"):
        sim.finalize()

    df = pd.DataFrame(history)
    final = df.iloc[-1]
    if fail_steps:
        last_fail = int(fail_steps[-1])
        post_start = last_fail + 20
        post_end = min(steps - 1, last_fail + 80)
        post = df[(df.step >= post_start) & (df.step <= post_end)]
    else:
        post_end = steps - 1
        post_start = max(0, post_end - 59)
        post = df.tail(min(60, len(df)))

    sample_metrics = _summary_from_samples(sim, post_start=post_start, post_end=post_end)
    out = {
        "algo": algo,
        "topo": topo,
        "size": int(num_nodes),
        "failure_profile": failure_profile,
        "seed": int(seed),
        "pdr_final": float(final.pdr),
        "delay_final": float(final.avg_delay),
        "hop_final": float(final.avg_hop),
        "loss_final": float(final.loss),
        "pdr_post": float(post.pdr.mean()),
        "delay_post": float(post.avg_delay.mean()),
    }
    out.update(sample_metrics)
    return out


def build_delay_group_summary(runs_df, rng):
    base = build_group_summary(runs_df, rng)
    metric_cols = [
        "delay_p50_final",
        "delay_p95_final",
        "delay_p99_final",
        "queue_delay_mean_final",
        "extra_hop_mean_final",
        "delay_p50_post",
        "delay_p95_post",
        "delay_p99_post",
        "queue_delay_mean_post",
        "extra_hop_mean_post",
        "n_delivered_post",
    ]
    rows = []
    keys = ["topo", "size", "failure_profile", "algo"]
    for key, group in runs_df.groupby(keys):
        row = {keys[i]: key[i] for i in range(len(keys))}
        for m in metric_cols:
            vals = group[m].to_numpy(dtype=float)
            vals = vals[np.isfinite(vals)]
            row[f"{m}_mean"] = float(np.mean(vals)) if vals.size > 0 else float("nan")
            row[f"{m}_std"] = float(np.std(vals, ddof=1)) if vals.size > 1 else 0.0
            lo, hi = bootstrap_ci(vals, rng=rng, n_boot=1000, alpha=0.05)
            row[f"{m}_ci95_lo"] = lo
            row[f"{m}_ci95_hi"] = hi
        rows.append(row)
    ext = pd.DataFrame(rows)
    return base.merge(ext, on=keys, how="left")


def build_delay_significance(runs_df, rng):
    base_sig = build_significance(runs_df, rng)
    metric_cols = [
        "delay_p95_final",
        "delay_p99_final",
        "delay_p95_post",
        "delay_p99_post",
        "queue_delay_mean_final",
        "extra_hop_mean_final",
        "queue_delay_mean_post",
        "extra_hop_mean_post",
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
                diffs = diffs[np.isfinite(diffs)]
                if diffs.size <= 0:
                    continue
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
    ext = pd.DataFrame(rows)
    if ext.empty:
        return base_sig
    return pd.concat([base_sig, ext], ignore_index=True)


def main():
    parser = argparse.ArgumentParser(description="Parallel delay-tail and delay-breakdown evaluation.")
    parser.add_argument("--algos", default="ospf,ecmp,ppo,snn")
    parser.add_argument("--topos", default="ba,er")
    parser.add_argument("--sizes", default="50,100")
    parser.add_argument("--seeds", default="1-20")
    parser.add_argument("--steps", type=int, default=240)
    parser.add_argument("--fail-step", type=int, default=150)
    parser.add_argument("--failure-profiles", default="single,frequent")
    parser.add_argument("--er-p", type=float, default=0.06)
    parser.add_argument("--ba-m", type=int, default=3)
    parser.add_argument("--background-scale", type=float, default=2.0)
    parser.add_argument("--workers", type=int, default=20)
    parser.add_argument("--out-prefix", default="run_dir/issue16_delay")
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
    summary_df = build_delay_group_summary(runs_df, rng)
    sig_df = build_delay_significance(runs_df, rng)

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
