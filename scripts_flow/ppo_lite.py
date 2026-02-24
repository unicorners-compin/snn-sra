import math

import numpy as np


def masked_softmax(logits):
    x = np.asarray(logits, dtype=float)
    if x.size == 0:
        return x
    m = np.max(x)
    z = np.exp(x - m)
    s = np.sum(z)
    if s <= 1e-12:
        return np.ones_like(z) / float(z.size)
    return z / s


class PPOLitePolicy:
    """
    Minimal PPO-style policy for discrete masked actions.
    The policy is linear over per-action features:
      logits_a = w^T * feat_a
    """

    def __init__(
        self,
        n_features,
        seed=7,
        lr=0.03,
        clip_eps=0.2,
        update_interval=256,
        epochs=3,
        max_grad_norm=1.0,
    ):
        self.n_features = int(n_features)
        self.lr = float(lr)
        self.clip_eps = float(clip_eps)
        self.update_interval = int(update_interval)
        self.epochs = int(epochs)
        self.max_grad_norm = float(max_grad_norm)

        self.rng = np.random.default_rng(seed)
        self.w = self.rng.normal(loc=0.0, scale=0.05, size=(self.n_features,))
        self.buffer = []
        self.update_count = 0

    def action_probs(self, feat_mat):
        logits = np.asarray(feat_mat, dtype=float) @ self.w
        probs = masked_softmax(logits)
        return logits, probs

    def select_action(self, feat_mat, greedy=False):
        _, probs = self.action_probs(feat_mat)
        if probs.size == 0:
            return None, None, probs
        if greedy:
            a = int(np.argmax(probs))
        else:
            a = int(self.rng.choice(probs.size, p=probs))
        logp = float(math.log(max(probs[a], 1e-12)))
        return a, logp, probs

    def record(self, feat_mat, action_idx, old_logp, reward):
        self.buffer.append(
            {
                "feat_mat": np.asarray(feat_mat, dtype=float),
                "action": int(action_idx),
                "old_logp": float(old_logp),
                "reward": float(reward),
            }
        )
        if len(self.buffer) >= self.update_interval:
            self.update()

    def _grad_logpi(self, feat_mat, probs, action):
        expected = probs @ feat_mat
        return feat_mat[action] - expected

    def update(self):
        if not self.buffer:
            return
        rewards = np.asarray([x["reward"] for x in self.buffer], dtype=float)
        adv = rewards - float(np.mean(rewards))
        std = float(np.std(adv))
        if std > 1e-8:
            adv = adv / std

        idxs = np.arange(len(self.buffer))
        for _ in range(self.epochs):
            self.rng.shuffle(idxs)
            for i in idxs:
                sample = self.buffer[i]
                feat_mat = sample["feat_mat"]
                a = sample["action"]
                old_logp = sample["old_logp"]
                a_adv = float(adv[i])

                _, probs = self.action_probs(feat_mat)
                if probs.size == 0:
                    continue
                new_logp = float(math.log(max(probs[a], 1e-12)))
                ratio = float(math.exp(new_logp - old_logp))

                # PPO clipped surrogate coefficient (for gradient-ascent form).
                if a_adv >= 0.0 and ratio > 1.0 + self.clip_eps:
                    coeff = 0.0
                elif a_adv < 0.0 and ratio < 1.0 - self.clip_eps:
                    coeff = 0.0
                else:
                    coeff = a_adv * ratio
                if abs(coeff) <= 1e-12:
                    continue

                grad_logpi = self._grad_logpi(feat_mat, probs, a)
                grad = coeff * grad_logpi
                gnorm = float(np.linalg.norm(grad))
                if gnorm > self.max_grad_norm:
                    grad = grad * (self.max_grad_norm / max(gnorm, 1e-12))
                self.w = self.w + self.lr * grad

        self.buffer = []
        self.update_count += 1

    def finalize(self):
        self.update()
