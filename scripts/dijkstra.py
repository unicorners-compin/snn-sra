import networkx as nx
import pandas as pd
import json

def simulate_lab_topology():
    """
    生成实验室标准的拓扑并计算全局路由表
    """
    # 1. 构建拓扑 (以典型的 Waxman 拓扑或自定义骨干网为例)
    # 这里我们手动建立一个 6 节点的环网+放射状拓扑，模拟 DPU 节点分布
    G = nx.Graph()
    edges = [
        (0, 1, 10), (1, 2, 10), (2, 3, 15), 
        (3, 4, 10), (4, 5, 10), (5, 0, 15),
        (0, 2, 25), (1, 4, 30)
    ]
    for u, v, w in edges:
        G.add_edge(u, v, weight=w)

    print(f">>> 拓扑构建完成: 节点数={G.number_of_nodes()}, 链路数={G.number_of_edges()}")

    # 2. 自动化路由计算 (Dijkstra 算法)
    # 计算全网最短路径 (All-Pairs Shortest Paths)
    all_routes = {}
    path_generator = nx.all_pairs_dijkstra_path(G, weight='weight')
    
    for source, paths in path_generator:
        all_routes[source] = paths

    # 3. 结果提取与格式化 (适配你的 SRv6/uSID 审计需求)
    route_data = []
    for src in all_routes:
        for dst in all_routes[src]:
            if src != dst:
                path = all_routes[src][dst]
                cost = nx.dijkstra_path_length(G, src, dst, weight='weight')
                
                # 模拟生成 SRv6 SID List (uSID 风格)
                sid_list = [f"fc00::{node:x}" for node in path[1:]]
                
                route_data.append({
                    "src": src,
                    "dst": dst,
                    "path": path,
                    "cost": cost,
                    "sid_list": sid_list
                })

    return G, pd.DataFrame(route_data)

if __name__ == "__main__":
    # 运行仿真
    topo, df = simulate_lab_topology()

    # 展示前 5 条路由结果
    print("\n>>> 自动化路由计算结果 (Top 5):")
    print(df.head())

    # 4. 导出为实验证据 (对接你的 grun.py)
    # 这里的 hash 将作为因果审计的核心凭证
    result_path = "results/routing_table.json"
    df.to_json(result_path, orient="records", indent=4)
    print(f"\n>>> 仿真结果已保存至 {result_path}，请执行 'grun' 进行因果对账。")