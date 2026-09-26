"""Second, independent reference for wrap identity: numeric CT profiles (criteria: "either one plus a
numeric CT profile"). Only scalar intensity profiles are read; nothing is saved but the verdicts.

Event rule (C_event): along the normal at the post-switch vertex (on sheet B), between B (t=0) and the
pre-switch sheet A (t=t_A, located in B's verified stack), the smoothed CT profile must show both
sheets bright, exactly one dark gap between them and no bright layer between them (= adjacent wraps).
Negative rule (C_neg): every vertex of the run is sampled; the surface must sit on a bright layer at
>= NEG_MIN_ON of vertices with no off-layer streak longer than NEG_MAX_STREAK (a wrap change must cross a gap).
Rule constants were fixed on human ladder controls and verified runs (tune_ct.py, calib_onlayer.py,
calib_negrun.py) before any unverified event or negative was confirmed.
"""
from __future__ import annotations

import numpy as np
from scipy.ndimage import gaussian_filter1d

from . import ct, label

SIGMA = 2.0        # vx smoothing of the profile   (chosen on human ladder controls, tune_ct.py)
MIN_DARK = 2.0     # vx minimum dark-run length to count as a gap
END_ZONE = 0.1     # x spacing: bright runs touching this zone around an end belong to that sheet
ON_WIN = 0.1       # x spacing: on-layer window half-width (set on ladder controls, calib_onlayer.py)
Q = 30             # threshold = midpoint of the Q-th and (100-Q)-th percentiles of the +/-3 s profile


def _runs(mask):
    out, i = [], 0
    while i < len(mask):
        if mask[i]:
            j = i
            while j < len(mask) and mask[j]:
                j += 1
            out.append((i, j))
            i = j
        else:
            i += 1
    return out


def event_profile_check(p0, n, t_a, s, step=0.5):
    """Adjacent-wrap test between t=0 and t=t_a along p0 + t n. Returns (passed, detail)."""
    lo_t, hi_t = min(0.0, t_a), max(0.0, t_a)
    w0, w1 = lo_t - 3 * s, hi_t + 3 * s
    t, v = ct.profile(np.asarray(p0), np.asarray(n), w0, w1, step)
    if np.isnan(v).mean() > 0.1:
        return None, dict(reason="outside volume")
    v = np.nan_to_num(v, nan=np.nanmedian(v))
    vs = gaussian_filter1d(v, SIGMA / step)
    lo, hi = np.percentile(vs, Q), np.percentile(vs, 100 - Q)
    if hi - lo < 15:
        return None, dict(reason="no contrast", lo=float(lo), hi=float(hi))
    thr = (lo + hi) / 2
    inside = (t >= lo_t) & (t <= hi_t)
    ti, vi = t[inside], vs[inside]
    ez = max(END_ZONE * s, step / 2 + 1e-6)  # at least one sample in each end window
    bright_lo = vs[(t >= lo_t - ez) & (t <= lo_t + ez)].max() > thr
    bright_hi = vs[(t >= hi_t - ez) & (t <= hi_t + ez)].max() > thr
    dark = [(a, b) for a, b in _runs(vi < thr) if (b - a) * step >= MIN_DARK]
    bright_mid = [(a, b) for a, b in _runs(vi >= thr)
                  if ti[a] > lo_t + ez and ti[b - 1] < hi_t - ez]
    ok = bool(bright_lo and bright_hi and len(dark) == 1 and not bright_mid)
    return ok, dict(n_dark=len(dark), n_bright_mid=len(bright_mid), bright_ends=[bool(bright_lo), bool(bright_hi)],
                    thr=float(thr), lo=float(lo), hi=float(hi))


def on_layer(p0, n, s, step=0.5, win=None):
    """Is the surface point on a bright layer? (max of smoothed profile within +/-0.25 s above midlevel)."""
    t, v = ct.profile(np.asarray(p0), np.asarray(n), -3 * s, 3 * s, step)
    if np.isnan(v).mean() > 0.1:
        return None
    v = np.nan_to_num(v, nan=np.nanmedian(v))
    vs = gaussian_filter1d(v, SIGMA / step)
    lo, hi = np.percentile(vs, Q), np.percentile(vs, 100 - Q)
    if hi - lo < 15:
        return None
    return bool(vs[np.abs(t) <= (ON_WIN if win is None else win) * s + step / 2 + 1e-9].max() > (lo + hi) / 2)


def confirm_event(P, N, ev, st, asg, max_members=3):
    """C reference for one deduplicated event. Returns (confirmed, details)."""
    X = np.array(ev["xyz"])
    mem = sorted(ev["members"], key=lambda m: np.linalg.norm(np.array(m["xyz"]) - X))[:max_members]
    votes, det = [], []
    for m in mem:
        ra, rb = tuple(m["rc_a"]), tuple(m["rc_b"])
        ka, kb = asg[ra][0], asg[rb][0]
        ja = label.find_in_stack(st[ra][ka], ra, st[rb], rb)
        if ja is not None:
            t_a = st[rb][ja]["t"] - st[rb][kb]["t"]
            s = label.spacing(st[rb], kb) or abs(t_a)
            ok, d = event_profile_check(P[rb], N[rb], t_a, s)
        else:
            jb = label.find_in_stack(st[rb][kb], rb, st[ra], ra)
            if jb is None:
                ok, d = None, dict(reason="no cross-visibility")
            else:
                t_b = st[ra][jb]["t"] - st[ra][ka]["t"]
                s = label.spacing(st[ra], ka) or abs(t_b)
                ok, d = event_profile_check(P[ra], N[ra], t_b, s)
        votes.append(ok)
        det.append(d)
    decided = [v for v in votes if v is not None]
    if not decided:
        return None, det
    return bool(sum(decided) * 2 > len(decided)), det


NEG_MIN_ON = 0.70     # min on-layer fraction along a negative run (~5th pct of verified 10 mm runs)
NEG_MAX_STREAK = 4    # max consecutive off-layer vertices (~95th pct of verified runs)


def confirm_negative(P, N, neg, asg, st):
    flags = []
    for rc in neg["verts"]:
        rc = tuple(rc)
        k, s, _ = asg.get(rc, (None, None, None))
        if s is None:
            s = 20.0
        flags.append(on_layer(P[rc], N[rc], s))
    f = [x for x in flags if x is not None]
    if len(f) < 0.8 * len(flags) or not f:
        return None, dict(n=len(flags), decided=len(f))
    frac = sum(f) / len(f)
    m = cur = 0
    for x in flags:
        cur = cur + 1 if x is False else 0
        m = max(m, cur)
    return bool(frac >= NEG_MIN_ON and m <= NEG_MAX_STREAK), dict(n=len(flags), decided=len(f), frac_on=frac,
                                                                   max_off_streak=m)
