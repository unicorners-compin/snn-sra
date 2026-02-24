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
from scripts_flow.main_snn import build_flow_config, build_snn_runtime_config
from scripts_flow.paper_stat_eval import bootstrap_ci, parse_int_ranges, sign_flip_pvalue
from scripts_flow.snn_node import SNNQueueNode
from scripts_flow.snn_router import SNNRouter
from scripts_flow.snn_simulator import SNNSimulator
from scripts_flow.traffic import TrafficGenerator


BASELINE_PARAMS = {
    "stress_smooth_gain": 7.0,
    "stress_smooth_center": 0.45,
    "softmin_temperature": 0.08,
    "switch_hysteresis": 0.25,
    "route_ttl": 40,
}

PARAM_KEYS = [
    "stress_smooth_gain",
    "stress_smooth_center",
    "softmin_temperature",
    "switch_hysteresis",
    "route_ttl",
]


def parse_float_list(spec):
    vals = []
    for part in [x.strip() for x in spec.split(",") if x.strip()]:
        vals.append(float(part))
    if not vals:
        raise ValueError("empty float list")
    return vals


def choose_failure_edges_multi(graph, k):
    if k <= 0:
        return []
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


def choose_failure_edges(graph, fail_steps):
    if len(fail_steps) <= 1:
        return choose_failure_edges_multi(graph, 1)[:1]
    return choose_failure_edges_multi(graph, len(fail_steps))


def parse_failure_steps(profile, fail_step, steps):
    if profile == "single":
        fs = [int(fail_step)]
    elif profile == "frequent":
        fs = [int(fail_step - 30), int(fail_step), int(fail_step + 30), int(fail_step + 60)]
    else:
        raise ValueError(f"unsupported failure profile: {profile}")
    return sorted({x for x in fs if 0 <= x < steps})


def build_snn_case(
    topo,
    graph,
    flow_cfg,
    snn_mode,
    stress_smooth_gain,
    stress_smooth_center,
    softmin_temperature,
    switch_hysteresis,
    route_ttl,
):
    n = graph.number_of_nodes()
    cfg = build_snn_runtime_config(topo, snn_mode, formula_mode="v2")

    router_kwargs = dict(cfg.get("router", {}))
    router_kwargs["beta_s"] = 8.0
    router_kwargs["softmin_temperature"] = float(softmin_temperature)
    router = SNNRouter(**router_kwargs)

    sim_kwargs = dict(cfg.get("sim", {}))
    sim_kwargs["known_destinations"] = [f["dst"] for f in flow_cfg]
    sim_kwargs["switch_hysteresis"] = float(switch_hysteresis)
    sim_kwargs["route_ttl"] = int(route_ttl)

    nodes = {
        i: SNNQueueNode(
            node_id=i,
            service_rate=22,
            buffer_size=180,
            alpha=0.22,
            beta_I=8.0,
            T_d=1,
            tau_m=4.0,
            v_th=1.0,
            stress_mode="v2_sigmoid",
            stress_smooth_gain=float(stress_smooth_gain),
            stress_smooth_center=float(stress_smooth_center),
        )
        for i in range(n)
    }

    return SNNSimulator(
        nodes,
        graph,
        router,
        routing_mode=snn_mode,
        **sim_kwargs,
    )


