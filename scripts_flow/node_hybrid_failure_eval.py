import argparse
import copy
import random
import re
import sys
from collections import defaultdict
from pathlib import Path

import networkx as nx
import numpy as np
import pandas as pd

# Path patch for local package imports.
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


EDGE_MODES = {"random", "targeted", "hybrid_alternating", "hybrid_simultaneous", "hybrid_flap"}


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


def choose_failure_nodes(graph, k, mode, rng):
    nodes = list(graph.nodes())
    if k <= 0 or not nodes:
        return []
    if mode == "random":
        k = min(int(k), len(nodes))
        return [int(n) for n in rng.sample(nodes, k)]
    if mode == "targeted":
        bet = nx.betweenness_centrality(graph)
        return [int(n) for n, _ in sorted(bet.items(), key=lambda kv: kv[1], reverse=True)[: int(k)]]
    raise ValueError(f"Unsupported failure node mode: {mode}")


def parse_failure_steps(profile, fail_step, steps):
    if profile == "single":
        return [int(fail_step)]
    if profile == "frequent":
        values = [int(fail_step - 30), int(fail_step), int(fail_step + 30), int(fail_step + 60)]
    elif profile == "early":
        values = [int(max(5, fail_step - 60)), int(fail_step - 30)]
    elif profile == "late":
        values = [int(fail_step), int(min(steps - 1, fail_step + 30)), int(min(steps - 1, fail_step + 60))]
    else:
        raise ValueError(f"Unsupported failure profile: {profile}")
    return sorted({v for v in values if 0 <= v < steps})


def build_sim(algo, topo, graph, flow_cfg, snn_mode, beta_s=8.0):
    n = graph.number_of_nodes()
    if algo == "v1":
        cfg = build_snn_runtime_config(topo, snn_mode)
        cfg["sim"]["event_max_period"] = 9999
        router_kwargs = dict(cfg.get("router", {}))
        router_kwargs["beta_s"] = beta_s
        router = SNNRouter(**router_kwargs)
        sim_kwargs = dict(cfg.get("sim", {}))
        sim_kwargs["known_destinations"] = [f["dst"] for f in flow_cfg]
        return SNNSimulator(build_nodes(n, beta_s), graph, router, routing_mode=snn_mode, **sim_kwargs)
    if algo == "v2":
        cfg = build_snn_runtime_config(topo, snn_mode, formula_mode="v2")
        router_kwargs = dict(cfg.get("router", {}))
        router_kwargs["beta_s"] = beta_s
        router = SNNRouter(**router_kwargs)
        sim_kwargs = dict(cfg.get("sim", {}))
        sim_kwargs["known_destinations"] = [f["dst"] for f in flow_cfg]
        return SNNSimulator(build_nodes(n, beta_s), graph, router, routing_mode=snn_mode, **sim_kwargs)

    if algo == "ospf_sync":
        return OSPFSyncSimulator(build_nodes(n, 0.0), graph, hop_limit=64, sync_period=12, spf_delay=4)
    if algo == "ecmp":
        return ECMPSimulator(build_nodes(n, 0.0), graph, hop_limit=64)
    if algo == "ppo":
        return PPOSimulator(build_nodes(n, 0.0), graph, hop_limit=64, seed=7, train=True)
    raise ValueError(f"Unsupported algo: {algo}")


def edge_key(u, v):
    return (int(u), int(v)) if u < v else (int(v), int(u))


class FailureController:
    def __init__(self, graph, base_graph):
        self.graph = graph
        self.base_graph = base_graph
        self.edge_ref_counts = defaultdict(int)

    def remove_node(self, n):
        if n not in self.graph.nodes:
            return
        neighbors = list(self.graph.neighbors(n))
        for nb in neighbors:
            self.remove_edge(n, nb)

    def restore_node(self, n):
        if n not in self.graph.nodes:
            return
        for nb in self.base_graph.neighbors(n):
            self.add_edge(n, nb)

    def remove_edge(self, u, v):
        key = edge_key(u, v)
        self.edge_ref_counts[key] += 1
        if self.graph.has_edge(*key):
            self.graph.remove_edge(*key)

    def add_edge(self, u, v):
        key = edge_key(u, v)
        c = self.edge_ref_counts.get(key, 0)
        if c <= 0:
            if self.base_graph.has_edge(*key) and not self.graph.has_edge(*key):
                self.graph.add_edge(*key)
            self.edge_ref_counts.pop(key, None)
            return
        c -= 1
        if c > 0:
            self.edge_ref_counts[key] = c
        else:
            self.edge_ref_counts.pop(key, None)
            if self.base_graph.has_edge(*key) and not self.graph.has_edge(*key):
                self.graph.add_edge(*key)



