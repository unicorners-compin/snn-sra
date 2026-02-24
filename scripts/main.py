import sys
import random
import numpy as np
from pathlib import Path

# 路径补丁
file_path = Path(__file__).resolve()
root_dir = file_path.parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from scripts.topo_manager import generate_grid_topo
from scripts.node import AutonomousNode
from scripts.simulator import DecentralizedSimulator
from scripts.analyzer import save_results

def main():
    NUM_NODES = 100
    ITERATIONS = 200 
    TRAFFIC_FLOWS = 300
    
    G = generate_grid_topo(10)
    # 稍微调高 beta_I，让路由切换的意愿更明显
    node_dict = {i: AutonomousNode(node_id=i, alpha=0.1, beta_I=8.0, T_d=5) 
                 for i in range(NUM_NODES)}
    
    nodes_list = list(G.nodes())
    traffic_pairs = [tuple(random.sample(nodes_list, 2)) for _ in range(TRAFFIC_FLOWS)]
    
    sim = DecentralizedSimulator(node_dict, G)
    
    # 严格检查字典初始化
    history = {
        'v_s': [], 
        'max_s': [], 
        'std_s': [],
        'initial_snapshot': None, 
        'final_snapshot': None,
        'peak_node_history': [] # 跟踪初始最堵节点的演化
    }

    print(">>> 启动去中心化 SRA 仿真（路由自适应模式）...")
    
    # 预先找到初始状态下的峰值节点（通常是中心节点）
    initial_v, initial_max = sim.run_step(0, traffic_pairs)
    initial_stresses = [node_dict[i].S for i in range(NUM_NODES)]
    peak_node_id = np.argmax(initial_stresses)
    history['initial_snapshot'] = initial_stresses

    for k in range(ITERATIONS):
        v_s, max_s = sim.run_step(k, traffic_pairs)
        
        current_stresses = [node_dict[i].S for i in range(NUM_NODES)]
        
        # 修正之前的 KeyError
        history['v_s'].append(v_s)
        history['max_s'].append(max_s)
        history['std_s'].append(np.std(current_stresses))
        history['peak_node_history'].append(node_dict[peak_node_id].S)
        
        if k % 20 == 0:
            print(f"迭代 {k}: 最大应力={max_s:.2f}, 瓶颈节点({peak_node_id})应力={node_dict[peak_node_id].S:.2f}")

    history['final_snapshot'] = [node_dict[i].S for i in range(NUM_NODES)]
    save_results(history)

if __name__ == "__main__":
    main()