#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdbool.h>
#include <inttypes.h>

#include <rte_eal.h>
#include <rte_ethdev.h>
#include <rte_ip.h>
#include <rte_malloc.h>
#include <rte_mbuf.h>
#include <rte_cycles.h>
#include <rte_branch_prediction.h>

#define RX_DESC 1024
#define TX_DESC 1024
#define NUM_MBUFS 8191
#define MBUF_CACHE_SIZE 256
#define BURST_SIZE 32

#define MAX_PORTS 8
#define MAX_DESTS 4096

/*
 * 简化版 SNN-SRA 状态：
 * S <- (1-alpha)*S + alpha*kappa
 * kappa 由队列负载/丢包/“spike”代理量组合得到。
 */
struct snn_node_state {
    float S;
    float spike_rate_ema;
    float recent_loss_ratio;
    float queue_load_ema;
};

struct route_entry {
    uint32_t dst_ip;
    uint16_t out_port;
    float score;
    bool valid;
};

struct app_ctx {
    struct rte_mempool *mbuf_pool;
    uint16_t nb_ports;
    struct snn_node_state nodes[MAX_PORTS];
    struct route_entry rt[MAX_DESTS];

    uint64_t rx_pkts[MAX_PORTS];
    uint64_t drop_pkts[MAX_PORTS];
    uint64_t tx_pkts[MAX_PORTS];
    uint64_t last_rx_pkts[MAX_PORTS];
    uint64_t last_drop_pkts[MAX_PORTS];
};

static inline float
clampf(float v, float lo, float hi)
{
    if (v < lo) return lo;
    if (v > hi) return hi;
    return v;
}

static int
port_init(uint16_t port, struct rte_mempool *pool)
{
    struct rte_eth_conf port_conf = {0};
    const uint16_t rx_rings = 1, tx_rings = 1;
    int ret;

    if (!rte_eth_dev_is_valid_port(port))
        return -1;

    ret = rte_eth_dev_configure(port, rx_rings, tx_rings, &port_conf);
    if (ret < 0) return ret;

    ret = rte_eth_rx_queue_setup(port, 0, RX_DESC, rte_eth_dev_socket_id(port), NULL, pool);
    if (ret < 0) return ret;

    ret = rte_eth_tx_queue_setup(port, 0, TX_DESC, rte_eth_dev_socket_id(port), NULL);
    if (ret < 0) return ret;

    ret = rte_eth_dev_start(port);
    if (ret < 0) return ret;

    rte_eth_promiscuous_enable(port);
    return 0;
}

static inline uint32_t
hash_dst(uint32_t dst_ip)
{
    return (dst_ip * 2654435761u) % MAX_DESTS;
}

static float
edge_cost(struct app_ctx *ctx, uint16_t in_port, uint16_t out_port, uint32_t dst_ip)
{
    const float base = 1.0f;
    const float beta_s = 8.0f;      /* 对应 Python 里的 beta_s */
    const float beta_h = 0.55f;     /* hop hint 的简化代理 */
    const float beta_f = 0.8f;      /* spike 影响权重 */
    const float beta_burst = 0.9f;  /* burst 影响权重 */

    float s_term = ctx->nodes[in_port].S + ctx->nodes[out_port].S;
    float spike_term = ctx->nodes[out_port].spike_rate_ema;
    float hop_hint = (float)((dst_ip ^ out_port) & 0x7) * 0.1f; /* 占位近似 */
    float burst_penalty = ctx->nodes[out_port].recent_loss_ratio;

    return base + beta_s * s_term + beta_h * hop_hint + beta_f * spike_term + beta_burst * burst_penalty;
}

static uint16_t
choose_next_hop(struct app_ctx *ctx, uint16_t in_port, uint32_t dst_ip)
{
    uint16_t best = UINT16_MAX;
    float best_score = 1e30f;

    for (uint16_t p = 0; p < ctx->nb_ports; p++) {
        if (p == in_port) continue;
        float score = edge_cost(ctx, in_port, p, dst_ip);
        if (score < best_score) {
            best_score = score;
            best = p;
        }
    }

    if (best == UINT16_MAX) return in_port;
    return best;
}

static void
update_control_plane(struct app_ctx *ctx)
{
    /*
     * 这里是“事件驱动 DV + 本地 SNN 打分”的最简原型：
     * 每轮基于当前 S/spike/loss 重算目的地址到出口端口映射。
     */
    for (int i = 0; i < MAX_DESTS; i++) {
        if (!ctx->rt[i].valid) continue;
        uint32_t dst = ctx->rt[i].dst_ip;
        uint16_t current = ctx->rt[i].out_port;
        uint16_t new_port = choose_next_hop(ctx, current % ctx->nb_ports, dst);
        ctx->rt[i].out_port = new_port;
        ctx->rt[i].score = edge_cost(ctx, current % ctx->nb_ports, new_port, dst);
    }
}

