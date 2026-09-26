"""Annotation attachment and the "#1621-style" annotation check (villa#1621: a patch's own winding
must agree with the human winding annotations it touches).

A point attaches to a surface if it lies within ATTACH vx of a vertex tangent plane (lateral <= one grid
step), the same 2.5 vx tolerance windaudit uses. For two attached points p, q of one collection:
  annotation:  dW_A = (w_q - w_p) + wrap(theta_q - theta_p) / 2pi      (same_wrap: w_q = w_p)
  surface:     dW_U = (theta_u(q) - theta_u(p)) / 2pi                   (theta unwrapped along the grid)
round(dW_A - dW_U) != 0 means the surface changes wrap between p and q -> alarm on the segment p-q.
"""
from __future__ import annotations

import json
from functools import lru_cache

import numpy as np
from scipy.spatial import cKDTree

from . import geom

ATTACH = 2.5
LAT = 14.0


@lru_cache(maxsize=1)
def points():
    out = []
    for fn in ("relative_windings", "same_windings", "abs_winding"):
        C = json.load(open(geom.DATA / f"{fn}.json"))["collections"]
        for cid, c in C.items():
            for pid, p in c["points"].items():
                w = p.get("wind_a")
                out.append(dict(file=fn, coll=f"{fn}:{cid}", pid=pid, p=np.array(p["p"], float),
                                w=(0.0 if fn == "same_windings" else (np.nan if w is None else float(w)))))
    return out, cKDTree(np.array([o["p"] for o in out]))


def attach(P, N):
    """Attached annotation points: list of (point dict, (r, c), normal distance)."""
    pts, tree = points()
    ok = np.isfinite(P).all(-1) & np.isfinite(N).all(-1)
    if not ok.any():
        return []
    r, c = np.nonzero(ok)
    V = P[ok]
    vt = cKDTree(V)
    near = tree.query_ball_point(V, r=LAT + ATTACH)
    cand = sorted({i for l in near for i in l})
    out = []
    for i in cand:
        x = pts[i]["p"]
        d, j = vt.query(x, k=min(4, len(V)))
        best = None
        for jj in np.atleast_1d(j):
            n = N[r[jj], c[jj]]
            nd = abs(float((x - V[jj]) @ n))
            lat = float(np.linalg.norm((x - V[jj]) - ((x - V[jj]) @ n) * n))
            if nd <= ATTACH and lat <= LAT and (best is None or nd < best[1]):
                best = ((int(r[jj]), int(c[jj])), nd)
        if best:
            out.append((pts[i], best[0], best[1]))
    return out


def check_1621(P, N):
    """Alarms: list of dict(p, q, xyz_p, xyz_q, mismatch)."""
    att = attach(P, N)
    if len(att) < 2:
        return dict(n_attached=len(att), alarms=[], pairs=0)
    tu = geom.unwrap_theta(P)
    from scipy.ndimage import label as cc_label
    comp, _ = cc_label(np.isfinite(P).all(-1))
    th = lambda x: geom.theta(x[None])[0]
    by = {}
    for a in att:
        key = "abs" if a[0]["file"] == "abs_winding" else a[0]["coll"]
        by.setdefault(key, []).append(a)
    alarms, pairs = [], 0
    for key, lst in by.items():
        for i in range(len(lst)):
            for j in range(i + 1, len(lst)):
                (pa, ra, _), (pb, rb, _) = lst[i], lst[j]
                if not (np.isfinite(pa["w"]) and np.isfinite(pb["w"])):
                    continue
                if not (np.isfinite(tu[ra]) and np.isfinite(tu[rb])) or comp[ra] != comp[rb]:
                    continue
                pairs += 1
                dth = th(pb["p"]) - th(pa["p"])
                dth = (dth + np.pi) % (2 * np.pi) - np.pi
                dA = (pb["w"] - pa["w"]) + dth / (2 * np.pi)
                dU = (tu[rb] - tu[ra]) / (2 * np.pi)
                mm = int(round(dA - dU))
                if mm != 0:
                    alarms.append(dict(coll=key, rc_p=ra, rc_q=rb, xyz_p=P[ra].tolist(), xyz_q=P[rb].tolist(),
                                       mismatch=mm))
    return dict(n_attached=len(att), alarms=alarms, pairs=pairs)
