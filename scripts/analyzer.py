import matplotlib.pyplot as plt
import pandas as pd
import numpy as np
import os

def save_results(history, run_dir='run_dir'):
    if not os.path.exists(run_dir):
        os.makedirs(run_dir)

    # 数据持久化
    df = pd.DataFrame({
        'iteration': range(len(history['v_s'])),
        'v_s': history['v_s'],
        'max_s': history['max_s'],
        'std_s': history['std_s'],
        'peak_node_s': history['peak_node_history']
    })
    df.to_csv(os.path.join(run_dir, 'metrics.csv'), index=False)
    
    fig, axs = plt.subplots(2, 2, figsize=(16, 10))
    
    # 1. 全局稳定性 (Lyapunov)
    axs[0, 0].plot(df['v_s'], color='#1f77b4', lw=2)
    axs[0, 0].set_yscale('log')
    axs[0, 0].set_title('Global Structural Stability (V(S))')
    axs[0, 0].grid(True, linestyle='--', alpha=0.6)

    # 2. 瓶颈自适应卸载 (核心创新点体现)
    # 观察初始峰值节点如何被 SRA 救活
    axs[0, 1].plot(df['max_s'], label='Global Max Stress', color='gray', alpha=0.5, ls='--')
    axs[0, 1].plot(df['peak_node_s'], color='#d62728', lw=2.5, label='Initial Bottleneck Node')
    axs[0, 1].set_title('Adaptive Route Emergence: Peak Offloading')
    axs[0, 1].legend()
    axs[0, 1].grid(True, linestyle='--', alpha=0.6)

    # 3. 负载均衡演化 (标准差下降代表路由分散)
    axs[1, 0].plot(df['std_s'], color='#ff7f0e', lw=2)
    axs[1, 0].set_title('Load Balancing (Stress Std Dev)')
    axs[1, 0].grid(True, linestyle='--', alpha=0.6)

    # 4. 压力分布迁移
    axs[1, 1].hist(history['initial_snapshot'], bins=15, alpha=0.4, label='Initial (SP)', color='gray')
    axs[1, 1].hist(history['final_snapshot'], bins=15, alpha=0.6, label='Final (SRA)', color='#2ca02c')
    axs[1, 1].set_title('Structural Stress Redistribution')
    axs[1, 1].legend()
    
    plt.tight_layout()
    plt.savefig(os.path.join(run_dir, 'adaptive_analysis.png'), dpi=300)