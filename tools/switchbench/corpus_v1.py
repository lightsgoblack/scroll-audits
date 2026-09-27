"""SwitchBench-natural v1 corpus (protocol P1 (prereg/switchbench_v1.md)): patches 3,001-10,000 of the v0 seeded order (20260925).

Per patch this runs the v0 pipeline as finally run, unchanged: same in-sample rule (>= 5% of valid
vertices assigned to a verified wrap, D1), same labeler and event definition (label.py, D4/D5), same
same-lineage exclusion, same level-2 CT verdicts for events (v0 rule, kept for comparison) and for
negative runs (on-layer rule, at most 20 seeded runs per patch, D8). New in v1: for every candidate
event it also stores the geometry of the CT check (profile origin, normal, far-sheet offset t and local
spacing s, exactly as confirm.confirm_event selects them) so the level-0 (2.4 um) rule can re-check
every candidate later without recomputing stacks (confirm_l0.py).

Mode "new": patches order[3000:10000] -> data/switchbench_v1/corpus/<patch>.json (full record).
Mode "regeom": v0 patches with candidate events -> data/switchbench_v1/regeom/<patch>.json (event
member geometry only; must reproduce the v0 event list exactly, checked in check_regeom()).
Usage: python -m tools.switchbench.corpus_v1 new [workers]
       python -m tools.switchbench.corpus_v1 regeom [workers]
"""
from __future__ import annotations

import json
import shutil
import sys
import time
import traceback
from multiprocessing import Pool

import numpy as np

from . import confirm, geom, label, pull, sanity
from .corpus import MIN_COVER, NEG_CT_CAP, lineage_of

V1 = geom.REPO / "data" / "switchbench_v1"
CORPUS1 = V1 / "corpus"
REGEOM = V1 / "regeom"
V0_CORPUS = geom.DATA / "corpus"
START, END = 3000, 10000          # 0-based slice of the seeded order: patches 3,001 to 10,000
CORPUS_CLOSE_UTC = "2026-09-30T23:59:00Z"
DISK_CAP = 10 * 2**30             # v1 data cap: data/paris4 + data/switchbench_v1
MIN_FREE = 6 * 2**30
_vi = None


def disk_check():
    free = shutil.disk_usage(geom.DATA).free
    used = pull.du(geom.DATA) + (pull.du(V1) if V1.exists() else 0)
    if free < MIN_FREE:
        raise SystemExit(f"STOP: free disk {free/2**30:.1f} GB < 6 GB")
    if used > DISK_CAP:
        raise SystemExit(f"STOP: v1 data {used/2**30:.2f} GB > 10 GB cap")
    return used, free


def member_geometry(P, N, ev, st, asg, max_members=3):
    """Geometry of the CT check for one event, mirroring confirm.confirm_event member selection."""
    X = np.array(ev["xyz"])
    mem = sorted(ev["members"], key=lambda m: np.linalg.norm(np.array(m["xyz"]) - X))[:max_members]
    out = []
    for m in mem:
        ra, rb = tuple(m["rc_a"]), tuple(m["rc_b"])
        ka, kb = asg[ra][0], asg[rb][0]
        ja = label.find_in_stack(st[ra][ka], ra, st[rb], rb)
        if ja is not None:
            t = st[rb][ja]["t"] - st[rb][kb]["t"]
            s = label.spacing(st[rb], kb) or abs(t)
            out.append(dict(side="b", rc=list(rb), p0=P[rb].tolist(), n=N[rb].tolist(), t=float(t), s=float(s)))
            continue
        jb = label.find_in_stack(st[rb][kb], rb, st[ra], ra)
        if jb is None:
            out.append(dict(side=None, reason="no cross-visibility"))
            continue
        t = st[ra][jb]["t"] - st[ra][ka]["t"]
        s = label.spacing(st[ra], ka) or abs(t)
        out.append(dict(side="a", rc=list(ra), p0=P[ra].tolist(), n=N[ra].tolist(), t=float(t), s=float(s)))
    return out


def _label(nm):
    """Load + label one unverified patch exactly as v0 corpus._process. Returns (rec, P, N, r) or rec."""
    global _vi
    if _vi is None:
        _vi = geom.VerifiedIndex()
    vi = _vi
    d = geom.DATA / "unverified_patches" / nm
    rec = dict(patch=nm)
    try:
        meta = json.load(open(d / "meta.json"))
        P = geom.load_tifxyz(d)
    except Exception as e:
        rec.update(status="load_error", error=str(e))
        return rec, None, None, None
    N = geom.orient_outward(P, geom.grid_normals(P))
    lin = lineage_of(nm, meta)
    excl = {n for n in vi.names if sanity.lineage(n) == lin}
    rec.update(lineage=lin, excluded_same_lineage=sorted(excl), shape=list(P.shape[:2]),
               mode=meta.get("vc_gsfs_mode"), seed=meta.get("seed"))
    if np.isnan(P).all():
        rec.update(status="empty")
        return rec, None, None, None
    lo = np.nanmin(P.reshape(-1, 3), 0); hi = np.nanmax(P.reshape(-1, 3), 0)
    cl = vi.local_cloud(lo, hi, exclude=excl)
    if cl is None:
        rec.update(status="no_verified_nearby", n_valid=int(np.isfinite(P).all(-1).sum()))
        return rec, None, None, None
    r = label.label_patch(P, N, cl)
    cover = r["stats"]["n_assigned"] / max(1, r["stats"]["n_valid"])
    rec.update(stats=r["stats"], cover=cover, in_sample=bool(cover >= MIN_COVER))
    return rec, P, N, r


