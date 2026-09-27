"""EXPLORATORY robustness analysis of SwitchBench-natural v0 (not pre-registered; changes no v0 or v1
verdict, file or code path). Plan committed before any number: results/switchbench_explore.json
(commit 6a0765e).

Question: is the tifxyz-doctor natural-vs-planted recall gap (6/54 vs 124/128) "definitional" (natural
switches gradual, planted proxy abrupt) or "just the operating point"?
  A  abruptness of each confirmed event (transition width along the trace; max single-step offset
     relative to the reference sheets; the doctor's own per-edge score), vs the planted proxy
  B  doctor / random hits vs abruptness; why each miss is missed
  C  doctor operating-point sweep through its public API (normal_step_ratio x min_component_cells) and
     its all-cue review_score; recall vs false alarms per 100 mm; random alarms at matched rate
  D  pre-stated takeaway rules, label-noise mixture check, measurement-noise floor

v0 code is imported read-only (geom, label, metrics). Doctor arrays come from explore_doctor.py (run in
the doctor's venv). Numeric only; no images. Intermediates live in $EXPLORE_DIR (default
data/paris4/explore_abruptness, gitignored).

Usage (project venv, repo root):
  EXPLORE_DIR=... python -m tools.switchbench.explore_abruptness geom     # A1-A3 + negatives noise floor
  EXPLORE_DIR=... python -m tools.switchbench.explore_abruptness sweep    # C scoring (+ random curve)
  EXPLORE_DIR=... python -m tools.switchbench.explore_abruptness report   # A-D -> results JSON

v1 (parametrized; see RELEASE_RUNBOOK.md 4a2): set EXPLORE_MODE=v1 (or pass --v1, which requires
EXPLORE_MODE=v1 already set -- module-level paths are fixed at import time) to run 'geom' and 'report'
against the v1 pooled corpus instead. 'geom' checkpoints per patch (resumable) and 'report' writes only
section A (per-event abrupt/gradual classification), the input tools.switchbench_kit.strata_gen needs.
'sweep' has no v1 mode.
  EXPLORE_MODE=v1 EXPLORE_DIR=data/switchbench_v1/explore_abruptness nice -n 10 \\
      python -m tools.switchbench.explore_abruptness geom --v1
  EXPLORE_MODE=v1 EXPLORE_DIR=data/switchbench_v1/explore_abruptness nice -n 10 \\
      python -m tools.switchbench.explore_abruptness report --v1
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import numpy as np
from scipy import ndimage, stats
from scipy.spatial import cKDTree

from . import geom, label, metrics
from .geom import MM

# v1 support (the frozen-criteria history / internal/release/RELEASE_RUNBOOK.md step 4a2): the natural-vs-planted abruptness
# split is v0/v1-agnostic geometry (member_metrics / event_level below use only the corpus records and,
# optionally, the doctor's per-edge capture arrays -- neither is v0-specific). What *was* hardcoded to v0
# is (a) the three paths below and (b) load_corpus()'s v0-only corpus directory and schema. Both are now
# switched by EXPLORE_MODE=v1 (or the `--v1` CLI flag, which sets it): default is unchanged ("v0"), so
# every existing invocation (no flag, no env var) behaves exactly as before.
MODE = os.environ.get("EXPLORE_MODE", "v0")
if MODE not in ("v0", "v1"):
    raise SystemExit(f"EXPLORE_MODE must be v0 or v1, got {MODE!r}")
IS_V1 = MODE == "v1"

V1_DATA = geom.REPO / "data" / "switchbench_v1"
_EXPLORE_DEFAULT = (V1_DATA if IS_V1 else geom.DATA) / "explore_abruptness"
EXPLORE = Path(os.environ.get("EXPLORE_DIR", str(_EXPLORE_DEFAULT)))
RES = geom.REPO / "vault" / "results"
# v0: the frozen exploration + its input (switchbench_natural.json). v1 has no equivalent frozen "v0_json"
# baseline to diff against (stage_report_v1 does not read it) and writes a differently-named output so it
# can never collide with, or be mistaken for, the pre-registered v0 file.
OUT_JSON = RES / ("switchbench_v1_abruptness.json" if IS_V1 else "switchbench_explore.json")
V0_JSON = RES / "switchbench_natural.json"
V1_EVENTS_JSON = V1_DATA / "switchbench_v1_events.json"  # the v1 kit-format events file (read-only; not opened here)
SEED = 20260925
B = 2000
STEP_VX = 20.0                 # grid step of the Paris4 traces (vx); 0.192 mm
ABRUPT_VX = 8.0                # planted proxy: 8 vx normal offset in one grid step (1 cell)
S3_SCORE = 0.20                # doctor score of the planted 8 vx x 1-cell step on a flat grid (0.204)
DOC_THR = 0.25                 # doctor default normal_step_ratio
DOC_MINC = 8                   # doctor default normal_step_min_component_cells
MATCH = metrics.MATCH_MM * MM  # 1 mm in vx
DEDUP = 0.5 * MM               # v0 alarm dedup radius
R_GRID = [0.03, 0.04, 0.05, 0.06, 0.07, 0.08, 0.09, 0.10, 0.11, 0.12, 0.13, 0.14, 0.15, 0.16, 0.17,
          0.18, 0.19, 0.20, 0.22, 0.25, 0.30, 0.35, 0.40, 0.50]
M_GRID = [1, 2, 4, 8, 16, 32]
TAU_GRID = [0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 0.95, 0.99, 1.0]
LAMBDAS = np.geomspace(0.003, 10.0, 25)
N_REP = 20
BIG = "auto_grown_w20231031143852"


# ----------------------------------------------------------------------------- corpus
def load_corpus_v0():
    recs = {}
    for f in sorted((geom.DATA / "corpus").glob("*.json")):
        r = json.load(open(f))
        if r.get("in_sample"):
            recs[r["patch"]] = r
    return recs


def load_corpus_v1():
    """v1 pooled corpus (protocol P1 (prereg/switchbench_v1.md)): v0's corpus (patches 1-3,000) plus the new v1 patches
    (3,001-10,000), each record exactly as corpus.py / corpus_v1.py wrote it (same schema
    stage_geom already expects: patch, excluded_same_lineage, events[{xyz, delta_signs, members,
    status}], negatives[{status, verts, len_mm}]) -- EXCEPT every event's `status` is overridden with
    its level-0 (2.4 um) verdict (confirm_l0.py), read from data/switchbench_v1/l0/<patch>.json, since
    that is the label v1 published (switchbench_v1.json), not the level-2 status the raw corpus file
    carries. Negatives keep the v0 (level-2, on-layer) status unchanged, same as
    tools.switchbench.evaluate_v1.load_pooled() -- this is a schema-preserving re-implementation of
    that same pooling rule, not a new one, so the two must never disagree (see
    tools/switchbench/tests/test_explore_abruptness_v1.py)."""
    recs = {}
    for d in (geom.DATA / "corpus", V1_DATA / "corpus"):
        for f in sorted(d.glob("*.json")):
            r = json.load(open(f))
            if not r.get("in_sample"):
                continue
            if r.get("events"):
                l0 = json.load(open(V1_DATA / "l0" / f"{r['patch']}.json"))
                if len(l0["events"]) != len(r["events"]):
                    raise RuntimeError(f"level-0 event count mismatch for {r['patch']}")
                for e, le in zip(r["events"], l0["events"]):
                    if np.linalg.norm(np.array(le["xyz"]) - np.array(e["xyz"])) > 1e-6:
                        raise RuntimeError(f"level-0 verdict mismatch {r['patch']}")
                    e["status"] = le["status_l0"]
            recs[r["patch"]] = r
    return recs


def load_corpus():
    return load_corpus_v1() if IS_V1 else load_corpus_v0()


def scored_patches(recs):
    return sorted(p for p, r in recs.items() if any(e["status"] == "confirmed" for e in r["events"])
                  or any(n["status"] == "confirmed" for n in r["negatives"]))


def patch_geom(nm):
    d = geom.DATA / "unverified_patches" / nm
    P = geom.load_tifxyz(d)
    N = geom.orient_outward(P, geom.grid_normals(P))
    return P, N


def event_points(e):
    return np.array([m["xyz"] for m in e["members"]] + [e["xyz"]], float)


def wilson(k, n):
    p, lo, hi = metrics.wilson(k, n)
    return dict(k=int(k), n=int(n), p=p, lo=lo, hi=hi)


# ----------------------------------------------------------------------------- A: geometry
def run_of(valid, axis, rc):
    r, c = rc
    line = valid[r, :] if axis == "row" else valid[:, c]
    i = c if axis == "row" else r
    s = i
    while s - 1 >= 0 and line[s - 1]:
        s -= 1
    e = i
    while e + 1 < len(line) and line[e + 1]:
        e += 1
    return [(r, x) for x in range(s, e + 1)] if axis == "row" else [(x, c) for x in range(s, e + 1)]


def arc_vx(P, verts):
    if len(verts) < 2:
        return 0.0
    X = np.array([P[v] for v in verts])
    return float(np.linalg.norm(np.diff(X, axis=0), axis=1).sum())


def track(st, run, p0, p1, obs, robs):
    """Follow one verified sheet along run positions p0 -> p1 (inclusive). Returns {pos: (j, t)}."""
    out = {}
    step = 1 if p1 >= p0 else -1
    cur_obs, cur_r = obs, robs
    for p in range(p0, p1 + step, step):
        v = run[p]
        stack = st.get(v) or []
        j = label.find_in_stack(cur_obs, cur_r, stack, v)
        if j is None and cur_r != robs:
            j = label.find_in_stack(obs, robs, stack, v)   # fall back to the original observation
        if j is not None:
            out[p] = (j, float(stack[j]["t"]))
            cur_obs, cur_r = stack[j], v
    return out


class Stacker:
    """v0 stacks for chosen vertices. One verified cloud per unverified patch over the union bounding box
    of the vertices needed (pad 160 vx, as v0), or one per run when that box overlaps > MAX_OVER verified
    patches or is wider than MAX_DIAG (memory). Stacks only use verified vertices within RQ = 100 vx of a
    vertex (< pad), so both give v0's stacks (all 809 member crossings reproduced)."""
    MAX_OVER = 2000
    MAX_DIAG = 3000.0   # vx; wider boxes (the 434 x 554 legacy patch) use per-run clouds

    def __init__(self):
        self.vi = geom.VerifiedIndex()
        self.cloud = None

    def set_patch(self, P, vert_lists, excl):
        X = np.concatenate([np.array([P[v] for v in vl]) for vl in vert_lists]) if vert_lists else None
        self.excl = set(excl)
        self.cloud = None
        if X is None:
            return
        n_over = len(self.vi.overlapping(X.min(0) - 160, X.max(0) + 160))
        if n_over <= self.MAX_OVER and float(np.linalg.norm(X.max(0) - X.min(0))) <= self.MAX_DIAG:
            self.cloud = self.vi.local_cloud(X.min(0), X.max(0), exclude=self.excl)
            self.cloud_mode = "patch"
        else:
            self.cloud_mode = "run"

    def stacks(self, P, N, verts, excl=None):
        if self.cloud is not None:
            return label.stacks(P, N, self.cloud, verts=list(verts))
        X = np.array([P[v] for v in verts])
        cl = self.vi.local_cloud(X.min(0), X.max(0), exclude=self.excl if excl is None else set(excl))
        return label.stacks(P, N, cl, verts=list(verts))

    def clear(self, cap=0):
        self.cloud = None
        if len(self.vi._cache) > cap:
            self.vi._cache.clear()


