"""SwitchBench v1 C4: report-only replication on PHerc0500P2 (protocol P1 (prereg/switchbench_v1.md) C4; lead call 2026-09-26,
Scout Report #8). No ink maps, numeric CT only, no images (0500P2 is an unread sample: nothing here can
produce a text-like result; no ink-detection file is read).

Inputs (S3 open data, single-file pulls, geometry only):
  traces      25 GrowPatch consensus traces PHerc0500P2/segments/*-z_dbg_gen_*/mesh/*-on-20250528085330-4.317um.tifxyz
  references  7 numbered layers -2..4 (segments 20250825181917--2 ... 20250825181939-4), same frame
  CT          PHerc0500P2/volumes/20250528085330-4.317um-1.2m-111keV-masked.zarr level 0 (4.317 um), numeric profiles
Same pipeline as Paris4 (label.py, v0 event definition), with the layers as the reference surfaces
(wrap = layer) and the voxel constants rescaled to 4.317 um by physical size, except MIN_SPACING (the
duplicate-trace merge on Paris4), which is capped at half the 10th percentile of adjacent-layer spacing
measured on the layers alone (7 distinct layers have no duplicates to merge). Grid normals are used as
computed (no umbilicus on a fragment). CT: the Paris4-tuned 2.4 um rule transferred in physical units
(no tuning on 0500P2); its rates on layer-derived controls are reported, not used to tune.
Not applicable here (reported as such): windaudit and the #1621 check (no winding annotations), C3
(no gen_avg_cost), sheet-topo-bench (not run, as on Paris4).
Independence check first: a trace-layer pairing is excluded if the trace's on-layer vertices copy the
layer (median point-to-plane offset < 1 vx, or >= 50% within 0.5 vx).
Usage: python -m tools.switchbench.c4_0500p2 pull | indep | controls | label [workers] | confirm | detect | evaluate
"""
from __future__ import annotations

import os

import json
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from multiprocessing import Pool
from pathlib import Path

import numpy as np
from scipy.spatial import cKDTree

from . import geom, label, rule_l0

S3 = "https://vesuvius-challenge-open-data.s3.us-east-1.amazonaws.com"
ROOT = geom.REPO / "data" / "switchbench_v1" / "c4_0500p2"
SEG = ROOT / "segments"
FRAME = "20250528085330-4.317um"
VOL = f"{S3}/PHerc0500P2/volumes/20250528085330-4.317um-1.2m-111keV-masked.zarr"
VOXEL_MM = 0.004317
MM = 1.0 / VOXEL_MM
K = 0.0096 / VOXEL_MM   # Paris4 level-2 voxel -> 0500P2 voxel (physical rescale factor, 2.224)
LAYERS = {-2: "20250825181917--2", -1: "20250825181859--1", 0: "20250825181907-0", 1: "20250825181922-1",
          2: "20250825181928-2", 3: "20250825181934-3", 4: "20250825181939-4"}
SEED = 20260925


def list_traces():
    x = urllib.request.urlopen(f"{S3}/?list-type=2&prefix=PHerc0500P2/segments/&delimiter=/&max-keys=1000",
                               timeout=60).read().decode()
    import re
    segs = [p.split("/")[-2] for p in re.findall(r"<Prefix>([^<]+)</Prefix>", x) if "z_dbg_gen_" in p]
    return sorted(segs)


def tifxyz_url(seg):
    ts = seg.split("-")[0]
    return f"{S3}/PHerc0500P2/segments/{seg}/mesh/{ts}-on-{FRAME}.tifxyz"


def pull():
    SEG.mkdir(parents=True, exist_ok=True)
    segs = list_traces() + list(LAYERS.values())
    jobs = [(seg, f) for seg in segs for f in ("x.tif", "y.tif", "z.tif", "meta.json")]

    def get(job):
        seg, f = job
        dst = SEG / seg / f
        if dst.exists():
            return 0
        dst.parent.mkdir(parents=True, exist_ok=True)
        for i in range(5):
            try:
                b = urllib.request.urlopen(f"{tifxyz_url(seg)}/{f}", timeout=120).read()
                dst.with_suffix(".part").write_bytes(b)
                dst.with_suffix(".part").rename(dst)
                return len(b)
            except Exception:
                time.sleep(2 ** (i + 1))
        raise RuntimeError(f"pull failed {seg}/{f}")

    with ThreadPoolExecutor(8) as ex:
        n = sum(ex.map(get, jobs))
    json.dump(dict(traces=list_traces(), layers=LAYERS), open(ROOT / "inventory.json", "w"), indent=1)
    print("pulled", n / 1e6, "MB;", len(list_traces()), "traces")


