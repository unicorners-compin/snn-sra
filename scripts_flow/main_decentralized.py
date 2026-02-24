import sys
import os
from pathlib import Path

# 路径补丁：确保能找到 scripts_flow 包
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

import pandas as pd
from scripts_flow.node import QueueNode
from scripts_flow.traffic import TrafficGenerator
from scripts_flow.simulator import FlowSimulator
from scripts.topo_manager import generate_grid_topo

def main():
    print(">>> [GLOBAL DYNAMICS] 启动全网平均指标追踪仿真...")
    RUN_DIR = "run_dir"
    os.makedirs(RUN_DIR, exist_ok=True)
    
    G = generate_grid_topo(10)
    # 严格按照 SRA 参数配置
    nodes = {i: QueueNode(node_id=i, beta_I=2000.0, alpha=0.5) for i in range(100)}
    sim = FlowSimulator(nodes, G)
    
    # 流量：不仅有主探测流，还增加一些背景流，让全网应力分布更复杂
    flow_cfg = [
        {'src': 5, 'dst': 95, 'base_rate': 12},
        {'src': 50, 'dst': 59, 'base_rate': 10, 'burst_start': 100, 'burst_end': 150, 'burst_rate': 100}
    ]
    tg = TrafficGenerator(flow_cfg)

    print("-" * 90)
    print(f"{'Slot':<6} | {'V(S)':<8} | {'AvgHop':<8} | {'Reach%':<8} | {'Loss':<6}")
    print("-" * 90)

    results = []
    for k in range(300):
        # Slot 200 注入故障
        if k == 200:
            edge = (45, 55)
            if G.has_edge(*edge): G.remove_edge(*edge)
            print(f"\n>>> [FAULT] 物理链路 {edge} 已断开")

        v_s, loss = sim.run_step(k, tg.generate(k))
        
        # 每 10 步进行一次全网大扫描，避免计算过于频繁
        if k % 10 == 0:
            avg_hop, reach = sim.get_global_metrics()
            print(f"{k:03d}    | {v_s:.4f} | {avg_hop:<8.2f} | {reach*100:<7.1f}% | {loss:<6}")
            
            results.append({
                'step': k, 'v_s': v_s, 'avg_hop': avg_hop, 
                'reachability': reach, 'loss': loss
            })

    pd.DataFrame(results).to_csv(f"{RUN_DIR}/global_metrics.csv", index=False)
    print("-" * 90)
    print(">>> 全网动力学数据已保存。")

if __name__ == "__main__":
    main()