def build_failure_events(mode, k, graph0, base_graph, fail_steps, rng, flap_duration=20):
    if mode.startswith("hybrid_"):
        if rng is None:
            rng = random.Random()
        node_mode = rng.choice(["random", "targeted"])
    else:
        node_mode = mode
    nodes = choose_failure_nodes(graph0, k=k, mode=node_mode, rng=rng)
    edges = choose_failure_edges_multi(graph0, k)

    events = []
    if mode in {"random", "targeted"}:
        for t in fail_steps:
            events.append((t, "remove_node_batch", nodes))
        return nodes, edges, events

    # hybrid modes
    for i, t in enumerate(fail_steps):
        if mode == "hybrid_alternating":
            if i % 2 == 0:
                events.append((t, "remove_node_batch", nodes))
            else:
                events.append((t, "remove_edge_batch", edges))
            continue

        if mode == "hybrid_simultaneous":
            events.append((t, "remove_node_batch", nodes))
            events.append((t, "remove_edge_batch", edges))
            continue

        if mode == "hybrid_flap":
            events.append((t, "remove_node_batch", nodes))
            events.append((t, "remove_edge_batch", edges))
            events.append((t + int(flap_duration), "restore_node_batch", nodes))
            events.append((t + int(flap_duration), "restore_edge_batch", edges))
            continue

        raise ValueError(f"Unsupported hybrid mode: {mode}")

    return nodes, edges, sorted(events, key=lambda x: x[0])


def _series_recovery_metrics(df, fail_steps, pre_window=20):
    if fail_steps:
        first_fail = int(min(fail_steps))
    else:
        first_fail = int(min(df["step"])) if not df.empty else 0

    pre = df[df["step"] < first_fail]
    if pre.empty:
        baseline = float("nan")
    else:
        baseline = float(pre.pdr.tail(pre_window).mean())

    after = df[df["step"] >= first_fail]
    if after.empty or not np.isfinite(baseline):
        return baseline, float("nan"), float("nan"), float("nan")

    pdr_arr = after["pdr"].to_numpy(dtype=float)
    idx_arr = np.arange(len(pdr_arr), dtype=int)
    min_after = float(np.nanmin(pdr_arr))
    max_drop = 100.0 * (baseline - min_after) / baseline

    ratio = pdr_arr / baseline
    t50 = float("nan")
    t90 = float("nan")
    for i, r in zip(idx_arr, ratio):
        if not np.isfinite(r):
            continue
        if np.isnan(t50) and r >= 0.5:
            t50 = float(i)
        if np.isnan(t90) and r >= 0.9:
            t90 = float(i)

    clipped = np.clip(ratio, 0.0, 1.0)
    auc = float(np.trapz(clipped, x=np.arange(clipped.size)) / max(1, clipped.size))
    return baseline, max_drop, t50, t90, auc


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
    failure_mode,
    k,
    flap_duration=20,
    pre_window=20,
):
    random.seed(seed)
    rng = random.Random(seed)
    np.random.seed(seed)

    graph0 = generate_topology(kind=topo, num_nodes=num_nodes, seed=seed, er_p=er_p, ba_m=ba_m)
    flow_cfg = build_flow_config(num_nodes=num_nodes, seed=seed)
    traffic = TrafficGenerator(flow_cfg)
    graph = copy.deepcopy(graph0)
    sim = make_sim(algo, topo, graph, flow_cfg, snn_mode)

    fail_steps = parse_failure_steps(failure_profile, fail_step, steps)
    nodes, edges, events = build_failure_events(
        failure_mode,
        k=k,
        graph0=graph0,
        base_graph=copy.deepcopy(graph0),
        fail_steps=fail_steps,
        rng=rng,
        flap_duration=flap_duration,
    )

    controller = FailureController(graph, graph0)
    by_step = {}
    for t, op, payload in events:
        by_step.setdefault(int(t), []).append((op, payload))

    history = []
    for t in range(steps):
        if t in by_step:
            for op, payload in by_step[t]:
                if op == "remove_node_batch":
                    for n in payload:
                        controller.remove_node(int(n))
                elif op == "restore_node_batch":
                    for n in payload:
                        controller.restore_node(int(n))
                elif op == "remove_edge_batch":
                    for u, v in payload:
                        controller.remove_edge(int(u), int(v))
                elif op == "restore_edge_batch":
                    for u, v in payload:
                        controller.add_edge(int(u), int(v))

        metrics = sim.run_step(t, traffic.generate(t))
        metrics["step"] = int(t)
        history.append(metrics)

    df = pd.DataFrame(history)
    final = df.iloc[-1]

    if not fail_steps:
        fail_steps = [max(1, fail_step)]
    last_fail = int(fail_steps[-1])

    p_after = df[df["step"] >= last_fail + 20]
    if p_after.empty:
        p_after = df.tail(min(60, len(df)))

    baseline, max_drop, t50, t90, auc = _series_recovery_metrics(
        df,
        fail_steps=fail_steps,
        pre_window=pre_window,
    )

    failure_pattern = "node" if failure_mode in {"random", "targeted"} else "hybrid"
    return {
        "issue": 15,
        "algo": algo,
        "topo": topo,
        "size": int(num_nodes),
        "seed": int(seed),
        "failure_mode": failure_mode,
        "failure_pattern": failure_pattern,
        "failure_profile": failure_profile,
        "k": int(k),
        "pdr_final": float(final.pdr),
        "loss_final": float(final.loss),
        "delay_final": float(final.avg_delay),
        "hop_final": float(final.avg_hop),
        "pdr_post": float(p_after.pdr.mean()),
        "delay_post": float(p_after.avg_delay.mean()),
        "baseline_pdr": float(baseline),
        "max_drop_pct": float(max_drop),
        "t50_steps": float(t50),
        "t90_steps": float(t90),
        "auc_recovery": float(auc),
        "flap_duration": float(flap_duration),
        "fail_step_last": int(last_fail),
    }