def load(seg):
    P = geom.load_tifxyz(SEG / seg, use_mask=False)
    return P, geom.grid_normals(P)


class LayerIndex:
    """The 7 reference layers as label.py 'verified patches' (pid = layer order index)."""

    def __init__(self, exclude=()):
        self.ids = [k for k in sorted(LAYERS) if k not in set(exclude)]
        self.P, self.N = {}, {}
        for k in self.ids:
            self.P[k], self.N[k] = load(LAYERS[k])

    def local_cloud(self, lo, hi, pad):
        lo = np.asarray(lo) - pad
        hi = np.asarray(hi) + pad
        pts, nrm, pid, rc, names = [], [], [], [], []
        for k in self.ids:
            P, n = self.P[k], self.N[k]
            ok = np.isfinite(P).all(-1) & np.isfinite(n).all(-1) & (P >= lo).all(-1) & (P <= hi).all(-1)
            if not ok.any():
                continue
            r, c = np.nonzero(ok)
            names.append(k)
            pts.append(P[r, c]); nrm.append(n[r, c])
            pid.append(np.full(len(r), len(names) - 1)); rc.append(np.stack([r, c], 1))
        if not pts:
            return None
        pts = np.concatenate(pts)
        return dict(pts=pts, nrm=np.concatenate(nrm), pid=np.concatenate(pid), rc=np.concatenate(rc),
                    names=names, tree=cKDTree(pts))


def layer_spacing_p10():
    """10th percentile of adjacent-layer spacing (point-to-plane, layer k vertices -> layer k+1), layers only."""
    li = LayerIndex()
    rng = np.random.default_rng(SEED)
    gaps = []
    for k in li.ids[:-1]:
        P, n = li.P[k], li.N[k]
        Q, m = li.P[k + 1], li.N[k + 1]
        okq = np.isfinite(Q).all(-1) & np.isfinite(m).all(-1)
        tq = cKDTree(Q[okq])
        mq = m[okq]
        ok = np.argwhere(np.isfinite(P).all(-1) & np.isfinite(n).all(-1))
        for r, c in ok[rng.choice(len(ok), min(3000, len(ok)), replace=False)]:
            d, j = tq.query(P[r, c])
            if d < 80:
                gaps.append(abs(float((Q[okq][j] - P[r, c]) @ mq[j])))
    g = np.array(gaps)
    return dict(p10=float(np.percentile(g, 10)), p50=float(np.percentile(g, 50)), p90=float(np.percentile(g, 90)), n=len(g))


def set_constants(min_spacing):
    """label.py constants rescaled to 4.317 um by physical size (Paris4 values x K), MIN_SPACING capped."""
    label.MM = MM
    label.RQ = 100.0 * K
    label.LAT = 14.0 * K
    label.PATCH_GAP = 6.0 * K
    label.MAX_SPACING = 40.0 * K
    label.MIN_SPACING = min(8.0 * K, min_spacing)
    label.CHUNK = 4000
    return dict(MM=label.MM, RQ=label.RQ, LAT=label.LAT, PATCH_GAP=label.PATCH_GAP, MAX_SPACING=label.MAX_SPACING,
                MIN_SPACING=label.MIN_SPACING, SAME_PATCH_CELLS=label.SAME_PATCH_CELLS, TOL=label.TOL)


def indep():
    """Independence check: does a trace copy a layer's geometry? Per pairing: on-layer vertex offsets."""
    li = LayerIndex()
    trees = {}
    for k in li.ids:
        ok = np.isfinite(li.P[k]).all(-1) & np.isfinite(li.N[k]).all(-1)
        trees[k] = (cKDTree(li.P[k][ok]), li.N[k][ok], li.P[k][ok])
    out = {}
    rng = np.random.default_rng(SEED)
    for seg in json.load(open(ROOT / "inventory.json"))["traces"]:
        P, _ = load(seg)
        V = P[np.isfinite(P).all(-1)]
        V = V[rng.choice(len(V), min(20000, len(V)), replace=False)]
        rec = {}
        for k, (t, nn, Q) in trees.items():
            d, j = t.query(V, distance_upper_bound=60.0)
            m = np.isfinite(d)
            if m.sum() == 0:
                continue
            off = np.abs(((V[m] - Q[j[m]]) * nn[j[m]]).sum(1))
            on = off <= 0.25 * 30.0   # on-layer candidates (0.25 x typical spacing ~30 vx)
            if on.sum() < 50:
                rec[k] = dict(n_on=int(on.sum()))
                continue
            o = off[on]
            dep = bool(np.median(o) < 1.0 or (o <= 0.5).mean() >= 0.5)
            rec[k] = dict(n_on=int(on.sum()), frac_on=float(on.mean()), median_offset=float(np.median(o)),
                          frac_within_0p5=float((o <= 0.5).mean()), exact_vertex_copies=int((d[m][on] < 1e-3).sum()),
                          dependent=dep)
        out[seg] = rec
    json.dump(out, open(ROOT / "independence.json", "w"), indent=1)
    dep = {s: [k for k, v in r.items() if v.get("dependent")] for s, r in out.items()}
    print(json.dumps({s: v for s, v in dep.items() if v}), "dependent pairings:", sum(len(v) for v in dep.values()))
    return out


