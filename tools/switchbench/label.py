"""Natural sheet-switch event labeler (SwitchBench-natural, IDEAS.md section 5, frozen criteria).

Per vertex u of a candidate surface (grid P, outward normals N):
  * "stack": all verified sheets crossed by the line u + t*n_u, |t| <= RQ, found by intersecting the
    line with the tangent planes of nearby verified vertices (lateral tolerance LAT), clustered per
    verified patch, then merged across patches (duplicates of one surface) into sheets.
  * local inter-wrap spacing s(u): measured from adjacent verified sheets in the stack (gaps between
    consecutive merged sheets, see spacing()).
  * assignment: u lies on sheet k iff |t_k| <= 0.25 * s(u) (criteria), else unassigned.
Along each connected 1D run (grid rows and grid columns), assigned vertices are chained. A change of
sheet is a switch candidate; the wrap difference is measured from verified geometry (reference G):
the old sheet is looked up in the new vertex's stack (or vice versa) by verified patch identity, and
the number of wraps between them is the count of intervening sheets + 1, checked against the gap.
"""
from __future__ import annotations

import numpy as np

from . import geom
from .geom import MM

RQ = 100.0        # vx: half-length of the normal line searched for verified sheets (~1 mm, ~4-5 wraps)
LAT = 14.0        # vx: max lateral distance from line/plane hit to the verified vertex (grid step 20)
COS_MIN = 0.5     # |n_u . n_v| minimum (sheet roughly parallel to the probe)
PATCH_GAP = 6.0   # vx: split one patch's hits into separate crossings if t differs by more
MERGE = 0.35      # merge crossings closer than MERGE * provisional spacing into one sheet
CHUNK = 4000      # vertices per stack batch
TOL = 0.25        # criteria: within 0.25 x local inter-wrap spacing
SAME_PATCH_CELLS = 30.0  # grid cells: same patch farther apart than this on its grid = another wrap
MAX_SPACING = 40.0  # vx: ~90th percentile of consecutive-wrap spacing on human ladders (relative_windings)
MIN_SPACING = 8.0  # vx: a "gap" below this is treated as the same sheet (both faces / duplicate trace)


def stacks(P: np.ndarray, N: np.ndarray, cloud: dict, verts=None):
    """For each valid vertex (or given (r, c) list) return a sorted list of sheets.

    sheet = dict(t=float, members={patch_idx: (r, c)})
    """
    H, W, _ = P.shape
    out = {}
    if cloud is None:
        return out
    if verts is None:
        ok = np.isfinite(P).all(-1) & np.isfinite(N).all(-1)
        verts = list(zip(*np.nonzero(ok)))
    if not verts:
        return out
    if len(verts) > CHUNK:  # bound memory on very large patches
        for i in range(0, len(verts), CHUNK):
            out.update(stacks(P, N, cloud, verts=verts[i:i + CHUNK]))
        return out
    U = np.array([P[r, c] for r, c in verts])
    NU = np.array([N[r, c] for r, c in verts])
    nbrs = cloud["tree"].query_ball_point(U, r=RQ)
    pts, nrm, pid, rcs = cloud["pts"], cloud["nrm"], cloud["pid"], cloud["rc"]
    for (r, c), u, nu, idx in zip(verts, U, NU, nbrs):
        if not idx:
            out[(r, c)] = []
            continue
        idx = np.asarray(idx)
        v = pts[idx]; nv = nrm[idx]
        cos = nv @ nu
        good = np.abs(cos) >= COS_MIN
        if not good.any():
            out[(r, c)] = []
            continue
        idx, v, nv, cos = idx[good], v[good], nv[good], cos[good]
        t = ((v - u) * nv).sum(1) / cos
        q = u[None] + t[:, None] * nu[None]
        lat = np.linalg.norm(q - v, axis=1)
        good = (lat <= LAT) & (np.abs(t) <= RQ)
        if not good.any():
            out[(r, c)] = []
            continue
        idx, t, lat = idx[good], t[good], lat[good]
        crossings = []  # (t, patch, (r, c))
        for p in np.unique(pid[idx]):
            m = pid[idx] == p
            tp, lp, ip = t[m], lat[m], idx[m]
            o = np.argsort(tp)
            tp, lp, ip = tp[o], lp[o], ip[o]
            splits = np.nonzero(np.diff(tp) > PATCH_GAP)[0] + 1
            for seg in np.split(np.arange(len(tp)), splits):
                j = seg[np.argmin(lp[seg])]
                crossings.append((float(tp[j]), int(p), tuple(int(x) for x in rcs[ip[j]])))
        crossings.sort()
        out[(r, c)] = _merge(crossings)
    return out