def member_metrics(P, run, st, asg, m, hs, vs, href, vref):
    rc_a, rc_b, delta = tuple(m["rc_a"]), tuple(m["rc_b"]), int(m["delta"])
    pos_a, pos_b = run.index(rc_a), run.index(rc_b)
    rep = False
    for chain in label.label_run(P, run, st, asg):
        for a, b in zip(chain[:-1], chain[1:]):
            if run[a["idx"][-1]] == rc_a and run[b["idx"][0]] == rc_b and b["label"] - a["label"] == delta:
                rep = True
    out = dict(axis=m["axis"], rc_a=list(rc_a), rc_b=list(rc_b), delta=delta, reproduced=rep,
               n_steps=pos_b - pos_a, W_mm=arc_vx(P, run[pos_a:pos_b + 1]) / MM)
    if not rep:
        return out
    ka, kb = asg[rc_a][0], asg[rc_b][0]
    trA = track(st, run, pos_a, pos_b, st[rc_a][ka], rc_a)
    trB = track(st, run, pos_b, pos_a, st[rc_b][kb], rc_b)
    o, gap = {}, {}
    for p in range(pos_a, pos_b + 1):
        if p in trA and p in trB and trA[p][0] != trB[p][0]:
            tA, tB = trA[p][1], trB[p][1]
            o[p] = -tA * float(np.sign(tB - tA))
            gap[p] = abs(tB - tA)
    defined = sorted(o)
    steps, partial = [], False
    for q1, q2 in zip(defined[:-1], defined[1:]):
        d = abs(o[q2] - o[q1])
        # X1 sheet-frame offset: how far across the A-B gap the trace moves (|delta f| x mean gap)
        f1 = o[q1] / gap[q1] if gap[q1] > 0 else None
        f2 = o[q2] / gap[q2] if gap[q2] > 0 else None
        dsf = abs(f2 - f1) * 0.5 * (gap[q1] + gap[q2]) if (f1 is not None and f2 is not None) else None
        L = arc_vx(P, run[q1:q2 + 1]) / MM
        if q2 - q1 > 1:
            partial = True
        steps.append(dict(step_vx=d / (q2 - q1), rate=d / L if L > 0 else None, exact=q2 - q1 == 1,
                          step_sf=(dsf / (q2 - q1)) if dsf is not None else None,
                          rate_sf=(dsf / L) if (dsf is not None and L > 0) else None))
    if defined and (defined[0] != pos_a or defined[-1] != pos_b):
        partial = True
    out.update(partial=partial, n_defined=len(defined), spacing_b=asg[rc_b][1],
               gap_a=gap.get(pos_a), gap_b=gap.get(pos_b),
               o_a=o.get(pos_a), o_b=o.get(pos_b),
               total_offset_vx=(o[pos_b] - o[pos_a]) if (pos_a in o and pos_b in o) else None,
               f_a=(o[pos_a] / gap[pos_a]) if pos_a in o and gap[pos_a] > 0 else None,
               f_b=(o[pos_b] / gap[pos_b]) if pos_b in o and gap[pos_b] > 0 else None,
               max_step_vx=max((s["step_vx"] for s in steps), default=None),
               max_rate_vx_per_mm=max((s["rate"] for s in steps if s["rate"] is not None), default=None),
               max_step_sf_vx=max((s["step_sf"] for s in steps if s["step_sf"] is not None), default=None),
               max_rate_sf_vx_per_mm=max((s["rate_sf"] for s in steps if s["rate_sf"] is not None), default=None),
               total_sf_vx=(0.5 * (gap[pos_a] + gap[pos_b]) * (o[pos_b] / gap[pos_b] - o[pos_a] / gap[pos_a]))
               if (pos_a in o and pos_b in o and gap[pos_a] > 0 and gap[pos_b] > 0) else None,
               n_step_measurements=len(steps))
    # the doctor's own per-edge score on this run's edges, rc_a-1 .. rc_b+1
    sc = []
    for p in range(pos_a - 1, pos_b + 1):
        if p < 0 or p + 1 >= len(run):
            continue
        r, c = run[p]
        val = hs[r, c] if m["axis"] == "row" else vs[r, c]
        if np.isfinite(val):
            sc.append(float(val))
    ref = href if m["axis"] == "row" else vref
    out.update(doctor_zone_max_score=max(sc) if sc else None,
               doctor_zone_max_vx=(max(sc) * ref) if sc else None)
    return out


def neg_noise(P, N, stk, n, excl):
    """Per-step change of the offset from the tracked sheet along a confirmed negative run (noise floor)."""
    verts = [tuple(v) for v in n["verts"]]
    st = stk.stacks(P, N, verts, excl)
    asg = {v: label.assign(s) for v, s in st.items()}
    first = next((i for i, v in enumerate(verts) if asg[v][0] is not None), None)
    if first is None:
        return []
    v0 = verts[first]
    k = asg[v0][0]
    tr = track(st, verts, first, len(verts) - 1, st[v0][k], v0)
    # pseudo-pair for the sheet-frame measure: the tracked sheet and its adjacent sheet in the stack
    kb = k + 1 if k + 1 < len(st[v0]) else (k - 1 if k > 0 else None)
    trb = track(st, verts, first, len(verts) - 1, st[v0][kb], v0) if kb is not None else {}
    out = []
    for p in range(first, len(verts) - 1):
        if p in tr and p + 1 in tr:
            rec = dict(step=abs(tr[p + 1][1] - tr[p][1]), step_sf=None)
            if p in trb and p + 1 in trb and trb[p][0] != tr[p][0] and trb[p + 1][0] != tr[p + 1][0]:
                g1, g2 = abs(trb[p][1] - tr[p][1]), abs(trb[p + 1][1] - tr[p + 1][1])
                if g1 > 0 and g2 > 0:
                    f1 = -tr[p][1] * np.sign(trb[p][1] - tr[p][1]) / g1
                    f2 = -tr[p + 1][1] * np.sign(trb[p + 1][1] - tr[p + 1][1]) / g2
                    rec["step_sf"] = float(abs(f2 - f1) * 0.5 * (g1 + g2))
            out.append(rec)
    return out


