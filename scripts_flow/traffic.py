# scripts_flow/traffic.py

import numpy as np

class Packet:
    def __init__(self, src, dst, creation_step):
        self.src = src
        self.dst = dst
        self.creation_step = creation_step

class TrafficGenerator:
    def __init__(self, flows_config):
        self.flows_config = flows_config

    def generate(self, step_k):
        new_packets = []
        for flow in self.flows_config:
            # 安全地获取参数，如果没有则使用基础速率
            base_rate = flow.get('base_rate', 10)
            burst_rate = flow.get('burst_rate', base_rate)
            burst_start = flow.get('burst_start', -1)
            burst_end = flow.get('burst_end', -1)
            
            # 判断是否处于突发窗口
            if burst_start <= step_k <= burst_end:
                rate = burst_rate
            else:
                rate = base_rate
            
            # 泊松生成报文
            num = np.random.poisson(rate)
            for _ in range(num):
                new_packets.append(Packet(flow['src'], flow['dst'], step_k))
        return new_packets