def _merge(crossings):
    """Single-linkage merge of crossings into sheets, threshold MIN_SPACING vx.

    A crossing is never merged into a sheet that already holds the same verified patch at a distant
    grid position (> SAME_PATCH_CELLS): that is another wrap of a multi-turn patch, not a duplicate.
    """
    sheets = []
    for t, p, rc in crossings:
        s = sheets[-1] if sheets else None
        if s is not None and t - s["tmax"] < MIN_SPACING:
            q = s["members"].get(p)
            if q is None or np.hypot(q[0] - rc[0], q[1] - rc[1]) <= SAME_PATCH_CELLS:
                s["ts"].append(t)
                s["tmax"] = t
                s["members"].setdefault(p, rc)
                continue
        sheets.append(dict(ts=[t], tmax=t, members={p: rc}))
    for s in sheets:
        s["t"] = float(np.median(s["ts"]))
        del s["ts"], s["tmax"]
    return sheets


def spacing(sheets, k: int | None, t0: float = 0.0):
    """Local inter-wrap spacing from adjacent verified sheets.

    If k is given (the sheet nearest the vertex): min of the gaps to its inner and outer neighbours.
    Otherwise: the gap of the enclosing pair around t0. None if not measurable.
    """
    ts = [s["t"] for s in sheets]
    if k is not None:
        g = []
        if k > 0:
            g.append(ts[k] - ts[k - 1])
        if k + 1 < len(ts):
            g.append(ts[k + 1] - ts[k])
        return min(g) if g else None
    for a, b in zip(ts[:-1], ts[1:]):
        if a <= t0 <= b:
            return b - a
    return None


def assign(sheets):
    """(sheet index, spacing, |t|) if the vertex lies within TOL x spacing of a sheet, else (None, s, d).

    The spacing is only trusted if it is plausibly ONE wrap: at most MAX_SPACING vx (90th percentile of
    human ladder spacings) and at most 1.5 x the median gap of the local verified stack. Otherwise an
    adjacent wrap is probably missing from verified coverage and the vertex stays unassigned.
    """
    if not sheets:
        return None, None, None
    k = int(np.argmin([abs(s["t"]) for s in sheets]))
    s = spacing(sheets, k)
    d = abs(sheets[k]["t"])
    if s is None:
        return None, None, d
    gaps = np.diff([x["t"] for x in sheets])
    if s > MAX_SPACING or s > 1.5 * float(np.median(gaps)):
        return None, s, d
    return (k if d <= TOL * s else None), s, d


def same_sheet(sa: dict, ra, sb: dict, rb, grid_slack=3.0) -> bool:
    """Two sheet observations (at vertices ra, rb of the candidate grid) are the same verified surface
    if they share a verified patch whose attach points are close on that patch's grid."""
    dist = np.hypot(ra[0] - rb[0], ra[1] - rb[1])
    for p, rc in sa["members"].items():
        if p in sb["members"]:
            rc2 = sb["members"][p]
            if np.hypot(rc[0] - rc2[0], rc[1] - rc2[1]) <= 1.5 * dist + grid_slack:
                return True
    return False


def find_in_stack(sheet_obs, r_obs, stack, r_stack):
    for j, s in enumerate(stack):
        if same_sheet(sheet_obs, r_obs, s, r_stack):
            return j
    return None