def cap_arrays(nm, dummy_shape=None):
    """Doctor per-edge capture arrays (hscore/vscore/href/vref), written by explore_doctor.py's
    'capture' stage. If dummy_shape (H, W) is given and the capture file is missing, an all-NaN
    stand-in is returned instead of raising: member_metrics only uses these to record
    doctor_zone_max_score/_vx (never abrupt_primary_sf/_planned, which come from geometry alone), so a
    dummy just leaves those two fields None rather than failing the whole run. v0 never passes
    dummy_shape, so its behaviour (raise if the capture file is missing) is unchanged."""
    f = EXPLORE / "capture" / f"{nm}.npz"
    if f.exists():
        return np.load(f)
    if dummy_shape is None:
        raise FileNotFoundError(f)
    h, w = dummy_shape
    return dict(hscore=np.full((h, w), np.nan), vscore=np.full((h, w), np.nan), href=1.0, vref=1.0)


def _geom_one_patch(stk, nm, r):
    """One patch's contribution to stage_geom: (event rows, negative-run noise steps). Pulled out of
    stage_geom so it can be checkpointed per patch (rule: 'every long job resumable ... checkpoint per
    patch') -- a killed run resumes at the next un-checkpointed patch instead of redoing the whole
    corpus."""
    P, N = patch_geom(nm)
    valid = np.isfinite(P).all(-1) & np.isfinite(N).all(-1)
    excl = r.get("excluded_same_lineage", [])
    z = cap_arrays(nm, dummy_shape=P.shape[:2] if IS_V1 else None)
    hs, vs, href, vref = z["hscore"], z["vscore"], float(z["href"]), float(z["vref"])
    need = [run_of(valid, m["axis"], tuple(m["rc_a"])) for e in r["events"]
            if e["status"] in ("confirmed", "contradicted") for m in e["members"]]
    need += [[tuple(v) for v in n["verts"]] for n in r["negatives"] if n["status"] == "confirmed"]
    stk.set_patch(P, need, excl)
    run_cache = {}
    rows = []
    for ie, e in enumerate(r["events"]):
        if e["status"] not in ("confirmed", "contradicted"):
            continue
        mems = []
        for m in e["members"]:
            run = run_of(valid, m["axis"], tuple(m["rc_a"]))
            key = (m["axis"], run[0], run[-1])
            if key not in run_cache:
                st = stk.stacks(P, N, run, excl)
                run_cache[key] = (run, st, {v: label.assign(s) for v, s in st.items()})
            run, st, asg = run_cache[key]
            if tuple(m["rc_b"]) not in run:
                mems.append(dict(axis=m["axis"], rc_a=m["rc_a"], rc_b=m["rc_b"], reproduced=False,
                                 note="rc_b not on rc_a's run"))
                continue
            mems.append(member_metrics(P, run, st, asg, m, hs, vs, href, vref))
        rows.append(dict(patch=nm, event_index=ie, status=e["status"], xyz=e["xyz"],
                         n_members=len(e["members"]), members=mems))
    noise = []
    for n in r["negatives"]:
        if n["status"] == "confirmed":
            noise += neg_noise(P, N, stk, n, excl)
    mode = stk.cloud_mode if need else "-"
    stk.clear()
    return rows, noise, mode


def stage_geom(only=None, checkpoint=False):
    """checkpoint=True (used by --v1, where a run over 237 patches is a new, much larger analysis than
    v0's ~39) writes each patch's result to EXPLORE/geom_patches/<patch>.json as it finishes, and skips
    any patch whose checkpoint file already exists -- so `setsid nohup ... geom --v1`, killed and
    re-run, picks up where it left off rather than redoing finished patches. v0 keeps its original
    all-in-memory, single-file behaviour (checkpoint defaults to False)."""
    recs = load_corpus()
    stk = Stacker()
    t0 = time.time()
    pats = sorted(p for p, r in recs.items() if any(e["status"] in ("confirmed", "contradicted") for e in r["events"])
                  or any(n["status"] == "confirmed" for n in r["negatives"]))
    if only:
        pats = [p for p in pats if p in only]
    ckpt_dir = EXPLORE / "geom_patches"
    if checkpoint:
        ckpt_dir.mkdir(parents=True, exist_ok=True)
    rows, noise = [], []
    n_skipped = 0
    for k, nm in enumerate(pats):
        ckpt_f = ckpt_dir / f"{nm}.json"
        if checkpoint and ckpt_f.exists():
            cached = json.load(open(ckpt_f))
            rows += cached["rows"]
            noise += cached["noise"]
            n_skipped += 1
            continue
        p_rows, p_noise, mode = _geom_one_patch(stk, nm, recs[nm])
        rows += p_rows
        noise += p_noise
        if checkpoint:
            json.dump(dict(rows=p_rows, noise=p_noise), open(ckpt_f, "w"), default=float)
        print("geom", k + 1, "/", len(pats), nm, mode, round(time.time() - t0), "s", flush=True)
    if checkpoint and n_skipped:
        print(f"geom: resumed, {n_skipped}/{len(pats)} patch(es) already checkpointed", flush=True)
    out = EXPLORE / ("geom.json" if not only else "geom_test.json")
    json.dump(dict(events=rows, neg_steps=noise), open(out, "w"), default=float)


# ----------------------------------------------------------------------------- C: scoring machinery
def dedup(X, rad=DEDUP):
    """v0 evaluate.dedup_alarms semantics (greedy in input order: keep a point unless a kept point lies
    within rad), via a pair list instead of an O(n^2) loop."""
    X = np.asarray(X, float).reshape(-1, 3)
    n = len(X)
    if n < 2:
        return X
    pairs = cKDTree(X).query_pairs(rad, output_type="ndarray")
    if len(pairs) == 0:
        return X
    pairs = pairs[np.lexsort((pairs[:, 1], pairs[:, 0]))]
    indptr = np.searchsorted(pairs[:, 0], np.arange(n + 1))
    removed = np.zeros(n, bool)
    keep = []
    for i in range(n):
        if removed[i]:
            continue
        keep.append(i)
        removed[pairs[indptr[i]:indptr[i + 1], 1]] = True
    return X[keep]


def cell_centres(P):
    """metrics.cells_to_xyz for every cell at once: mean of the cell's valid corners (NaN if none)."""
    C = np.stack([P[:-1, :-1], P[:-1, 1:], P[1:, :-1], P[1:, 1:]], 0)
    ok = np.isfinite(C).all(-1)
    s = np.where(ok[..., None], C, 0.0).sum(0)
    n = ok.sum(0)
    with np.errstate(invalid="ignore", divide="ignore"):
        out = s / n[..., None]
    out[n == 0] = np.nan
    return out


class PatchScorer:
    def __init__(self, nm, rec):
        self.nm = nm
        P, _ = patch_geom(nm)
        self.P = P
        self.C = cell_centres(P)
        self.conf = [e for e in rec["events"] if e["status"] == "confirmed"]
        self.ev_pts = [event_points(e) for e in self.conf]
        allp = [event_points(e) for e in rec["events"]]
        self.all_ev = np.concatenate(allp) if allp else np.zeros((0, 3))
        self.all_ev_tree = cKDTree(self.all_ev) if len(self.all_ev) else None
        negs = [n for n in rec["negatives"] if n["status"] == "confirmed"]
        self.neg_V = [np.array([P[tuple(v)] for v in n["verts"]]) for n in negs]
        self.neg_trees = [cKDTree(V) for V in self.neg_V]
        self.neg_mm = sum(n["len_mm"] for n in negs)
        self.neg_all = np.concatenate(self.neg_V) if self.neg_V else np.zeros((0, 3))
        vv = np.argwhere(np.isfinite(P).all(-1))
        self.valid_v = vv
        self.area_mm2 = len(vv) * (STEP_VX / MM) ** 2

    def alarms_from_cells(self, mask):
        cells = np.argwhere(mask)
        if len(cells) == 0:
            return np.zeros((0, 3))
        X = self.C[cells[:, 0], cells[:, 1]]
        return X[np.isfinite(X).all(-1)]

    def score(self, A, do_dedup=True):
        """(event hits list, false alarms, negative vertices flagged, negative vertices) under v0 rules."""
        A = dedup(A) if do_dedup else np.asarray(A).reshape(-1, 3)
        if len(A) == 0:
            return [False] * len(self.conf), 0, 0, len(self.neg_all)
        T = cKDTree(A)
        hits = [bool(T.query(X)[0].min() <= MATCH) for X in self.ev_pts]
        off = ~(self.all_ev_tree.query(A)[0] <= MATCH) if self.all_ev_tree is not None else np.ones(len(A), bool)
        fa = 0
        for tr in self.neg_trees:
            fa += int(((tr.query(A)[0] <= MATCH) & off).sum())
        flagged = int((T.query(self.neg_all)[0] <= MATCH).sum()) if len(self.neg_all) else 0
        return hits, fa, flagged, len(self.neg_all)