static void
update_node_state(struct app_ctx *ctx)
{
    const float alpha = 0.22f;
    const float ema_decay = 0.90f;

    for (uint16_t p = 0; p < ctx->nb_ports; p++) {
        uint64_t rx_delta = ctx->rx_pkts[p] - ctx->last_rx_pkts[p];
        uint64_t drop_delta = ctx->drop_pkts[p] - ctx->last_drop_pkts[p];

        ctx->last_rx_pkts[p] = ctx->rx_pkts[p];
        ctx->last_drop_pkts[p] = ctx->drop_pkts[p];

        float loss = 0.0f;
        if (rx_delta + drop_delta > 0)
            loss = (float)drop_delta / (float)(rx_delta + drop_delta);

        float q_proxy = clampf((float)rx_delta / 100000.0f, 0.0f, 1.0f);
        float spike = (q_proxy + loss > 0.7f) ? 1.0f : 0.0f;

        ctx->nodes[p].recent_loss_ratio = loss;
        ctx->nodes[p].queue_load_ema = ema_decay * ctx->nodes[p].queue_load_ema + (1.0f - ema_decay) * q_proxy;
        ctx->nodes[p].spike_rate_ema = ema_decay * ctx->nodes[p].spike_rate_ema + (1.0f - ema_decay) * spike;

        float kappa = clampf(
            0.55f * ctx->nodes[p].spike_rate_ema +
            0.25f * ctx->nodes[p].queue_load_ema +
            0.20f * ctx->nodes[p].recent_loss_ratio,
            0.0f, 1.0f
        );

        ctx->nodes[p].S = (1.0f - alpha) * ctx->nodes[p].S + alpha * kappa;
    }
}

static void
install_default_routes(struct app_ctx *ctx)
{
    memset(ctx->rt, 0, sizeof(ctx->rt));
    for (uint32_t i = 0; i < 256; i++) {
        uint32_t dst = rte_cpu_to_be_32((10u << 24) | i); /* 10.0.0.x */
        uint32_t idx = hash_dst(dst);
        ctx->rt[idx].dst_ip = dst;
        ctx->rt[idx].out_port = (uint16_t)(i % ctx->nb_ports);
        ctx->rt[idx].score = 0.0f;
        ctx->rt[idx].valid = true;
    }
}

static inline uint16_t
route_lookup(struct app_ctx *ctx, uint16_t in_port, uint32_t dst_ip)
{
    uint32_t idx = hash_dst(dst_ip);
    if (ctx->rt[idx].valid && ctx->rt[idx].dst_ip == dst_ip)
        return ctx->rt[idx].out_port;

    /* miss 时走本地 SNN 选择 */
    return choose_next_hop(ctx, in_port, dst_ip);
}

int
main(int argc, char **argv)
{
    int ret = rte_eal_init(argc, argv);
    if (ret < 0)
        rte_exit(EXIT_FAILURE, "EAL init failed\n");

    struct app_ctx *ctx = rte_zmalloc("snn_sra_ctx", sizeof(*ctx), 0);
    if (!ctx)
        rte_exit(EXIT_FAILURE, "ctx alloc failed\n");

    ctx->nb_ports = rte_eth_dev_count_avail();
    if (ctx->nb_ports < 2)
        rte_exit(EXIT_FAILURE, "need >= 2 ports\n");
    if (ctx->nb_ports > MAX_PORTS)
        ctx->nb_ports = MAX_PORTS;

    ctx->mbuf_pool = rte_pktmbuf_pool_create(
        "MBUF_POOL",
        NUM_MBUFS * ctx->nb_ports,
        MBUF_CACHE_SIZE,
        0,
        RTE_MBUF_DEFAULT_BUF_SIZE,
        rte_socket_id()
    );
    if (!ctx->mbuf_pool)
        rte_exit(EXIT_FAILURE, "mbuf pool create failed\n");

    for (uint16_t p = 0; p < ctx->nb_ports; p++) {
        if (port_init(p, ctx->mbuf_pool) < 0)
            rte_exit(EXIT_FAILURE, "port %" PRIu16 " init failed\n", p);
    }

    install_default_routes(ctx);

    printf("SNN-SRA DPDK prototype started. ports=%u\n", ctx->nb_ports);

    uint64_t hz = rte_get_timer_hz();
    uint64_t last_ctrl = rte_get_timer_cycles();
    const uint64_t ctrl_period = hz / 100; /* 10ms */

    struct rte_mbuf *pkts[BURST_SIZE];

    while (1) {
        for (uint16_t in_port = 0; in_port < ctx->nb_ports; in_port++) {
            uint16_t n_rx = rte_eth_rx_burst(in_port, 0, pkts, BURST_SIZE);
            if (unlikely(n_rx == 0))
                continue;

            ctx->rx_pkts[in_port] += n_rx;

            for (uint16_t i = 0; i < n_rx; i++) {
                struct rte_mbuf *m = pkts[i];
                struct rte_ether_hdr *eth = rte_pktmbuf_mtod(m, struct rte_ether_hdr *);
                if (eth->ether_type != rte_cpu_to_be_16(RTE_ETHER_TYPE_IPV4)) {
                    rte_pktmbuf_free(m);
                    continue;
                }

                struct rte_ipv4_hdr *ip = (struct rte_ipv4_hdr *)(eth + 1);
                uint16_t out_port = route_lookup(ctx, in_port, ip->dst_addr);

                uint16_t n_tx = rte_eth_tx_burst(out_port, 0, &m, 1);
                if (unlikely(n_tx == 0)) {
                    ctx->drop_pkts[in_port]++;
                    rte_pktmbuf_free(m);
                } else {
                    ctx->tx_pkts[out_port]++;
                }
            }
        }

        uint64_t now = rte_get_timer_cycles();
        if (unlikely(now - last_ctrl >= ctrl_period)) {
            update_node_state(ctx);
            update_control_plane(ctx);
            last_ctrl = now;
        }
    }

    return 0;
}
