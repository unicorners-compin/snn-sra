# DPDK 原型说明（SNN-SRA）

本目录提供一个“可落地改造”的 DPDK C 原型，用于把当前 `scripts_flow/` 的增强版 SNN-SRA 思路映射到数据面。

文件：

- `snn_sra_dpdk_prototype.c`

## 1. 当前项目（增强版）逻辑摘要

当前 `scripts_flow` 主线可概括为：

1. 节点维护状态：`S`（结构应力）、`spike_rate_ema`、`loss/queue` 相关量。
2. 每步更新神经状态：`S <- (1-alpha)*S + alpha*kappa`，`kappa` 来自 spike/queue/loss 组合。
3. 路由评分：对候选下一跳计算 `score = link_cost + hop_hint + spike + burst(+beacon)`。
4. 控制面：事件触发式更新（含最小保持时间、抖动抑制、路由老化）。
5. 转发面：按当前策略选下一跳，统计 PDR/loss/delay/hop 等指标。

## 2. DPDK 原型映射

`snn_sra_dpdk_prototype.c` 做了以下映射：

- `port -> node`：每个物理端口维护一个 `snn_node_state`。
- `route_entry`：用简化表维护 `dst_ip -> out_port`。
- `update_node_state()`：按端口 `rx/drop` 增量更新 `loss/queue/spike/S`。
- `update_control_plane()`：周期性重算目的地址出口（事件驱动的简化占位）。
- `route_lookup()`：先查表，miss 时调用 `choose_next_hop()` 做本地评分决策。
- 主循环：`rx_burst -> IPv4解析 -> route_lookup -> tx_burst`。

## 3. 编译

示例（依赖 `libdpdk`）：

```bash
cc -O2 -Wall -Wextra dpdk/snn_sra_dpdk_prototype.c -o dpdk/snn_sra_dpdk_prototype $(pkg-config --cflags --libs libdpdk)
```

## 4. 运行（示例）

```bash
sudo ./dpdk/snn_sra_dpdk_prototype -l 0-1 -n 4 --vdev=net_tap0 --vdev=net_tap1
```

说明：

- 这是原型骨架，不是可直接上线的完整路由器。
- 真实部署需要补齐：ARP/邻居解析、LPM/FIB、多核流水线、统计导出、故障注入接口。

## 5. 下一步建议（从原型到可用版本）

1. 用 `rte_lpm` 替换当前 `dst_ip` 哈希表。
2. 把 `S/spike/loss` 状态搬到 per-lcore + 周期聚合，减少锁开销。
3. 引入 ring + worker pipeline：`RX -> classify -> route_decide -> TX`。
4. 增加控制面通道（gRPC/Unix socket）以注入 beacon/故障事件。
5. 对齐现有 Python 评估指标，增加 CSV/Prometheus 导出。 
