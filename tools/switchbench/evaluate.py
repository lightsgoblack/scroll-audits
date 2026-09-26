"""Score detectors and baselines on the SwitchBench-natural corpus and write the results JSON.

Usage: python -m tools.switchbench.evaluate
"""
from __future__ import annotations

import json
import time

import numpy as np

from . import annot, detectors, geom, metrics, run_windaudit
from .geom import MM

RES = geom.REPO / "vault" / "results"


def load_corpus():
    recs = [json.load(open(f)) for f in sorted((geom.DATA / "corpus").glob("*.json"))]
    return recs


def patch_geom(nm):
    d = geom.DATA / "unverified_patches" / nm
    P = geom.load_tifxyz(d)
    N = geom.orient_outward(P, geom.grid_normals(P))
    meta = json.load(open(d / "meta.json"))
    return P, N, meta


def event_points(e):
    return np.array([m["xyz"] for m in e["members"]] + [e["xyz"]])


def near(X, A, mm=metrics.MATCH_MM):
    """Boolean per row of A: within mm of any point in X."""
    if len(X) == 0 or len(A) == 0:
        return np.zeros(len(A), bool)
    from scipy.spatial import cKDTree
    d, _ = cKDTree(X).query(A)
    return d <= mm * MM


def dedup_alarms(A, mm=0.5):
    """Merge alarms closer than mm into one (so a cue band counts once)."""
    A = np.asarray(A).reshape(-1, 3)
    keep = []
    for a in A:
        if all(np.linalg.norm(a - b) > mm * MM for b in keep):
            keep.append(a)
    return np.array(keep).reshape(-1, 3)


def segment_points(p, q, n=20):
    p, q = np.asarray(p), np.asarray(q)
    return p[None] + np.linspace(0, 1, n)[:, None] * (q - p)[None]


