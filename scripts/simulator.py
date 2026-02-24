import networkx as nx

class DecentralizedSimulator:
    def __init__(self, node_dict, physical_graph):
        self.nodes = node_dict       # {id: AutonomousNode}
        self.G = physical_graph      # 物理拓扑
        
    def run_step(self, step_k, traffic_pairs):
        """执行一个分布式仿真步长"""
        # 1. 更新链路权重：基于各节点的当前应力 S
        for u, v in self.G.edges():
            # 链路成本由两端节点的 SRA 状态共同决定
            cost_u = 1.0 + self.nodes[u].beta_I * self.nodes[u].S
            cost_v = 1.0 + self.nodes[v].beta_I * self.nodes[v].S
            self.G[u][v]['weight'] = (cost_u + cost_v) / 2.0

        # 2. 流量转发与采样：模拟数据面执行
        # 在 RDP 协议下，流量会避开权重（应力）高的路径
        for src, dst in traffic_pairs:
            try:
                # 模拟基于局部权重的分布式路径查找
                path = nx.shortest_path(self.G, source=src, target=dst, weight='weight')
                for n_id in path:
                    self.nodes[n_id].observe_flow(src, dst)
            except nx.NetworkXNoPath:
                continue

        # 3. 节点状态更新：每个节点自主执行泄露积分更新
        all_v_s = []
        for node in self.nodes.values():
            node.update_state(step_k)
            all_v_s.append(node.S**2)
            
        return 0.5 * sum(all_v_s), max([n.S for n in self.nodes.values()])