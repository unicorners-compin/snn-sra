import argparse
import copy
import random
import sys
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed

import networkx as nx
import numpy as np
import pandas as pd

root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from scripts.topo_manager import generate_topology
from scripts_flow.compare_snn_vs_ospf import ECMPSimulator, OSPFSyncSimulator, PPOSimulator, build_nodes
from scripts_flow.main_snn import build_flow_config, build_snn_runtime_config
from scripts_flow.paper_stat_eval import bootstrap_ci, parse_int_ranges, sign_flip_pvalue
from scripts_flow.snn_node import SNNQueueNode
from scripts_flow.snn_router import SNNRouter
from scripts_flow.snn_simulator import SNNSimulator
from scripts_flow.traffic import TrafficGenerator


def choose_attack_set(graph, mode, k, rng):
    if k <= 0:
        return {"edges": [], "nodes": []}
    if mode == "random_edge":
        edges = list(graph.edges())
        if not edges:
            return {"edges": [], "nodes": []}
        picked = rng.sample(edges, min(k, len(edges)))
        return {"edges": [(int(u), int(v)) for u, v in picked], "nodes": []}
    if mode == "target_edge":
        ebc = nx.edge_betweenness_centrality(graph)
        picked = [e for e, _ in sorted(ebc.items(), key=lambda kv: kv[1], reverse=True)[:k]]
        return {"edges": [(int(u), int(v)) for u, v in picked], "nodes": []}
    if mode == "target_node":
        nbc = nx.betweenness_centrality(graph)
        picked = [n for n, _ in sorted(nbc.items(), key=lambda kv: kv[1], reverse=True)[:k]]
        return {"edges": [], "nodes": [int(n) for n in picked]}
    raise ValueError(f"Unsupported attack mode: {mode}")


def inject_failures(graph, attack):
    # Node failure is modeled as cutting all incident edges (node isolate), avoiding simulator state mismatch.
    for u, v in attack.get("edges", []):
        if graph.has_edge(u, v):
            graph.remove_edge(u, v)
    for n in attack.get("nodes", []):
        if graph.has_node(n):
            for v in list(graph.neighbors(n)):
                if graph.has_edge(n, v):
                    graph.remove_edge(n, v)


def build_snn_sim(graph, flow_cfg, topo, formula_mode, snn_mode, beta_s):
    n = graph.number_of_nodes()
    cfg = build_snn_runtime_config(topo, snn_mode, formula_mode=formula_mode)
    router_kwargs = dict(cfg.get("router", {}))
    router_kwargs["beta_s"] = beta_s
    router = SNNRouter(**router_kwargs)
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
        for i in range(n)
    }
    sim_kwargs = dict(cfg.get("sim", {}))
    sim_kwargs["known_destinations"] = [f["dst"] for f in flow_cfg]
    return SNNSimulator(nodes, graph, router, routing_mode=snn_mode, **sim_kwargs)


def build_sim(algo, graph, flow_cfg, topo, snn_mode, beta_s, seed):
    n = graph.number_of_nodes()
    if algo == "v1":
        return build_snn_sim(graph, flow_cfg, topo, "v1", snn_mode, beta_s)
    if algo == "v2":
        return build_snn_sim(graph, flow_cfg, topo, "v2", snn_mode, beta_s)
    if algo == "ospf_sync":
        return OSPFSyncSimulator(build_nodes(n, 0.0), graph, hop_limit=64, sync_period=12, spf_delay=4)
    if algo == "ecmp":
        return ECMPSimulator(build_nodes(n, 0.0), graph, hop_limit=64)
    if algo == "ppo":
        return PPOSimulator(build_nodes(n, 0.0), graph, hop_limit=64, seed=seed, train=True)
    raise ValueError(f"Unsupported algo: {algo}")


def run_case(algo, topo, size, seed, steps, fail_step, attack_mode, k, er_p, ba_m, snn_mode, beta_s):
    random.seed(seed)
    np.random.seed(seed)
    rng = random.Random(seed * 1009 + size * 97 + k * 31)

    graph0 = generate_topology(kind=topo, num_nodes=size, seed=seed, er_p=er_p, ba_m=ba_m)
    n_actual = graph0.number_of_nodes()
    flow_cfg = build_flow_config(num_nodes=n_actual, seed=seed)
    attack = choose_attack_set(graph0, attack_mode, k, rng)

    graph = copy.deepcopy(graph0)
    sim = build_sim(algo, graph, flow_cfg, topo, snn_mode, beta_s, seed)
    traffic = TrafficGenerator(flow_cfg)

    rows = []
    injected = False
    for t in range(steps):
        if (not injected) and t == fail_step:
            inject_failures(graph, attack)
            injected = True
        m = sim.run_step(t, traffic.generate(t))
        m["step"] = t
        rows.append(m)

    df = pd.DataFrame(rows)
    final = df.iloc[-1]
    post = df[(df.step >= fail_step + 20) & (df.step <= min(steps - 1, fail_step + 80))]
    if post.empty:
        post = df.tail(min(60, len(df)))

    return {
        "algo": algo,
        "topo": topo,
        "size": int(n_actual),
        "seed": int(seed),
        "attack_mode": attack_mode,
        "k": int(k),
        "pdr_final": float(final.pdr),
        "delay_final": float(final.avg_delay),
        "hop_final": float(final.avg_hop),
        "loss_final": float(final.loss),
        "pdr_post": float(post.pdr.mean()),
        "delay_post": float(post.avg_delay.mean()),
    }


