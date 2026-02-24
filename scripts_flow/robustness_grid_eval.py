import argparse
import copy
import random
import re
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import networkx as nx
import numpy as np
import pandas as pd

# Path patch for local package imports.
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from scripts.topo_manager import generate_topology
from scripts_flow.compare_snn_vs_ospf import ECMPSimulator, OSPFSimulator, OSPFSyncSimulator, PPOSimulator, build_nodes
from scripts_flow.main_snn import build_flow_config, build_snn_runtime_config, choose_failure_edge
from scripts_flow.paper_stat_eval import bootstrap_ci, sign_flip_pvalue
from scripts_flow.snn_router import SNNRouter
from scripts_flow.snn_simulator import SNNSimulator
from scripts_flow.traffic import TrafficGenerator


def parse_float_list(spec):
    vals = []
    for part in [x.strip() for x in spec.split(",") if x.strip()]:
        vals.append(float(part))
    return vals


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
    elif profile == "very_frequent":
        fs = [
            int(fail_step - 45),
            int(fail_step - 25),
            int(fail_step - 5),
            int(fail_step + 15),
            int(fail_step + 35),
            int(fail_step + 55),
            int(fail_step + 75),
        ]
    else:
        raise ValueError(f"Unsupported failure profile: {profile}")
    fs = sorted({x for x in fs if 0 <= x < steps})
    return fs


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
    background_scale,
):
    random.seed(seed)
    np.random.seed(seed)

    graph0 = generate_topology(kind=topo, num_nodes=num_nodes, seed=seed, er_p=er_p, ba_m=ba_m)
    n_actual = int(graph0.number_of_nodes())
    flow_cfg = scale_flow_config(build_flow_config(num_nodes=n_actual, seed=seed), background_scale)
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
        last_fail = fail_steps[-1]
        post = df[(df.step >= last_fail + 20) & (df.step <= min(steps - 1, last_fail + 80))]
    else:
        post = df.tail(min(60, len(df)))
    if post.empty:
        post = df.tail(min(60, len(df)))

    return {
        "algo": algo,
        "topo": topo,
        "size": int(n_actual),
        "seed": int(seed),
        "failure_profile": failure_profile,
        "background_scale": float(background_scale),
        "er_p": float(er_p),
        "ba_m": int(ba_m),
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
    keys = ["topo", "size", "failure_profile", "background_scale", "er_p", "ba_m", "algo"]
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
    metric_cols = ["pdr_final", "delay_final", "hop_final", "loss_final", "pdr_post", "delay_post"]
    rows = []
    keys = ["topo", "size", "failure_profile", "background_scale", "er_p", "ba_m"]
    for key, group in runs_df.groupby(keys):
        snn = group[group.algo == "snn"]
        if snn.empty:
            continue
        for base_algo in ["ospf", "ospf_sync", "ecmp", "ppo"]:
            base = group[group.algo == base_algo]
            if base.empty:
                continue
            merged = snn.merge(
                base,
                on=["seed", "topo", "size", "failure_profile", "background_scale", "er_p", "ba_m"],
                suffixes=("_snn", "_base"),
            )
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
                        "background_scale": key[3],
                        "er_p": key[4],
                        "ba_m": key[5],
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


def build_boundary(sig_df):
    if sig_df.empty:
        return pd.DataFrame()

    sub = sig_df[sig_df.metric.isin(["pdr_final", "loss_final"])].copy()
    rows = []
    keys = ["topo", "size", "failure_profile", "background_scale", "er_p", "ba_m", "base_algo"]
    for key, g in sub.groupby(keys):
        pdr = g[g.metric == "pdr_final"]
        loss = g[g.metric == "loss_final"]
        if pdr.empty or loss.empty:
            continue
        pdr_diff = float(pdr.iloc[0].mean_diff_snn_minus_base)
        pdr_p = float(pdr.iloc[0].p_value_two_sided)
        loss_diff = float(loss.iloc[0].mean_diff_snn_minus_base)
        loss_p = float(loss.iloc[0].p_value_two_sided)

        pdr_adv = pdr_diff > 0 and pdr_p < 0.05
        loss_adv = loss_diff < 0 and loss_p < 0.05
        robust_advantage = bool(pdr_adv and loss_adv)

        if robust_advantage:
            status = "robust"
        elif (pdr_diff > 0 and loss_diff < 0):
            status = "weakened"
        else:
            status = "failed"

        rows.append(
            {
                "topo": key[0],
                "size": key[1],
                "failure_profile": key[2],
                "background_scale": key[3],
                "er_p": key[4],
                "ba_m": key[5],
                "base_algo": key[6],
                "pdr_final_diff": pdr_diff,
                "pdr_final_p": pdr_p,
                "loss_final_diff": loss_diff,
                "loss_final_p": loss_p,
                "status": status,
            }
        )

    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["scope"] = "group"

    rank = {"robust": 0, "weakened": 1, "failed": 2}
    out = []
    for (topo, size, base_algo), g in df.groupby(["topo", "size", "base_algo"]):
        worst = g.iloc[g.status.map(rank).argmax()]
        out.append(
            {
                "topo": topo,
                "size": int(size),
                "base_algo": base_algo,
                "worst_status": worst.status,
                "at_failure_profile": worst.failure_profile,
                "at_background_scale": float(worst.background_scale),
                "at_er_p": float(worst.er_p),
                "at_ba_m": int(worst.ba_m),
            }
        )
    boundary_df = pd.DataFrame(out)
    return pd.concat([df, boundary_df.assign(scope="worst_case")], ignore_index=True, sort=False)


def main():
    parser = argparse.ArgumentParser(description="Robustness grid evaluation for SNN vs baselines.")
    parser.add_argument("--algos", default="ospf,ecmp,ppo,snn")
    parser.add_argument("--topos", default="ba,er")
    parser.add_argument("--sizes", default="50,100")
    parser.add_argument("--seeds", default="1-20")
    parser.add_argument("--steps", type=int, default=240)
    parser.add_argument("--fail-step", type=int, default=150)
    parser.add_argument("--failure-profiles", default="single,frequent,very_frequent")
    parser.add_argument("--background-scales", default="1.0,1.5,2.0,2.5")
    parser.add_argument("--er-ps", default="0.05,0.06,0.07")
    parser.add_argument("--ba-ms", default="2,3,4")
    parser.add_argument("--workers", type=int, default=20)
    parser.add_argument("--out-prefix", default="run_dir/issue19_robustness")
    parser.add_argument("--random-seed", type=int, default=20260223)
    args = parser.parse_args()

    algos = [x.strip() for x in args.algos.split(",") if x.strip()]
    topos = [x.strip() for x in args.topos.split(",") if x.strip()]
    sizes = parse_int_ranges(args.sizes)
    seeds = parse_int_ranges(args.seeds)
    profiles = [x.strip() for x in args.failure_profiles.split(",") if x.strip()]
    scales = parse_float_list(args.background_scales)
    er_ps = parse_float_list(args.er_ps)
    ba_ms = parse_int_ranges(args.ba_ms)

    valid_algos = {"ospf", "ospf_sync", "ecmp", "ppo", "snn"}
    invalid = [a for a in algos if a not in valid_algos]
    if invalid:
        raise ValueError(f"Unsupported algos: {invalid}")

    valid_profiles = {"single", "frequent", "very_frequent"}
    inv_profile = [p for p in profiles if p not in valid_profiles]
    if inv_profile:
        raise ValueError(f"Unsupported failure profiles: {inv_profile}")

    tasks = []
    for topo in topos:
        for size in sizes:
            for profile in profiles:
                for scale in scales:
                    if topo == "er":
                        for er_p in er_ps:
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
                                            "er_p": float(er_p),
                                            "ba_m": 3,
                                            "background_scale": float(scale),
                                        }
                                    )
                    elif topo == "ba":
                        for ba_m in ba_ms:
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
                                            "er_p": 0.06,
                                            "ba_m": int(ba_m),
                                            "background_scale": float(scale),
                                        }
                                    )
                    else:
                        raise ValueError(f"Unsupported topo: {topo}")

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
    runs_df = runs_df.sort_values(
        ["topo", "size", "failure_profile", "background_scale", "er_p", "ba_m", "seed", "algo"]
    ).reset_index(drop=True)

    rng = np.random.default_rng(args.random_seed)
    summary_df = build_group_summary(runs_df, rng)
    sig_df = build_significance(runs_df, rng)
    boundary_df = build_boundary(sig_df)

    runs_path = f"{args.out_prefix}_runs.csv"
    summary_path = f"{args.out_prefix}_summary.csv"
    sig_path = f"{args.out_prefix}_significance.csv"
    boundary_path = f"{args.out_prefix}_boundary.csv"

    runs_df.to_csv(runs_path, index=False)
    summary_df.to_csv(summary_path, index=False)
    sig_df.to_csv(sig_path, index=False)
    boundary_df.to_csv(boundary_path, index=False)

    print("\n=== summary (head) ===")
    print(summary_df.head(20).to_string(index=False))
    print("\n=== significance (head) ===")
    print(sig_df.head(30).to_string(index=False))
    print("\n=== boundary (head) ===")
    print(boundary_df.head(30).to_string(index=False))
    print(f"\nSaved: {runs_path}")
    print(f"Saved: {summary_path}")
    print(f"Saved: {sig_path}")
    print(f"Saved: {boundary_path}")


if __name__ == "__main__":
    main()
