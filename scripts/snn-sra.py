import argparse
import networkx as nx

#!/usr/bin/env python3
# 创建并保存一个 Barabási–Albert (BA) 网络图
# 保存路径默认: ./ba_graph.png

import matplotlib.pyplot as plt

def main():
    p = argparse.ArgumentParser(description="生成 BA 图并保存为图片")
    p.add_argument("--n", type=int, default=100, help="节点数 (默认 100)")
    p.add_argument("--m", type=int, default=2, help="每次加入新节点时连接的现有节点数 m (默认 2)")
    p.add_argument("--seed", type=int, default=None, help="随机种子 (可选)")
    p.add_argument("--out", default="ba_graph.png", help="输出图片文件名 (默认 ba_graph.png)")
    p.add_argument("--dpi", type=int, default=150, help="输出图片分辨率 DPI")
    args = p.parse_args()

    G = nx.barabasi_albert_graph(args.n, args.m, seed=args.seed)

    # 使用确定性布局（若提供 seed 则布局可重复）
    pos = nx.spring_layout(G, seed=args.seed)

    # 节点颜色按度数映射
    degrees = [d for _, d in G.degree()]

    plt.figure(figsize=(8, 6))
    nx.draw_networkx_edges(G, pos, alpha=0.4, width=0.7)
    nx.draw_networkx_nodes(G, pos, node_size=50, node_color=degrees, cmap="viridis")
    plt.axis("off")
    plt.tight_layout()
    plt.savefig(args.out, dpi=args.dpi)
    plt.close()

    print(f"生成 BA 图: n={args.n}, m={args.m}, 输出 -> {args.out}")

if __name__ == "__main__":
    main()