def _process_new(nm):
    out_f = CORPUS1 / f"{nm}.json"
    if out_f.exists():
        return json.load(open(out_f))
    t0 = time.time()
    rec, P, N, r = _label(nm)
    if r is None:
        json.dump(rec, open(out_f, "w"))
        return rec
    st, asg = r["stacks"], r["asg"]
    evs = []
    for e in r["events"]:
        ok, det = confirm.confirm_event(P, N, e, st, asg) if rec["in_sample"] else (None, [])
        evs.append(dict(xyz=e["xyz"], delta_signs=e["delta_signs"], ct=ok, ct_detail=det,
                        status="confirmed" if ok else ("contradicted" if ok is False else "unconfirmed"),
                        l0_geom=member_geometry(P, N, e, st, asg),
                        members=[{k: v for k, v in m.items() if k != "run"} for m in e["members"]]))
    negs = []
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
    rec.update(status="done", events=evs, negatives=negs, multi_wrap=multi, elapsed_s=time.time() - t0,
               finished_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    json.dump(rec, open(out_f, "w"), default=lambda o: o.tolist() if hasattr(o, "tolist") else str(o))
    return rec


def _process_regeom(nm):
    out_f = REGEOM / f"{nm}.json"
    if out_f.exists():
        return json.load(open(out_f))
    rec, P, N, r = _label(nm)
    if r is None:
        json.dump(rec, open(out_f, "w"))
        return rec
    rec.update(status="done", events=[dict(xyz=e["xyz"], delta_signs=e["delta_signs"],
                                           l0_geom=member_geometry(P, N, e, r["stacks"], r["asg"]))
                                      for e in r["events"]])
    json.dump(rec, open(out_f, "w"), default=lambda o: o.tolist() if hasattr(o, "tolist") else str(o))
    return rec


def process(args):
    mode, nm = args
    try:
        return (_process_new if mode == "new" else _process_regeom)(nm)
    except Exception as e:  # never let one patch kill the pool; the error is recorded
        rec = dict(patch=nm, status="error", error=repr(e), tb=traceback.format_exc()[-800:])
        json.dump(rec, open((CORPUS1 if mode == "new" else REGEOM) / f"{nm}.json", "w"))
        return rec


def summary(d=CORPUS1):
    recs = [json.load(open(f)) for f in sorted(d.glob("*.json"))]
    ins = [r for r in recs if r.get("in_sample")]
    ev = [e for r in ins for e in r["events"]]
    ng = [n for r in ins for n in r["negatives"]]
    return dict(processed=len(recs), in_sample=len(ins), candidates=len(ev),
                events_confirmed_l2=sum(e["status"] == "confirmed" for e in ev),
                events_contradicted_l2=sum(e["status"] == "contradicted" for e in ev),
                negatives_confirmed=sum(n["status"] == "confirmed" for n in ng),
                neg_mm_confirmed=sum(n["len_mm"] for n in ng if n["status"] == "confirmed"),
                errors=sum(r.get("status") == "error" for r in recs))


def run_new(workers=3, batch=150):
    CORPUS1.mkdir(parents=True, exist_ok=True)
    order = json.load(open(geom.DATA / "unverified_order.json"))[START:END]
    t_wall = time.time()
    n = [0]

    def gen():
        for i in range(0, len(order), batch):
            if time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()) > CORPUS_CLOSE_UTC:
                print("corpus closed (2026-09-30 23:59Z); stopping", flush=True)
                return
            disk_check()
            todo = [nm for nm in order[i:i + batch] if not (CORPUS1 / f"{nm}.json").exists()]
            pull.pull_unverified(todo)
            for nm in order[i:i + batch]:
                yield ("new", nm)

    with Pool(workers) as pool:
        for rec in pool.imap_unordered(process, gen()):
            n[0] += 1
            if n[0] % 100 == 0:
                s = summary()
                s.update(wall_s=time.time() - t_wall, disk_used_gb=disk_check()[0] / 2**30)
                json.dump(s, open(V1 / "corpus_progress.json", "w"))
                print(json.dumps(s), flush=True)
    s = summary()
    s.update(wall_s=time.time() - t_wall, finished=True, finished_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    json.dump(s, open(V1 / "corpus_progress.json", "w"))
    print(json.dumps(s), flush=True)


def v0_candidate_patches():
    out = []
    for f in sorted(V0_CORPUS.glob("*.json")):
        r = json.load(open(f))
        if r.get("in_sample") and r.get("events"):
            out.append(r["patch"])
    return out


def run_regeom(workers=3):
    REGEOM.mkdir(parents=True, exist_ok=True)
    names = v0_candidate_patches()
    with Pool(workers) as pool:
        for i, _ in enumerate(pool.imap_unordered(process, [("regeom", nm) for nm in names])):
            if (i + 1) % 20 == 0:
                print("regeom", i + 1, "/", len(names), flush=True)
    print(json.dumps(check_regeom()), flush=True)


def check_regeom():
    """The re-run labeler must reproduce every v0 candidate event (same count, same location)."""
    bad = []
    n = 0
    for nm in v0_candidate_patches():
        a = json.load(open(V0_CORPUS / f"{nm}.json"))["events"]
        f = REGEOM / f"{nm}.json"
        b = json.load(open(f)).get("events", []) if f.exists() else []
        n += len(a)
        if len(a) != len(b) or any(np.linalg.norm(np.array(x["xyz"]) - np.array(y["xyz"])) > 1e-6
                                   for x, y in zip(a, b)):
            bad.append(nm)
    return dict(v0_candidate_patches=len(v0_candidate_patches()), v0_candidates=n, mismatched_patches=bad)


if __name__ == "__main__":
    mode = sys.argv[1]
    w = int(sys.argv[2]) if len(sys.argv) > 2 else 3
    run_new(w) if mode == "new" else run_regeom(w)
