import numpy as np

class SRAEngine:
    def __init__(self, num_nodes, alpha=0.1, beta_I=5.0, T_d=5):
        self.num_nodes = num_nodes
        self.alpha = alpha     # 学习率/平滑因子
        self.beta_I = beta_I   # 结构压力成本因子
        self.T_d = T_d         # 最小停留时间
        self.S = np.zeros(num_nodes)
        self.kappa = np.zeros(num_nodes) # 观测到的中心性

    def update_routing_costs(self, G):
        """根据公式 C = 1 + beta_I * S 更新拓扑图的边成本"""
        for u, v in G.edges():
            # 链路成本由两端节点的应力状态决定
            G[u][v]['cost'] = 1.0 + self.beta_I * (self.S[u] + self.S[v])

    def step(self, new_obs_kappa, k):
        """执行一个步长的状态更新"""
        # 只有在 T_d 的倍数步长时才触发路径/策略切换 (模拟停留时间约束)
        if k % self.T_d == 0:
            self.kappa = np.array(new_obs_kappa)
        
        # 状态平滑更新: S(k+1) = (1-alpha)S(k) + alpha * kappa(k)
        self.S = (1 - self.alpha) * self.S + self.alpha * self.kappa
        
        # 计算当前的 Lyapunov 函数值 V(S) = 0.5 * sum(S^2)
        v_s = 0.5 * np.sum(self.S**2)
        return self.S, v_s