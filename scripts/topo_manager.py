import networkx as nx

def generate_grid_topo(dim=10):
    """生成一个 dim*dim 的网格拓扑，并初始化边权重"""
    G = nx.grid_2d_graph(dim, dim)
    # 将坐标标签转换为整数 ID (0-99)
    G = nx.convert_node_labels_to_integers(G)
    # 初始化边成本为 1.0
    for u, v in G.edges():
        G[u][v]['cost'] = 1.0
    return G


def _init_edge_costs(G):
    for u, v in G.edges():
        G[u][v]["cost"] = 1.0
    return G


def _ensure_connected_random_graph(graph_builder, max_tries=20):
    """Build a connected random graph; retry if disconnected."""
    for _ in range(max_tries):
        G = graph_builder()
        if nx.is_connected(G):
            return G
    # Fallback: return largest connected component relabeled to contiguous IDs.
    G = graph_builder()
    ccs = sorted(nx.connected_components(G), key=len, reverse=True)
    H = G.subgraph(ccs[0]).copy()
    return nx.convert_node_labels_to_integers(H)


def generate_er_topo(num_nodes=100, p=0.06, seed=7):
    """Generate a connected Erdos-Renyi graph and initialize edge costs."""
    def _builder():
        g = nx.erdos_renyi_graph(num_nodes, p, seed=seed + _builder.counter)
        _builder.counter += 1
        return g
    _builder.counter = 0
    G = _ensure_connected_random_graph(_builder)
    G = nx.convert_node_labels_to_integers(G)
    return _init_edge_costs(G)


def generate_ba_topo(num_nodes=100, m=3, seed=7):
    """Generate a Barabasi-Albert graph and initialize edge costs."""
    m = max(1, min(m, num_nodes - 1))
    G = nx.barabasi_albert_graph(num_nodes, m, seed=seed)
    G = nx.convert_node_labels_to_integers(G)
    return _init_edge_costs(G)


def generate_topology(kind="ba", num_nodes=100, seed=7, grid_dim=10, er_p=0.06, ba_m=3):
    """Factory for grid/ER/BA topologies."""
    k = (kind or "ba").lower()
    if k == "grid":
        dim = grid_dim
        if dim * dim != num_nodes:
            dim = int(num_nodes ** 0.5)
        return generate_grid_topo(dim)
    if k == "er":
        return generate_er_topo(num_nodes=num_nodes, p=er_p, seed=seed)
    if k == "ba":
        return generate_ba_topo(num_nodes=num_nodes, m=ba_m, seed=seed)
    raise ValueError(f"Unsupported topology kind: {kind}")


def build_layout_positions(G, layout="spring", seed=7):
    """Return normalized [0,1] node positions for visualization."""
    layout_kind = (layout or "spring").lower()
    if layout_kind == "kamada":
        pos = nx.kamada_kawai_layout(G)
    elif layout_kind == "spectral":
        pos = nx.spectral_layout(G)
    elif layout_kind == "grid":
        # Recover coordinates for perfect-square node counts.
        dim = int(len(G.nodes()) ** 0.5)
        pos = {n: ((n % dim), (n // dim)) for n in G.nodes()}
    else:
        pos = nx.spring_layout(G, seed=seed)

    xs = [p[0] for p in pos.values()]
    ys = [p[1] for p in pos.values()]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    dx = max(max_x - min_x, 1e-9)
    dy = max(max_y - min_y, 1e-9)
    norm = {n: ((pos[n][0] - min_x) / dx, (pos[n][1] - min_y) / dy) for n in G.nodes()}
    return norm


def get_node_centrality(G, traffic_pairs):
    """
    计算基于当前成本的最短路径中心性
    模拟流量在网络中的实际分布情况
    """
    num_nodes = G.number_of_nodes()
    counts = [0] * num_nodes
    for s, d in traffic_pairs:
        try:
            path = nx.shortest_path(G, source=s, target=d, weight='cost')
            for node in path:
                counts[node] += 1
        except nx.NetworkXNoPath:
            continue
    return counts
