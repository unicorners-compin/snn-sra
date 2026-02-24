from collections import deque
import math


class SNNQueueNode:
    """Queue node with a lightweight LIF neuron for online stress estimation."""

    def __init__(
        self,
        node_id,
        service_rate=25,
        buffer_size=300,
        alpha=0.25,
        beta_I=8.0,
        T_d=1,
        tau_m=4.0,
        v_reset=0.0,
        v_th=1.0,
        refractory_steps=1,
        input_gain=1.6,
        spike_ema_decay=0.9,
        target_rate=0.08,
        homeostasis_lr=0.02,
        stress_mode="v1",
        stress_smooth_gain=6.0,
        stress_smooth_center=0.5,
    ):
        self.node_id = node_id
        self.service_rate = service_rate
        self.buffer_size = buffer_size
        self.alpha = alpha
        self.beta_I = beta_I
        self.T_d = T_d

        self.input_queue = deque()
        self.dropped_in_window = 0
        self.total_dropped = 0

        # SNN state
        self.tau_m = tau_m
        self.v_reset = v_reset
        self.v_th = v_th
        self.refractory_steps = refractory_steps
        self.input_gain = input_gain
        self.spike_ema_decay = spike_ema_decay
        self.target_rate = target_rate
        self.homeostasis_lr = homeostasis_lr
        self.stress_mode = stress_mode
        self.stress_smooth_gain = stress_smooth_gain
        self.stress_smooth_center = stress_smooth_center

        self.v = v_reset
        self.refractory_left = 0
        self.last_spike = 0
        self.spike_rate_ema = 0.0

        # Structural stress used by routing.
        self.S = 0.0
        self.recent_loss_ratio = 0.0
        self.last_queue_load = 0.0

    def receive_packet(self, packet):
        if len(self.input_queue) < self.buffer_size:
            self.input_queue.append(packet)
            return True
        self.dropped_in_window += 1
        self.total_dropped += 1
        return False

    def notify_link_failure_drop(self):
        # Convert physical failure to a strong local stress pulse.
        self.dropped_in_window += self.service_rate
        self.total_dropped += 1

    def _update_neuron(self, drive):
        if self.refractory_left > 0:
            self.refractory_left -= 1
            self.last_spike = 0
        else:
            dv = (-(self.v - self.v_reset) + self.input_gain * drive) / max(self.tau_m, 1e-6)
            self.v += dv
            if self.v >= self.v_th:
                self.last_spike = 1
                self.v = self.v_reset
                self.refractory_left = self.refractory_steps
            else:
                self.last_spike = 0

        self.spike_rate_ema = (
            self.spike_ema_decay * self.spike_rate_ema + (1.0 - self.spike_ema_decay) * float(self.last_spike)
        )
        # Keep firing rate around a target band to avoid network-wide saturation.
        self.v_th += self.homeostasis_lr * (self.spike_rate_ema - self.target_rate)
        self.v_th = min(2.0, max(0.4, self.v_th))

    def process_and_forward(self, step_k):
        forwarded = []
        for _ in range(min(len(self.input_queue), self.service_rate)):
            if self.input_queue:
                forwarded.append(self.input_queue.popleft())

        queue_load = len(self.input_queue) / max(self.buffer_size, 1)
        loss_intensity = self.dropped_in_window / max(self.service_rate * self.T_d, 1)
        drive = min(1.0, queue_load + loss_intensity)
        self._update_neuron(drive)

        if step_k % self.T_d == 0:
            self.recent_loss_ratio = min(1.0, loss_intensity)
            self.last_queue_load = queue_load
            raw = 0.55 * self.spike_rate_ema + 0.25 * queue_load + 0.20 * self.recent_loss_ratio
            if self.stress_mode == "v2_sigmoid":
                z = self.stress_smooth_gain * (raw - self.stress_smooth_center)
                kappa = 1.0 / (1.0 + math.exp(-z))
            else:
                kappa = min(1.0, raw)
            self.S = (1.0 - self.alpha) * self.S + self.alpha * kappa
            self.dropped_in_window = 0

        return forwarded