def build_summary(df, rng):
    metrics = ["pdr_final", "delay_final", "hop_final", "loss_final", "pdr_post", "delay_post"]
    rows = []
    keys = ["topo", "size", "attack_mode", "k", "algo"]
    for key, g in df.groupby(keys):
        row = {keys[i]: key[i] for i in range(len(keys))}
        row["n"] = int(len(g))
        for m in metrics:
            arr = g[m].to_numpy(dtype=float)
            row[f"{m}_mean"] = float(np.mean(arr))
            row[f"{m}_std"] = float(np.std(arr, ddof=1)) if len(arr) > 1 else 0.0
            lo, hi = bootstrap_ci(arr, rng=rng, n_boot=1000, alpha=0.05)
            row[f"{m}_ci95_lo"] = lo
            row[f"{m}_ci95_hi"] = hi
        rows.append(row)
    return pd.DataFrame(rows)


def build_significance(df, rng):
    metrics = ["pdr_final", "delay_final", "hop_final", "loss_final", "pdr_post", "delay_post"]
    rows = []
    keys = ["topo", "size", "attack_mode", "k"]
    for key, g in df.groupby(keys):
        v2 = g[g.algo == "v2"]
        if v2.empty:
            continue
        for base in ["v1", "ospf_sync", "ecmp", "ppo"]:
            b = g[g.algo == base]
            if b.empty:
                continue
            merged = v2.merge(b, on=["seed", "topo", "size", "attack_mode", "k"], suffixes=("_v2", "_base"))
            if merged.empty:
                continue
            for m in metrics:
                diffs = (merged[f"{m}_v2"] - merged[f"{m}_base"]).to_numpy(dtype=float)
                lo, hi = bootstrap_ci(diffs, rng=rng, n_boot=2000, alpha=0.05)
                p = sign_flip_pvalue(diffs, rng=rng, n_perm=10000)
                rows.append(
                    {
                        "topo": key[0],
                        "size": key[1],
                        "attack_mode": key[2],
                        "k": key[3],
                        "base_algo": base,
                        "metric": m,
                        "n_pairs": int(len(diffs)),
                        "mean_diff_v2_minus_base": float(np.mean(diffs)),
                        "ci95_lo": lo,
                        "ci95_hi": hi,
                        "p_value_two_sided": p,
                    }
                )
    return pd.DataFrame(rows)


def build_boundary(sig_df):
    rows = []
    if sig_df.empty:
        return pd.DataFrame(rows)
    keys = ["topo", "size", "attack_mode", "base_algo"]
    for key, g in sig_df[sig_df.metric == "pdr_final"].groupby(keys):
        robust = int(((g.mean_diff_v2_minus_base > 0) & (g.p_value_two_sided < 0.05)).sum())
        total = int(len(g))
        frac = robust / max(total, 1)
        if frac >= 0.70:
            status = "robust"
        elif frac >= 0.40:
            status = "weakened"
        else:
            status = "failed"
        rows.append(
            {
                "topo": key[0],
                "size": key[1],
                "attack_mode": key[2],
                "base_algo": key[3],
                "robust_k_points": robust,
                "total_k_points": total,
                "robust_ratio": frac,
                "status": status,
            }
        )
    return pd.DataFrame(rows)


def main():
    parser = argparse.ArgumentParser(description="Targeted attack and k-failure resilience boundary evaluation.")
    parser.add_argument("--algos", default="v1,v2,ospf_sync,ecmp,ppo")
    parser.add_argument("--topos", default="ba,er")
    parser.add_argument("--sizes", default="50,100")
    parser.add_argument("--seeds", default="1-10")
    parser.add_argument("--attack-modes", default="random_edge,target_edge,target_node")
    parser.add_argument("--k-values", default="1-4")
    parser.add_argument("--steps", type=int, default=160)
    parser.add_argument("--fail-step", type=int, default=80)
    parser.add_argument("--er-p", type=float, default=0.06)
    parser.add_argument("--ba-m", type=int, default=3)
    parser.add_argument("--snn-mode", default="snn_event_dv")
    parser.add_argument("--beta-s", type=float, default=8.0)
    parser.add_argument("--out-prefix", default="run_dir/issue13_boundary")
    parser.add_argument("--random-seed", type=int, default=20260224)
    parser.add_argument("--workers", type=int, default=20)
    args = parser.parse_args()

    rng = np.random.default_rng(args.random_seed)
    algos = [x.strip() for x in args.algos.split(",") if x.strip()]
    topos = [x.strip() for x in args.topos.split(",") if x.strip()]
    sizes = parse_int_ranges(args.sizes)
    seeds = parse_int_ranges(args.seeds)
    attack_modes = [x.strip() for x in args.attack_modes.split(",") if x.strip()]
    k_values = parse_int_ranges(args.k_values)

    tasks = []
    for topo in topos:
        for size in sizes:
            for seed in seeds:
                for attack_mode in attack_modes:
                    for k in k_values:
                        for algo in algos:
                            tasks.append(
                                {
                                    "algo": algo,
                                    "topo": topo,
                                    "size": size,
                                    "seed": seed,
                                    "steps": args.steps,
                                    "fail_step": args.fail_step,
                                    "attack_mode": attack_mode,
                                    "k": k,
                                    "er_p": args.er_p,
                                    "ba_m": args.ba_m,
                                    "snn_mode": args.snn_mode,
                                    "beta_s": args.beta_s,
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
            if done % 50 == 0 or done == total:
                print(f"[{done:04d}/{total:04d}] done", flush=True)

    runs_df = pd.DataFrame(rows)
    summary_df = build_summary(runs_df, rng)
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

    print("\n=== boundary (head) ===")
    print(boundary_df.head(30).to_string(index=False))
    print(f"\nSaved: {runs_path}")
    print(f"Saved: {summary_path}")
    print(f"Saved: {sig_path}")
    print(f"Saved: {boundary_path}")


if __name__ == "__main__":
    main()
