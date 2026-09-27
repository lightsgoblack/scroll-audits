"""SwitchBench v1: choose the level-0 (2.4 um) adjacent-wrap rule on human ladder controls only.

Input: data/switchbench_v1/ladder_profiles.npz (ladder_l0.py; relative_windings.json only, no corpus).
Grid and objective were fixed in this file before it was first run:
  grid      sigma {0.5, 1, 1.5, 2, 3} vx, end_zone {0.1, 0.15, 0.2, 0.3} x s, min_dark {1, 2, 3} vx,
            q {10, 20, 30}, mid_bias {0, 0.15, 0.3}                       (540 variants; level-2 vx units)
  objective on the TUNE half of the ladder collections: maximise adjacent pass among variants whose
            two-apart and same-sheet false-pass rates are both <= 5%; ties -> larger margin; if no
            variant qualifies, maximise margin = adjacent - max(two-apart, same-sheet) (v0's objective).
  report    rates of the chosen rule on the tune half, the held-out TEST half and all ladders (Wilson
            95% CI). STRONG (protocol P1 (prereg/switchbench_v1.md)) is judged on the held-out half: both false-pass rates <= 5%
            and adjacent pass >= 70%.
Also reported on the same controls: v0's rule constants at level 2 (the v0 setting) and at level 0.
Usage: python -m tools.switchbench.tune_l0
"""
from __future__ import annotations

import itertools
import json
import time

import numpy as np

from . import confirm, metrics, rule_l0
from .ladder_l0 import OUT as PROFILES, V1

OUT = V1 / "ct_rule_l0.json"
GRID = dict(sigma=[0.5, 1.0, 1.5, 2.0, 3.0], end_zone=[0.1, 0.15, 0.2, 0.3], min_dark=[1.0, 2.0, 3.0],
            q=[10, 20, 30], mid_bias=[0.0, 0.15, 0.3])
FP_MAX, ADJ_MIN = 0.05, 0.70
V0_RULE = dict(sigma=confirm.SIGMA, end_zone=confirm.END_ZONE, min_dark=confirm.MIN_DARK, q=confirm.Q, mid_bias=0.0)
KINDS = ("adjacent", "two_apart", "same_sheet")


def load():
    z = np.load(PROFILES)
    ctrl = [dict(kind=str(k), prof=int(p), t0=float(a), t1=float(b), s=float(s))
            for k, p, a, b, s in zip(z["c_kind"], z["c_prof"], z["c_t0"], z["c_t1"], z["c_s"])]
    split = z["split"]
    prof = {}
    for lev in (0, 2):
        off, v, step = z[f"off{lev}"], z[f"v{lev}"], float(z[f"step{lev}"])
        prof[lev] = [(z["t_lo"][j] + step * np.arange(off[j + 1] - off[j]), v[off[j]:off[j + 1]].astype(float))
                     for j in range(len(off) - 1)]
    return ctrl, split, prof, {0: float(z["step0"]), 2: float(z["step2"])}


def rates(res, idx):
    out = {}
    for k in KINDS:
        r = [res[i] for i in idx[k]]
        d = [x for x in r if x is not None]
        p, lo, hi = metrics.wilson(sum(d), len(d)) if d else (None, None, None)
        out[k] = dict(n=len(r), decided=len(d), passed=int(sum(d)), rate=p, ci95=[lo, hi])
    return out