# ----------------------------------------------------------------------------- CT (4.317 um volume)
RULE_PHYS = None  # Paris4 2.4 um rule converted to 0500P2 voxels (set by rule())


def sampler():
    from .ct0 import Sampler
    za = json.loads(urllib.request.urlopen(f"{VOL}/0/.zarray", timeout=60).read())
    assert za["chunks"] == [128, 128, 128] and za["compressor"] is None and za["dtype"] == "|u1" \
        and za.get("dimension_separator", "/") == "/", za
    s = Sampler(0, max_chunks=320)
    s.base = f"{VOL}/0"
    s.shape = np.array(za["shape"])            # level 0 (z, y, x), 4.317 um
    s.scale = 1.0                              # trace coordinates are level-0 voxels of this volume
    return s


def rule():
    """The Paris4-tuned rule (level-2 vx units) converted to 0500P2 voxels by physical size; no tuning here."""
    r = json.load(open(geom.REPO / "data" / "switchbench_v1" / "ct_rule_l0.json"))["chosen"]
    return dict(sigma=r["sigma"] * K, end_zone=r["end_zone"], min_dark=r["min_dark"] * K, q=r["q"],
                mid_bias=r["mid_bias"]), 0.25 * K   # step = 2.4 um


def event_check(smp, p0, n, t_end, s):
    params, step = rule()
    lo_t, hi_t = min(0.0, t_end), max(0.0, t_end)
    t, v = smp.profile(p0, n, lo_t - 3 * s, hi_t + 3 * s, step)
    return rule_l0.check(t, v, 0.0, t_end, s, params, step)


def on_layer(smp, p0, n, s):
    """v0's on-layer rule (confirm.on_layer) at 9.6 um-equivalent smoothing, in 0500P2 voxels."""
    from scipy.ndimage import gaussian_filter1d
    step = 0.5 * K
    t, v = smp.profile(p0, n, -3 * s, 3 * s, step)
    if np.isnan(v).mean() > 0.1:
        return None
    v = np.nan_to_num(v, nan=np.nanmedian(v))
    vs = gaussian_filter1d(v, 2.0 * K / step)
    lo, hi = np.percentile(vs, 30), np.percentile(vs, 70)
    if hi - lo < 15:
        return None
    return bool(vs[np.abs(t) <= 0.1 * s + step / 2 + 1e-9].max() > (lo + hi) / 2)