def stage_sweep():
    recs = load_corpus()
    pats = scored_patches(recs)
    scorers = {nm: PatchScorer(nm, recs[nm]) for nm in pats}
    order = [(nm, i) for nm in pats for i in range(len(scorers[nm].conf))]
    neg_mm = sum(s.neg_mm for s in scorers.values())
    t0 = time.time()

    def total(fn):
        hits, fa, fl, nv = [], 0, 0, 0
        per_patch = {}
        for nm in pats:
            h, f, g, n = fn(nm, scorers[nm])
            hits += h
            fa += f
            fl += g
            nv += n
            per_patch[nm] = dict(fa=f, flagged=g, nv=n)
        return dict(hits=[int(x) for x in hits], fa=fa, fa_per_100mm=100 * fa / neg_mm, flagged_frac=fl / max(nv, 1),
                    per_patch=per_patch)

    out = dict(event_order=order, negative_mm=neg_mm, doctor={}, doctor_nodedup_hits={}, review={}, random={})
    lv = {nm: np.load(EXPLORE / "sweep" / f"{nm}.npz") for nm in pats}
    val = dict(viol_r=int(sum(int(z["viol_r"]) for z in lv.values())),
               viol_m=int(sum(int(z["viol_m"]) for z in lv.values())))
    # validation: sweep default == capture default, and the rebuilt mask from captured scores == both
    mism_default, mism_rebuild = [], []
    for nm in pats:
        cz = cap_arrays(nm)
        d_sweep = lv[nm]["default_mask"]
        if not np.array_equal(d_sweep, cz["cns"]):
            mism_default.append(nm)
        if not np.array_equal(rebuild_mask(cz, DOC_THR, DOC_MINC), cz["cns"]):
            mism_rebuild.append(nm)
    val.update(default_mismatch=mism_default, rebuild_mismatch=mism_rebuild)
    out["validation"] = val
    for j, m in enumerate(M_GRID):
        for r in R_GRID:
            key = f"r={r:.2f},m={m}"
            out["doctor"][key] = total(lambda nm, s: s.score(s.alarms_from_cells(lv[nm]["level"][j] >= r - 1e-9)))
            if (r, m) in ((DOC_THR, DOC_MINC), (DOC_THR, 1), (0.10, 8), (0.10, 1)):
                out["doctor_nodedup_hits"][key] = total(
                    lambda nm, s: s.score(s.alarms_from_cells(lv[nm]["level"][j] >= r - 1e-9), do_dedup=False))["hits"]
        print("sweep m", m, round(time.time() - t0), "s", flush=True)
    for tau in TAU_GRID:
        out["review"][f"tau={tau}"] = total(
            lambda nm, s: s.score(s.alarms_from_cells(np.nan_to_num(cap_arrays(nm)["review_score"], nan=-1) >= tau)))
    out["review"]["default_review_cue_mask"] = total(
        lambda nm, s: s.score(s.alarms_from_cells(cap_arrays(nm)["review_cue_mask"])))
    print("review done", round(time.time() - t0), "s", flush=True)
    for li, lam in enumerate(LAMBDAS):
        reps = []
        for k in range(N_REP):
            rng = np.random.default_rng([SEED + k, li])

            def rnd(nm, s):
                n = rng.poisson(lam * s.area_mm2)
                if n == 0:
                    return s.score(np.zeros((0, 3)))
                pick = s.valid_v[rng.choice(len(s.valid_v), min(n, len(s.valid_v)), replace=False)]
                return s.score(s.P[pick[:, 0], pick[:, 1]])
            t = total(rnd)
            reps.append(dict(hits=t["hits"], fa_per_100mm=t["fa_per_100mm"], flagged_frac=t["flagged_frac"]))
        out["random"][f"{lam:.5g}"] = reps
    print("random done", round(time.time() - t0), "s", flush=True)
    json.dump(out, open(EXPLORE / "sweep_scored.json", "w"), default=float)


def rebuild_mask(cz, r, m):
    """Coherent mask from the captured per-edge scores, the doctor's own rule (edge flags projected to
    incident cells, 8-connected components >= m cells, restricted to valid cells)."""
    h, v, cv = cz["hscore"], cz["vscore"], cz["valid_cells"]
    hf = np.isfinite(h) & (h >= r)
    vf = np.isfinite(v) & (v >= r)
    cand = np.zeros(cv.shape, bool)
    cand |= hf[:-1, :]
    cand |= hf[1:, :]
    cand |= vf[:, :-1]
    cand |= vf[:, 1:]
    cand &= cv
    lab, n = ndimage.label(cand, structure=np.ones((3, 3), int))
    if n == 0:
        return cand
    sizes = np.bincount(lab.ravel())
    keep = sizes >= m
    keep[0] = False
    return keep[lab]


def candidate_components(cz, r=DOC_THR):
    h, v, cv = cz["hscore"], cz["vscore"], cz["valid_cells"]
    hf = np.isfinite(h) & (h >= r)
    vf = np.isfinite(v) & (v >= r)
    cand = np.zeros(cv.shape, bool)
    cand |= hf[:-1, :]
    cand |= hf[1:, :]
    cand |= vf[:, :-1]
    cand |= vf[:, 1:]
    cand &= cv
    lab, n = ndimage.label(cand, structure=np.ones((3, 3), int))
    sizes = np.bincount(lab.ravel())
    return lab, sizes


# ----------------------------------------------------------------------------- report helpers
def dist(x):
    x = np.asarray([v for v in x if v is not None and np.isfinite(v)], float)
    if len(x) == 0:
        return dict(n=0)
    q = np.percentile(x, [10, 25, 50, 75, 90])
    return dict(n=int(len(x)), median=float(q[2]), iqr=[float(q[1]), float(q[3])], p10=float(q[0]),
                p90=float(q[4]), min=float(x.min()), max=float(x.max()), mean=float(x.mean()))


def fisher(a_hit, a_n, b_hit, b_n):
    if a_n == 0 or b_n == 0:
        return None
    return float(stats.fisher_exact([[a_hit, a_n - a_hit], [b_hit, b_n - b_hit]])[1])


def too_small(w):
    return bool(w["n"] < 10 or (w["hi"] - w["lo"]) > 0.5) if w["n"] else True


def block_boot_recall(hits, patches, seed=SEED, B=B):
    pats = sorted(set(patches))
    by = {p: [h for h, q in zip(hits, patches) if q == p] for p in pats}
    rng = np.random.default_rng(seed)
    vals = []
    for _ in range(B):
        pick = rng.choice(len(pats), len(pats), replace=True)
        h = [x for i in pick for x in by[pats[i]]]
        if h:
            vals.append(sum(h) / len(h))
    return [float(np.percentile(vals, 2.5)), float(np.percentile(vals, 97.5))]


def event_level(ev):
    """Aggregate member crossings into one event (plan A3; X1 sheet-frame measure beside the planned one)."""
    mem = [m for m in ev["members"] if m.get("reproduced")]
    if not mem:
        return None

    def vals(k):
        return [m[k] for m in mem if m.get(k) is not None]

    W, ns = vals("W_mm"), vals("n_steps")
    steps, steps_sf = vals("max_step_vx"), vals("max_step_sf_vx")
    sc, scv = vals("doctor_zone_max_score"), vals("doctor_zone_max_vx")
    e = dict(n_members=len(ev["members"]), n_reproduced=len(mem),
             W_mm_median=float(np.median(W)), W_mm_min=float(np.min(W)),
             steps_median=float(np.median(ns)), steps_min=int(np.min(ns)),
             max_step_vx=max(steps) if steps else None,
             median_member_max_step_vx=float(np.median(steps)) if steps else None,
             max_step_sf_vx=max(steps_sf) if steps_sf else None,
             median_member_max_step_sf_vx=float(np.median(steps_sf)) if steps_sf else None,
             max_rate_vx_per_mm=max(vals("max_rate_vx_per_mm"), default=None),
             max_rate_sf_vx_per_mm=max(vals("max_rate_sf_vx_per_mm"), default=None),
             total_offset_vx_median=float(np.median(vals("total_offset_vx"))) if vals("total_offset_vx") else None,
             total_sf_vx_median=float(np.median(vals("total_sf_vx"))) if vals("total_sf_vx") else None,
             gap_a_median=float(np.median(vals("gap_a"))) if vals("gap_a") else None,
             gap_b_median=float(np.median(vals("gap_b"))) if vals("gap_b") else None,
             spacing_b_median=float(np.median(vals("spacing_b"))) if vals("spacing_b") else None,
             doctor_zone_max_score=max(sc) if sc else None, doctor_zone_max_vx=max(scv) if scv else None,
             n_step_measurements=int(sum(m.get("n_step_measurements", 0) for m in mem)),
             any_partial=any(m.get("partial") for m in mem))
    ge = lambda x, t: None if x is None else bool(x >= t)
    e["abrupt_primary_planned"] = ge(e["max_step_vx"], ABRUPT_VX)
    e["abrupt_primary_sf"] = ge(e["max_step_sf_vx"], ABRUPT_VX)
    e["abrupt_s1_median_member_planned"] = ge(e["median_member_max_step_vx"], ABRUPT_VX)
    e["abrupt_s1_median_member_sf"] = ge(e["median_member_max_step_sf_vx"], ABRUPT_VX)
    e["abrupt_s2_width_1step"] = bool(np.median(ns) <= 1)
    e["abrupt_s3_intrinsic_planted_level"] = ge(e["doctor_zone_max_score"], S3_SCORE)
    e["abrupt_s4_doctor_candidate"] = ge(e["doctor_zone_max_score"], DOC_THR)
    return e


