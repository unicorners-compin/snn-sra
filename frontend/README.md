# SNN Routing Frontend

## 启动方式

在仓库根目录执行：

```bash
python3 -m http.server 8000
```

然后在浏览器打开：

`http://127.0.0.1:8000/frontend/snn_route_viz.html`

页面会默认读取 `run_dir/snn_route_viz.json`。

## 数据生成

如果没有可视化数据，先运行：

```bash
python3 scripts_flow/main_snn.py
```

可选：指定拓扑类型（默认 `ba`）：

```bash
SNN_TOPOLOGY=er python3 scripts_flow/main_snn.py
```

这会生成：

- `run_dir/snn_route_viz.json`
- `run_dir/snn_metrics.csv`
- `run_dir/snn_ablation_summary.csv`