def run_case(
    topo,
    seed,
    num_nodes,
    steps,
    fail_step,
    failure_profile,
    er_p,
    ba_m,
    snn_mode,
    stress_smooth_gain,
    stress_smooth_center,
    softmin_temperature,
    switch_hysteresis,
    route_ttl,
):
    random.seed(seed)
    np.random.seed(seed)

    graph0 = generate_topology(kind=topo, num_nodes=num_nodes, seed=seed, er_p=er_p, ba_m=ba_m)
    flow_cfg = build_flow_config(num_nodes=graph0.number_of_nodes(), seed=seed)
    traffic = TrafficGenerator(flow_cfg)

    fail_steps = parse_failure_steps(failure_profile, fail_step, steps)
    fail_edges = choose_failure_edges(graph0, fail_steps)

    graph = copy.deepcopy(graph0)
    sim = build_snn_case(
        topo=topo,
        graph=graph,
        flow_cfg=flow_cfg,
        snn_mode=snn_mode,
        stress_smooth_gain=stress_smooth_gain,
        stress_smooth_center=stress_smooth_center,
        softmin_temperature=softmin_temperature,
        switch_hysteresis=switch_hysteresis,
        route_ttl=route_ttl,
    )

    history = []
    fi = 0
    for t in range(steps):
        while fi < len(fail_steps) and t == fail_steps[fi]:
            if fi < len(fail_edges):
                e = fail_edges[fi]
                if e is not None and graph.has_edge(*e):
                    graph.remove_edge(*e)
            fi += 1

        metrics = sim.run_step(t, traffic.generate(t))
        metrics["step"] = int(t)
        history.append(metrics)

    if hasattr(sim, "finalize"):
        sim.finalize()

    df = pd.DataFrame(history)
    final = df.iloc[-1]
    if fail_steps:
        last_fail = int(fail_steps[-1])
        post = df[(df.step >= last_fail + 20) & (df.step <= min(steps - 1, last_fail + 80))]
    else:
        post = df.tail(min(60, len(df)))

    if post.empty:
        post = df.tail(min(60, len(df)))

    return {
        "topo": topo,
        "size": int(graph0.number_of_nodes()),
        "seed": int(seed),
        "failure_profile": failure_profile,
        "stress_smooth_gain": float(stress_smooth_gain),
        "stress_smooth_center": float(stress_smooth_center),
        "softmin_temperature": float(softmin_temperature),
        "switch_hysteresis": float(switch_hysteresis),
        "route_ttl": int(route_ttl),
        "pdr_final": float(final.pdr),
        "loss_final": float(final.loss),
        "delay_final": float(final.avg_delay),
        "hop_final": float(final.avg_hop),
        "pdr_post": float(post.pdr.mean()),
        "delay_post": float(post.avg_delay.mean()),
        "route_changes_final": float(final.route_changes),
        "table_updates_final": float(final.table_updates),
    }


def _case_value_token(value):
    if isinstance(value, float):
        if value.is_integer():
            return f"{int(value)}"
        return f"{value:.6g}"
    return f"{int(value)}"


def _to_case_id(prefix, value):
    return f"{prefix}_{_case_value_token(value)}"


