import argparse
import copy
import itertools
import random
import re
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
from scripts_flow.compare_snn_vs_ospf import (
    BackpressureSimulator,
    ECMPSimulator,
    OSPFSimulator,
    OSPFSyncSimulator,
    PPOSimulator,
    build_nodes,
)
from scripts_flow.main_snn import build_flow_config, build_snn_runtime_config, choose_failure_edge
from scripts_flow.snn_router import SNNRouter
from scripts_flow.snn_simulator import SNNSimulator
from scripts_flow.traffic import TrafficGenerator


def scale_flow_config(flow_cfg, background_scale):
    scale = float(background_scale)
    if abs(scale - 1.0) <= 1e-12:
        return flow_cfg
    out = []
    for flow in flow_cfg:
        item = dict(flow)
        base = float(item.get("base_rate", 1.0)) * scale
        burst = float(item.get("burst_rate", base)) * scale
        item["base_rate"] = max(0.01, base)
        item["burst_rate"] = max(item["base_rate"], burst)
        out.append(item)
    return out


def parse_int_ranges(spec):
    vals = []
    for part in [x.strip() for x in spec.split(",") if x.strip()]:
        m = re.fullmatch(r"(\d+)-(\d+)", part)
        if m:
            a, b = int(m.group(1)), int(m.group(2))
            if a <= b:
                vals.extend(list(range(a, b + 1)))
            else:
                vals.extend(list(range(a, b - 1, -1)))
        else:
            vals.append(int(part))
    return vals


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
    fs = sorted({x for x in fs if 0 <= x < steps})
    return fs