# ----------------------------------------------------------------------------- report
def _grp(rows, flag, hitkey):
    a = [r for r in rows if r[flag] is True]
    g = [r for r in rows if r[flag] is False]
    wa = wilson(sum(r[hitkey] for r in a), len(a))
    wg = wilson(sum(r[hitkey] for r in g), len(g))
    return dict(abrupt=wa, gradual=wg, abrupt_too_small=too_small(wa), gradual_too_small=too_small(wg),
                n_undetermined=sum(1 for r in rows if r[flag] is None),
                fisher_p=fisher(wa["k"], wa["n"], wg["k"], wg["n"]))


def miss_decomposition(recs, geo_rows):
    """Per confirmed event: max doctor edge score within 1 mm, largest candidate component (r = 0.25)
    touching cells within 1 mm, and the class (i) sub-threshold / (ii) incoherent / (iii) coherent."""
    out = {}
    by_patch = {}
    for r in geo_rows:
        by_patch.setdefault(r["patch"], []).append(r)
    for nm, rows in by_patch.items():
        P, _ = patch_geom(nm)
        cz = cap_arrays(nm)
        hs, vs = cz["hscore"], cz["vscore"]
        Mh = 0.5 * (P[:, :-1] + P[:, 1:])
        Mv = 0.5 * (P[:-1, :] + P[1:, :])
        M = np.concatenate([Mh.reshape(-1, 3), Mv.reshape(-1, 3)])
        S = np.concatenate([hs.reshape(-1), vs.reshape(-1)])
        ok = np.isfinite(M).all(-1)
        M, S = M[ok], S[ok]
        tree = cKDTree(M)
        C = cell_centres(P)
        lab, sizes = candidate_components(cz)
        cok = np.isfinite(C).all(-1)
        cidx = np.argwhere(cok)
        ctree = cKDTree(C[cok])
        for r in rows:
            e = recs[nm]["events"][r["event_index"]]
            X = event_points(e)
            ids = sorted({j for lst in tree.query_ball_point(X, r=MATCH) for j in lst})
            sc = S[ids]
            sc = sc[np.isfinite(sc)]
            mx = float(sc.max()) if len(sc) else None
            cids = sorted({j for lst in ctree.query_ball_point(X, r=MATCH) for j in lst})
            labs = [int(lab[tuple(cidx[j])]) for j in cids]
            comp = max((int(sizes[l]) for l in labs if l > 0), default=0)
            cls = ("i_subthreshold" if (mx is None or mx < DOC_THR) else
                   ("ii_incoherent" if comp < DOC_MINC else "iii_coherent"))
            out[(nm, r["event_index"])] = dict(max_edge_score_1mm=mx, max_candidate_component_1mm=comp, cls=cls)
    return out