def build_plan(base_values, pairwise_pairs):
    base = {k: base_values[k] for k in PARAM_KEYS}
    entries = []

    entries.append(
        {
            **base,
            "case_id": "baseline",
            "variant_type": "baseline",
            "param_name": None,
            "param_name_b": None,
        }
    )

    for key in PARAM_KEYS:
        for val in base_values["perturbations"][key]:
            entries.append(
                {
                    **base,
                    "case_id": _to_case_id(key, val),
                    "variant_type": f"single:{key}",
                    "param_name": key,
                    "param_name_b": None,
                    key: val,
                }
            )

    for k1, k2 in pairwise_pairs:
        for v1 in base_values["perturbations"][k1]:
            for v2 in base_values["perturbations"][k2]:
                entries.append(
                    {
                        **base,
                        "case_id": f"pair_{k1}_{_case_value_token(v1)}_{k2}_{_case_value_token(v2)}",
                        "variant_type": f"pair:{k1}+{k2}",
                        "param_name": k1,
                        "param_name_b": k2,
                        k1: v1,
                        k2: v2,
                    }
                )

    deduped = []
    seen = set()
    for e in entries:
        key = (
            e["variant_type"],
            e.get("param_name"),
            e.get("param_name_b"),
            round(float(e["stress_smooth_gain"]), 6),
            round(float(e["stress_smooth_center"]), 6),
            round(float(e["softmin_temperature"]), 6),
            round(float(e["switch_hysteresis"]), 6),
            int(e["route_ttl"]),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(e)
    return deduped


def build_group_summary(runs_df):
    metric_cols = [
        "pdr_final",
        "loss_final",
        "delay_final",
        "hop_final",
        "pdr_post",
        "delay_post",
        "route_changes_final",
        "table_updates_final",
    ]
    keys = [
        "topo",
        "size",
        "failure_profile",
        "variant_type",
        "param_name",
        "param_name_b",
        "stress_smooth_gain",
        "stress_smooth_center",
        "softmin_temperature",
        "switch_hysteresis",
        "route_ttl",
    ]

    rows = []
    rng = np.random.default_rng(20260224)
    for key, g in runs_df.groupby(keys):
        row = {keys[i]: key[i] for i in range(len(keys))}
        row["n"] = int(len(g))
        for m in metric_cols:
            arr = g[m].to_numpy(dtype=float)
            arr = arr[np.isfinite(arr)]
            row[f"{m}_mean"] = float(np.mean(arr)) if arr.size else float("nan")
            row[f"{m}_std"] = float(np.std(arr, ddof=1)) if arr.size > 1 else float("nan")
            lo, hi = bootstrap_ci(arr, rng=rng, n_boot=1000, alpha=0.05)
            row[f"{m}_ci95_lo"] = lo
            row[f"{m}_ci95_hi"] = hi
        rows.append(row)

    return pd.DataFrame(rows).sort_values(keys).reset_index(drop=True)


def build_significance(runs_df):
    metric_cols = [
        "pdr_final",
        "loss_final",
        "delay_final",
        "hop_final",
        "pdr_post",
        "delay_post",
        "route_changes_final",
        "table_updates_final",
    ]

    base = runs_df[runs_df.variant_type == "baseline"]
    target = runs_df[runs_df.variant_type != "baseline"]
    if base.empty or target.empty:
        return pd.DataFrame(
            columns=[
                "topo",
                "size",
                "failure_profile",
                "variant_type",
                "param_name",
                "param_name_b",
                "stress_smooth_gain",
                "stress_smooth_center",
                "softmin_temperature",
                "switch_hysteresis",
                "route_ttl",
                "metric",
                "n_pairs",
                "mean_diff_target_minus_base",
                "ci95_lo",
                "ci95_hi",
                "p_value_two_sided",
            ]
        )

    merged = target.merge(
        base,
        on=["seed", "topo", "size", "failure_profile"],
        suffixes=("_target", "_base"),
    )
    if merged.empty:
        return pd.DataFrame(
            columns=[
                "topo",
                "size",
                "failure_profile",
                "variant_type",
                "param_name",
                "param_name_b",
                "stress_smooth_gain",
                "stress_smooth_center",
                "softmin_temperature",
                "switch_hysteresis",
                "route_ttl",
                "metric",
                "n_pairs",
                "mean_diff_target_minus_base",
                "ci95_lo",
                "ci95_hi",
                "p_value_two_sided",
            ]
        )

    rows = []
    for key, g in merged.groupby(
        [
            "topo",
            "size",
            "failure_profile",
            "variant_type_target",
            "param_name_target",
            "param_name_b_target",
            "stress_smooth_gain_target",
            "stress_smooth_center_target",
            "softmin_temperature_target",
            "switch_hysteresis_target",
            "route_ttl_target",
        ]
    ):
        for m in metric_cols:
            diffs = (g[f"{m}_target"].to_numpy(dtype=float) - g[f"{m}_base"].to_numpy(dtype=float))
            diffs = diffs[np.isfinite(diffs)]
            if diffs.size == 0:
                continue
            lo, hi = bootstrap_ci(diffs, rng=np.random.default_rng(20260224), n_boot=2000, alpha=0.05)
            p = sign_flip_pvalue(diffs, rng=np.random.default_rng(20260224), n_perm=4000)
            rows.append(
                {
                    "topo": key[0],
                    "size": int(key[1]),
                    "failure_profile": key[2],
                    "variant_type": key[3],
                    "param_name": key[4],
                    "param_name_b": key[5],
                    "stress_smooth_gain": float(key[6]),
                    "stress_smooth_center": float(key[7]),
                    "softmin_temperature": float(key[8]),
                    "switch_hysteresis": float(key[9]),
                    "route_ttl": int(key[10]),
                    "metric": m,
                    "n_pairs": int(diffs.size),
                    "mean_diff_target_minus_base": float(np.mean(diffs)),
                    "ci95_lo": lo,
                    "ci95_hi": hi,
                    "p_value_two_sided": p,
                }
            )

    return pd.DataFrame(rows)


def build_stable_region(runs_df, pdr_tol=0.02, loss_tol_ratio=0.05, change_tol_ratio=0.30, table_tol_ratio=0.30):
    metric_keys = ["topo", "size", "failure_profile", "variant_type_target", "param_name_target", "param_name_b_target"]
    base = runs_df[runs_df.variant_type == "baseline"]
    target = runs_df[runs_df.variant_type != "baseline"]
    if base.empty or target.empty:
        return pd.DataFrame(
            columns=[
                "topo",
                "size",
                "failure_profile",
                "variant_type",
                "param_name",
                "param_name_b",
                "stable_ratio",
                "status",
                "n_points",
                "n_stable",
            ]
        )

    merged = target.merge(
        base,
        on=["seed", "topo", "size", "failure_profile"],
        suffixes=("_target", "_base"),
    )
    if merged.empty:
        return pd.DataFrame(
            columns=[
                "topo",
                "size",
                "failure_profile",
                "variant_type",
                "param_name",
                "param_name_b",
                "stable_ratio",
                "status",
                "n_points",
                "n_stable",
            ]
        )

    def _abs_tol(base_val, ratio):
        base_abs = np.abs(np.asarray(base_val, dtype=float))
        return np.maximum(1e-9, base_abs) * ratio

    pdr_ok = (merged["pdr_final_target"] - merged["pdr_final_base"]) >= -pdr_tol
    loss_ok = np.abs(merged["loss_final_target"] - merged["loss_final_base"]) <= _abs_tol(
        merged["loss_final_base"],
        loss_tol_ratio,
    )
    route_ok = np.abs(merged["route_changes_final_target"] - merged["route_changes_final_base"]) <= _abs_tol(
        merged["route_changes_final_base"],
        change_tol_ratio,
    )
    table_ok = np.abs(merged["table_updates_final_target"] - merged["table_updates_final_base"]) <= _abs_tol(
        merged["table_updates_final_base"],
        table_tol_ratio,
    )
    merged["stable"] = pdr_ok & loss_ok & route_ok & table_ok

    rows = []
    for key, g in merged.groupby(metric_keys):
        ratio = float(np.mean(g["stable"].to_numpy(dtype=float))) if len(g) else 0.0
        if ratio >= 0.75:
            status = "robust"
        elif ratio >= 0.45:
            status = "weakened"
        else:
            status = "failed"

        rows.append(
            {
                "topo": key[0],
                "size": int(key[1]),
                "failure_profile": key[2],
                "variant_type": key[3],
                "param_name": key[4],
                "param_name_b": key[5],
                "stable_ratio": ratio,
                "status": status,
                "n_points": int(len(g)),
                "n_stable": int(np.sum(g["stable"].to_numpy(dtype=bool))),
            }
        )
    return pd.DataFrame(rows)


def main():
    parser = argparse.ArgumentParser(description="V2 parameter sensitivity and stability evaluation.")
    parser.add_argument("--topos", default="ba,er")
    parser.add_argument("--sizes", default="25,50")
    parser.add_argument("--seeds", default="1-3")
    parser.add_argument("--steps", type=int, default=160)
    parser.add_argument("--fail-step", type=int, default=90)
    parser.add_argument("--failure-profiles", default="single")
    parser.add_argument("--er-p", type=float, default=0.06)
    parser.add_argument("--ba-m", type=int, default=3)
    parser.add_argument("--snn-mode", default="snn_event_dv")
    parser.add_argument("--out-prefix", default="run_dir/issue17_v2_sensitivity")
    parser.add_argument("--pairwise", default="stress_smooth_gain,stress_smooth_center,softmin_temperature")
    parser.add_argument("--base-mult", type=float, default=0.2)
    parser.add_argument("--base-random-seed", type=int, default=20260224)
    parser.add_argument("--issue-id", type=int, default=17)
    args = parser.parse_args()

    topos = [x.strip() for x in args.topos.split(",") if x.strip()]
    sizes = parse_int_ranges(args.sizes)
    seeds = parse_int_ranges(args.seeds)
    failure_profiles = [x.strip() for x in args.failure_profiles.split(",") if x.strip()]

    pairwise_params = [x.strip() for x in args.pairwise.split(",") if x.strip()]
    for p in pairwise_params:
        if p not in PARAM_KEYS:
            raise ValueError(f"unsupported pairwise param: {p}")

    base = dict(BASELINE_PARAMS)
    if args.base_mult <= 0:
        raise ValueError("base-mult must be > 0")

    route_ttl_low = max(5, int(base["route_ttl"] * (1.0 - args.base_mult)))
    route_ttl_high = max(5, int(base["route_ttl"] * (1.0 + args.base_mult)))

    base["perturbations"] = {
        "stress_smooth_gain": [base["stress_smooth_gain"] * (1.0 - args.base_mult), base["stress_smooth_gain"] * (1.0 + args.base_mult)],
        "stress_smooth_center": [base["stress_smooth_center"] * (1.0 - args.base_mult), base["stress_smooth_center"] * (1.0 + args.base_mult)],
        "softmin_temperature": [max(0.001, base["softmin_temperature"] * (1.0 - args.base_mult)), base["softmin_temperature"] * (1.0 + args.base_mult)],
        "switch_hysteresis": [max(0.01, base["switch_hysteresis"] * (1.0 - args.base_mult)), base["switch_hysteresis"] * (1.0 + args.base_mult)],
        "route_ttl": [route_ttl_low, route_ttl_high],
    }

    pairwise = []
    for i in range(len(pairwise_params)):
        for j in range(i + 1, len(pairwise_params)):
            pairwise.append((pairwise_params[i], pairwise_params[j]))

    plan = build_plan(base, pairwise)
    total = len(topos) * len(sizes) * len(seeds) * len(failure_profiles) * len(plan)
    rows = []
    done = 0

    for topo in topos:
        for size in sizes:
            for seed in seeds:
                for profile in failure_profiles:
                    for entry in plan:
                        done += 1
                        print(
                            f"[{done:04d}/{total:04d}] topo={topo} size={size} seed={seed} profile={profile} case={entry['case_id']}",
                            flush=True,
                        )
                        rows.append(
                            {
                                "issue": args.issue_id,
                                "case_id": entry["case_id"],
                                "variant_type": entry["variant_type"],
                                "param_name": entry["param_name"],
                                "param_name_b": entry["param_name_b"],
                                **run_case(
                                    topo=topo,
                                    seed=seed,
                                    num_nodes=size,
                                    steps=args.steps,
                                    fail_step=args.fail_step,
                                    failure_profile=profile,
                                    er_p=args.er_p,
                                    ba_m=args.ba_m,
                                    snn_mode=args.snn_mode,
                                    stress_smooth_gain=entry["stress_smooth_gain"],
                                    stress_smooth_center=entry["stress_smooth_center"],
                                    softmin_temperature=entry["softmin_temperature"],
                                    switch_hysteresis=entry["switch_hysteresis"],
                                    route_ttl=entry["route_ttl"],
                                ),
                            }
                        )

    runs_df = pd.DataFrame(rows)
    summary_df = build_group_summary(runs_df)
    sig_df = build_significance(runs_df)
    stable_df = build_stable_region(runs_df)

    runs_path = f"{args.out_prefix}_sensitivity_runs.csv"
    summary_path = f"{args.out_prefix}_sensitivity_summary.csv"
    sig_path = f"{args.out_prefix}_sensitivity_significance.csv"
    stable_path = f"{args.out_prefix}_stable_region.csv"

    runs_df.to_csv(runs_path, index=False)
    summary_df.to_csv(summary_path, index=False)
    sig_df.to_csv(sig_path, index=False)
    stable_df.to_csv(stable_path, index=False)

    print(f"Saved: {runs_path}")
    print(f"Saved: {summary_path}")
    print(f"Saved: {sig_path}")
    print(f"Saved: {stable_path}")


if __name__ == "__main__":
    main()
