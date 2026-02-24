import numpy as np
from collections import deque

class QueueNode:
    def __init__(self, node_id, service_rate=25, buffer_size=300, alpha=0.5, beta_I=2000.0, T_d=2):
        self.node_id = node_id
        self.service_rate = service_rate
        self.buffer_size = buffer_size
        self.input_queue = deque()
        
        # 论文核心参数：alpha (学习率), beta_I (应力增益)
        self.alpha = alpha
        self.beta_I = beta_I
        self.T_d = T_d
        
        # 结构应力状态 S
        self.S = 0.0
        
        self.dropped_in_window = 0
        self.total_dropped = 0

    def receive_packet(self, packet):
        if len(self.input_queue) < self.buffer_size:
            self.input_queue.append(packet)
            return True
        self.dropped_in_window += 1
        self.total_dropped += 1
        return False

    def notify_link_failure_drop(self):
        """链路失效导致的物理丢包，作为强应力信号注入"""
        self.dropped_in_window += self.service_rate
        self.total_dropped += 1

    def process_and_forward(self, step_k):
        # 物理转发逻辑
        forwarded = []
        for _ in range(min(len(self.input_queue), self.service_rate)):
            if self.input_queue:
                forwarded.append(self.input_queue.popleft())
            
        # 严格执行论文 Eq. (3)
        if step_k % self.T_d == 0:
            queue_load = len(self.input_queue) / self.buffer_size
            loss_intensity = self.dropped_in_window / (self.service_rate * self.T_d)
            kappa = min(1.0, queue_load + loss_intensity)
            
            # S 状态的漏积分器演化
            self.S = (1 - self.alpha) * self.S + self.alpha * kappa
            self.dropped_in_window = 0 
            
        return forwarded