def wrap_delta(stack_b, kb, sheet_a, ra, rb):
    """Wraps from sheet A to sheet B (B = assigned sheet kb in stack_b at vertex rb), from geometry.

    Returns (delta, detail) with delta None if A is not visible in B's stack. Missing verified wraps
    are accounted for by rounding each gap by the local spacing (gaps < 1.5 s count 1)."""
    ja = find_in_stack(sheet_a, ra, stack_b, rb)
    if ja is None:
        return None, None
    if ja == kb:
        return 0, dict(n_between=0, gap_ratio=0.0)
    lo, hi = sorted((ja, kb))
    ts = [s["t"] for s in stack_b]
    gaps = np.diff(ts[lo:hi + 1])
    s_loc = spacing(stack_b, kb) or float(np.min(gaps))
    wraps = int(sum(max(1, int(round(g / s_loc))) for g in gaps))
    sign = 1 if kb > ja else -1  # B outward of A -> +1
    return sign * wraps, dict(n_between=hi - lo - 1, gap=float(ts[kb] - ts[ja]), spacing=float(s_loc),
                              gap_ratio=float(abs(ts[kb] - ts[ja]) / s_loc))


# ----------------------------------------------------------------------------- runs
EVENT_MIN_MM = 1.0     # criteria: w +/- 1 held for >= 1 mm
PRE_MIN_VERTS = 2      # the w side must be held by >= 2 assigned vertices (see results md, D4)
NEG_MIN_MM = 10.0      # criteria: negatives are >= 10 mm single-wrap runs
LIE_FRAC = 0.8         # a segment "lies on" a wrap if >= 80% of its vertices are assigned to it
MAX_UNASSIGNED_MM = 1.0  # and no unassigned stretch inside it is longer than this
DEDUP_MM = 1.0         # row/column detections of one switch closer than this are one event


def runs_of(valid: np.ndarray):
    """Connected 1D runs along grid rows and grid columns: list of (axis, [(r, c), ...])."""
    H, W = valid.shape
    out = []
    for r in range(H):
        c = 0
        while c < W:
            if valid[r, c]:
                s = c
                while c < W and valid[r, c]:
                    c += 1
                out.append(("row", [(r, x) for x in range(s, c)]))
            else:
                c += 1
    for c in range(W):
        r = 0
        while r < H:
            if valid[r, c]:
                s = r
                while r < H and valid[r, c]:
                    r += 1
                out.append(("col", [(x, c) for x in range(s, r)]))
            else:
                r += 1
    return out


def _arc(P, verts):
    if len(verts) < 2:
        return 0.0
    X = np.array([P[r, c] for r, c in verts])
    return float(np.linalg.norm(np.diff(X, axis=0), axis=1).sum())


def label_run(P, verts, st, asg):
    """Chain the assigned vertices of one run into wrap-labelled segments.

    Returns list of chains; each chain is a list of segments dict(label, i0, i1, idx=[run positions]).
    Chains break where the relation between consecutive sheets cannot be measured from geometry.
    """
    chains, chain = [], []
    prev = None  # (pos, (r, c), sheet obs, label)
    for pos, rc in enumerate(verts):
        k = asg.get(rc, (None,))[0]
        if k is None:
            continue
        obs = st[rc][k]
        if prev is None:
            chain = [dict(label=0, idx=[pos])]
            prev = (pos, rc, obs, 0)
            continue
        ppos, prc, pobs, plab = prev
        if same_sheet(pobs, prc, obs, rc):
            d = 0
        else:
            # wrap difference must be measured from BOTH sides: old sheet in the new stack and new
            # sheet in the old stack, with the same result (bilateral cross-visibility)
            d1, _ = wrap_delta(st[rc], k, pobs, prc, rc)
            d2, _ = wrap_delta(st[prc], asg[prc][0], obs, rc, prc)
            if d1 == 0 or d2 == 0:
                d = 0
            elif d1 is None or d2 is None or d1 != -d2:
                d = None
            else:
                d = d1
        if d is None:
            chains.append(chain)
            chain = [dict(label=0, idx=[pos])]
            prev = (pos, rc, obs, 0)
            continue
        lab = plab + d
        if lab == chain[-1]["label"]:
            chain[-1]["idx"].append(pos)
        else:
            chain.append(dict(label=lab, idx=[pos]))
        prev = (pos, rc, obs, lab)
    if chain:
        chains.append(chain)
    return chains