def controls(n_per=150):
    """Layer-derived controls for the transferred rule (report only): adjacent (k -> k+1), two-apart
    (k -> k+2), same-layer (+/- 0.2 s around a layer-k vertex). Seeded sample of layer-k vertices."""
    li = LayerIndex()
    smp = sampler()
    rng = np.random.default_rng(SEED)
    trees = {}
    for k in li.ids:
        ok = np.isfinite(li.P[k]).all(-1) & np.isfinite(li.N[k]).all(-1)
        trees[k] = (cKDTree(li.P[k][ok]), li.P[k][ok], li.N[k][ok])

    def cross(p, n, k):
        """t along n where the line meets layer k's tangent plane (nearest vertex along the line)."""
        t, Q, M = trees[k]
        idx = t.query_ball_point(p, 160.0)
        best = None
        for j in idx:
            c = M[j] @ n
            if abs(c) < 0.5:
                continue
            tt = ((Q[j] - p) @ M[j]) / c
            lat = np.linalg.norm(p + tt * n - Q[j])
            if lat <= label.LAT and (best is None or lat < best[1]):
                best = (tt, lat)
        return None if best is None else best[0]

    res = {"adjacent": [], "two_apart": [], "same_layer": []}
    for k in li.ids[:-2]:
        P, N = li.P[k], li.N[k]
        ok = np.argwhere(np.isfinite(P).all(-1) & np.isfinite(N).all(-1))
        for r, c in ok[rng.choice(len(ok), min(4 * n_per, len(ok)), replace=False)]:
            if len(res["adjacent"]) >= n_per * (li.ids.index(k) + 1) / (len(li.ids) - 2):
                break
            p, n = P[r, c], N[r, c]
            t1, t2 = cross(p, n, k + 1), cross(p, n, k + 2)
            if t1 is None or t2 is None or np.sign(t1) != np.sign(t2) or abs(t2) <= abs(t1):
                continue
            s1, s2 = abs(t1), abs(t2) - abs(t1)
            res["adjacent"].append(event_check(smp, p, n, t1, s1))
            res["two_apart"].append(event_check(smp, p, n, t2, min(s1, s2)))
            params, step = rule()
            tt, v = smp.profile(p, n, -0.2 * s1 - 3 * s1, 0.2 * s1 + 3 * s1, step)
            res["same_layer"].append(rule_l0.check(tt, v, -0.2 * s1, 0.2 * s1, s1, params, step))
    from . import metrics
    out = {}
    for kk, v in res.items():
        d = [x for x in v if x is not None]
        p_, lo, hi = metrics.wilson(sum(d), len(d)) if d else (None, None, None)
        out[kk] = dict(n=len(v), decided=len(d), rate=p_, ci95=[lo, hi])
    out["rule_0500p2_voxels"], out["step"] = rule()
    json.dump(out, open(ROOT / "ct_controls.json", "w"), indent=1)
    print(json.dumps(out))
    return out


# ----------------------------------------------------------------------------- labeling
_LI = {}


def _li(exclude):
    key = tuple(sorted(exclude))
    if key not in _LI:
        _LI.clear()
        _LI[key] = LayerIndex(exclude)
    return _LI[key]