def make_sim(algo, topo, graph, flow_cfg, snn_mode):
    if algo == "snn":
        return build_sim("v2", topo, graph, flow_cfg, snn_mode)
    return build_sim(algo, topo, graph, flow_cfg, snn_mode)


def build_group_summary(runs_df):
    keys = ["topo", "size", "failure_pattern", "failure_mode", "failure_profile", "k", "algo"]
    metric_cols = [
        "pdr_final",
        "loss_final",
        "delay_final",
        "hop_final",
        "pdr_post",
        "delay_post",
        "max_drop_pct",
        "t50_steps",
        "t90_steps",
        "auc_recovery",
    ]
    rows = []
    for key, g in runs_df.groupby(keys):
        row = {keys[i]: key[i] for i in range(len(keys))}
        row["n"] = int(len(g))
        for m in metric_cols:
            vals = g[m].to_numpy(dtype=float)
            vals = vals[np.isfinite(vals)]
            row[f"{m}_mean"] = float(np.mean(vals)) if vals.size else float("nan")
            row[f"{m}_std"] = float(np.std(vals, ddof=1)) if vals.size > 1 else float("nan")
            lo, hi = bootstrap_ci(vals, rng=np.random.default_rng(20260224), n_boot=1000, alpha=0.05)
            row[f"{m}_ci95_lo"] = lo
            row[f"{m}_ci95_hi"] = hi
        rows.append(row)
    return pd.DataFrame(rows)


def build_significance(runs_df, base_algo="v1", rng=None):
    if rng is None:
        rng = np.random.default_rng(20260224)
    metric_cols = [
        "pdr_final",
        "loss_final",
        "delay_final",
        "max_drop_pct",
        "t50_steps",
        "t90_steps",
        "auc_recovery",
    ]
    rows = []
    keys = ["topo", "size", "failure_pattern", "failure_mode", "failure_profile", "k"]
    for key, g in runs_df.groupby(keys):
        base = g[g.algo == base_algo]
        if base.empty:
            continue
        var = g[g.algo != base_algo]
        for target in sorted(var.algo.unique()):
            if target == base_algo:
                continue
            tdf = var[var.algo == target]
            merged = tdf.merge(base, on=["seed", "topo", "size", "failure_pattern", "failure_mode", "failure_profile", "k"], suffixes=("_target", "_base"))
            if merged.empty:
                continue
            for m in metric_cols:
                d = (merged[f"{m}_target"] - merged[f"{m}_base"]).to_numpy(dtype=float)
                d = d[np.isfinite(d)]
                if d.size == 0:
                    continue
                lo, hi = bootstrap_ci(d, rng=rng, n_boot=2000, alpha=0.05)
                p = sign_flip_pvalue(d, rng=rng, n_perm=3000)
                rows.append(
                    {
                        "topo": key[0],
                        "size": key[1],
                        "failure_pattern": key[2],
                        "failure_mode": key[3],
                        "failure_profile": key[4],
                        "k": key[5],
                        "base_algo": base_algo,
                        "target_algo": target,
                        "metric": m,
                        "n_pairs": int(len(d)),
                        "mean_diff_target_minus_base": float(np.mean(d)),
                        "ci95_lo": lo,
                        "ci95_hi": hi,
                        "p_value_two_sided": p,
                    }
                )
    return pd.DataFrame(rows)


