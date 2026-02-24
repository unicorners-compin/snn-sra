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
from scripts_flow.compare_snn_vs_ospf import build_nodes
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


def make_snn_ablation_sim(topo, graph, flow_cfg, variant):
    cfg = build_snn_runtime_config(topo, "snn_spike_native")
    router_kwargs = dict(cfg.get("router", {}))
    sim_kwargs = dict(cfg.get("sim", {}))

    router_kwargs["beta_s"] = 8.0

    if variant == "no_dst_beacon":
        sim_kwargs["enable_dst_beacon"] = False
    elif variant == "no_lif_burst":
        sim_kwargs["enable_lif_burst"] = False
    elif variant == "no_stdp":
        router_kwargs["eta_stdp"] = 0.0
    elif variant == "no_min_hold":
        sim_kwargs["native_min_hold_steps"] = 0
        sim_kwargs["native_emergency_improvement"] = 1e9
    elif variant == "full":
        pass
    else:
        raise ValueError(f"Unsupported ablation variant: {variant}")

    router = SNNRouter(**router_kwargs)
    sim_kwargs["known_destinations"] = [f["dst"] for f in flow_cfg]
    return SNNSimulator(build_nodes(graph.number_of_nodes(), 8.0), graph, router, routing_mode="snn_spike_native", **sim_kwargs)