def stage_report():
    recs = load_corpus()
    plan = json.load(open(OUT_JSON))
    v0 = json.load(open(V0_JSON))
    geo = json.load(open(EXPLORE / "geom.json"))
    sw = json.load(open(EXPLORE / "sweep_scored.json"))
    pl = json.load(open(EXPLORE / "planted.json"))
    res = {}

    # ---------------- A
    conf_rows, contra_rows = [], []
    mem_total = mem_rep = 0
    for r in geo["events"]:
        el = event_level(r)
        mem_total += len(r["members"])
        mem_rep += sum(1 for m in r["members"] if m.get("reproduced"))
        row = dict(patch=r["patch"], event_index=r["event_index"], status=r["status"],
                   xyz=[round(v, 1) for v in r["xyz"]], reproduced=el is not None)
        if el:
            row.update(el)
        (conf_rows if r["status"] == "confirmed" else contra_rows).append(row)
    conf_ok = [r for r in conf_rows if r["reproduced"]]
    contra_ok = [r for r in contra_rows if r["reproduced"]]
    A = dict(n_confirmed=len(conf_rows), n_confirmed_reproduced=len(conf_ok),
             n_contradicted=len(contra_rows), n_contradicted_reproduced=len(contra_ok),
             members_total=mem_total, members_reproduced=mem_rep,
             n_confirmed_with_offset_measure=sum(1 for r in conf_ok if r["max_step_vx"] is not None),
             n_confirmed_any_partial=sum(1 for r in conf_ok if r["any_partial"]))
    A["distributions_confirmed"] = {k: dist([r[k] for r in conf_ok]) for k in (
        "W_mm_median", "W_mm_min", "steps_median", "max_step_vx", "max_step_sf_vx", "median_member_max_step_vx",
        "median_member_max_step_sf_vx", "max_rate_vx_per_mm", "max_rate_sf_vx_per_mm", "total_offset_vx_median",
        "total_sf_vx_median", "gap_a_median", "gap_b_median", "spacing_b_median", "doctor_zone_max_score",
        "doctor_zone_max_vx", "n_members")}
    flags = ["abrupt_primary_planned", "abrupt_primary_sf", "abrupt_s1_median_member_planned",
             "abrupt_s1_median_member_sf", "abrupt_s2_width_1step", "abrupt_s3_intrinsic_planted_level",
             "abrupt_s4_doctor_candidate"]
    A["fraction_abrupt_confirmed"] = {f: dict(**wilson(sum(1 for r in conf_ok if r[f] is True),
                                                     sum(1 for r in conf_ok if r[f] is not None)),
                                              n_undetermined=sum(1 for r in conf_ok if r[f] is None)) for f in flags}
    A["fraction_abrupt_contradicted"] = {f: wilson(sum(1 for r in contra_ok if r[f] is True),
                                                   sum(1 for r in contra_ok if r[f] is not None)) for f in flags}

    def bins(vals, edges, labels):
        vals = [v for v in vals if v is not None]
        c = {l: 0 for l in labels}
        for v in vals:
            for (lo, hi), l in zip(edges, labels):
                if lo < v <= hi:
                    c[l] += 1
                    break
        return c
    A["bins_W_steps_median"] = bins([r["steps_median"] for r in conf_ok],
                                    [(-1, 1), (1, 2), (2, 5), (5, 10), (10, 1e9)], ["1", "2", "3-5", "6-10", ">10"])
    sb = [(-1, 2.75 - 1e-9), (2.75 - 1e-9, 5 - 1e-9), (5 - 1e-9, 8 - 1e-9), (8 - 1e-9, 16 - 1e-9), (16 - 1e-9, 1e9)]
    sl = ["<2.75", "2.75-5", "5-8", "8-16", ">=16"]
    A["bins_max_step_planned"] = bins([r["max_step_vx"] for r in conf_ok], sb, sl)
    A["bins_max_step_sf"] = bins([r["max_step_sf_vx"] for r in conf_ok], sb, sl)
    A["bins_doctor_zone_max_vx"] = bins([r["doctor_zone_max_vx"] for r in conf_ok], sb, sl)
    A["abrupt_sf_by_member_count"] = {lab: wilson(sum(1 for r in conf_ok if lo <= r["n_members"] <= hi and r["abrupt_primary_sf"]),
                                                  sum(1 for r in conf_ok if lo <= r["n_members"] <= hi and r["abrupt_primary_sf"] is not None))
                                      for lab, lo, hi in (("1", 1, 1), ("2-5", 2, 5), ("6+", 6, 10 ** 6))}
    A["abrupt_planned_by_member_count"] = {lab: wilson(sum(1 for r in conf_ok if lo <= r["n_members"] <= hi and r["abrupt_primary_planned"]),
                                                       sum(1 for r in conf_ok if lo <= r["n_members"] <= hi and r["abrupt_primary_planned"] is not None))
                                           for lab, lo, hi in (("1", 1, 1), ("2-5", 2, 5), ("6+", 6, 10 ** 6))}
    # measurement-noise floor from confirmed negative runs (trace stays on one sheet)
    ns_pl = np.array([x["step"] for x in geo["neg_steps"]], float)
    ns_sf = np.array([x["step_sf"] for x in geo["neg_steps"] if x["step_sf"] is not None], float)
    noise = {}
    for name, arr, key in (("planned", ns_pl, "n_step_measurements"), ("sf", ns_sf, "n_step_measurements")):
        q = float((arr >= ABRUPT_VX).mean()) if len(arr) else None
        exp_noise = float(sum(1 - (1 - q) ** r[key] for r in conf_ok)) if q is not None else None
        noise[name] = dict(n_steps=int(len(arr)), median=float(np.median(arr)) if len(arr) else None,
                           p90=float(np.percentile(arr, 90)) if len(arr) else None,
                           p99=float(np.percentile(arr, 99)) if len(arr) else None,
                           p999=float(np.percentile(arr, 99.9)) if len(arr) else None,
                           frac_ge_8vx=q, expected_noise_only_abrupt_events=exp_noise)
    A["noise_floor_confirmed_negatives"] = noise
    # planted yardstick (A6)
    prow = pl["rows"]
    pub = {(4, 1): 0, (4, 4): 0, (4, 12): 1, (8, 1): 124, (8, 4): 0, (8, 12): 2, (16, 1): 128, (16, 4): 2, (16, 12): 8}
    ladder = []
    for off in (4.0, 8.0, 16.0):
        for wdt in (1, 4, 12):
            rr = [x for x in prow if x["offset_vx"] == off and x["width_cells"] == wdt]
            ms = [x["max_score"] for x in rr if x["max_score"] is not None]
            mls = [x["median_line_max_score"] for x in rr if x["median_line_max_score"] is not None]
            fr = [x["frac_lines_ge_025"] for x in rr if x["frac_lines_ge_025"] is not None]
            ref = [x["ref_spacing"] for x in rr]
            flat = next((x for x in pl["flat"] if x["offset_vx"] == off and x["width_cells"] == wdt), None)
            ladder.append(dict(offset_vx=off, width_cells=wdt, n=len(rr), detected_replicated=sum(x["detected"] for x in rr),
                               detected_published_holdout=pub[(int(off), wdt)],
                               max_step_vx=rr[0]["max_step_vx"] if rr else None,
                               max_rate_vx_per_mm=(rr[0]["max_step_vx"] / (STEP_VX / MM)) if rr else None,
                               n_transition_steps=rr[0]["n_transition_steps"] if rr else None,
                               seam_max_score_median=float(np.median(ms)) if ms else None,
                               seam_line_max_score_median=float(np.median(mls)) if mls else None,
                               frac_lines_ge_025_median=float(np.median(fr)) if fr else None,
                               ref_spacing_median=float(np.median(ref)) if ref else None,
                               flat_grid_max_score=flat["max_score"] if flat else None))
    base = [x["base_median_line_max_score"] for x in prow if x["offset_vx"] == 8.0 and x["width_cells"] == 1
            and x["base_median_line_max_score"] is not None]
    A["planted_yardstick"] = dict(note=("detected_replicated counts new coherent-normal-step cells only; the published "
                                        "gradual rows (x4, x12 cells) count any new cue, so small differences there are "
                                        "expected; the abrupt rows match exactly (124/128 and 128/128)"),
                                  ladder=ladder, unplanted_seam_line_max_score_median=float(np.median(base)) if base else None,
                                  n_patches=len({x["patch"] for x in prow}), errors=pl.get("errors", []),
                                  grid_step_vx_median=float(np.median([x["ref_spacing"] for x in prow])))
    # A6b (addition X2): the same ladder on 20 vx meshes (the natural corpus's resolution)
    p20 = json.load(open(EXPLORE / "planted20.json"))
    rows20 = p20["rows"]
    lad20 = []
    for off in (4.0, 8.0, 16.0):
        for wdt in (1, 4, 12):
            rr = [x for x in rows20 if x["offset_vx"] == off and x["width_cells"] == wdt]
            lad20.append(dict(offset_vx=off, width_cells=wdt, n=len(rr),
                              detected_default=wilson(sum(x["detected"] for x in rr), len(rr)),
                              detected_by_ratio_m8={k: sum(x["detected_by_ratio_m8"][k] for x in rr) for k in rr[0]["detected_by_ratio_m8"]},
                              max_step_vx=rr[0]["max_step_vx"], n_transition_steps=rr[0]["n_transition_steps"],
                              seam_max_score_median=float(np.median([x["max_score"] for x in rr if x["max_score"] is not None])),
                              seam_line_max_score_median=float(np.median([x["median_line_max_score"] for x in rr
                                                                          if x["median_line_max_score"] is not None]))))
    p8 = next(x for x in lad20 if x["offset_vx"] == 8.0 and x["width_cells"] == 1)
    ok_r = [float(k) for k, v in p8["detected_by_ratio_m8"].items() if v >= 124]
    A["planted_yardstick_20vx"] = dict(ladder=lad20, n_patches=len(p20["accepted"]), n_skipped=len(p20["skipped"]),
                                       n_candidates=p20["n_candidates"], rebuild_default_mismatches=p20["rebuild_default_mismatches"],
                                       grid_step_vx_median=float(np.median([x["ref_spacing"] for x in rows20])),
                                       seam_length_cells_median=float(np.median([x["n_lines"] for x in rows20])),
                                       matched_sensitivity_ratio_m8=max(ok_r) if ok_r else None)
    res["A_abruptness"] = A

    # ---------------- B
    idx = {}
    for nm in scored_patches(recs):
        k = 0
        for ie, e in enumerate(recs[nm]["events"]):
            if e["status"] == "confirmed":
                idx[(nm, k)] = ie
                k += 1
    order = [(nm, idx[(nm, i)]) for nm, i in sw["event_order"]]
    v0rows = v0["scored_events"]
    geo_by = {(r["patch"], r["event_index"]): r for r in conf_rows}
    for r in v0rows:
        e_idx = next(ie for ie, e in enumerate(recs[r["patch"]]["events"])
                     if e["status"] == "confirmed" and np.allclose(e["xyz"], r["xyz"], atol=1e-6))
        g = geo_by[(r["patch"], e_idx)]
        g["hit_v0_doctor"] = bool(r["tifxyz-doctor (coherent-normal-step)"])
        g["hit_v0_random"] = bool(r["random"])
    dflt = sw["doctor"][f"r={DOC_THR:.2f},m={DOC_MINC}"]["hits"]
    for key, h in zip(order, dflt):
        geo_by[key]["hit_mask_default"] = bool(h)
    md = miss_decomposition(recs, conf_rows)
    for key, v in md.items():
        geo_by[key].update(v)
    rows_ok = [r for r in conf_rows if r["reproduced"]]
    Bres = dict(n_events=len(rows_ok), n_not_reproduced=len(conf_rows) - len(rows_ok),
                hits_total={h: int(sum(r.get(h, False) for r in conf_rows)) for h in ("hit_v0_doctor", "hit_v0_random", "hit_mask_default")},
                hits_in_reproduced={h: int(sum(r.get(h, False) for r in rows_ok)) for h in ("hit_v0_doctor", "hit_v0_random", "hit_mask_default")})
    Bres["tables"] = {h: {f: _grp(rows_ok, f, h) for f in ("abrupt_primary_planned", "abrupt_primary_sf",
                                                             "abrupt_s3_intrinsic_planted_level", "abrupt_s4_doctor_candidate")}
                      for h in ("hit_v0_doctor", "hit_v0_random", "hit_mask_default")}
    keep = ["patch", "xyz", "n_members", "W_mm_median", "steps_median", "max_step_vx", "max_step_sf_vx",
            "doctor_zone_max_score", "max_edge_score_1mm", "max_candidate_component_1mm", "cls",
            "abrupt_primary_planned", "abrupt_primary_sf", "hit_v0_doctor", "hit_v0_random", "hit_mask_default"]
    Bres["doctor_v0_hits"] = [{k: r.get(k) for k in keep} for r in conf_rows if r.get("hit_v0_doctor")]
    Bres["random_v0_hits"] = [{k: r.get(k) for k in keep} for r in conf_rows if r.get("hit_v0_random")]
    Bres["mask_default_hits"] = [{k: r.get(k) for k in keep} for r in conf_rows if r.get("hit_mask_default")]
    cls = [r.get("cls") for r in conf_rows]
    Bres["miss_decomposition_all_events"] = {c: cls.count(c) for c in ("i_subthreshold", "ii_incoherent", "iii_coherent")}
    Bres["miss_decomposition_v0_misses"] = {c: sum(1 for r in conf_rows if not r.get("hit_v0_doctor") and r.get("cls") == c)
                                            for c in ("i_subthreshold", "ii_incoherent", "iii_coherent")}
    Bres["max_edge_score_1mm"] = dist([r.get("max_edge_score_1mm") for r in conf_rows])
    res["B_hits_vs_abruptness"] = Bres

    # ---------------- C
    pats = scored_patches(recs)
    ev_patch = [nm for nm, _ in order]
    negmm = {nm: sum(n["len_mm"] for n in recs[nm]["negatives"] if n["status"] == "confirmed") for nm in pats}
    NEG = sw["negative_mm"]
    rng = np.random.default_rng(SEED)
    capped = set()
    for nm in pats:
        ii = [i for i, (p, _) in enumerate(order) if p == nm]
        if len(ii) > 3:
            ii = sorted(rng.choice(ii, 3, replace=False).tolist())
        capped.update(ii)
    abr_sf = [geo_by[k].get("abrupt_primary_sf") for k in order]
    abr_pl = [geo_by[k].get("abrupt_primary_planned") for k in order]

    def summarize(t, label_):
        h = t["hits"]
        w = wilson(sum(h), len(h))
        noBIG = [x for x, p in zip(h, ev_patch) if p != BIG]
        cap = [x for i, x in enumerate(h) if i in capped]
        fa_nb = (t["fa"] - t["per_patch"].get(BIG, {}).get("fa", 0)) / (NEG - negmm.get(BIG, 0)) * 100
        split = {}
        for nmf, ab in (("sf", abr_sf), ("planned", abr_pl)):
            split[nmf] = dict(abrupt=wilson(sum(x for x, a in zip(h, ab) if a is True), sum(1 for a in ab if a is True)),
                              gradual=wilson(sum(x for x, a in zip(h, ab) if a is False), sum(1 for a in ab if a is False)))
        return dict(config=label_, recall=w, fa_per_100mm=t["fa_per_100mm"], false_alarms=t["fa"],
                    flagged_frac=t["flagged_frac"], recall_excl_big=wilson(sum(noBIG), len(noBIG)),
                    fa_per_100mm_excl_big=fa_nb, recall_cap3=wilson(sum(cap), len(cap)), split=split)
    table = [summarize(t, k) for k, t in sw["doctor"].items()]
    review = [summarize(t, k) for k, t in sw["review"].items()]
    # random curve
    rc = []
    for lam, reps in sw["random"].items():
        rec_ = [sum(x["hits"]) / len(x["hits"]) for x in reps]
        fa_ = [x["fa_per_100mm"] for x in reps]
        rc.append(dict(density_per_mm2=float(lam), recall_mean=float(np.mean(rec_)), recall_p2_5=float(np.percentile(rec_, 2.5)),
                       recall_p97_5=float(np.percentile(rec_, 97.5)), fa_mean=float(np.mean(fa_)),
                       flagged_frac_mean=float(np.mean([x["flagged_frac"] for x in reps]))))
    rc.sort(key=lambda x: x["fa_mean"])
    rfa = np.array([x["fa_mean"] for x in rc])
    rre = np.array([x["recall_mean"] for x in rc])

    def rand_at(fa):
        return float(np.interp(fa, rfa, rre))

    def best(tab, cap):
        ok = [t for t in tab if t["fa_per_100mm"] <= cap]
        if not ok:
            return None
        b = max(ok, key=lambda t: (t["recall"]["p"], -t["fa_per_100mm"]))
        hk = sw["doctor"].get(b["config"]) or sw["review"].get(b["config"])
        out = dict(b)
        out["recall_patch_block_ci95"] = block_boot_recall(hk["hits"], ev_patch)
        out["random_recall_at_same_fa"] = rand_at(b["fa_per_100mm"])
        out["doctor_minus_random"] = b["recall"]["p"] - out["random_recall_at_same_fa"]
        out["precision_corrected_upper"] = min(1.0, b["recall"]["hi"] / plan_prec(v0))
        out["n_configs_eligible"] = len(ok)
        return out
    C = dict(validation=sw["validation"], n_configs=len(table), negative_mm=NEG)
    dkey = f"r={DOC_THR:.2f},m={DOC_MINC}"
    C["default_mask_point"] = next(t for t in table if t["config"] == dkey)
    C["default_mask_point"]["recall_patch_block_ci95"] = block_boot_recall(sw["doctor"][dkey]["hits"], ev_patch)
    C["default_mask_point"]["random_recall_at_same_fa"] = rand_at(C["default_mask_point"]["fa_per_100mm"])
    C["v0_cli_point"] = dict(hits=6, n=54, recall=6 / 54, fa_per_100mm=v0["evaluation"]["detectors"]["tifxyz-doctor (coherent-normal-step)"]["fa_per_100mm"])
    C["nodedup_hits"] = {k: int(sum(v)) for k, v in sw["doctor_nodedup_hits"].items()}
    ms = A["planted_yardstick_20vx"]["matched_sensitivity_ratio_m8"]
    if ms is not None:
        mk = f"r={ms:.2f},m=8"
        mp = dict(next(t for t in table if t["config"] == mk))
        mp["recall_patch_block_ci95"] = block_boot_recall(sw["doctor"][mk]["hits"], ev_patch)
        mp["random_recall_at_same_fa"] = rand_at(mp["fa_per_100mm"])
        mp["planted_8vx_1cell_20vx_detected"] = p8["detected_by_ratio_m8"][f"{ms:.2f}"]
        C["matched_sensitivity_point"] = mp
    C["best_fa_le_1"] = best(table, 1.0)
    C["best_fa_le_5"] = best(table, 5.0)
    C["review_score_best_fa_le_1"] = best(review, 1.0)
    C["review_score_best_fa_le_5"] = best(review, 5.0)
    C["random_curve"] = rc
    C["random_recall_at_fa_1"] = rand_at(1.0)
    C["random_recall_at_fa_5"] = rand_at(5.0)
    C["sweep_table"] = [dict(config=t["config"], hits=t["recall"]["k"], recall=t["recall"]["p"], recall_ci95=[t["recall"]["lo"], t["recall"]["hi"]],
                             fa_per_100mm=t["fa_per_100mm"], flagged_frac=t["flagged_frac"],
                             random_recall_at_same_fa=rand_at(t["fa_per_100mm"]),
                             hits_abrupt_sf=t["split"]["sf"]["abrupt"]["k"], n_abrupt_sf=t["split"]["sf"]["abrupt"]["n"],
                             hits_gradual_sf=t["split"]["sf"]["gradual"]["k"], n_gradual_sf=t["split"]["sf"]["gradual"]["n"])
                        for t in table]
    C["review_table"] = [dict(config=t["config"], hits=t["recall"]["k"], recall=t["recall"]["p"], fa_per_100mm=t["fa_per_100mm"],
                              flagged_frac=t["flagged_frac"]) for t in review]
    # per-event highest r at which the event is hit (m = 8 and m = 1)
    per_ev_thr = {}
    for mm_ in (8, 1):
        best_r = [0.0] * len(order)
        for r in R_GRID:
            h = sw["doctor"][f"r={r:.2f},m={mm_}"]["hits"]
            for i, x in enumerate(h):
                if x and r > best_r[i]:
                    best_r[i] = r
        per_ev_thr[mm_] = best_r
    C["per_event_highest_hit_ratio_m8"] = dist([x for x in per_ev_thr[8]])
    C["events_never_hit_m8"] = int(sum(1 for x in per_ev_thr[8] if x == 0))
    C["events_never_hit_m1"] = int(sum(1 for x in per_ev_thr[1] if x == 0))
    for i, k in enumerate(order):
        geo_by[k]["highest_hit_ratio_m8"] = per_ev_thr[8][i]
        geo_by[k]["highest_hit_ratio_m1"] = per_ev_thr[1][i]
    fr = []
    for cap in (0.1, 0.25, 0.5, 1, 2, 3, 5, 10, 20, 50):
        okc = [t for t in C["sweep_table"] if t["fa_per_100mm"] <= cap]
        b = max(okc, key=lambda t: (t["recall"], -t["fa_per_100mm"]))
        fr.append(dict(fa_cap=cap, config=b["config"], hits=b["hits"], recall=b["recall"], recall_ci95=b["recall_ci95"],
                       fa_per_100mm=b["fa_per_100mm"], flagged_frac=b["flagged_frac"],
                       random_recall_at_same_fa=b["random_recall_at_same_fa"],
                       abrupt_sf=[b["hits_abrupt_sf"], b["n_abrupt_sf"]], gradual_sf=[b["hits_gradual_sf"], b["n_gradual_sf"]]))
    C["frontier_best_over_grid"] = fr
    v0d = v0["evaluation"]["random_density_per_mm2"]
    lams = sorted(sw["random"], key=float)
    lo_l = max((l for l in lams if float(l) <= v0d), key=float)
    hi_l = min((l for l in lams if float(l) >= v0d), key=float)
    C["random_near_v0_density"] = dict(
        v0_density_per_mm2=v0d, v0_realized=dict(hits=5, fa_per_100mm=v0["evaluation"]["detectors"]["random"]["fa_per_100mm"]),
        bracket={l: dict(fa_min_median_max=[float(np.min([x["fa_per_100mm"] for x in sw["random"][l]])),
                                            float(np.median([x["fa_per_100mm"] for x in sw["random"][l]])),
                                            float(np.max([x["fa_per_100mm"] for x in sw["random"][l]]))],
                         hits_min_median_max=[int(np.min([sum(x["hits"]) for x in sw["random"][l]])),
                                              float(np.median([sum(x["hits"]) for x in sw["random"][l]])),
                                              int(np.max([sum(x["hits"]) for x in sw["random"][l]]))]) for l in (lo_l, hi_l)})
    res["C_operating_point_sweep"] = C
    ms_r = A["planted_yardstick_20vx"]["matched_sensitivity_ratio_m8"]
    prof = {}
    for nmf, flag in (("abrupt_sf", True), ("gradual_sf", False)):
        g = [geo_by[k] for k in order if geo_by[k].get("abrupt_primary_sf") is flag]
        prof[nmf] = dict(n=len(g), members_le_2=sum(1 for e in g if e["n_members"] <= 2),
                         members_median=float(np.median([e["n_members"] for e in g])),
                         doctor_zone_max_score_median=float(np.median([e["doctor_zone_max_score"] for e in g])),
                         max_edge_score_1mm_median=float(np.median([e["max_edge_score_1mm"] for e in g])),
                         W_steps_median=float(np.median([e["steps_median"] for e in g])),
                         total_sf_vx_median=float(np.median([e["total_sf_vx_median"] for e in g if e.get("total_sf_vx_median") is not None])),
                         miss_classes={c: sum(1 for e in g if e.get("cls") == c) for c in ("i_subthreshold", "ii_incoherent", "iii_coherent")},
                         hit_at_matched_ratio_m8=sum(1 for e in g if ms_r is not None and e.get("highest_hit_ratio_m8", 0) >= ms_r - 1e-9))
    res["B_hits_vs_abruptness"]["abrupt_vs_gradual_profile"] = prof

    # ---------------- D
    fa = A["fraction_abrupt_confirmed"]

    def rule_g(w):
        if w["n"] == 0:
            return "UNRESOLVED"
        return "SUPPORTED" if w["hi"] < 0.5 else ("CONTRADICTED" if w["lo"] > 0.5 else "UNRESOLVED")
    g_pl, g_sf = rule_g(fa["abrupt_primary_planned"]), rule_g(fa["abrupt_primary_sf"])
    claim_g = g_pl if g_pl == g_sf else "UNRESOLVED"
    b5 = C["best_fa_le_5"]
    if b5 is None:
        claim_t = "UNRESOLVED"
    else:
        claim_t = "SUPPORTED" if b5["recall"]["hi"] < 0.5 else ("CONTRADICTED" if b5["recall"]["p"] >= 0.5 else "UNRESOLVED")
    # label-noise mixture (indicative)
    ln = v0["label_noise"]
    pi_c = ln["est_precision_of_confirmed_events"]
    n_dec = v0["corpus"]["events_confirmed"] + v0["corpus"]["events_contradicted"]
    pi_x = (ln["est_true_switch_fraction_among_geometry_events"] * n_dec - pi_c * v0["corpus"]["events_confirmed"]) / v0["corpus"]["events_contradicted"]
    mix = {}
    for f in ("abrupt_primary_planned", "abrupt_primary_sf", "abrupt_s3_intrinsic_planted_level"):
        ac = [r[f] for r in conf_ok if r[f] is not None]
        ax = [r[f] for r in contra_ok if r[f] is not None]

        def solve(a1, a2):
            M = np.array([[pi_c, 1 - pi_c], [pi_x, 1 - pi_x]])
            return np.linalg.solve(M, np.array([a1, a2]))
        pt = solve(np.mean(ac), np.mean(ax)) if ac and ax else None
        rngm = np.random.default_rng(SEED)
        bs = []
        for _ in range(B):
            a1 = np.mean(rngm.choice(ac, len(ac), replace=True))
            a2 = np.mean(rngm.choice(ax, len(ax), replace=True))
            bs.append(solve(a1, a2))
        bs = np.array(bs)
        mix[f] = dict(abrupt_frac_confirmed=float(np.mean(ac)) if ac else None, abrupt_frac_contradicted=float(np.mean(ax)) if ax else None,
                      n_confirmed=len(ac), n_contradicted=len(ax),
                      est_abrupt_frac_true_switches=float(pt[0]) if pt is not None else None,
                      est_abrupt_frac_false_events=float(pt[1]) if pt is not None else None,
                      true_ci95_unclipped=[float(np.percentile(bs[:, 0], 2.5)), float(np.percentile(bs[:, 0], 97.5))],
                      false_ci95_unclipped=[float(np.percentile(bs[:, 1], 2.5)), float(np.percentile(bs[:, 1], 97.5))])
    res["D_takeaway"] = dict(claim_G=dict(verdict=claim_g, under_planned=g_pl, under_sheet_frame=g_sf),
                             claim_T=dict(verdict=claim_t, best_fa_le_5_recall=b5["recall"] if b5 else None,
                                          best_fa_le_5_config=b5["config"] if b5 else None),
                             label_noise_mixture=dict(pi_confirmed=pi_c, pi_contradicted=pi_x, by_definition=mix))
    res["per_event"] = [{k: (round(v, 4) if isinstance(v, float) else v) for k, v in r.items()} for r in conf_rows]
    plan["status"] = ("RESULTS (exploratory). Plan committed before any number (6a0765e); deviation X1 (c4fd704) and "
                      "addition X2 (655503d) logged before the numbers they affect.")
    plan["results"] = res
    plan["provenance"] = dict(generated_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                              doctor_commit="5ca0444fb31863c8e02466316bf9e560cf567876",
                              intermediates="session scratchpad (EXPLORE_DIR), regenerable with the usage lines in the code")
    json.dump(plan, open(OUT_JSON, "w"), indent=1, default=float)
    print(json.dumps(dict(A=A["fraction_abrupt_confirmed"], D=res["D_takeaway"]["claim_G"], T=claim_t), default=float)[:3000])


