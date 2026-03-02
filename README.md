# SNN-SRA: Stress-Aware Spiking Neural Routing (Simulation)

本项目实现了一个以“神经应力”为核心信号的路由仿真框架，当前主线代码在 `scripts_flow/`。  
核心思想是将队列负载、丢包和放电活动统一映射为节点应力 \(S_i(t)\)，再用 \(S_i(t)\) 驱动链路代价与路由决策。

## 1. 系统对象与状态

给定网络图 \(G=(V,E)\)，节点 \(i\in V\)，离散时间步 \(t\in\mathbb{N}\)。

每个节点维护：

- 队列长度：\(Q_i(t)\)
- 缓冲容量：\(B_i\)
- 服务率：\(\mu_i\)
- 结构应力：\(S_i(t)\)
- 膜电位：\(v_i(t)\)
- 放电指示：\(s_i(t)\in\{0,1\}\)
- 放电率 EMA：\(r_i(t)\)
- 阈值：\(\theta_i(t)\)
- 最近丢包比：\(\ell_i(t)\)

## 2. 节点动力学（`scripts_flow/snn_node.py`）

### 2.1 局部观测量

\[
q_i(t)=\frac{|Q_i(t)|}{B_i},\qquad
\lambda_i(t)=\frac{D_i^{(w)}(t)}{\mu_i T_d}
\]

其中 \(D_i^{(w)}(t)\) 是窗口内丢包量，\(T_d\) 为状态更新周期。

\[
u_i(t)=\min\{1,\;q_i(t)+\lambda_i(t)\}
\]

### 2.2 LIF 神经元更新

非不应期时：
\[
v_i(t+1)=v_i(t)+\frac{-(v_i(t)-v_{\text{reset}})+g_i\,u_i(t)}{\tau_m}
\]

放电规则：
\[
s_i(t+1)=
\begin{cases}
1,& v_i(t+1)\ge \theta_i(t)\\
0,& \text{otherwise}
\end{cases}
\]

若放电则 \(v_i(t+1)\leftarrow v_{\text{reset}}\)，并进入不应期。

放电率 EMA：
\[
r_i(t+1)=\rho\,r_i(t)+(1-\rho)\,s_i(t+1)
\]

阈值稳态调节：
\[
\theta_i(t+1)=\mathrm{clip}\!\left(\theta_i(t)+\eta_h\left(r_i(t+1)-r^\star\right),\theta_{\min},\theta_{\max}\right)
\]

### 2.3 结构应力更新

仅在 \(t \bmod T_d=0\) 时更新：
\[
\ell_i(t)=\min\{1,\lambda_i(t)\}
\]
\[
\kappa_i(t)=\min\{1,\;0.55\,r_i(t)+0.25\,q_i(t)+0.20\,\ell_i(t)\}
\]
\[
S_i(t+1)=(1-\alpha)S_i(t)+\alpha\,\kappa_i(t)
\]

## 3. 链路代价与突触惩罚（`scripts_flow/snn_router.py`）

### 3.1 节点迹线与 STDP-样惩罚

\[
x_i(t)=\delta\,x_i(t-1)+s_i(t)
\]

对边 \((i,j)\)：
\[
\psi_{ij}^{-}(t)=\gamma_{\text{syn}}\psi_{ij}(t-1)
\]
\[
\xi_{ij}(t)=\frac{\ell_i(t)+\ell_j(t)}{2}
\]

若最近放电步差 \(\Delta t_{ij}\le W\)：
\[
\phi_{ij}(t)=\frac{1}{1+\Delta t_{ij}/\tau_{\text{stdp}}},\quad\text{否则 }0
\]

\[
\Delta\psi_{ij}(t)=\eta_{\text{stdp}}\!\left(0.7\,x_i(t)x_j(t)+0.3\,\phi_{ij}(t)\right)+\eta_{\text{loss}}\,\xi_{ij}(t)
\]

\[
\psi_{ij}(t)=\mathrm{clip}\!\left(\psi_{ij}^{-}(t)+\Delta\psi_{ij}(t),\psi_{\min},\psi_{\max}\right)
\]

### 3.2 链路基础代价

\[
c_{ij}(t)=c_0+\beta_s\left(S_i(t)+S_j(t)\right)+\psi_{ij}(t)
\]

## 4. 本地路由评分（`scripts_flow/snn_router.py`, `scripts_flow/snn_simulator.py`）

节点 \(i\) 面向目的 \(d\) 选择邻居 \(j\in\mathcal{N}(i)\)：

\[
\text{score}_{i\to j}^{(d)}(t)=
c_{ij}(t)+
\beta_h\,h_{j,d}(t)+
\beta_f\,r_j(t)+
\beta_b\,b_{ij}(t)+
\mathbb{1}[j\in\mathcal{V}_{\text{visited}}]\cdot \lambda_{\text{loop}}
\]