def main():
    t0 = time.time()
    recs = load_corpus()
    ins = [r for r in recs if r.get("in_sample")]
    scored = [r for r in ins if any(e["status"] == "confirmed" for e in r["events"])
              or any(n["status"] == "confirmed" for n in r["negatives"])]
    rng = np.random.default_rng(metrics.SEED)
    tools = ["tifxyz-doctor (coherent-normal-step)", "tifxyz-doctor (any cue)", "windcheck", "windaudit",
             "#1621-style annotation check", "random"]
    per = {t: dict(hit=0, n=0, fa=0, neg_mm=0.0, patches_with_verdict=0) for t in tools}
    ev_rows, gac_items = [], []
    # random baseline density: mean tifxyz-doctor any-cue alarms per mm^2 over scored patches (fixed rule)
    dens = []
    geoms = {}
    for r in scored:
        nm = r["patch"]
        P, N, meta = patch_geom(nm)
        geoms[nm] = (P, N, meta)
        td = detectors.tifxyz_doctor(nm)
        area_mm2 = np.isfinite(P).all(-1).sum() * (20 / MM) ** 2
        dens.append(len(dedup_alarms(metrics.cells_to_xyz(P, td.get("alarms_any", [])))) / max(area_mm2, 1e-9))
    rand_density = float(np.mean(dens)) if dens else 0.0
    for r in scored:
        nm = r["patch"]
        P, N, meta = geoms[nm]
        td = detectors.tifxyz_doctor(nm)
        wc = detectors.windcheck(nm)
        a1621 = annot.check_1621(P, N)
        wa = run_windaudit.run(nm, P, N)
        alarms = {
            "tifxyz-doctor (coherent-normal-step)": dedup_alarms(metrics.cells_to_xyz(P, td.get("alarms_primary", []))),
            "tifxyz-doctor (any cue)": dedup_alarms(metrics.cells_to_xyz(P, td.get("alarms_any", []))),
            "windcheck": dedup_alarms(np.array(wc.get("alarms_xyz", [])).reshape(-1, 3)),
            "windaudit": dedup_alarms(np.array(wa.get("alarms_xyz", [])).reshape(-1, 3)),
            "#1621-style annotation check": np.concatenate(
                [segment_points(a["xyz_p"], a["xyz_q"]) for a in a1621["alarms"]]).reshape(-1, 3)
            if a1621["alarms"] else np.zeros((0, 3)),
        }
        valid = np.argwhere(np.isfinite(P).all(-1))
        area_mm2 = len(valid) * (20 / MM) ** 2
        k = rng.poisson(rand_density * area_mm2)
        pick = valid[rng.choice(len(valid), min(k, len(valid)), replace=False)] if k else np.zeros((0, 2), int)
        alarms["random"] = np.array([P[tuple(x)] for x in pick]).reshape(-1, 3)
        verdict = {"windcheck": wc.get("verdict") in ("clean", "alarm"),
                   "windaudit": wa.get("verdict") in ("clean", "alarm"),
                   "#1621-style annotation check": a1621["pairs"] > 0}
        all_ev_pts = np.concatenate([event_points(e) for e in r["events"]]).reshape(-1, 3) if r["events"] else np.zeros((0, 3))
        for t in tools:
            per[t]["patches_with_verdict"] += int(verdict.get(t, True))
        for e in r["events"]:
            if e["status"] != "confirmed":
                continue
            X = event_points(e)
            row = dict(patch=nm, xyz=e["xyz"], delta_signs=e["delta_signs"], n_members=len(e["members"]),
                       both_sides_1mm=any(m.get("both_sides_1mm") for m in e["members"]))
            for t in tools:
                hit = bool(near(X, alarms[t]).any()) if len(alarms[t]) else False
                per[t]["n"] += 1
                per[t]["hit"] += int(hit)
                row[t] = hit
            row["verdict_windcheck"] = verdict["windcheck"]
            row["verdict_windaudit"] = wa.get("verdict")
            row["verdict_1621"] = verdict["#1621-style annotation check"]
            ev_rows.append(row)
        for n in r["negatives"]:
            if n["status"] != "confirmed":
                continue
            V = np.array([P[tuple(v)] for v in n["verts"]])
            for t in tools:
                A = alarms[t]
                if len(A):
                    on_run = near(V, A)
                    off_ev = ~near(all_ev_pts, A) if len(all_ev_pts) else np.ones(len(A), bool)
                    per[t]["fa"] += int((on_run & off_ev).sum())
                per[t]["neg_mm"] += n["len_mm"]
        # gen_avg_cost windows (generation proxy, see metrics.gen_estimate)
        gac = meta.get("gen_avg_cost")
        seed = meta.get("seed")
        if gac and seed:
            G = metrics.gen_estimate(P, seed)
            for e in r["events"]:
                if e["status"] != "confirmed":
                    continue
                rcs = [tuple(m["rc_a"]) for m in e["members"]] + [tuple(m["rc_b"]) for m in e["members"]]
                g = np.array([G[x] for x in rcs if np.isfinite(G[x])])
                if len(g):
                    gac_items.append((nm, 1, metrics.window_score(gac, g), r.get("mode")))
            for n in r["negatives"]:
                if n["status"] != "confirmed":
                    continue
                vv = [tuple(v) for v in n["verts"]]
                for i in range(0, len(vv) - 4, 5):   # ~1 mm windows (5 grid steps = 0.96 mm)
                    w = vv[i:i + 5]
                    Wp = np.array([P[x] for x in w])
                    if len(all_ev_pts) and near(all_ev_pts, Wp).any():
                        continue
                    g = np.array([G[x] for x in w if np.isfinite(G[x])])
                    if len(g):
                        gac_items.append((nm, 0, metrics.window_score(gac, g), r.get("mode")))
    out = dict(generated=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), match_mm=metrics.MATCH_MM,
               random_density_per_mm2=rand_density, detectors={})
    for t in tools:
        k, n = per[t]["hit"], per[t]["n"]
        p, lo, hi = metrics.wilson(k, n)
        pub_key = "tifxyz-doctor" if t.startswith("tifxyz") else t
        if t == "tifxyz-doctor (any cue)":
            pub_key = None
        pub = metrics.PUBLISHED.get(pub_key, {}) if pub_key else {}
        pv = pub.get("value")
        out["detectors"][t] = dict(hits=k, n_events=n, recall=p, recall_ci95=[lo, hi],
                                   false_alarms=per[t]["fa"], negative_mm=per[t]["neg_mm"],
                                   fa_per_100mm=(100 * per[t]["fa"] / per[t]["neg_mm"]) if per[t]["neg_mm"] else None,
                                   patches_with_verdict=per[t]["patches_with_verdict"], n_patches=len(scored),
                                   published_planted_recall=pv, published_text=pub.get("text"),
                                   published_source=pub.get("source"),
                                   gap=(p - pv) if (p is not None and pv is not None) else None,
                                   ci_excludes_published=(hi < pv or lo > pv) if (pv is not None and lo is not None) else None)
    items = [(a, b, c) for a, b, c, _ in gac_items]
    out["gen_avg_cost"] = dict(n_event_windows=sum(1 for x in items if x[1] == 1),
                               n_negative_windows=sum(1 for x in items if x[1] == 0),
                               n_patches=len({x[0] for x in items}),
                               auroc=metrics.block_bootstrap_auroc(items) if items else None)
    rnd = [(a, b, float(rng.random())) for a, b, _ in items]
    out["random_score_auroc"] = metrics.block_bootstrap_auroc(rnd) if rnd else None
    out["events"] = ev_rows
    out["elapsed_s"] = time.time() - t0
    json.dump(out, open(geom.DATA / "evaluation.json", "w"), indent=1, default=float)
    return out


if __name__ == "__main__":
    o = main()
    print(json.dumps({k: v for k, v in o.items() if k != "events"}, indent=1, default=float))