def label_one(args):
    seg, exclude, consts, kind = args
    out_f = ROOT / ("label" if kind == "trace" else "label_layers") / f"{seg}.json"
    if out_f.exists():
        return json.load(open(out_f))
    out_f.parent.mkdir(parents=True, exist_ok=True)
    set_constants(consts["min_spacing_cap"])
    label.PRE_MIN_VERTS = int(round(2 * K))
    label.SAME_PATCH_CELLS = 30.0 * K
    from .corpus_v1 import member_geometry
    t0 = time.time()
    P, N = load(seg)
    li = _li(exclude)
    lo = np.nanmin(P.reshape(-1, 3), 0); hi = np.nanmax(P.reshape(-1, 3), 0)
    cl = li.local_cloud(lo, hi, pad=160.0 * K)
    rec = dict(seg=seg, kind=kind, excluded_layers=sorted(exclude), shape=list(P.shape[:2]))
    if cl is None:
        rec.update(status="no_reference_nearby")
        json.dump(rec, open(out_f, "w"))
        return rec
    names = cl["names"]
    r = label.label_patch(P, N, cl)
    cover = r["stats"]["n_assigned"] / max(1, r["stats"]["n_valid"])
    st, asg = r["stacks"], r["asg"]

    def layer_of(rc):
        k = asg[tuple(rc)][0]
        return None if k is None else sorted(names[p] for p in st[tuple(rc)][k]["members"])

    evs = []
    for e in r["events"]:
        evs.append(dict(xyz=e["xyz"], delta_signs=e["delta_signs"], l0_geom=member_geometry(P, N, e, st, asg),
                        layers=[[layer_of(m["rc_a"]), layer_of(m["rc_b"])] for m in e["members"]],
                        members=[{k: v for k, v in m.items() if k != "run"} for m in e["members"]]))
    negs = [dict(axis=n["axis"], verts=[list(map(int, v)) for v in n["verts"]], len_mm=n["len_mm"],
                 layer=layer_of(n["verts"][len(n["verts"]) // 2])) for n in r["negatives"]]
    rec.update(status="done", stats=r["stats"], cover=cover, in_sample=bool(cover >= 0.05), events=evs, negatives=negs,
               multi_wrap=[dict(xyz=m["xyz"], delta_signs=m["delta_signs"]) for m in r["multi"]],
               constants=set_constants(consts["min_spacing_cap"]) | dict(PRE_MIN_VERTS=label.PRE_MIN_VERTS,
                                                                           SAME_PATCH_CELLS=label.SAME_PATCH_CELLS),
               elapsed_s=time.time() - t0)
    json.dump(rec, open(out_f, "w"), default=lambda o: o.tolist() if hasattr(o, "tolist") else str(o))
    return rec


def label_all(workers=3):
    sp = layer_spacing_p10()
    consts = dict(min_spacing_cap=0.5 * sp["p10"], layer_spacing=sp)
    json.dump(consts, open(ROOT / "constants.json", "w"), indent=1)
    ind = json.load(open(ROOT / "independence.json"))
    jobs = [(seg, [int(k) for k, v in ind.get(seg, {}).items() if v.get("dependent")], consts, "trace")
            for seg in json.load(open(ROOT / "inventory.json"))["traces"]]
    # sanity: every layer labeled against the other six (layers are label-grade: events = labeler noise)
    jobs += [(LAYERS[k], [k], consts, "layer") for k in sorted(LAYERS)]
    with Pool(workers) as pool:
        for rec in pool.imap_unordered(label_one, jobs):
            print(rec["seg"], rec.get("status"), rec.get("in_sample"), len(rec.get("events", [])),
                  len(rec.get("negatives", [])), round(rec.get("elapsed_s", 0)), flush=True)


# ----------------------------------------------------------------------------- confirmation
NEG_CT_CAP = 20


def confirm_all():
    """Events: transferred 2.4 um rule, majority over <= 3 members (v0). Negatives: transferred on-layer
    rule on <= 20 seeded runs per trace (v0 D8), >= 70% on-layer, streak <= 4 x K vertices."""
    smp = sampler()
    streak_max = int(round(4 * K))
    # v0 used the local spacing of each vertex; the records keep no per-vertex spacing, so the median
    # adjacent-layer spacing (measured on the layers alone, constants.json) stands in for it
    s_neg = json.load(open(ROOT / "constants.json"))["layer_spacing"]["p50"]
    out = {}
    for f in sorted((ROOT / "label").glob("*.json")) + sorted((ROOT / "label_layers").glob("*.json")):
        r = json.load(open(f))
        if r.get("status") != "done" or not r.get("in_sample"):
            continue
        P, N = load(r["seg"])
        evs = []
        for e in r["events"]:
            votes = [None if g.get("side") is None else event_check(smp, g["p0"], g["n"], g["t"], g["s"]) for g in e["l0_geom"]]
            d = [v for v in votes if v is not None]
            ok = None if not d else bool(sum(d) * 2 > len(d))
            evs.append(dict(votes=votes, status="confirmed" if ok else ("contradicted" if ok is False else "unconfirmed")))
        negs = []
        check = set(np.random.default_rng(SEED).permutation(len(r["negatives"]))[:NEG_CT_CAP].tolist())
        for i, n in enumerate(r["negatives"]):
            if i not in check:
                negs.append(dict(status="unconfirmed"))
                continue
            flags = [on_layer(smp, P[tuple(v)], N[tuple(v)], s_neg) for v in n["verts"]]
            fl = [x for x in flags if x is not None]
            if len(fl) < 0.8 * len(flags) or not fl:
                negs.append(dict(status="unconfirmed"))
                continue
            m = cur = 0
            for x in flags:
                cur = cur + 1 if x is False else 0
                m = max(m, cur)
            okn = sum(fl) / len(fl) >= 0.70 and m <= streak_max
            negs.append(dict(status="confirmed" if okn else "contradicted", frac_on=sum(fl) / len(fl), max_off_streak=m))
        out[r["seg"]] = dict(kind=r["kind"], events=evs, negatives=negs)
        print(r["seg"], [e["status"] for e in evs], sum(n["status"] == "confirmed" for n in negs), flush=True)
    json.dump(out, open(ROOT / "confirm.json", "w"), indent=1)
    return out


# ----------------------------------------------------------------------------- detectors
def detect():
    import subprocess
    import tempfile
    from . import doctor_v1
    det = ROOT / "detect"
    doctor_v1.OUT = det / "tifxyz_doctor"
    here = Path(__file__).resolve().parent
    wc = os.environ.get("SWITCHBENCH_EXT", "ext") + "/windcheck"
    for seg in json.load(open(ROOT / "inventory.json"))["traces"]:
        d = SEG / seg
        doctor_v1.run(seg, patch_dir=d)
        f = det / "windcheck" / f"{seg}.json"
        if not f.exists():
            f.parent.mkdir(parents=True, exist_ok=True)
            out = det / "windcheck_raw" / seg
            p = subprocess.run(["uv", "run", "--project", wc, "windcheck", "check", str(d), "--out", str(out)],
                               capture_output=True, text=True, cwd=wc)
            al = []
            if out.exists():
                for pf in out.glob("*_points.json"):
                    for c in json.load(open(pf)).get("collections", {}).values():
                        al += [pt["p"] for pt in c.get("points", {}).values()]
            so = (p.stdout + p.stderr).strip()[-400:]
            json.dump(dict(returncode=p.returncode, stdout=so, alarms_xyz=al,
                           verdict="no_verdict" if "below the census validity threshold" in so else
                           ("clean" if not al and p.returncode == 0 else ("alarm" if al else "error"))), open(f, "w"))
        f = det / "windcheck_patchmode" / f"{seg}.json"
        if not f.exists():
            f.parent.mkdir(parents=True, exist_ok=True)
            work = Path(tempfile.mkdtemp(prefix="wc_", dir=ROOT))
            subprocess.run(["uv", "run", "--project", wc, "python", str(here / "wc_patchmode.py"), str(d), str(work),
                            str(f.with_suffix(".raw.json"))], capture_output=True, text=True, cwd=wc)
            r = json.load(open(f.with_suffix(".raw.json")))
            f.with_suffix(".raw.json").unlink()
            import shutil
            shutil.rmtree(work, ignore_errors=True)
            json.dump(dict(transverse_both=r["transverse_both"], n_valid=r["n_valid"],
                           alarms_xyz=[c[k] for c in r["contacts"] for k in ("xyz1", "xyz2") if c.get(k)],
                           verdict="alarm" if r["transverse_both"] else "clean"), open(f, "w"))
        f = det / "seamcheck" / f"{seg}.json"
        if not f.exists():
            f.parent.mkdir(parents=True, exist_ok=True)
            subprocess.run([os.environ.get("SWITCHBENCH_EXT", "ext") + "/seamcheck/.venv/bin/python", str(here / "seamcheck_run.py"), str(d),
                            str(f.with_suffix(".raw.json"))], capture_output=True, text=True)
            r = json.load(open(f.with_suffix(".raw.json")))
            f.with_suffix(".raw.json").unlink()
            json.dump(dict(verdict=r["verdict"], winding_verdict=r["winding_verdict"], flagged=r["flagged"],
                           alarms_xyz=[s["xyz"] for s in r["flagged_steps"]] if r["verdict"] in ("REVIEW", "WATCH") else []),
                      open(f, "w"))
        print("detect", seg, flush=True)


# ----------------------------------------------------------------------------- evaluation
def evaluate():
    from . import metrics
    conf = json.load(open(ROOT / "confirm.json"))
    det = ROOT / "detect"
    rng = np.random.default_rng(SEED)
    rows, prow = [], []
    c2x = lambda P, cells: metrics.cells_to_xyz(P, cells)
    counts = dict(traces=0, in_sample=0, candidates=0, confirmed=0, contradicted=0, unconfirmed=0, multi_wrap=0,
                  negatives_confirmed=0, neg_mm=0.0)
    layer_sanity = dict(layers=0, in_sample=0, candidates=0, confirmed=0)
    dens, per = [], []
    for seg in json.load(open(ROOT / "inventory.json"))["traces"]:
        lr = json.load(open(ROOT / "label" / f"{seg}.json"))
        counts["traces"] += 1
        if not lr.get("in_sample"):
            continue
        counts["in_sample"] += 1
        cf = conf[seg]
        counts["candidates"] += len(cf["events"])
        for e in cf["events"]:
            counts[e["status"]] += 1
        counts["multi_wrap"] += len(lr["multi_wrap"])
        P, N = load(seg)
        td = json.load(open(det / "tifxyz_doctor" / f"{seg}.json"))
        al = {"tifxyz-doctor (coherent-normal-step)": c2x(P, td["alarms_primary"]),
              "tifxyz-doctor (any cue)": c2x(P, td["alarms_any"]),
              "tifxyz-doctor (cns) capped examples (v0 D10)": c2x(P, td["alarms_primary_capped"])}
        for t, name in (("windcheck", "windcheck"), ("windcheck_patchmode", "windcheck [patch mode]"), ("seamcheck", "seamcheck")):
            al[name] = np.asarray(json.load(open(det / t / f"{seg}.json")).get("alarms_xyz", []), float).reshape(-1, 3)
        from .sanity_v1 import fast_dedup
        area = np.isfinite(P).all(-1).sum() * (20 / MM) ** 2
        dens.append(len(fast_dedup(al["tifxyz-doctor (any cue)"], 0.5 * MM / geom.MM)) / max(area, 1e-9))
        per.append((seg, P, N, lr, cf, al, area))
    density = float(np.mean(dens)) if dens else 0.0
    sel_rng = np.random.default_rng(SEED)
    for seg, P, N, lr, cf, al, area in sorted(per, key=lambda x: x[0]):
        valid = np.argwhere(np.isfinite(P).all(-1))
        k = rng.poisson(density * area)
        pick = valid[rng.choice(len(valid), min(k, len(valid)), replace=False)] if k else np.zeros((0, 2), int)
        al["random"] = np.array([P[tuple(x)] for x in pick]).reshape(-1, 3)
        conf_idx = sorted([i for i, e in enumerate(cf["events"]) if e["status"] == "confirmed"],
                          key=lambda i: tuple(lr["events"][i]["xyz"]))
        capped = set(conf_idx if len(conf_idx) <= 3 else [conf_idx[j] for j in sorted(sel_rng.choice(len(conf_idx), 3, replace=False))])
        evpts = [np.array([m["xyz"] for m in lr["events"][i]["members"]] + [lr["events"][i]["xyz"]]) for i in range(len(lr["events"]))]
        allev = np.concatenate(evpts) if evpts else np.zeros((0, 3))
        for i in conf_idx:
            X = evpts[i]
            rows.append(dict(seg=seg, i=i, capped=i in capped,
                             hit={t: {r: bool(len(A) and (cKDTree(A).query(X)[0] <= r * MM).any()) for r in (0.5, 1.0, 2.0)}
                                  for t, A in al.items()}))
        fa = {t: 0 for t in al}
        nm_ = 0.0
        for n, nc in zip(lr["negatives"], cf["negatives"]):
            if nc["status"] != "confirmed":
                continue
            V = np.array([P[tuple(v)] for v in n["verts"]])
            nm_ += n["len_mm"]
            for t, A in al.items():
                if len(A):
                    from .sanity_v1 import fast_dedup
                    Ad = fast_dedup(A, 0.5 * MM / geom.MM)
                    on = cKDTree(V).query(Ad)[0] <= MM
                    off = cKDTree(allev).query(Ad)[0] > MM if len(allev) else np.ones(len(Ad), bool)
                    fa[t] += int((on & off).sum())
        counts["negatives_confirmed"] += sum(1 for nc in cf["negatives"] if nc["status"] == "confirmed")
        counts["neg_mm"] += nm_
        prow.append(dict(seg=seg, fa=fa, neg_mm=nm_))
    tools = sorted({t for r in prow for t in r["fa"]})
    res = {}
    for t in tools:
        d = {}
        for r_ in (0.5, 1.0, 2.0):
            for cap in (True, False):
                rs = [x for x in rows if x["capped"] or not cap]
                kk = sum(x["hit"][t][r_] for x in rs)
                p_, lo, hi = metrics.wilson(kk, len(rs))
                pats = sorted({x["seg"] for x in rs})
                by = {pp: [x["hit"][t][r_] for x in rs if x["seg"] == pp] for pp in pats}
                brng = np.random.default_rng(SEED)
                vals = []
                for _ in range(2000):
                    pk = brng.choice(len(pats), len(pats), replace=True) if pats else []
                    h = [v for ii in pk for v in by[pats[ii]]]
                    if h:
                        vals.append(sum(h) / len(h))
                d[f"r{r_}_{'capped' if cap else 'uncapped'}"] = dict(hits=kk, n_events=len(rs), recall=p_, wilson95=[lo, hi],
                                                                      boot95=[float(np.percentile(vals, 2.5)), float(np.percentile(vals, 97.5))] if vals else None)
        fa = sum(x["fa"][t] for x in prow)
        mm_ = sum(x["neg_mm"] for x in prow)
        d["fa"] = dict(false_alarms=fa, negative_mm=mm_, fa_per_100mm=100 * fa / mm_ if mm_ else None)
        res[t] = d
    for f in sorted((ROOT / "label_layers").glob("*.json")):
        r = json.load(open(f))
        layer_sanity["layers"] += 1
        if r.get("in_sample"):
            layer_sanity["in_sample"] += 1
            layer_sanity["candidates"] += len(r["events"])
            layer_sanity["confirmed"] += sum(1 for e in conf.get(r["seg"], {}).get("events", []) if e["status"] == "confirmed")
    out = dict(counts=counts, layer_sanity=layer_sanity, random_density_per_mm2=density, tools=res,
               independence={s: [k for k, v in r.items() if v.get("dependent")] for s, r in json.load(open(ROOT / "independence.json")).items()},
               ct_controls=json.load(open(ROOT / "ct_controls.json")) if (ROOT / "ct_controls.json").exists() else None,
               constants=json.load(open(ROOT / "constants.json")),
               not_applicable=dict(windaudit="no human winding annotations on PHerc0500P2",
                                   **{"#1621-style check": "no human winding annotations"},
                                   C3="no gen_avg_cost or generations in trace meta.json",
                                   **{"sheet-topo-bench": "not run (as on Paris4, V10)"}))
    json.dump(out, open(ROOT / "evaluation.json", "w"), indent=1, default=float)
    print(json.dumps(dict(counts=counts, layer_sanity=layer_sanity,
                          doctor={k: res["tifxyz-doctor (coherent-normal-step)"][k] for k in ("r1.0_capped", "fa")}), default=float))
    return out


def events_file():
    """Kit-compatible labeled events file for the replication (its own frame, voxel_mm, patch_source)."""
    import hashlib
    conf = json.load(open(ROOT / "confirm.json"))
    out = dict(scroll="PHerc0500P2", frame=f"level-0 voxels (x, y, z) of volume {FRAME} (4.317 um/vx)", voxel_mm=VOXEL_MM,
               patch_source=dict(s3_bucket="vesuvius-challenge-open-data", prefix="PHerc0500P2/segments",
                                 layout="<segment>/mesh/<timestamp>-on-20250528085330-4.317um.tifxyz/{x,y,z}.tif"),
               references={str(k): v for k, v in LAYERS.items()},
               labels="status = Paris4-tuned 2.4 um rule transferred in physical units (no tuning on this sample)",
               scoring=dict(per_patch_cap=3, match_mm=1.0, fa_dedup_mm=0.5, bootstrap=2000, seed=SEED),
               events=[], negatives=[], multi_wrap=[])
    grids = {}
    for seg in json.load(open(ROOT / "inventory.json"))["traces"]:
        lr = json.load(open(ROOT / "label" / f"{seg}.json"))
        if not lr.get("in_sample"):
            continue
        cf = conf[seg]
        P, _ = load(seg)
        for e, c in zip(lr["events"], cf["events"]):
            out["events"].append(dict(patch=seg, status=c["status"], xyz=[round(v, 1) for v in e["xyz"]],
                                      delta_signs=e["delta_signs"], layers=e["layers"],
                                      transitions=[dict(axis=m["axis"], rc_a=m["rc_a"], rc_b=m["rc_b"],
                                                        len_a_mm=round(m["len_a_mm"], 2), len_b_mm=round(m["len_b_mm"], 2))
                                                   for m in e["members"]]))
        for n, c in zip(lr["negatives"], cf["negatives"]):
            v0, v1 = tuple(n["verts"][0]), tuple(n["verts"][-1])
            out["negatives"].append(dict(patch=seg, status=c["status"], axis=n["axis"], rc0=list(v0), rc1=list(v1),
                                         len_mm=round(n["len_mm"], 2), layer=n.get("layer"),
                                         xyz0=[round(x, 1) for x in P[v0].tolist()], xyz1=[round(x, 1) for x in P[v1].tolist()]))
        for m in lr["multi_wrap"]:
            out["multi_wrap"].append(dict(patch=seg, xyz=[round(v, 1) for v in m["xyz"]], delta_signs=m["delta_signs"]))
        if any(c["status"] == "confirmed" for c in cf["events"]) or any(c["status"] == "confirmed" for c in cf["negatives"]):
            grids[seg] = P
    from tools.switchbench_kit import geometry as kg
    out["geometry_sha256"] = kg.fingerprint({k: kg.load_tifxyz(SEG / k) for k in grids})
    p = geom.REPO / "vault" / "results" / "switchbench_v1_0500p2_events.json"
    p.write_text(json.dumps(out, separators=(",", ":")))
    print(p, p.stat().st_size, hashlib.sha256(p.read_bytes()).hexdigest())
    return p


if __name__ == "__main__":
    cmd = sys.argv[1]
    {"pull": pull, "indep": indep, "controls": controls, "confirm": confirm_all, "detect": detect, "evaluate": evaluate,
     "events": events_file,
     "label": lambda: label_all(int(sys.argv[2]) if len(sys.argv) > 2 else 3)}[cmd]()
