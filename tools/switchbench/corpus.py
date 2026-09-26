"""Build the natural sheet-switch corpus: seeded (20260925) walk over PHercParis4 unverified patches.

For each patch (in seeded order): pull x/y/z/mask/meta, exclude same-lineage verified patches from
the reference, run the labeler (reference G = verified geometry), confirm events and negatives with
numeric CT profiles (reference C), save per-patch JSON under data/paris4/corpus/ (gitignored).
Stops when >= 30 confirmed events are reached (then finishes the batch in flight) or at the cap.
Usage: python -m tools.switchbench.corpus [max_patches] [workers]
"""
from __future__ import annotations

import json
import re
import sys
import time
from multiprocessing import Pool
from pathlib import Path

import numpy as np

from . import confirm, geom, label, pull, sanity

CORPUS = geom.DATA / "corpus"
NEG_CT_CAP = 20      # max negative runs CT-checked per patch (one 434x554 legacy patch has hundreds)
MIN_COVER = 0.05     # patch "overlaps verified coverage" if >= 5% of valid vertices are assigned
TARGET = 30
T_START = "2026-09-26T03:47:00Z"   # first line of bet code (pull.py)
CAP_S = 3 * 24 * 3600
_vi = None


def lineage_of(nm, meta):
    src = meta.get("source_tifxyz")
    if src:
        return Path(src).name
    return re.sub(r"_region_\d+$", "", nm)


def process(nm):
    try:
        return _process(nm)
    except Exception as e:  # never let one patch kill the pool; the error is recorded
        import traceback
        rec = dict(patch=nm, status="error", error=repr(e), tb=traceback.format_exc()[-800:])
        json.dump(rec, open(CORPUS / f"{nm}.json", "w"))
        return rec


def _process(nm):
    global _vi
    out_f = CORPUS / f"{nm}.json"
    if out_f.exists():
        return json.load(open(out_f))
    if _vi is None:
        _vi = geom.VerifiedIndex()
    vi = _vi
    t0 = time.time()
    d = geom.DATA / "unverified_patches" / nm
    rec = dict(patch=nm)
    try:
        meta = json.load(open(d / "meta.json"))
        P = geom.load_tifxyz(d)
    except Exception as e:  # missing files
        rec.update(status="load_error", error=str(e))
        json.dump(rec, open(out_f, "w"))
        return rec
    N = geom.orient_outward(P, geom.grid_normals(P))
    lin = lineage_of(nm, meta)
    excl = {n for n in vi.names if sanity.lineage(n) == lin}
    rec.update(lineage=lin, excluded_same_lineage=sorted(excl), shape=list(P.shape[:2]),
               mode=meta.get("vc_gsfs_mode"), seed=meta.get("seed"))
    if np.isnan(P).all():
        rec.update(status="empty")
        json.dump(rec, open(out_f, "w"))
        return rec
    lo = np.nanmin(P.reshape(-1, 3), 0); hi = np.nanmax(P.reshape(-1, 3), 0)
    cl = vi.local_cloud(lo, hi, exclude=excl)
    if cl is None:
        rec.update(status="no_verified_nearby", n_valid=int(np.isfinite(P).all(-1).sum()))
        json.dump(rec, open(out_f, "w"))
        return rec
    r = label.label_patch(P, N, cl)
    st, asg = r["stacks"], r["asg"]
    cover = r["stats"]["n_assigned"] / max(1, r["stats"]["n_valid"])
    rec.update(stats=r["stats"], cover=cover, in_sample=bool(cover >= MIN_COVER))
    evs = []
    for e in r["events"]:
        ok, det = confirm.confirm_event(P, N, e, st, asg) if rec["in_sample"] else (None, [])
        evs.append(dict(xyz=e["xyz"], delta_signs=e["delta_signs"], ct=ok, ct_detail=det,
                        status="confirmed" if ok else ("contradicted" if ok is False else "unconfirmed"),
                        members=[{k: v for k, v in m.items() if k != "run"} for m in e["members"]]))
    negs = []
    # CT-check at most NEG_CT_CAP negative runs per patch (seeded choice); the rest are logged unchecked
    check = set(np.random.default_rng(20260925).permutation(len(r["negatives"]))[:NEG_CT_CAP].tolist())
    for i_n, n in enumerate(r["negatives"]):
        if rec["in_sample"] and i_n in check:
            ok, det = confirm.confirm_negative(P, N, n, asg, st)
        else:
            ok, det = None, {"reason": "not CT-checked (per-patch cap)" if rec["in_sample"] else "not in sample"}
        negs.append(dict(axis=n["axis"], verts=[list(map(int, v)) for v in n["verts"]], len_mm=n["len_mm"],
                         xyz0=P[tuple(n["verts"][0])].tolist(), xyz1=P[tuple(n["verts"][-1])].tolist(),
                         ct=ok, ct_detail=det,
                         status="confirmed" if ok else ("contradicted" if ok is False else "unconfirmed")))
    multi = [dict(xyz=m["xyz"], delta_signs=m["delta_signs"], n_members=len(m["members"])) for m in r["multi"]]
    rec.update(status="done", events=evs, negatives=negs, multi_wrap=multi, elapsed_s=time.time() - t0)
    json.dump(rec, open(out_f, "w"), default=lambda o: o.tolist() if hasattr(o, "tolist") else str(o))
    return rec


