import numpy as np

class AutonomousNode:
    def __init__(self, node_id, alpha=0.15, beta_I=3.0, T_d=5):
        self.node_id = node_id
        self.alpha = alpha
        self.beta_I = beta_I
        self.T_d = T_d
        
        self.S = 0.0           # 内部应力状态
        self.kappa_hat = 0.0   # 局部估计的中心性
        self.observed_flows = set() # 记录观察到的 (src, dst) 流对
        self.neighbor_costs = {}    # 邻居反馈的成本

    def observe_flow(self, src, dst):
        """模拟硬件采样：记录流经本节点的唯一流对"""
        self.observed_flows.add((src, dst))

    def update_state(self, step_k):
        """泄露积分器更新逻辑"""
        # 局部 BC 估计：当前周期内观察到的流对数量
        current_kappa = len(self.observed_flows)
        
        # 满足最小停留时间 T_d 时更新状态，模拟 SRA 的块状收敛
        if step_k % self.T_d == 0:
            self.kappa_hat = current_kappa
            # 核心方程：泄露积分器的遗忘与累积
            self.S = (1 - self.alpha) * self.S + self.alpha * self.kappa_hat
            self.observed_flows.clear() # 进入新观测周期
            
        # 返回当前节点的压力成本
        return 1.0 + self.beta_I * self.S