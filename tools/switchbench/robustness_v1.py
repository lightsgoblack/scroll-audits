"""POST-HOC, DESCRIPTIVE robustness checks for SwitchBench v1's C1 verdict (SUPPORTED, scored
2026-09-27). Nothing here can change the frozen verdict -- P1 (prereg/switchbench_v1.md) is never
edited, and the blind review's frozen combination (tifxyz-doctor coherent-normal-step, per-patch cap 3,
1 mm match, pooled + new) is the only one that counts. This module varies match radius, per-patch cap
and pooling choice around that point, using cached scoring outputs only (no detector is re-run):

  * ev_rows/patch_rows come from data/switchbench_v1/evaluation_v1.json (written by evaluate_v1.main());
    those already hold, per confirmed event, whether each tool's cached alarms land within 0.5/1/2 mm.
  * CT-contradicted candidates (status "contradicted" in the v1 events file) are not in evaluation_v1.json
    (evaluate_v1.build_rows only scores confirmed events), so this module matches them against the same
    cached tifxyz-doctor per-patch alarm files directly -- reading cached JSON and patch geometry only,
    never running the detector and never opening data/switchbench_v1/blind_key.json (the reviewer's
    answer key; irrelevant here -- "contradicted" is the public CT-profile label, not a blind-review answer).

In plain English: this asks "does the headline number (about 1 in 9 real switches caught) survive if we
had drawn the match radius, the per-patch cap, or which patches we grouped together slightly differently?"
It also asks a separate, purely descriptive question: on the batch of candidates where the CT check and
the geometry disagree, does the doctor's alarm rate look like its rate on confirmed real switches (which
would suggest some of those "contradicted" candidates are in fact real) or like its rate on background
(which would not)? Neither question can overturn C1; P1 fixed the one frozen combination that decides it.

Usage: python -m tools.switchbench.robustness_v1
"""
from __future__ import annotations

import json
import re
import time
from collections import Counter

import numpy as np

from . import evaluate, evaluate_v1 as e1, geom, metrics

RES = geom.REPO / "vault" / "results"
V1 = geom.REPO / "data" / "switchbench_v1"
DOCTOR = "tifxyz-doctor (coherent-normal-step)"
ANYCUE = "tifxyz-doctor (any cue)"
TOOLS = (DOCTOR, ANYCUE)
CAPS = (1, 3, None)                    # 3 = frozen (P1)
FROZEN = dict(cap=3, radius=1.0)
CORRECTED_BAR = 0.60
BATCH_RE = re.compile(r"^auto_grown_(\d{8})")


def batch_of(patch):
    """First 8 digits of the auto_grown timestamp (a date, YYYYMMDD); legacy full-size v0 patches
    (not auto-grown) fall into 'legacy'."""
    m = BATCH_RE.match(patch)
    return m.group(1) if m else "legacy"


def precision_lower_bound():
    """The blind review's measured precision, Wilson 95% lower bound (results/switchbench_natural_v1_blind_review_score.json).
    Not the blind key -- the already-scored result."""
    return json.load(open(RES / "switchbench_v1_blind_review_score.json"))["precision"]["wilson95"][0]


# ----------------------------------------------------------------------------- cached confirmed-event rows
def load_cached_ev_rows():
    """ev_rows from the cached evaluate_v1 run, with hit-dict radius keys restored to float (JSON
    round-tripped them to strings)."""
    d = json.load(open(V1 / "evaluation_v1.json"))
    ev_rows = d["ev_rows"]
    for r in ev_rows:
        r["hit"] = {t: {float(rr): v for rr, v in rd.items()} for t, rd in r["hit"].items()}
    return ev_rows


def sel_set(recs_scored, cap):
    """{(patch, event index)} selected under per-patch cap `cap` (None = uncapped)."""
    if cap is None:
        return None
    d = e1.cap_selection(recs_scored, cap)
    return {(p, i) for p, idxs in d.items() for i in idxs}


def cap_filter(sel):
    return None if sel is None else (lambda x, sel=sel: (x["patch"], x["i"]) in sel)


def combine(*fns):
    fns = [f for f in fns if f is not None]
    if not fns:
        return None
    return lambda x: all(f(x) for f in fns)


def with_corrected(stats, prec_lo):
    up = stats["boot95"][1]
    corr = (up / prec_lo) if up is not None else None
    stats = dict(stats, corrected_upper=corr, c1_would_hold=(corr is not None and corr < CORRECTED_BAR))
    return stats


# ----------------------------------------------------------------------------- main grid
def grid_rows(ev_rows, recs_scored, prec_lo):
    """(tool, cap, radius, subset) recall + patch-block bootstrap CI + corrected upper, pooled/new/v0_prefix."""
    out = []
    sel_by_cap = {cap: sel_set(recs_scored, cap) for cap in CAPS}
    subsets = (("pooled", None), ("new", "new"), ("v0_prefix", "v0"))
    for tool in TOOLS:
        for cap in CAPS:
            ef = cap_filter(sel_by_cap[cap])
            for radius in e1.RADII:
                for sname, sval in subsets:
                    stats = e1.recall_stats(ev_rows, tool, sval, False, radius, ef)
                    out.append(dict(tool=tool, cap=("none" if cap is None else cap), radius=radius,
                                    subset=sname, frozen=(cap == FROZEN["cap"] and radius == FROZEN["radius"]),
                                    **with_corrected(stats, prec_lo)))
    return out