def summary():
    recs = [json.load(open(f)) for f in sorted(CORPUS.glob("*.json"))]
    ins = [r for r in recs if r.get("in_sample")]
    ev = [e for r in ins for e in r["events"]]
    ng = [n for r in ins for n in r["negatives"]]
    return dict(processed=len(recs), in_sample=len(ins),
                events_confirmed=sum(e["status"] == "confirmed" for e in ev),
                events_contradicted=sum(e["status"] == "contradicted" for e in ev),
                events_unconfirmed=sum(e["status"] == "unconfirmed" for e in ev),
                negatives_confirmed=sum(n["status"] == "confirmed" for n in ng),
                negatives_other=sum(n["status"] != "confirmed" for n in ng),
                neg_mm_confirmed=sum(n["len_mm"] for n in ng if n["status"] == "confirmed"),
                multi_wrap=sum(len(r.get("multi_wrap", [])) for r in ins))


def main(max_patches=3000, workers=3, batch=150):
    """Continuous pool over the seeded order (no batch barrier, so one very large patch does not stall
    the others). Processes a fixed prefix of the seeded order (max_patches, declared before the run and
    independent of results); extend the prefix only if the prefix yields < TARGET confirmed events."""
    CORPUS.mkdir(parents=True, exist_ok=True)
    order = json.load(open(geom.DATA / "unverified_order.json"))[:max_patches]
    t_wall = time.time()
    done = {"n": 0, "confirmed": 0}

    def gen():
        for i in range(0, len(order), batch):
            pull.pull_unverified(order[i:i + batch])
            for nm in order[i:i + batch]:
                yield nm

    with Pool(workers) as pool:
        for rec in pool.imap_unordered(process, gen()):
            done["n"] += 1
            done["confirmed"] += sum(1 for e in rec.get("events", []) if e.get("status") == "confirmed")
            if done["n"] % 50 == 0:
                s = summary()
                s.update(wall_s=time.time() - t_wall)
                json.dump(s, open(geom.DATA / "corpus_progress.json", "w"))
                print(json.dumps(s), flush=True)
    s = summary()
    s.update(wall_s=time.time() - t_wall, finished=True)
    json.dump(s, open(geom.DATA / "corpus_progress.json", "w"))
    print(json.dumps(s), flush=True)
    return s


if __name__ == "__main__":
    main(*(int(a) for a in sys.argv[1:]))