def plan_prec(v0):
    return v0["label_noise"]["est_precision_of_confirmed_events"]


def stage_report_v1():
    """v1's report stage: only section A (per-event abruptness geometry -> abrupt_primary_sf), the one
    thing tools.switchbench_kit.strata_gen reads (results.per_event). No sweep/planted/label-noise
    sections (B/C/D): those compare against a v0-only operating-point sweep and the doctor's planted
    holdout, which are out of scope for the abrupt/gradual strata this stage feeds -- see
    internal/release/RELEASE_RUNBOOK.md 4a2. Uses the identical event_level() classification as v0
    (same ABRUPT_VX threshold, same sheet-frame measure), just without the doctor capture arrays."""
    geo = json.load(open(EXPLORE / "geom.json"))
    conf_rows, contra_rows = [], []
    mem_total = mem_rep = 0
    for r in geo["events"]:
        el = event_level(r)
        mem_total += len(r["members"])
        mem_rep += sum(1 for m in r["members"] if m.get("reproduced"))
        row = dict(patch=r["patch"], event_index=r["event_index"], status=r["status"],
                   xyz=[round(v, 1) for v in r["xyz"]], reproduced=el is not None)
        if el:
            row.update(el)
        (conf_rows if r["status"] == "confirmed" else contra_rows).append(row)
    conf_ok = [r for r in conf_rows if r["reproduced"]]
    flags = ["abrupt_primary_planned", "abrupt_primary_sf"]
    fraction_abrupt = {f: dict(**wilson(sum(1 for r in conf_ok if r[f] is True),
                                        sum(1 for r in conf_ok if r[f] is not None)),
                               n_undetermined=sum(1 for r in conf_ok if r[f] is None)) for f in flags}
    out = dict(
        title="SwitchBench-natural v1 abruptness exploration",
        status="RESULTS (exploratory, v1; not pre-registered, changes no v1 verdict, file or code path). "
               "Same event_level() classification as v0's switchbench_explore.json.",
        corpus=dict(n_confirmed=len(conf_rows), n_confirmed_reproduced=len(conf_ok),
                    n_contradicted=len(contra_rows), members_total=mem_total, members_reproduced=mem_rep),
        results=dict(fraction_abrupt_confirmed=fraction_abrupt,
                    per_event=[{k: (round(v, 4) if isinstance(v, float) else v) for k, v in r.items()}
                               for r in conf_rows]),
        provenance=dict(generated_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                        doctor_commit=None,
                        note="doctor per-edge capture arrays were not run for v1 (dummy NaN stand-in; see "
                             "cap_arrays): doctor_zone_max_score/_vx are None for every event, but "
                             "abrupt_primary_sf/_planned (the fields strata_gen reads) do not depend on them.",
                        intermediates="EXPLORE_DIR, resumable per-patch checkpoints under geom_patches/"))
    json.dump(out, open(OUT_JSON, "w"), indent=1, default=float)
    print(json.dumps(dict(corpus=out["corpus"], fraction_abrupt_confirmed=fraction_abrupt), default=float)[:3000])


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("mode", choices=["geom", "sweep", "report"])
    ap.add_argument("patches", nargs="*", help="geom only: restrict to these patch ids (default: all scored)")
    ap.add_argument("--v1", action="store_true",
                    help="run against the v1 pooled corpus instead of v0 (equivalent to EXPLORE_MODE=v1; "
                         "must be set consistently across geom/report for one EXPLORE_DIR). 'sweep' has no "
                         "v1 mode (out of scope for the abrupt/gradual strata; see RELEASE_RUNBOOK.md 4a2).")
    a = ap.parse_args()
    if a.v1 and not IS_V1:
        raise SystemExit("--v1 was passed but EXPLORE_MODE is not 'v1'; set EXPLORE_MODE=v1 in the "
                          "environment (module-level constants like EXPLORE/OUT_JSON are fixed at import "
                          "time) and re-run, e.g.: EXPLORE_MODE=v1 python -m tools.switchbench.explore_abruptness "
                          f"{a.mode} --v1 " + " ".join(a.patches))
    if a.mode == "geom":
        stage_geom(set(a.patches) or None, checkpoint=IS_V1)
    elif a.mode == "sweep":
        if IS_V1:
            raise SystemExit("sweep has no v1 mode; see RELEASE_RUNBOOK.md 4a2")
        stage_sweep()
    elif a.mode == "report":
        stage_report_v1() if IS_V1 else stage_report()