def run_case(
    variant,
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
    sim = make_snn_ablation_sim(topo, graph, flow_cfg, variant)

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
    else:
        post = df.tail(min(60, len(df)))

    return {
        "variant": variant,
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
        "route_changes_final": float(final.route_changes),
        "broadcasts_final": float(final.broadcasts),
    }


def build_variant_summary(runs_df, rng):
    metric_cols = [
        "pdr_final",
        "delay_final",
        "hop_final",
        "loss_final",
        "pdr_post",
        "delay_post",
        "route_changes_final",
        "broadcasts_final",
    ]
    rows = []
    keys = ["topo", "size", "failure_profile", "variant"]
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


def build_significance_vs_full(runs_df, rng):
    metric_cols = [
        "pdr_final",
        "delay_final",
        "hop_final",
        "loss_final",
        "pdr_post",
        "delay_post",
        "route_changes_final",
        "broadcasts_final",
    ]
    rows = []
    keys = ["topo", "size", "failure_profile"]
    for key, group in runs_df.groupby(keys):
        g = group.copy()
        full = g[g.variant == "full"]
        if full.empty:
            continue
        variants = sorted([v for v in g.variant.unique().tolist() if v != "full"])
        for var in variants:
            one = g[g.variant == var]
            merged = one.merge(full, on=["seed", "topo", "size", "failure_profile"], suffixes=("_var", "_full"))
            if merged.empty:
                continue
            for m in metric_cols:
                diffs = (merged[f"{m}_var"] - merged[f"{m}_full"]).to_numpy(dtype=float)
                lo, hi = bootstrap_ci(diffs, rng=rng, n_boot=2000, alpha=0.05)
                rows.append(
                    {
                        "topo": key[0],
                        "size": key[1],
                        "failure_profile": key[2],
                        "variant": var,
                        "metric": m,
                        "n_pairs": int(len(diffs)),
                        "mean_diff_variant_minus_full": float(np.mean(diffs)),
                        "ci95_lo": lo,
                        "ci95_hi": hi,
                        "p_value_two_sided": sign_flip_pvalue(diffs, rng=rng, n_perm=10000),
                    }
                )
    return pd.DataFrame(rows)


def build_contribution(runs_df):
    rows = []
    keys = ["topo", "size", "failure_profile"]
    for key, group in runs_df.groupby(keys):
        full = group[group.variant == "full"]
        if full.empty:
            continue
        for var in sorted([v for v in group.variant.unique().tolist() if v != "full"]):
            one = group[group.variant == var]
            merged = one.merge(full, on=["seed", "topo", "size", "failure_profile"], suffixes=("_var", "_full"))
            if merged.empty:
                continue

            full_pdr = np.maximum(merged["pdr_post_full"].to_numpy(dtype=float), 1e-9)
            full_loss = np.maximum(merged["loss_final_full"].to_numpy(dtype=float), 1.0)

            deg_pdr = (merged["pdr_post_full"].to_numpy(dtype=float) - merged["pdr_post_var"].to_numpy(dtype=float)) / full_pdr
            deg_loss = (merged["loss_final_var"].to_numpy(dtype=float) - merged["loss_final_full"].to_numpy(dtype=float)) / full_loss
            score = 0.5 * float(np.mean(deg_pdr)) + 0.5 * float(np.mean(deg_loss))

            rows.append(
                {
                    "topo": key[0],
                    "size": key[1],
                    "failure_profile": key[2],
                    "variant": var,
                    "pdr_post_relative_drop": float(np.mean(deg_pdr)),
                    "loss_final_relative_rise": float(np.mean(deg_loss)),
                    "contribution_score": score,
                    "n_pairs": int(len(merged)),
                }
            )

    contrib_df = pd.DataFrame(rows)
    if contrib_df.empty:
        return contrib_df

    global_df = (
        contrib_df.groupby("variant", as_index=False)[
            ["pdr_post_relative_drop", "loss_final_relative_rise", "contribution_score", "n_pairs"]
        ]
        .mean()
        .sort_values("contribution_score", ascending=False)
        .reset_index(drop=True)
    )
    global_df["topo"] = "all"
    global_df["size"] = -1
    global_df["failure_profile"] = "all"
    global_df["scope"] = "global"
    local_df = contrib_df.copy()
    local_df["scope"] = "group"
    return pd.concat([global_df, local_df], ignore_index=True, sort=False)


def main():
    parser = argparse.ArgumentParser(description="Paper ablation evaluation for SNN core modules.")
    parser.add_argument("--variants", default="full,no_dst_beacon,no_lif_burst,no_stdp,no_min_hold")
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
    parser.add_argument("--out-prefix", default="run_dir/issue17_ablation")
    parser.add_argument("--random-seed", type=int, default=20260223)
    args = parser.parse_args()

    variants = [x.strip() for x in args.variants.split(",") if x.strip()]
    topos = [x.strip() for x in args.topos.split(",") if x.strip()]
    sizes = parse_int_ranges(args.sizes)
    seeds = parse_int_ranges(args.seeds)
    profiles = [x.strip() for x in args.failure_profiles.split(",") if x.strip()]

    valid_variants = {"full", "no_dst_beacon", "no_lif_burst", "no_stdp", "no_min_hold"}
    invalid = [v for v in variants if v not in valid_variants]
    if invalid:
        raise ValueError(f"Unsupported variants: {invalid}")

    tasks = []
    for topo in topos:
        for size in sizes:
            for profile in profiles:
                for seed in seeds:
                    for variant in variants:
                        tasks.append(
                            {
                                "variant": variant,
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
    runs_df = runs_df.sort_values(["topo", "size", "failure_profile", "seed", "variant"]).reset_index(drop=True)

    rng = np.random.default_rng(args.random_seed)
    summary_df = build_variant_summary(runs_df, rng)
    sig_df = build_significance_vs_full(runs_df, rng)
    contrib_df = build_contribution(runs_df)

    runs_path = f"{args.out_prefix}_runs.csv"
    summary_path = f"{args.out_prefix}_summary.csv"
    sig_path = f"{args.out_prefix}_significance.csv"
    contrib_path = f"{args.out_prefix}_contrib.csv"

    runs_df.to_csv(runs_path, index=False)
    summary_df.to_csv(summary_path, index=False)
    sig_df.to_csv(sig_path, index=False)
    contrib_df.to_csv(contrib_path, index=False)

    print("\n=== summary (head) ===")
    print(summary_df.head(20).to_string(index=False))
    print("\n=== significance vs full (head) ===")
    print(sig_df.head(30).to_string(index=False))
    print("\n=== contribution (global) ===")
    if contrib_df.empty:
        print("(empty)")
    else:
        print(contrib_df[contrib_df.scope == "global"].to_string(index=False))

    print(f"\nSaved: {runs_path}")
    print(f"Saved: {summary_path}")
    print(f"Saved: {sig_path}")
    print(f"Saved: {contrib_path}")


if __name__ == "__main__":
    main()
