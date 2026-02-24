import sys
import os
import random
from pathlib import Path
import pandas as pd

# 路径补丁
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from scripts_flow.node import QueueNode
from scripts_flow.traffic import TrafficGenerator
from scripts_flow.failure_manager import FailureManager
from scripts_flow.simulator import FlowSimulator
from scripts.topo_manager import generate_grid_topo

def main():
    print(">>> [INIT] 启动去中心化流量仿真引擎...")
    RUN_DIR = os.getenv("EXPERIMENT_RUN_DIR", "run_dir")
    os.makedirs(RUN_DIR, exist_ok=True)
    
    # 初始化拓扑与节点
    G = generate_grid_topo(10)
    nodes = {i: QueueNode(node_id=i, beta_I=20.0) for i in range(100)}
    fm = FailureManager(G)
    sim = FlowSimulator(nodes, G)
    
    # 流量场景：背景流 + Slot 100 突发
    tg = TrafficGenerator([
        {'src': i, 'dst': 99-i, 'base_rate': 10, 
         'burst_rate': 60, 'burst_start': 100, 'burst_end': 130}
        for i in range(5)
    ])

    results = []
    for k in range(400):
        if k == 250: # 在 250 步注入链路故障
            fm.inject_link_failure(45, 55, k)
            
        v_s, loss = sim.run_step(k, tg.generate(k))
        results.append({'step': k, 'v_s': v_s, 'loss': loss, 
                        'max_s': max([n.S for n in nodes.values()])})
        
        if k % 50 == 0:
            print(f"Slot {k:03d} | Lyapunov V(S): {v_s:.4f} | Loss: {loss}")

    # 保存数据
    df = pd.DataFrame(results)
    df.to_csv(f"{RUN_DIR}/flow_metrics.csv", index=False)
    print(f">>> [DONE] 数据已保存至 {RUN_DIR}/flow_metrics.csv")

if __name__ == "__main__":
    main()