def batch_rows(ev_rows, recs_scored, prec_lo):
    """Same recall/CI/corrected-upper, per auto-grown batch (date prefix), frozen radius (1 mm)."""
    out = []
    counts = Counter(batch_of(r["patch"]) for r in recs_scored)
    sel_by_cap = {cap: sel_set(recs_scored, cap) for cap in CAPS}
    for tool in TOOLS:
        for cap in CAPS:
            efc = cap_filter(sel_by_cap[cap])
            for batch in sorted(counts):
                ef = combine(efc, lambda x, b=batch: batch_of(x["patch"]) == b)
                stats = e1.recall_stats(ev_rows, tool, None, False, 1.0, ef)
                out.append(dict(tool=tool, cap=("none" if cap is None else cap), radius=1.0, batch=batch,
                                n_patches_in_batch=counts[batch], **with_corrected(stats, prec_lo)))
    return out, dict(counts)


# ----------------------------------------------------------------------------- CT-contradicted candidates
def load_contradicted_rows(recs):
    """One row per CT-contradicted candidate (status == 'contradicted') in a patch that already has a
    cached tifxyz-doctor run -- shaped like evaluate_v1's ev_rows (capped=True: every such row counts, no
    cap concept applies to a group that isn't 'confirmed switches'), so evaluate_v1.recall_stats can score
    it unmodified. No detector is re-run; patches with no cached detector output are skipped and counted."""
    rows = []
    patches_with_candidate, patches_cached = set(), set()
    for r in recs:
        contr = [e for e in r["events"] if e["status"] == "contradicted"]
        if not contr:
            continue
        patches_with_candidate.add(r["patch"])
        td = e1._j("tifxyz_doctor", r["patch"])
        if td is None:
            continue
        patches_cached.add(r["patch"])
        P, N, meta = e1.patch_geom(r["patch"])
        c2x = lambda cells: metrics.cells_to_xyz(P, cells)
        alarms = {DOCTOR: c2x(td["alarms_primary"]), ANYCUE: c2x(td["alarms_any"])}
        for e in contr:
            X = evaluate.event_points(e)
            rows.append(dict(patch=r["patch"], subset=r["subset"], i=e["i"], capped=True,
                             hit={tool: {rr: bool(e1.near_any(X, A, rr).any()) for rr in e1.RADII}
                                  for tool, A in alarms.items()}))
    return rows, dict(candidate_patches=len(patches_with_candidate), cached_patches=len(patches_cached),
                      candidate_events=sum(len([e for e in r["events"] if e["status"] == "contradicted"])
                                          for r in recs))


def contradicted_stats(rows, ev_rows, prec_lo):
    out = {}
    for tool in TOOLS:
        out[tool] = {}
        for sname, sval in (("pooled", None), ("new", "new"), ("v0_prefix", "v0")):
            ct = e1.recall_stats(rows, tool, sval, True, 1.0)
            conf = e1.recall_stats(ev_rows, tool, sval, False, 1.0)  # confirmed events, uncapped, same radius
            out[tool][sname] = dict(ct_contradicted=ct, confirmed_uncapped_comparison=conf)
    return out


# ----------------------------------------------------------------------------- assemble + write
def main():
    t0 = time.time()
    recs = e1.load_pooled()
    sc = e1.scored(recs)
    ev_rows = load_cached_ev_rows()
    prec_lo = precision_lower_bound()

    grid = grid_rows(ev_rows, sc, prec_lo)
    batches, batch_counts_map = batch_rows(ev_rows, sc, prec_lo)
    ctr_rows, ctr_cov = load_contradicted_rows(recs)
    ctr = contradicted_stats(ctr_rows, ev_rows, prec_lo)

    frozen_row = next(r for r in grid if r["tool"] == DOCTOR and r["cap"] == 3 and r["radius"] == 1.0 and r["subset"] == "pooled")
    frozen_new = next(r for r in grid if r["tool"] == DOCTOR and r["cap"] == 3 and r["radius"] == 1.0 and r["subset"] == "new")
    all_hold = all(r["c1_would_hold"] for r in grid if r["n_events"] > 0)

    out = dict(
        label="POST-HOC and DESCRIPTIVE: robustness checks around the frozen C1 result (P1). The frozen "
              "verdict (SUPPORTED) stands regardless of anything in this file.",
        generated_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        precision_lower_bound=dict(value=prec_lo, source="results/switchbench_natural_v1_blind_review_score.json precision.wilson95[0]"),
        corrected_upper_bar=CORRECTED_BAR,
        frozen_reproduction=dict(pooled=dict(recall=frozen_row["recall"], boot95=frozen_row["boot95"],
                                             corrected_upper=frozen_row["corrected_upper"]),
                                 new=dict(recall=frozen_new["recall"], boot95=frozen_new["boot95"],
                                         corrected_upper=frozen_new["corrected_upper"]),
                                 matches_switchbench_v1_json="see results/switchbench_natural_v1_blind_review_score.md"),
        grid=grid,
        all_grid_points_hold=all_hold,
        batches=batches,
        batch_patch_counts=batch_counts_map,
        ct_contradicted=dict(coverage=ctr_cov, stats=ctr),
        elapsed_s=time.time() - t0,
    )
    json.dump(out, open(RES / "switchbench_v1_robustness.json", "w"), indent=1, default=float)
    return out


if __name__ == "__main__":
    main()