其中：

- \(h_{j,d}(t)\)：hop hint（图最短跳近似）
- \(b_{ij}(t)\)：burst 平面附加惩罚
- \(\lambda_{\text{loop}}\)：环路惩罚常数

选择规则：
\[
j^\star=\arg\min_{j\in\mathcal{N}(i)}\text{score}_{i\to j}^{(d)}(t)
\]

## 5. 目的地 Beacon 势场（可选）

对目的 \(d\) 的 beacon 值 \(B_i^{(d)}(t)\)：
\[
B_i^{(d)}(t+1)=
\begin{cases}
\max(g_{\text{dst}},B_i^{(d)}(t)), & i=d\\
\max\left(\gamma_d B_i^{(d)}(t),\gamma_d\max\limits_{k\in\mathcal{N}(i)} B_k^{(d)}(t)\right), & i\neq d
\end{cases}
\]

对评分做梯度修正：
\[
\Delta_j^{(d)}(t)=\max\{0,B_j^{(d)}(t)-B_i^{(d)}(t)\}
\]
\[
\text{score}'_{i\to j}=\text{score}_{i\to j}-w_d\,\sigma(t)\,\frac{\Delta_j^{(d)}(t)}{\max_m\Delta_m^{(d)}(t)+\varepsilon}
\]

## 6. 事件驱动控制面（`snn_event_dv`）

广播触发度量：
\[
m_i(t)=S_i(t)+r_i(t)+0.5\,\ell_i(t)
\]
\[
\text{broadcast if }\left(|m_i(t)-m_i^{\text{last}}|\ge \theta_{\text{evt}}\right)\;\lor\;\left(t\ge t_i^{\text{next}}\right)
\]

周期自适应：
\[
p_i(t)=\mathrm{clip}\!\left(\mathrm{round}\left(\frac{p_0}{\max(0.08,S_i(t)+r_i(t))}\right),1,p_{\max}\right)
\]

DV 更新：
\[
\tilde d_{u\to d}(t)=c_{ub}(t)+d_{b\to d}(t)
\]
满足“同下一跳”或“显著更优（hysteresis）”则替换，并更新时间戳；超 TTL 路由失效。

## 7. 转发与性能指标

### 7.1 转发过程

每步流程：

1. 控制面更新（DV 或本地模式）
2. 新包注入队列
3. 每节点按服务率出队并选下一跳
4. 链路在下一时隙到达，断链则记丢包

### 7.2 全局指标（`scripts_flow/snn_simulator.py`）

\[
V(S,t)=\frac{1}{2}\sum_{i\in V} S_i(t)^2
\]
\[
\mathrm{PDR}(t)=\frac{N_{\text{delivered}}(t)}{N_{\text{generated}}(t)}
\]
\[
\bar D(t)=\frac{1}{N_{\text{delivered}}}\sum D_{\text{pkt}},\qquad
\bar H(t)=\frac{1}{N_{\text{delivered}}}\sum H_{\text{pkt}}
\]

并支持 `P50/P95/P99`、`queue_delay`、`extra_hop` 等分解指标。

## 8. 实验脚本入口

- 主 SNN A/B：`scripts_flow/main_snn.py`
- 基线对比：`scripts_flow/compare_snn_vs_ospf.py`
- 路由灰度（无前端，时变拓扑轨迹输入）：`scripts_flow/run_routing_shadow.py`
- 路由灰度（直接读取 new_huan 当前拓扑矩阵）：`scripts_flow/run_new_huan_routing_compare.py`
- 统计评估：`scripts_flow/paper_stat_eval*.py`
- 时延分解：`scripts_flow/paper_delay_eval_parallel.py`
- 消融：`scripts_flow/paper_ablation_eval.py`
- 开销：`scripts_flow/overhead_eval.py`
- 稳健性：`scripts_flow/robustness_grid_eval.py`

示例：

```bash
python scripts_flow/run_routing_shadow.py \
  --trace /path/to/topology_trace.jsonl \
  --nodes 300 \
  --snn-mode snn_event_dv \
  --out run_dir/routing_shadow_steps.csv \
  --out-agg run_dir/routing_shadow_summary.csv
```

```bash
sudo -n python3 scripts_flow/run_new_huan_routing_compare.py \
  --redis-host 172.17.0.1 \
  --matrix-key net:topology:matrix \
  --nodes 300 \
  --steps 120 \
  --dt 1.0 \
  --out run_dir/new_huan_live_steps.csv \
  --out-agg run_dir/new_huan_live_summary.csv
```

## 9. 模型性质说明

当前公式属于“机制驱动 + 工程可调”建模：

- 非纯理论最优控制推导；
- 通过 ablation / 多种子统计验证有效性；
- 可继续替换为更强的可学习参数化（例如归一化、多目标拉格朗日、策略梯度形式）。
