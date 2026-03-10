#!/usr/bin/env python3
import argparse
import json
import os
import random
import select
import socket
import subprocess
import time


def sh(cmd):
    return subprocess.run(cmd, text=True, capture_output=True, check=False)


class DistAgent:
    def __init__(self, cfg):
        self.cfg = cfg
        self.node_id = int(cfg["node_id"])
        self.group = cfg.get("group", "239.255.50.51")
        self.port = int(cfg.get("port", 50051))
        self.route_prefix = cfg.get("route_prefix", "10.255.0.0/16")
        self.send_period = float(cfg.get("send_period_s", 1.0))
        self.event_max_period = float(cfg.get("event_max_period_s", max(2.0, self.send_period * 6.0)))
        self.event_delta_threshold = float(cfg.get("event_delta_threshold", 0.03))
        self.min_broadcast_gap = float(cfg.get("min_broadcast_gap_s", 0.2))
        self.hello_period = float(cfg.get("hello_period_s", 1.0))
        self.beacon_period = float(cfg.get("beacon_period_s", self.hello_period))
        self.ack_timeout = float(cfg.get("ack_timeout_s", 2.0))
        self.miss_down_k = int(cfg.get("miss_down_k", 2))
        self.ack_mode = str(cfg.get("ack_mode", "hybrid"))
        self.neighbor_establish_k = int(cfg.get("neighbor_establish_k", 2))
        self.discovery_batch_size = int(cfg.get("discovery_batch_size", 24))
        self.discovery_probe_min = int(cfg.get("discovery_probe_min", 2))
        self.dead_interval = float(cfg.get("dead_interval_s", 12.0))
        self.rejoin_boost_s = float(cfg.get("rejoin_boost_s", 8.0))
        self.rejoin_hello_period_s = float(cfg.get("rejoin_hello_period_s", min(self.hello_period, 0.2)))
        self.rejoin_beacon_period_s = float(cfg.get("rejoin_beacon_period_s", min(self.beacon_period, 0.2)))
        self.rejoin_probe_min = int(cfg.get("rejoin_probe_min", max(self.discovery_probe_min * 3, 8)))
        self.rejoin_ack_silence_s = float(cfg.get("rejoin_ack_silence_s", max(2.0, self.dead_interval * 0.5)))
        self.probe_backoff_base_s = float(cfg.get("probe_backoff_base_s", 0.5))
        self.probe_backoff_max_s = float(cfg.get("probe_backoff_max_s", 8.0))
        self.est_fast_down_s = float(cfg.get("est_fast_down_s", 1.5))
        self.exploratory_s = float(cfg.get("exploratory_s", 12.0))
        self.safety_hold_s = float(cfg.get("safety_hold_s", 5.0))
        self.safety_rx_rate_threshold = float(cfg.get("safety_rx_rate_threshold", 1200.0))
        self.diag_period = float(cfg.get("diag_period_s", 5.0))
        self.full_period = float(cfg.get("full_period_s", 10.0))
        self.route_ttl = float(cfg.get("route_ttl_s", 20.0))
        self.hyst = float(cfg.get("hysteresis", 0.3))
        self.table = int(cfg.get("route_table", 110))
        self.metric_scale = float(cfg.get("metric_scale", 4.0))
        self.beta_s = float(cfg.get("beta_s", 1.0))
        self.min_hold = float(cfg.get("min_hold_s", 2.0))
        self.link_stat_period = float(cfg.get("link_stat_period_s", 1.0))
        self.neighbors = {int(x["peer_id"]): x for x in cfg["neighbors"]}
        self.dst_ip = {int(k): v for k, v in cfg["dst_ip_map"].items()}

        self.routes = {self.node_id: {"nh": self.node_id, "cost": 0.0, "ts": time.time()}}
        self.last_switch = {}
        self.last_from = {}
        self.nei_metric = {nid: 0.0 for nid in self.neighbors}
        self.nei_state = {
            nid: {
                "state": "init",
                "hello_rx_ok": 0,
                "hello_ack_ok": 0,
                "ever_up": False,
                "last_hello_rx": 0.0,
                "last_ack_rx": 0.0,
                "rtt_ema": 0.0,
                "loss_ema": 0.0,
                "miss_consec": 0,
                "probe_fail": 0,
                "next_probe_ts": 0.0,
            }
            for nid in self.neighbors
        }
        self.pending_acks = {}
        self.ack_tx = 0
        self.ack_rx = 0
        self.hello_tx = 0
        self.adv_tx = 0
        self.adv_rx = 0
        self.hello_rx = 0
        self.route_updates_since_diag = 0
        self.last_sent_seq = 0
        self.changed = True
        self.next_send = time.time()
        self.next_hello = 10**12
        self.next_beacon = time.time()
        self.next_full = time.time() + self.full_period
        self.next_diag = time.time() + self.diag_period
        self.start_ts = time.time()
        self.last_broadcast_metric = 0.0
        self.last_send_ts = 0.0
        self.rejoin_active = False
        self.rejoin_until = 0.0
        self.rejoin_reason = ""
        self.mode = "exploratory"
        self.safety_until = 0.0
        self.rx_window_sec = int(time.time())
        self.rx_window_cnt = 0

        self.stats_prev = {}
        self.last_stat_ts = 0.0
        self.last_util = 0.0
        self.last_drop = 0.0
        self.v = 0.0
        self.spike_ema = 0.0
        self.S = 0.0

        self.recv_sock = None
        self.send_sock = {}

    def _ack_enabled(self):
        if self.ack_mode == "always":
            return True
        if self.ack_mode == "never":
            return False
        if self.rejoin_active:
            return True
        if self.mode in ("exploratory", "safety"):
            return True
        return False

    def _on_rx_msg(self):
        now_s = int(time.time())
        if now_s != self.rx_window_sec:
            self.rx_window_sec = now_s
            self.rx_window_cnt = 0
        self.rx_window_cnt += 1
        if self.mode != "safety" and self.rx_window_cnt >= self.safety_rx_rate_threshold:
            self.mode = "safety"
            self.safety_until = time.time() + self.safety_hold_s

    def _update_mode(self):
        now = time.time()
        if self.mode == "safety":
            if now < self.safety_until:
                return
            self.mode = "exploratory" if (now - self.start_ts) < self.exploratory_s else "laminar"
            return
        if (now - self.start_ts) >= self.exploratory_s and not self.rejoin_active:
            self.mode = "laminar"
        else:
            self.mode = "exploratory"

    def _read_link_stats(self):
        now = time.time()
        if now - self.last_stat_ts < self.link_stat_period:
            return self.last_util, self.last_drop
        util = 0.0
        drop = 0.0
        established = [nid for nid in self.neighbors if self.nei_state.get(nid, {}).get("state") == "established"]
        scan_ids = established if established else list(self.neighbors.keys())
        for nid in scan_ids:
            nb = self.neighbors[nid]
            iface = nb["iface"]
            rx_b = int(open(f"/sys/class/net/{iface}/statistics/rx_bytes", "r", encoding="utf-8").read().strip())
            tx_b = int(open(f"/sys/class/net/{iface}/statistics/tx_bytes", "r", encoding="utf-8").read().strip())
            rx_d = int(open(f"/sys/class/net/{iface}/statistics/rx_dropped", "r", encoding="utf-8").read().strip())
            tx_d = int(open(f"/sys/class/net/{iface}/statistics/tx_dropped", "r", encoding="utf-8").read().strip())
            cur = (rx_b, tx_b, rx_d, tx_d)
            prev = self.stats_prev.get(iface)
            self.stats_prev[iface] = cur
            if not prev:
                continue
            d_b = max(0, (rx_b - prev[0]) + (tx_b - prev[1]))
            d_d = max(0, (rx_d - prev[2]) + (tx_d - prev[3]))
            util += min(1.0, d_b / 1_000_000.0)
            drop += min(1.0, d_d / 10.0)
        n = max(1, len(scan_ids))
        self.last_util = util / n
        self.last_drop = drop / n
        self.last_stat_ts = now
        return self.last_util, self.last_drop

    def _update_snn_metric(self):
        util, drop = self._read_link_stats()
        drive = min(1.0, util + drop)
        self.v = 0.85 * self.v + drive
        spike = 1.0 if self.v >= 1.0 else 0.0
        if spike > 0:
            self.v = 0.0
        self.spike_ema = 0.9 * self.spike_ema + 0.1 * spike
        kappa = min(1.0, 0.55 * self.spike_ema + 0.25 * util + 0.20 * drop)
        self.S = 0.78 * self.S + 0.22 * kappa
        return self.S

    def _ensure_policy(self):
        sh(["ip", "route", "flush", "table", str(self.table)])
        sh(["ip", "rule", "add", "pref", "110", "to", self.route_prefix, "lookup", str(self.table)])

    def _setup_sockets(self):
        self.recv_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        self.recv_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.recv_sock.bind(("0.0.0.0", self.port))
        for nid, nb in self.neighbors.items():
            local_ip = nb["local_ip"]
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
            s.bind((local_ip, 0))
            self.send_sock[nid] = s

    def _payload_for_neighbor(self, peer):
        entries = []
        now = time.time()
        for dst, r in self.routes.items():
            if int(dst) == self.node_id:
                entries.append({"d": int(dst), "c": 0.0})
                continue
            if now - r["ts"] > self.route_ttl:
                continue
            # poison-reverse for neighbor peer
            if int(r["nh"]) == int(peer):
                entries.append({"d": int(dst), "c": 1e9})
            else:
                entries.append({"d": int(dst), "c": round(float(r["cost"]), 6)})
        return {
            "t": "adv",
            "nid": self.node_id,
            "seq": self.last_sent_seq,
            "m": round(float(self.S), 6),
            "r": entries,
        }

    def _update_neighbor_state(self, nid):
        now = time.time()
        ns = self.nei_state[nid]
        prev = ns["state"]
        if ns.get("ever_up", False) and (now - ns.get("last_hello_rx", 0.0)) > self.est_fast_down_s:
            ns["state"] = "down"
            if prev != "down":
                self._on_neighbor_down(nid)
                self._enter_rejoin(f"neighbor_down_{nid}")
            return
        if ns.get("ever_up", False) and ns.get("miss_consec", 0) >= self.miss_down_k:
            ns["state"] = "down"
            if prev != "down":
                self._on_neighbor_down(nid)
                self._enter_rejoin(f"neighbor_down_{nid}")
            return
        age = now - max(ns["last_hello_rx"], ns["last_ack_rx"], self.last_from.get(nid, 0.0))
        if ns.get("ever_up", False) and age > self.dead_interval:
            ns["state"] = "down"
        elif ns.get("ever_up", False) and age > max(1.0, self.dead_interval * 0.5):
            ns["state"] = "suspect"
        elif ns["hello_rx_ok"] >= self.neighbor_establish_k and ns["hello_ack_ok"] >= self.neighbor_establish_k:
            ns["state"] = "established"
            ns["ever_up"] = True
        else:
            ns["state"] = "init"
        if ns.get("ever_up", False) and ns["state"] == "down" and prev != "down":
            self._on_neighbor_down(nid)
            self._enter_rejoin(f"neighbor_down_{nid}")

    def _on_neighbor_down(self, nid):
        self.last_from.pop(nid, None)
        self.nei_metric[nid] = 1.0
        for dst, r in list(self.routes.items()):
            if dst == self.node_id:
                continue
            if int(r.get("nh", -1)) == nid:
                self.routes.pop(dst, None)
                self._del_route(dst)
                self.changed = True

    def _enter_rejoin(self, reason):
        now = time.time()
        self.rejoin_active = True
        self.rejoin_until = max(self.rejoin_until, now + self.rejoin_boost_s)
        self.rejoin_reason = reason

    def _maybe_exit_rejoin(self):
        now = time.time()
        if not self.rejoin_active:
            return
        if now < self.rejoin_until:
            return
        est = 0
        for ns in self.nei_state.values():
            if ns["state"] == "established":
                est += 1
        if est > 0:
            self.rejoin_active = False
            self.rejoin_reason = ""

    def _send_ack(self, peer, ack_seq, ack_t):
        s = self.send_sock.get(peer)
        if s is None:
            return
        peer_ip = self.neighbors[peer]["peer_ip"]
        b = json.dumps(
            {"t": "ack", "nid": self.node_id, "ack_t": ack_t, "ack_seq": int(ack_seq), "ts": time.time()},
            separators=(",", ":"),
        ).encode("utf-8")
        s.sendto(b, (peer_ip, self.port))

    def _send_hello_all(self):
        self.last_sent_seq += 1
        seq = self.last_sent_seq
        now = time.time()
        peer_ids = list(self.send_sock.keys())
        established = [nid for nid in peer_ids if self.nei_state[nid]["state"] == "established"]
        others = []
        for nid in peer_ids:
            if nid in established:
                continue
            ns = self.nei_state[nid]
            if now >= float(ns.get("next_probe_ts", 0.0)):
                others.append(nid)
        need = max(0, self.discovery_batch_size - len(established))
        if others:
            # Keep probing non-established neighbors; otherwise discovery can stall forever.
            need = max(need, self.discovery_probe_min)
            if self.rejoin_active:
                need = max(need, self.rejoin_probe_min)
        sample = random.sample(others, min(need, len(others)))
        targets = list(dict.fromkeys(established + sample))
        for nid in targets:
            s = self.send_sock[nid]
            peer_ip = self.neighbors[nid]["peer_ip"]
            msg = {"t": "hello", "nid": self.node_id, "seq": seq, "m": round(float(self.S), 6), "ts": now}
            b = json.dumps(msg, separators=(",", ":")).encode("utf-8")
            s.sendto(b, (peer_ip, self.port))
            self.pending_acks[(nid, seq, "hello")] = now
            self.ack_tx += 1
            self.hello_tx += 1
        hp = self.rejoin_hello_period_s if self.rejoin_active else self.hello_period
        self.next_hello = now + hp

    def _send_adv_to_peer(self, nid, full=True):
        s = self.send_sock.get(nid)
        if s is None:
            return
        self.last_sent_seq += 1
        now = time.time()
        msg = self._payload_for_neighbor(nid)
        if not full and not self.changed:
            msg["r"] = []
        ack_req = self._ack_enabled()
        msg["ra"] = 1 if ack_req else 0
        b = json.dumps(msg, separators=(",", ":")).encode("utf-8")
        peer_ip = self.neighbors[nid]["peer_ip"]
        s.sendto(b, (peer_ip, self.port))
        if ack_req:
            self.pending_acks[(nid, self.last_sent_seq, "adv")] = now
            self.ack_tx += 1
        self.adv_tx += 1

    def _sweep_pending_acks(self):
        now = time.time()
        drop = []
        for k, ts in self.pending_acks.items():
            if now - ts > self.ack_timeout:
                peer = k[0]
                ns = self.nei_state.get(peer)
                if ns is not None:
                    ns["loss_ema"] = 0.9 * ns["loss_ema"] + 0.1
                    ns["probe_fail"] += 1
                    backoff = min(self.probe_backoff_max_s, self.probe_backoff_base_s * (2 ** max(0, ns["probe_fail"] - 1)))
                    ns["next_probe_ts"] = now + backoff
                    if ns.get("ever_up", False):
                        ns["miss_consec"] += 1
                    self._update_neighbor_state(peer)
                drop.append(k)
        for k in drop:
            self.pending_acks.pop(k, None)

    def _broadcast(self, full=False):
        # In laminar mode beacon traffic already provides keep-alive; avoid duplicate heartbeats.
        if not full and not self.changed and self.mode == "laminar" and not self.rejoin_active:
            now = time.time()
            self.next_send = now + max(self.min_broadcast_gap, self.send_period)
            return
        self.last_sent_seq += 1
        now = time.time()
        for nid, s in self.send_sock.items():
            self._update_neighbor_state(nid)
            if self.nei_state[nid]["state"] != "established":
                continue
            msg = self._payload_for_neighbor(nid)
            if not full and not self.changed:
                # incremental control: send only node metric heartbeat
                msg["r"] = []
            ack_req = self._ack_enabled()
            msg["ra"] = 1 if ack_req else 0
            b = json.dumps(msg, separators=(",", ":")).encode("utf-8")
            peer_ip = self.neighbors[nid]["peer_ip"]
            s.sendto(b, (peer_ip, self.port))
            if ack_req:
                self.pending_acks[(nid, self.last_sent_seq, "adv")] = now
                self.ack_tx += 1
            self.adv_tx += 1
        self.changed = False
        self.last_send_ts = now
        strength = max(0.08, float(self.S + self.spike_ema))
        dyn_period = self.send_period / strength
        dyn_period = max(self.min_broadcast_gap, min(self.event_max_period, dyn_period))
        self.next_send = now + dyn_period
        if full:
            self.next_full = now + self.full_period

    def _link_cost(self, nid):
        m2 = self.nei_metric.get(nid, 0.0)
        return 1.0 + self.metric_scale * (self.beta_s * self.S + self.beta_s * m2)

    def _set_route(self, dst, nh):
        if dst == self.node_id:
            return
        if nh not in self.neighbors:
            return
        nb = self.neighbors[nh]
        dev = nb["iface"]
        via = nb["peer_ip"]
        dip = self.dst_ip.get(dst)
        if not dip:
            return
        sh(["ip", "-4", "route", "replace", f"{dip}/32", "via", via, "dev", dev, "table", str(self.table), "proto", "static", "metric", "5"])

    def _del_route(self, dst):
        if dst == self.node_id:
            return
        dip = self.dst_ip.get(dst)
        if not dip:
            return
        sh(["ip", "-4", "route", "del", f"{dip}/32", "table", str(self.table)])

    def _process_msg(self, msg):
        now = time.time()
        self._on_rx_msg()
        if msg.get("t") == "ack":
            nid = int(msg.get("nid", -1))
            ack_seq = int(msg.get("ack_seq", -1))
            ack_t = str(msg.get("ack_t", ""))
            key = (nid, ack_seq, ack_t)
            if key in self.pending_acks:
                sent_ts = self.pending_acks.pop(key)
                self.ack_rx += 1
                ns = self.nei_state.get(nid)
                if ns is not None:
                    rtt = max(0.0, now - sent_ts)
                    ns["rtt_ema"] = 0.8 * ns["rtt_ema"] + 0.2 * rtt
                    ns["loss_ema"] = 0.9 * ns["loss_ema"]
                    ns["last_ack_rx"] = now
                    ns["miss_consec"] = 0
                    ns["probe_fail"] = 0
                    ns["next_probe_ts"] = now
                    if ack_t == "hello" or ack_t == "adv":
                        ns["hello_ack_ok"] += 1
                    self._update_neighbor_state(nid)
            return

        nid = int(msg.get("nid", -1))
        if nid == self.node_id or nid not in self.neighbors:
            return
        ns = self.nei_state[nid]
        ns["last_hello_rx"] = now
        ns["miss_consec"] = 0
        ns["probe_fail"] = 0
        ns["next_probe_ts"] = now
        if msg.get("t") == "hello":
            self.hello_rx += 1
            ns["hello_rx_ok"] += 1
            self._send_ack(nid, int(msg.get("seq", 0)), "hello")
            self._update_neighbor_state(nid)
            if self.nei_state[nid]["state"] != "established":
                # Assist rejoin: provide a full snapshot hint immediately.
                self._send_adv_to_peer(nid, full=True)
            return

        if msg.get("t") != "adv":
            return

        self.adv_rx += 1
        ns["hello_rx_ok"] += 1
        ns["hello_ack_ok"] += 1
        self.last_from[nid] = now
        self.nei_metric[nid] = float(msg.get("m", 0.0))
        if int(msg.get("ra", 0)) == 1 or self._ack_enabled():
            self._send_ack(nid, int(msg.get("seq", 0)), "adv")
        self._update_neighbor_state(nid)
        if self.nei_state[nid]["state"] != "established":
            return
        link_c = self._link_cost(nid)
        for ent in msg.get("r", []):
            dst = int(ent["d"])
            adv_c = float(ent["c"])
            if adv_c >= 1e8:
                continue
            if dst == self.node_id:
                continue
            new_c = link_c + adv_c
            cur = self.routes.get(dst)
            if not cur:
                self.routes[dst] = {"nh": nid, "cost": new_c, "ts": now}
                self._set_route(dst, nid)
                self.last_switch[dst] = now
                self.changed = True
                self.route_updates_since_diag += 1
                continue
            same = int(cur["nh"]) == nid
            better = new_c + self.hyst < float(cur["cost"])
            hold_ok = (now - self.last_switch.get(dst, 0.0)) >= self.min_hold
            if same or (better and hold_ok):
                if int(cur["nh"]) != nid:
                    self.last_switch[dst] = now
                cur["nh"] = nid
                cur["cost"] = new_c
                cur["ts"] = now
                self._set_route(dst, nid)
                self.changed = True
                self.route_updates_since_diag += 1

    def _expire(self):
        now = time.time()
        for dst, r in list(self.routes.items()):
            if dst == self.node_id:
                continue
            if now - float(r["ts"]) > self.route_ttl:
                self.routes.pop(dst, None)
                self._del_route(dst)
                self.changed = True
        dead = [nid for nid, t in self.last_from.items() if now - t > self.dead_interval]
        for nid in dead:
            del self.last_from[nid]
            self.nei_metric[nid] = 1.0
            for dst, r in list(self.routes.items()):
                if int(r["nh"]) == nid and dst != self.node_id:
                    self.routes.pop(dst, None)
                    self._del_route(dst)
                    self.changed = True
        for nid in self.neighbors:
            self._update_neighbor_state(nid)

    def _send_adv_beacon(self):
        now = time.time()
        peer_ids = list(self.send_sock.keys())
        established = [nid for nid in peer_ids if self.nei_state[nid]["state"] == "established"]
        others = [nid for nid in peer_ids if nid not in established]
        targets = []
        if established:
            targets.extend(established)
        if others:
            need = self.discovery_probe_min
            if self.rejoin_active:
                need = max(need, self.rejoin_probe_min)
            sample = random.sample(others, min(need, len(others)))
            targets.extend(sample)
        targets = list(dict.fromkeys(targets))
        for nid in targets:
            self._send_adv_to_peer(nid, full=False)
        bp = self.rejoin_beacon_period_s if self.rejoin_active else self.beacon_period
        self.next_beacon = now + bp

    def run(self):
        self._ensure_policy()
        self._setup_sockets()
        self._send_adv_beacon()
        self._broadcast(full=True)
        while True:
            self._update_snn_metric()
            r, _, _ = select.select([self.recv_sock], [], [], 0.2)
            if r:
                data, _ = self.recv_sock.recvfrom(65535)
                try:
                    msg = json.loads(data.decode("utf-8"))
                    self._process_msg(msg)
                except Exception:
                    pass
            self._expire()
            self._sweep_pending_acks()
            now = time.time()
            if self.ack_rx == 0 and (now - self.start_ts) > self.rejoin_ack_silence_s:
                self._enter_rejoin("ack_silence")
            self._maybe_exit_rejoin()
            self._update_mode()
            if now >= self.next_beacon:
                self._send_adv_beacon()
            metric = float(self.S + self.spike_ema + 0.5 * self.v)
            delta = abs(metric - self.last_broadcast_metric)
            event_due = delta >= self.event_delta_threshold and (now - self.last_send_ts) >= self.min_broadcast_gap
            if now >= self.next_send or event_due:
                self.last_broadcast_metric = metric
                self._broadcast(full=False)
            if now >= self.next_full:
                self._broadcast(full=True)
            if now >= self.next_diag:
                est = 0
                suspect = 0
                down = 0
                for ns in self.nei_state.values():
                    st = ns["state"]
                    if st == "established":
                        est += 1
                    elif st == "suspect":
                        suspect += 1
                    elif st == "down":
                        down += 1
                ack_ratio = (self.ack_rx / self.ack_tx) if self.ack_tx > 0 else 0.0
                print(
                    "[diag] "
                    f"ts={now:.3f} "
                    f"node={self.node_id} routes={len(self.routes)} est={est} suspect={suspect} down={down} "
                    f"ack_rx={self.ack_rx} ack_tx={self.ack_tx} ack_ratio={ack_ratio:.3f} "
                    f"hello_tx={self.hello_tx} hello_rx={self.hello_rx} "
                    f"adv_tx={self.adv_tx} adv_rx={self.adv_rx} "
                    f"route_updates={self.route_updates_since_diag} "
                    f"rejoin={1 if self.rejoin_active else 0} reason={self.rejoin_reason or 'na'} "
                    f"mode={self.mode} "
                    f"S={self.S:.3f} spike={self.spike_ema:.3f}",
                    flush=True,
                )
                self.route_updates_since_diag = 0
                self.next_diag = now + self.diag_period


def main():
    ap = argparse.ArgumentParser(description="Distributed SNN-SRA agent (broadcast + RIP-like).")
    ap.add_argument("--config", required=True)
    args = ap.parse_args()
    cfg = json.loads(open(args.config, "r", encoding="utf-8").read())
    DistAgent(cfg).run()


if __name__ == "__main__":
    main()