def main():
    t_start = time.time()
    ctrl, split, prof, step = load()
    idx = {sp: {k: [i for i, c in enumerate(ctrl) if c["kind"] == k and split[c["prof"]] == sp] for k in KINDS}
           for sp in ("tune", "test")}
    idx["all"] = {k: idx["tune"][k] + idx["test"][k] for k in KINDS}

    def run_rule(params, lev):
        return [rule_l0.check(*prof[lev][c["prof"]], c["t0"], c["t1"], c["s"], params, step[lev]) for c in ctrl]

    # windows (level 0) once per control; NaN guard as v0
    win = []
    for c in ctrl:
        t, v = prof[0][c["prof"]]
        tw, vw = rule_l0.window(t, v, c["t0"], c["t1"], c["s"])
        if len(vw) == 0 or np.isnan(vw).mean() > 0.1:
            win.append(None)
        else:
            win.append((tw, np.nan_to_num(vw, nan=np.nanmedian(vw))))
    table = []
    combos = list(itertools.product(GRID["end_zone"], GRID["min_dark"], GRID["q"], GRID["mid_bias"]))
    results = {}
    for sigma in GRID["sigma"]:
        sm = [None if w is None else (w[0], rule_l0.smooth(w[1], sigma, step[0])) for w in win]
        for ez, md, q, mb in combos:
            res = [None if w is None else rule_l0.evaluate(w[0], w[1], c["t0"], c["t1"], c["s"], ez, md, q, mb, step[0])
                   for w, c in zip(sm, ctrl)]
            p = dict(sigma=sigma, end_zone=ez, min_dark=md, q=q, mid_bias=mb)
            key = json.dumps(p, sort_keys=True)
            results[key] = res
            rt = rates(res, idx["tune"])
            a, t2, ss = (rt[k]["rate"] or 0.0 for k in KINDS)
            table.append(dict(params=p, tune=dict(adjacent=a, two_apart=t2, same_sheet=ss),
                              margin=a - max(t2, ss), qualifies=bool(t2 <= FP_MAX and ss <= FP_MAX)))
    qual = [r for r in table if r["qualifies"]]
    if qual:
        best = max(qual, key=lambda r: (r["tune"]["adjacent"], r["margin"]))
        objective_used = "max adjacent pass s.t. tune false-pass rates <= 5%"
    else:
        best = max(table, key=lambda r: r["margin"])
        objective_used = "no variant met the 5% false-pass limits on the tune half: max margin (v0 objective)"
    chosen = best["params"]
    res_c = results[json.dumps(chosen, sort_keys=True)]
    rep = {sp: rates(res_c, idx[sp]) for sp in ("tune", "test", "all")}
    t = rep["test"]
    strong = bool(t["two_apart"]["rate"] is not None and t["two_apart"]["rate"] <= FP_MAX
                  and t["same_sheet"]["rate"] <= FP_MAX and t["adjacent"]["rate"] >= ADJ_MIN)
    strong_in_sample = bool(rep["all"]["two_apart"]["rate"] <= FP_MAX and rep["all"]["same_sheet"]["rate"] <= FP_MAX
                            and rep["all"]["adjacent"]["rate"] >= ADJ_MIN)
    res_v0_l2 = run_rule(V0_RULE, 2)
    res_v0_l0 = run_rule(V0_RULE, 0)
    table.sort(key=lambda r: (-r["qualifies"], -r["tune"]["adjacent"] if r["qualifies"] else 0, -r["margin"]))
    top = []
    for r in table[:10]:
        res = results[json.dumps(r["params"], sort_keys=True)]
        top.append(dict(params=r["params"], tune=r["tune"], test={k: v["rate"] for k, v in rates(res, idx["test"]).items()}))
    # best achievable on the TUNE half for each false-pass ceiling (how far the family is from STRONG)
    frontier = {}
    for ceil in (0.05, 0.075, 0.10, 0.15):
        ok = [r for r in table if r["tune"]["two_apart"] <= ceil and r["tune"]["same_sheet"] <= ceil]
        if ok:
            b = max(ok, key=lambda r: r["tune"]["adjacent"])
            res = results[json.dumps(b["params"], sort_keys=True)]
            frontier[str(ceil)] = dict(params=b["params"], tune=b["tune"],
                                       test={k: v["rate"] for k, v in rates(res, idx["test"]).items()})
    out = dict(source="relative_windings.json ladders (human) only; split by collection, seed 20260925",
               n_controls={sp: {k: len(v) for k, v in idx[sp].items()} for sp in ("tune", "test")},
               grid=GRID, grid_size=len(table), objective=objective_used, chosen=chosen,
               chosen_rates=rep, strong_rule="test-half two-apart <= 5% and same-sheet <= 5% and adjacent >= 70%",
               strong=strong, strong_if_judged_on_all_ladders=strong_in_sample,
               v0_rule_level2={sp: rates(res_v0_l2, idx[sp]) for sp in ("tune", "test", "all")},
               v0_rule_level0={sp: rates(res_v0_l0, idx[sp]) for sp in ("tune", "test", "all")},
               top10_on_tune=top, frontier_on_tune=frontier, step=step,
               written_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), elapsed_s=time.time() - t_start)
    json.dump(out, open(OUT, "w"), indent=1)
    f = lambda r: {k: (round(v["rate"], 3) if v["rate"] is not None else None) for k, v in r.items()}
    print("chosen", chosen, objective_used)
    print("tune", f(rep["tune"]), "\ntest", f(rep["test"]), "\nall", f(rep["all"]), "\nSTRONG", strong)
    print("v0 rule L2 test", f(out["v0_rule_level2"]["test"]), " v0 rule L0 test", f(out["v0_rule_level0"]["test"]))
    return out


if __name__ == "__main__":
    main()
