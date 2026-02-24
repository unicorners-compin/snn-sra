class FailureManager:
    def __init__(self, physical_graph):
        self.G = physical_graph
        self.active_failures = []

    def inject_link_failure(self, u, v, step_k):
        if self.G.has_edge(u, v):
            edge_data = self.G.get_edge_data(u, v)
            self.G.remove_edge(u, v)
            self.active_failures.append({'u': u, 'v': v, 'step': step_k, 'data': edge_data})
            print(f">>> [FAILURE] 链路 ({u}, {v}) 在步长 {step_k} 被断开")