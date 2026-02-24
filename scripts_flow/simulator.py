import networkx as nx
import copy

class FlowSimulator:
    def __init__(self, node_dict, physical_graph):
        self.nodes = node_dict
        self.G = physical_graph
        self.inflight_packets = [] 
        # 初始路由表：从孤岛状态开始
        self.routing_tables = {n: {dest: (None, float('inf')) for dest in node_dict} for n in node_dict}
        for u in self.nodes:
            self.routing_tables[u][u] = (u, 0.0)

    def update_control_plane(self):
        """分布式代价传播：实现 SRA 的‘应力波’扩散"""
        new_tables = copy.deepcopy(self.routing_tables)
        for u in self.nodes:
            active_neighbors = list(self.G.neighbors(u))
            
            # 物理链路失效清理
            for dest in self.routing_tables[u]:
                nxt, _ = self.routing_tables[u][dest]
                if nxt is not None and nxt != u and nxt not in active_neighbors:
                    new_tables[u][dest] = (None, float('inf'))

            # 邻居信息交换 (RIP-like)
            for v in active_neighbors:
                # 链路成本计算 (基于两端 SRA 应力)
                edge_cost = 1.0 + self.nodes[u].beta_I * self.nodes[u].S + \
                                  self.nodes[v].beta_I * self.nodes[v].S
                
                for dest, (v_next, v_dist) in self.routing_tables[v].items():
                    if v_next == u: continue 
                    new_dist = edge_cost + v_dist
                    curr_next, curr_dist = self.routing_tables[u][dest]
                    
                    # 关键：支持坏消息传导。如果当前下一跳变贵了，必须接受
                    if new_dist < curr_dist or v == curr_next:
                        new_tables[u][dest] = (v, new_dist)
                            
        self.routing_tables = new_tables

    def run_step(self, step_k, new_packets):
        # 控制面与转发面同步步进
        self.update_control_plane() 

        for pkt in new_packets:
            self.nodes[pkt.src].receive_packet(pkt)

        for node_id, node in self.nodes.items():
            pkts = node.process_and_forward(step_k)
            for p in pkts:
                if p.dst == node_id: continue
                res = self.routing_tables[node_id].get(p.dst)
                next_hop = res[0] if res else None
                if next_hop is not None:
                    self.inflight_packets.append((p, next_hop, step_k + 1, node_id))
                else:
                    node.notify_link_failure_drop()

        remaining = []
        for p, nxt, arr_t, last_node in self.inflight_packets:
            if step_k >= arr_t:
                if self.G.has_edge(last_node, nxt):
                    self.nodes[nxt].receive_packet(p)
                else:
                    self.nodes[last_node].notify_link_failure_drop()
            else:
                remaining.append((p, nxt, arr_t, last_node))
        self.inflight_packets = remaining

        v_s = 0.5 * sum([n.S**2 for n in self.nodes.values()])
        total_loss = sum([n.total_dropped for n in self.nodes.values()])
        return v_s, total_loss

    def get_path_for_flow(self, src, dst):
        path, curr, visited = [src], src, {src}
        while curr != dst:
            res = self.routing_tables.get(curr, {}).get(dst)
            if not res or res[0] is None or res[0] in visited or res[1] == float('inf'):
                path.append('X'); break
            next_node = res[0]; path.append(next_node); visited.add(next_node); curr = next_node
        return path
    
    def get_global_metrics(self):
        """
        全网扫描：计算平均跳数和连通率
        """
        total_hops = 0
        reachable_pairs = 0
        total_pairs = len(self.nodes) * (len(self.nodes) - 1)
        
        for src in self.nodes:
            for dst in self.nodes:
                if src == dst: continue
                
                # 追踪跳数
                path = self.get_path_for_flow(src, dst)
                if 'X' not in path:
                    total_hops += (len(path) - 1)
                    reachable_pairs += 1
        
        avg_hop = total_hops / reachable_pairs if reachable_pairs > 0 else 0
        reachability = reachable_pairs / total_pairs
        
        return avg_hop, reachability