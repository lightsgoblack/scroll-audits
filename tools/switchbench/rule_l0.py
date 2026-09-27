"""SwitchBench v1 adjacent-wrap CT rule (shared by the ladder tuning and the corpus confirmation).

The rule is v0's (confirm.event_profile_check) evaluated on level-0 (2.4 um) profiles, with one added
knob, mid_bias: a bright layer strictly between the two ends is detected at the threshold
thr - mid_bias * (hi - lo), so a faint middle sheet also blocks a pass (mid_bias = 0 is v0's rule).
Profile coordinates t are level-2 voxels along a unit direction; ends at t0, t1; local spacing s.
Window = [min(t0,t1) - 3 s, max(t0,t1) + 3 s], as in v0. Returns True / False / None (undecided).
"""
from __future__ import annotations

import numpy as np
from scipy.ndimage import gaussian_filter1d

CONTRAST_MIN = 15.0  # v0: undecided if the smoothed window has less contrast than this (uint8 units)


def runs(mask):
    out, i, n = [], 0, len(mask)
    while i < n:
        if mask[i]:
            j = i
            while j < n and mask[j]:
                j += 1
            out.append((i, j))
            i = j
        else:
            i += 1
    return out


def window(t, v, t0, t1, s):
    lo_t, hi_t = min(t0, t1), max(t0, t1)
    m = (t >= lo_t - 3 * s - 1e-9) & (t <= hi_t + 3 * s + 1e-9)
    return t[m], v[m]


def smooth(v, sigma, step):
    return gaussian_filter1d(v, sigma / step)


def evaluate(t, vs, t0, t1, s, end_zone, min_dark, q, mid_bias, step):
    """Apply the rule to an already windowed and smoothed profile (t, vs)."""
    lo_t, hi_t = min(t0, t1), max(t0, t1)
    lo, hi = np.percentile(vs, q), np.percentile(vs, 100 - q)
    if hi - lo < CONTRAST_MIN:
        return None
    thr = (lo + hi) / 2
    thr_mid = thr - mid_bias * (hi - lo)
    ez = max(end_zone * s, step / 2 + 1e-6)
    zl = (t >= lo_t - ez) & (t <= lo_t + ez)
    zh = (t >= hi_t - ez) & (t <= hi_t + ez)
    if not zl.any() or not zh.any():
        return None
    bright_lo = vs[zl].max() > thr
    bright_hi = vs[zh].max() > thr
    inside = (t >= lo_t) & (t <= hi_t)
    ti, vi = t[inside], vs[inside]
    if len(ti) < 2:
        return None
    dark = [(a, b) for a, b in runs(vi < thr) if (b - a) * step >= min_dark]
    mid = [(a, b) for a, b in runs(vi >= thr_mid) if ti[a] > lo_t + ez and ti[b - 1] < hi_t - ez]
    return bool(bright_lo and bright_hi and len(dark) == 1 and not mid)


def check(t, v, t0, t1, s, params, step):
    """Full rule on a raw profile: NaN guard (v0: > 10% NaN = undecided), window, smoothing, rule."""
    tw, vw = window(t, v, t0, t1, s)
    if len(vw) == 0 or np.isnan(vw).mean() > 0.1:
        return None
    vw = np.nan_to_num(vw, nan=np.nanmedian(vw))
    vs = smooth(vw, params["sigma"], step)
    return evaluate(tw, vs, t0, t1, s, params["end_zone"], params["min_dark"], params["q"],
                    params.get("mid_bias", 0.0), step)
