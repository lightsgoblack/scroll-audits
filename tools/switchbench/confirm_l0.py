"""SwitchBench v1: re-confirm every candidate event with the level-0 (2.4 um) numeric CT rule.

Rule constants = data/switchbench_v1/ct_rule_l0.json "chosen" (tune_l0.py; human ladder controls only).
Per candidate, the members and profile geometry are exactly v0's (corpus_v1.member_geometry, mirroring
confirm.confirm_event): profile along the stored normal from min(0, t) - 3 s to max(0, t) + 3 s,
sampled at level 0 with step 0.25 level-2 vx; per-member verdict by rule_l0.check; event verdict =
majority of decided members (v0 rule); no decided member = "unconfirmed".
Inputs: data/switchbench_v1/regeom/*.json (v0 candidates) and data/switchbench_v1/corpus/*.json (new).
Output: data/switchbench_v1/l0/<patch>.json (verdicts) and .npz (numeric profiles; no images).
Usage: python -m tools.switchbench.confirm_l0 [threads]
"""
from __future__ import annotations

import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor

import numpy as np

from . import rule_l0
from .ct0 import Sampler
from .corpus_v1 import CORPUS1, REGEOM, V1

OUT = V1 / "l0"
RULE = V1 / "ct_rule_l0.json"
STEP = 0.25


def load_rule():
    return json.load(open(RULE))["chosen"]


def member_verdict(sampler, g, params):
    if g.get("side") is None:
        return None, None, dict(reason=g.get("reason", "no geometry"))
    t_end, s = g["t"], g["s"]
    lo_t, hi_t = min(0.0, t_end), max(0.0, t_end)
    t, v = sampler.profile(g["p0"], g["n"], lo_t - 3 * s, hi_t + 3 * s, STEP)
    ok = rule_l0.check(t, v, 0.0, t_end, s, params, STEP)
    return ok, v.astype(np.float32), dict(t0=lo_t - 3 * s, n=len(v))


def event_verdict(votes):
    d = [v for v in votes if v is not None]
    if not d:
        return None
    return bool(sum(d) * 2 > len(d))


def do_patch(sampler, rec, params, source):
    nm = rec["patch"]
    f = OUT / f"{nm}.json"
    if f.exists():
        return json.load(open(f))
    evs, profs = [], {}
    for i, e in enumerate(rec.get("events", [])):
        votes, det = [], []
        for j, g in enumerate(e.get("l0_geom", [])):
            ok, v, d = member_verdict(sampler, g, params)
            votes.append(ok)
            det.append(d)
            if v is not None:
                profs[f"e{i}_m{j}"] = v
        ok = event_verdict(votes)
        evs.append(dict(i=i, xyz=e["xyz"], votes=votes, detail=det, l0=ok,
                        status_l0="confirmed" if ok else ("contradicted" if ok is False else "unconfirmed")))
    out = dict(patch=nm, source=source, rule=params, step=STEP, events=evs)
    np.savez_compressed(OUT / f"{nm}.npz", **profs) if profs else None
    json.dump(out, open(f, "w"))
    return out


def todo():
    items = []
    for d, src in ((REGEOM, "v0"), (CORPUS1, "new")):
        for f in sorted(d.glob("*.json")):
            r = json.load(open(f))
            if r.get("status") != "done" or not r.get("events"):
                continue
            if src == "new" and not r.get("in_sample"):
                continue
            if src == "v0" and not r.get("in_sample"):
                continue
            if not (OUT / f"{r['patch']}.json").exists():
                items.append((r, src))
    return items


def main(threads=4):
    OUT.mkdir(parents=True, exist_ok=True)
    params = load_rule()
    sampler = Sampler(0, max_chunks=360)
    items = todo()
    print(f"{len(items)} patches with candidates to confirm at level 0", flush=True)
    t0 = time.time()
    done = [0]

    def work(it):
        r, src = it
        do_patch(sampler, r, params, src)
        done[0] += 1
        if done[0] % 20 == 0:
            print(f"  {done[0]}/{len(items)} patches, {sampler.stats['fetched']} chunks "
                  f"{sampler.stats['bytes']/1e9:.1f} GB, {time.time()-t0:.0f}s", flush=True)

    with ThreadPoolExecutor(threads) as ex:
        list(ex.map(work, items))
    print(json.dumps(dict(patches=len(items), elapsed_s=time.time() - t0, stats=sampler.stats)), flush=True)


if __name__ == "__main__":
    main(*(int(a) for a in sys.argv[1:]))