def _seg_ok(P, verts, seg, min_mm):
    """Segment lies on its wrap for >= min_mm (coverage and unassigned-gap rules)."""
    i0, i1 = seg["idx"][0], seg["idx"][-1]
    span = verts[i0:i1 + 1]
    L = _arc(P, span) / MM
    cover = len(seg["idx"]) / (i1 - i0 + 1)
    gaps = np.diff(seg["idx"])
    maxgap = 0.0
    for a, b, g in zip(seg["idx"][:-1], seg["idx"][1:], gaps):
        if g > 1:
            maxgap = max(maxgap, _arc(P, verts[a:b + 1]) / MM)
    return L >= min_mm and cover >= LIE_FRAC and maxgap <= MAX_UNASSIGNED_MM, L


def label_patch(P, N, cloud, stacks_cache=None):
    """Run the labeler on one surface. Returns dict(events=[...], negatives=[...], multi=[...], stats)."""
    valid = np.isfinite(P).all(-1) & np.isfinite(N).all(-1)
    st = stacks_cache if stacks_cache is not None else stacks(P, N, cloud)
    asg = {rc: assign(s) for rc, s in st.items()}
    n_assigned = sum(1 for a in asg.values() if a[0] is not None)
    raw_events, negatives, multi = [], [], []
    for axis, verts in runs_of(valid):
        if len(verts) < 2:
            continue
        for chain in label_run(P, verts, st, asg):
            for a, b in zip(chain[:-1], chain[1:]):
                dl = b["label"] - a["label"]
                pre_ok = len(a["idx"]) >= PRE_MIN_VERTS
                a_ok, La = _seg_ok(P, verts, a, EVENT_MIN_MM)
                b_ok, Lb = _seg_ok(P, verts, b, EVENT_MIN_MM)
                pre_b = len(b["idx"]) >= PRE_MIN_VERTS
                if (b_ok and pre_ok) or (a_ok and pre_b):
                    ra, rb = verts[a["idx"][-1]], verts[b["idx"][0]]
                    rec = dict(axis=axis, rc_a=ra, rc_b=rb, delta=int(dl), len_a_mm=La, len_b_mm=Lb,
                               both_sides_1mm=bool(a_ok and b_ok),
                               xyz=((P[ra] + P[rb]) / 2).tolist(), run=[verts[0], verts[-1]])
                    (raw_events if abs(dl) == 1 else multi).append(rec)
            for seg in chain:
                ok, L = _seg_ok(P, verts, seg, NEG_MIN_MM)
                if ok:
                    i0, i1 = seg["idx"][0], seg["idx"][-1]
                    negatives.append(dict(axis=axis, verts=verts[i0:i1 + 1], len_mm=L))
    events = dedup(raw_events)
    return dict(events=events, negatives=negatives, multi=dedup(multi), raw_events=raw_events,
                stats=dict(n_valid=int(valid.sum()), n_assigned=n_assigned), stacks=st, asg=asg)


def dedup(raw):
    """Cluster row/column detections of the same switch (3D distance < DEDUP_MM)."""
    if not raw:
        return []
    X = np.array([e["xyz"] for e in raw])
    lab = -np.ones(len(raw), int)
    cur = 0
    for i in range(len(raw)):
        if lab[i] >= 0:
            continue
        lab[i] = cur
        stack_ = [i]
        while stack_:
            j = stack_.pop()
            d = np.linalg.norm(X - X[j], axis=1)
            for k in np.nonzero((d < DEDUP_MM * MM) & (lab < 0))[0]:
                lab[k] = cur
                stack_.append(k)
        cur += 1
    out = []
    for g in range(cur):
        mem = [raw[i] for i in np.nonzero(lab == g)[0]]
        out.append(dict(xyz=np.mean([m["xyz"] for m in mem], 0).tolist(), members=mem,
                        delta_signs=sorted({m["delta"] for m in mem})))
    return out