def make_sim(algo, topo, graph, flow_cfg, snn_mode):
    n = graph.number_of_nodes()
    if algo == "ospf":
        return OSPFSimulator(build_nodes(n, 0.0), graph, hop_limit=64)
    if algo == "ospf_sync":
        return OSPFSyncSimulator(build_nodes(n, 0.0), graph, hop_limit=64, sync_period=12, spf_delay=4)
    if algo == "ecmp":
        return ECMPSimulator(build_nodes(n, 0.0), graph, hop_limit=64)
    if algo == "backpressure":
        return BackpressureSimulator(build_nodes(n, 0.0), graph, hop_limit=64)
    if algo == "ppo":
        return PPOSimulator(build_nodes(n, 0.0), graph, hop_limit=64, seed=7, train=True)
    if algo == "snn":
        cfg = build_snn_runtime_config(topo, snn_mode)
        router_kwargs = dict(cfg.get("router", {}))
        router_kwargs["beta_s"] = 8.0
        router = SNNRouter(**router_kwargs)
        sim_kwargs = dict(cfg.get("sim", {}))
        sim_kwargs["known_destinations"] = [f["dst"] for f in flow_cfg]
        return SNNSimulator(build_nodes(n, 8.0), graph, router, routing_mode=snn_mode, **sim_kwargs)
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
    snn_mode,
    background_scale=1.0,
):
    random.seed(seed)
    np.random.seed(seed)
    graph0 = generate_topology(kind=topo, num_nodes=num_nodes, seed=seed, er_p=er_p, ba_m=ba_m)
    flow_cfg = scale_flow_config(build_flow_config(num_nodes=num_nodes, seed=seed), background_scale)
    traffic = TrafficGenerator(flow_cfg)

    fail_steps = failure_steps_from_profile(failure_profile, fail_step, steps)
    if len(fail_steps) <= 1:
        e = choose_failure_edge(graph0)
        fail_edges = [e] if e is not None else []
    else:
        fail_edges = choose_failure_edges_multi(graph0, len(fail_steps))

    graph = copy.deepcopy(graph0)
    sim = make_sim(algo, topo, graph, flow_cfg, snn_mode)

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
        last_fail = fail_steps[-1]
        post = df[(df.step >= last_fail + 20) & (df.step <= min(steps - 1, last_fail + 80))]
    else:
        post = df.tail(min(60, len(df)))
    return {
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


def bootstrap_ci(values, rng, n_boot=1000, alpha=0.05):
    arr = np.asarray(values, dtype=float)
    arr = arr[np.isfinite(arr)]
    if arr.size == 0:
        return float("nan"), float("nan")
    if arr.size == 1:
        x = float(arr[0])
        return x, x
    idx = rng.integers(0, arr.size, size=(n_boot, arr.size))
    means = arr[idx].mean(axis=1)
    lo = float(np.quantile(means, alpha / 2.0))
    hi = float(np.quantile(means, 1.0 - alpha / 2.0))
    return lo, hi


def sign_flip_pvalue(diffs, rng, n_perm=10000):
    arr = np.asarray(diffs, dtype=float)
    arr = arr[np.isfinite(arr)]
    if arr.size == 0:
        return float("nan")
    obs = abs(float(np.mean(arr)))
    if arr.size <= 12:
        signs = np.array(list(itertools.product([-1.0, 1.0], repeat=arr.size)))
        vals = np.abs((signs * arr).mean(axis=1))
        p = (np.sum(vals >= obs) + 1.0) / (vals.size + 1.0)
        return float(p)
    signs = rng.choice([-1.0, 1.0], size=(n_perm, arr.size))
    vals = np.abs((signs * arr).mean(axis=1))
    p = (np.sum(vals >= obs) + 1.0) / (n_perm + 1.0)
    return float(p)


def build_group_summary(runs_df, rng):
    metric_cols = ["pdr_final", "delay_final", "hop_final", "loss_final", "pdr_post", "delay_post"]
    rows = []
    keys = ["topo", "size", "failure_profile", "algo"]
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
        g = group.copy()
        snn = g[g.algo == "snn"]
        if snn.empty:
            continue
        for base_algo in ["ospf", "ospf_sync", "ecmp", "backpressure", "ppo"]:
            base = g[g.algo == base_algo]
            if base.empty:
                continue
            merged = snn.merge(base, on=["seed", "topo", "size", "failure_profile"], suffixes=("_snn", "_base"))
            if merged.empty:
                continue
            for m in metric_cols:
                diffs = (merged[f"{m}_snn"] - merged[f"{m}_base"]).to_numpy(dtype=float)
                mean_diff = float(np.mean(diffs))
                lo, hi = bootstrap_ci(diffs, rng=rng, n_boot=2000, alpha=0.05)
                p = sign_flip_pvalue(diffs, rng=rng, n_perm=10000)
                rows.append(
                    {
                        "topo": key[0],
                        "size": key[1],
                        "failure_profile": key[2],
                        "base_algo": base_algo,
                        "metric": m,
                        "n_pairs": int(len(diffs)),
                        "mean_diff_snn_minus_base": mean_diff,
                        "ci95_lo": lo,
                        "ci95_hi": hi,
                        "p_value_two_sided": p,
                    }
                )
    return pd.DataFrame(rows)


def main():
    parser = argparse.ArgumentParser(description="Paper-grade statistical evaluation for routing baselines.")
    parser.add_argument("--algos", default="ospf,ecmp,backpressure,ppo,snn")
    parser.add_argument("--topos", default="ba,er")
    parser.add_argument("--sizes", default="50,100")
    parser.add_argument("--seeds", default="1-20")
    parser.add_argument("--steps", type=int, default=240)
    parser.add_argument("--fail-step", type=int, default=150)
    parser.add_argument("--failure-profiles", default="single,frequent")
    parser.add_argument("--er-p", type=float, default=0.06)
    parser.add_argument("--ba-m", type=int, default=3)
    parser.add_argument("--background-scale", type=float, default=1.0)
    parser.add_argument("--snn-mode", default="snn_spike_native")
    parser.add_argument("--out-prefix", default="run_dir/issue10")
    parser.add_argument("--random-seed", type=int, default=20260223)
    args = parser.parse_args()

    rng = np.random.default_rng(args.random_seed)

    algos = [x.strip() for x in args.algos.split(",") if x.strip()]
    topos = [x.strip() for x in args.topos.split(",") if x.strip()]
    sizes = parse_int_ranges(args.sizes)
    seeds = parse_int_ranges(args.seeds)
    failure_profiles = [x.strip() for x in args.failure_profiles.split(",") if x.strip()]

    valid_algos = {"ospf", "ospf_sync", "ecmp", "backpressure", "ppo", "snn"}
    invalid = [a for a in algos if a not in valid_algos]
    if invalid:
        raise ValueError(f"Unsupported algos: {invalid}")

    rows = []
    total = len(topos) * len(sizes) * len(failure_profiles) * len(seeds) * len(algos)
    done = 0
    for topo in topos:
        for size in sizes:
            for profile in failure_profiles:
                for seed in seeds:
                    for algo in algos:
                        done += 1
                        print(
                            f"[{done:04d}/{total:04d}] topo={topo} size={size} profile={profile} seed={seed} algo={algo}",
                            flush=True,
                        )
                        rows.append(
                            run_case(
                                algo=algo,
                                topo=topo,
                                seed=seed,
                                num_nodes=size,
                                steps=args.steps,
                                fail_step=args.fail_step,
                                failure_profile=profile,
                                er_p=args.er_p,
                                ba_m=args.ba_m,
                                snn_mode=args.snn_mode,
                                background_scale=args.background_scale,
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
