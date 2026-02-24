import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import sys
from pathlib import Path

import numpy as np
import pandas as pd

# Path patch for local package imports.
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from scripts_flow.paper_stat_eval import (
    build_group_summary,
    build_significance,
    parse_int_ranges,
    run_case,
)


def main():
    parser = argparse.ArgumentParser(description="Parallel paper-grade statistical evaluation.")
    parser.add_argument("--algos", default="ospf,ecmp,ppo,snn")
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
    parser.add_argument("--workers", type=int, default=20)
    parser.add_argument("--out-prefix", default="run_dir/issue13_heavybg")
    parser.add_argument("--random-seed", type=int, default=20260223)
    args = parser.parse_args()

    algos = [x.strip() for x in args.algos.split(",") if x.strip()]
    topos = [x.strip() for x in args.topos.split(",") if x.strip()]
    sizes = parse_int_ranges(args.sizes)
    seeds = parse_int_ranges(args.seeds)
    profiles = [x.strip() for x in args.failure_profiles.split(",") if x.strip()]

    valid_algos = {"ospf", "ospf_sync", "ecmp", "backpressure", "ppo", "snn"}
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
                                "snn_mode": args.snn_mode,
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