def main():
    parser = argparse.ArgumentParser(description="Node failure and node+link hybrid robustness evaluation.")
    parser.add_argument("--algos", default="v1,v2,ospf_sync,ecmp,ppo")
    parser.add_argument("--topos", default="ba,er")
    parser.add_argument("--sizes", default="50,100")
    parser.add_argument("--seeds", default="1-10")
    parser.add_argument("--node-k-values", default="1-3")
    parser.add_argument("--hybrid-k-values", default="1-2")
    parser.add_argument("--steps", type=int, default=240)
    parser.add_argument("--fail-step", type=int, default=150)
    parser.add_argument("--failure-profiles", default="single")
    parser.add_argument("--er-p", type=float, default=0.06)
    parser.add_argument("--ba-m", type=int, default=3)
    parser.add_argument("--snn-mode", default="snn_event_dv")
    parser.add_argument("--flap-duration", type=int, default=20)
    parser.add_argument("--out-prefix", default="run_dir/issue15_node_hybrid")
    parser.add_argument("--random-seed", type=int, default=20260224)
    args = parser.parse_args()

    rng = np.random.default_rng(args.random_seed)
    algos = [x.strip() for x in args.algos.split(",") if x.strip()]
    topos = [x.strip() for x in args.topos.split(",") if x.strip()]
    sizes = parse_int_ranges(args.sizes)
    seeds = parse_int_ranges(args.seeds)
    node_k_values = parse_int_ranges(args.node_k_values)
    hybrid_k_values = parse_int_ranges(args.hybrid_k_values)
    failure_profiles = [x.strip() for x in args.failure_profiles.split(",") if x.strip()]

    valid = {"v1", "v2", "ospf_sync", "ecmp", "ppo", "snn"}
    invalid = [a for a in algos if a not in valid]
    if invalid:
        raise ValueError(f"Unsupported algos: {invalid}")

    rows = []
    for topo in topos:
        for size in sizes:
            for seed in seeds:
                for profile in failure_profiles:
                    for k in node_k_values:
                        for mode in ["random", "targeted"]:
                            for algo in algos:
                                if algo == "snn":
                                    algo = "v2"
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
                                        failure_mode=mode,
                                        k=k,
                                        flap_duration=args.flap_duration,
                                    )
                                )
                    for k in hybrid_k_values:
                        for mode in ["hybrid_alternating", "hybrid_simultaneous", "hybrid_flap"]:
                            for algo in algos:
                                if algo == "snn":
                                    algo = "v2"
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
                                        failure_mode=mode,
                                        k=k,
                                        flap_duration=args.flap_duration,
                                    )
                                )

    runs_df = pd.DataFrame(rows)
    node_runs = runs_df[runs_df["failure_pattern"] == "node"].copy()
    hybrid_runs = runs_df[runs_df["failure_pattern"] == "hybrid"].copy()

    summary_df = build_group_summary(runs_df)
    sig_df = build_significance(runs_df, rng=rng)

    runs_prefix = Path(f"{args.out_prefix}")
    runs_prefix.parent.mkdir(parents=True, exist_ok=True)
    node_path = f"{args.out_prefix}_node_failure_runs.csv"
    hybrid_path = f"{args.out_prefix}_hybrid_failure_runs.csv"
    summary_path = f"{args.out_prefix}_summary.csv"
    sig_path = f"{args.out_prefix}_significance.csv"

    node_runs.to_csv(node_path, index=False)
    hybrid_runs.to_csv(hybrid_path, index=False)
    summary_df.to_csv(summary_path, index=False)
    sig_df.to_csv(sig_path, index=False)

    print(f"Saved: {node_path}")
    print(f"Saved: {hybrid_path}")
    print(f"Saved: {summary_path}")
    print(f"Saved: {sig_path}")


if __name__ == "__main__":
    main()
