"""SwitchBench-natural v1 evaluation (protocol P1 (prereg/switchbench_v1.md); frozen text prereg/switchbench_v1.md).

Corpus = v0 prefix (seeded order 20260925, patches 1-3,000; data/paris4/corpus) + new patches
3,001-10,000 (data/switchbench_v1/corpus), same in-sample rule and event definition (v0 as run).
Labels: every candidate re-confirmed with the level-0 (2.4 um) rule (confirm_l0.py); negatives keep
v0's on-layer rule. Scored patches: in sample with >= 1 confirmed event or >= 1 confirmed negative run.
Choices fixed before any v1 result (see switchbench_v1.md deviations table):
  * hit = ANY raw alarm location within r mm of an event point (event centre + member transition
    points); 0.5 mm-deduplicated alarms are used only for false-alarm counts and the random density
    (S4 harness fix). Primary r = 1 mm (v0 D10); sensitivity 0.5 / 2 mm.
  * per-patch cap 3: one RNG (seed 20260925) over patches sorted by name picks 3 of a patch's
    confirmed events (sorted by position) when it has more; uncapped = sensitivity.
  * patch-block bootstrap: B = 2000, a fresh RNG seeded 20260925 for every (tool, subset, setting).
  * C1 detector = tifxyz-doctor coherent-normal-step, uncapped union (API mask + CLI examples).
  * random baseline: Poisson alarms at the doctor's any-cue union density (0.5 mm-deduplicated) per
    mm^2 of each patch (seed 20260925, patches sorted by name).
  * C2 "handles natural switches": intended-mode recall lower bound >= 0.80 under either CI.
Usage: python -m tools.switchbench.evaluate_v1
"""
from __future__ import annotations

import json
import time
from functools import lru_cache

import numpy as np
from scipy.spatial import cKDTree

from . import evaluate, geom, metrics
from .geom import MM
from .sanity_v1 import fast_dedup

V1 = geom.REPO / "data" / "switchbench_v1"
DET = V1 / "detect"
SEED = 20260925
B = 2000
CAP = 3
RADII = (0.5, 1.0, 2.0)


# ----------------------------------------------------------------------------- corpus
def _l0(nm):
    f = V1 / "l0" / f"{nm}.json"
    return json.load(open(f)) if f.exists() else None


def load_pooled():
    """Unified in-sample patch records with v1 (level-0) event statuses."""
    out = []
    for subset, d in (("v0", geom.DATA / "corpus"), ("new", V1 / "corpus")):
        for f in sorted(d.glob("*.json")):
            r = json.load(open(f))
            if not r.get("in_sample"):
                continue
            l0 = _l0(r["patch"]) if r.get("events") else None
            evs = []
            for i, e in enumerate(r.get("events", [])):
                if l0 is None:
                    raise RuntimeError(f"no level-0 verdicts for {r['patch']}")
                le = l0["events"][i]
                if np.linalg.norm(np.array(le["xyz"]) - np.array(e["xyz"])) > 1e-6:
                    raise RuntimeError(f"level-0 verdict mismatch {r['patch']} event {i}")
                evs.append(dict(i=i, xyz=e["xyz"], delta_signs=e["delta_signs"], members=e["members"],
                                status=le["status_l0"], status_l2=e["status"], votes=le["votes"]))
            out.append(dict(patch=r["patch"], subset=subset, events=evs, negatives=r.get("negatives", []),
                            multi_wrap=r.get("multi_wrap", []), mode=r.get("mode"), seed=r.get("seed")))
    return out


def scored(recs):
    return [r for r in recs if any(e["status"] == "confirmed" for e in r["events"])
            or any(n["status"] == "confirmed" for n in r["negatives"])]


def scored_patches():
    return [r["patch"] for r in scored(load_pooled())]


def cap_selection(recs, cap=CAP):
    """{patch: set(event index i)} of the confirmed events that count toward capped recall. `cap`
    defaults to the frozen per-patch cap (P1); a different `cap` is POST-HOC/sensitivity only (e.g.
    tools.switchbench.robustness_v1), never the frozen scoring path."""
    rng = np.random.default_rng(SEED)
    sel = {}
    for r in sorted(recs, key=lambda x: x["patch"]):
        conf = sorted([e for e in r["events"] if e["status"] == "confirmed"], key=lambda e: tuple(e["xyz"]))
        if len(conf) > cap:
            pick = sorted(rng.choice(len(conf), cap, replace=False).tolist())
            sel[r["patch"]] = {conf[j]["i"] for j in pick}
        else:
            sel[r["patch"]] = {e["i"] for e in conf}
    return sel


# ----------------------------------------------------------------------------- geometry + alarms
@lru_cache(maxsize=64)
def patch_geom(nm):
    return evaluate.patch_geom(nm)


def _j(tool, nm):
    f = DET / tool / f"{nm}.json"
    return json.load(open(f)) if f.exists() else None


def alarms_for(nm, P):
    """{tool name: (raw alarm xyz (N,3), has_verdict bool)} for one patch."""
    td = _j("tifxyz_doctor", nm)
    if td is None:
        raise RuntimeError(f"tifxyz-doctor not run on {nm}")
    c2x = lambda cells: metrics.cells_to_xyz(P, cells)
    xyz = lambda lst: np.asarray(lst, float).reshape(-1, 3)
    out = {
        "tifxyz-doctor (coherent-normal-step)": (c2x(td["alarms_primary"]), True),
        "tifxyz-doctor (any cue)": (c2x(td["alarms_any"]), True),
        "tifxyz-doctor (cns) mask only": (c2x(td["mask_primary"]), True),
        "tifxyz-doctor (cns) capped examples (v0 D10)": (c2x(td["alarms_primary_capped"]), True),
        "tifxyz-doctor (cns) all candidate edges": (c2x(td["alarms_primary_alledges"]), True),
        "tifxyz-doctor (any cue) mask only": (c2x(td["mask_any"]), True),
        "tifxyz-doctor (any cue) capped examples (v0 D10)": (c2x(td["alarms_any_capped"]), True),
    }
    wc = _j("windcheck", nm)
    out["windcheck"] = (xyz(wc.get("alarms_xyz", [])), wc.get("verdict") in ("clean", "alarm"))
    wp = _j("windcheck_patchmode", nm)
    out["windcheck [intended: patch mode, no cell floor]"] = (xyz(wp.get("alarms_xyz", [])), wp.get("verdict") in ("clean", "alarm"))
    for mode, name in (("default", "windaudit"), ("intended", "windaudit [intended: attachment 0.45 D]")):
        wa = _j(f"windaudit_{mode}", nm)
        out[name] = (xyz(wa.get("alarms_xyz", [])), wa.get("verdict") in ("clean", "alarm"))
    a = _j("annot1621", nm)
    seg = [evaluate.segment_points(x["xyz_p"], x["xyz_q"]) for x in a["alarms"]]
    out["#1621-style annotation check"] = (np.concatenate(seg).reshape(-1, 3) if seg else np.zeros((0, 3)), a["pairs"] > 0)
    sc = _j("seamcheck", nm)
    out["seamcheck [secondary, added after freeze]"] = (xyz(sc.get("alarms_xyz", [])), sc.get("verdict") in ("REVIEW", "WATCH", "OK"))
    return out, dict(seamcheck_winding=sc.get("winding_verdict"), doctor_capped_cues=td.get("capped_emitted_cues", []))


PRIMARY = ["tifxyz-doctor (coherent-normal-step)", "tifxyz-doctor (any cue)", "windcheck", "windaudit",
           "#1621-style annotation check"]
INTENDED = {"windcheck": "windcheck [intended: patch mode, no cell floor]",
            "windaudit": "windaudit [intended: attachment 0.45 D]"}
SECONDARY = ["windcheck [intended: patch mode, no cell floor]", "windaudit [intended: attachment 0.45 D]",
             "seamcheck [secondary, added after freeze]"]
DOCTOR_VARIANTS = ["tifxyz-doctor (cns) mask only", "tifxyz-doctor (cns) capped examples (v0 D10)",
                   "tifxyz-doctor (cns) all candidate edges", "tifxyz-doctor (any cue) mask only",
                   "tifxyz-doctor (any cue) capped examples (v0 D10)"]


def near_any(X, A, mm):
    if len(X) == 0 or len(A) == 0:
        return np.zeros(len(X), bool)
    d, _ = cKDTree(A).query(X)
    return d <= mm * MM


# ----------------------------------------------------------------------------- scoring
def build_rows(recs):
    """Per scored patch: per-tool hits per confirmed event (per radius) and false alarms per radius."""
    sc = scored(recs)
    sel = cap_selection(sc)
    # random density: doctor any-cue union, deduplicated, per mm^2 (mean over scored patches)
    dens = []
    geo = {}
    for r in sorted(sc, key=lambda x: x["patch"]):
        P, N, meta = patch_geom(r["patch"])
        al, extra = alarms_for(r["patch"], P)
        geo[r["patch"]] = (al, extra)
        area = np.isfinite(P).all(-1).sum() * (20 / MM) ** 2
        dens.append(len(fast_dedup(al["tifxyz-doctor (any cue)"][0])) / max(area, 1e-9))
    density = float(np.mean(dens)) if dens else 0.0
    rng = np.random.default_rng(SEED)
    ev_rows, patch_rows = [], []
    for r in sorted(sc, key=lambda x: x["patch"]):
        nm = r["patch"]
        P, N, meta = patch_geom(nm)
        al, extra = geo[nm]
        valid = np.argwhere(np.isfinite(P).all(-1))
        area = len(valid) * (20 / MM) ** 2
        k = rng.poisson(density * area)
        pick = valid[rng.choice(len(valid), min(k, len(valid)), replace=False)] if k else np.zeros((0, 2), int)
        al["random"] = (np.array([P[tuple(x)] for x in pick]).reshape(-1, 3), True)
        all_ev = (np.concatenate([evaluate.event_points(e) for e in r["events"]]).reshape(-1, 3)
                  if r["events"] else np.zeros((0, 3)))
        prow = dict(patch=nm, subset=r["subset"], verdict={t: v for t, (_, v) in al.items()},
                    fa={t: {rr: 0 for rr in RADII} for t in al}, neg_mm=0.0, extra=extra,
                    n_alarms={t: int(len(a)) for t, (a, _) in al.items()})
        dd = {t: fast_dedup(a) for t, (a, _) in al.items()}
        for n in r["negatives"]:
            if n["status"] != "confirmed":
                continue
            V = np.array([P[tuple(v)] for v in n["verts"]])
            prow["neg_mm"] += n["len_mm"]
            for t, A in dd.items():
                if not len(A):
                    continue
                for rr in RADII:
                    on_run = near_any(A, V, rr)
                    off_ev = ~near_any(A, all_ev, rr) if len(all_ev) else np.ones(len(A), bool)
                    prow["fa"][t][rr] += int((on_run & off_ev).sum())
        patch_rows.append(prow)
        for e in r["events"]:
            if e["status"] != "confirmed":
                continue
            X = evaluate.event_points(e)
            row = dict(patch=nm, subset=r["subset"], i=e["i"], capped=e["i"] in sel[nm],
                       both_sides_1mm=any(m.get("both_sides_1mm") for m in e["members"]),
                       status_l2=e["status_l2"], hit={})
            for t, (A, _) in al.items():
                row["hit"][t] = {rr: bool(near_any(X, A, rr).any()) for rr in RADII}
            ev_rows.append(row)
    return ev_rows, patch_rows, density


def recall_stats(ev_rows, tool, subset=None, capped=True, radius=1.0, extra_filter=None):
    rows = [x for x in ev_rows if (subset is None or x["subset"] == subset) and (x["capped"] or not capped)
            and (extra_filter is None or extra_filter(x))]
    k = sum(x["hit"][tool][radius] for x in rows)
    n = len(rows)
    p, lo, hi = metrics.wilson(k, n)
    pats = sorted({x["patch"] for x in rows})
    by = {pp: [x["hit"][tool][radius] for x in rows if x["patch"] == pp] for pp in pats}
    rng = np.random.default_rng(SEED)
    vals = []
    for _ in range(B):
        pick = rng.choice(len(pats), len(pats), replace=True) if pats else []
        h = [v for i in pick for v in by[pats[i]]]
        if h:
            vals.append(sum(h) / len(h))
    bl, bh = (float(np.percentile(vals, 2.5)), float(np.percentile(vals, 97.5))) if vals else (None, None)
    return dict(hits=int(k), n_events=n, n_patches=len(pats), recall=p, wilson95=[lo, hi], boot95=[bl, bh])


def fa_stats(patch_rows, tool, subset=None, radius=1.0):
    rows = [x for x in patch_rows if subset is None or x["subset"] == subset]
    fa = sum(x["fa"][tool][radius] for x in rows)
    mm = sum(x["neg_mm"] for x in rows)
    return dict(false_alarms=int(fa), negative_mm=mm, fa_per_100mm=(100 * fa / mm) if mm else None,
                patches_with_verdict=sum(1 for x in rows if x["verdict"][tool]), n_patches=len(rows))


def gen_avg_cost(recs, subset=None, capped_sel=None):
    """C3 as v0 evaluate.py (generation proxy D6), on scored patches of the subset."""
    items = []
    for r in sorted(scored(recs), key=lambda x: x["patch"]):
        if subset is not None and r["subset"] != subset:
            continue
        P, N, meta = patch_geom(r["patch"])
        gac, seed = meta.get("gen_avg_cost"), meta.get("seed")
        if not (gac and seed):
            continue
        G = metrics.gen_estimate(P, seed)
        all_ev = (np.concatenate([evaluate.event_points(e) for e in r["events"]]).reshape(-1, 3)
                  if r["events"] else np.zeros((0, 3)))
        for e in r["events"]:
            if e["status"] != "confirmed" or (capped_sel is not None and e["i"] not in capped_sel[r["patch"]]):
                continue
            rcs = [tuple(m["rc_a"]) for m in e["members"]] + [tuple(m["rc_b"]) for m in e["members"]]
            g = np.array([G[x] for x in rcs if np.isfinite(G[x])])
            if len(g):
                items.append((r["patch"], 1, metrics.window_score(gac, g)))
        for n in r["negatives"]:
            if n["status"] != "confirmed":
                continue
            vv = [tuple(v) for v in n["verts"]]
            for i in range(0, len(vv) - 4, 5):
                w = vv[i:i + 5]
                Wp = np.array([P[x] for x in w])
                if len(all_ev) and evaluate.near(all_ev, Wp).any():
                    continue
                g = np.array([G[x] for x in w if np.isfinite(G[x])])
                if len(g):
                    items.append((r["patch"], 0, metrics.window_score(gac, g)))
    rnd_rng = np.random.default_rng(SEED)
    rnd = [(a, b, float(rnd_rng.random())) for a, b, _ in items]
    return dict(n_event_windows=sum(1 for x in items if x[1] == 1), n_negative_windows=sum(1 for x in items if x[1] == 0),
                n_patches=len({x[0] for x in items}),
                auroc=metrics.block_bootstrap_auroc(items) if items else None,
                random_score_auroc=metrics.block_bootstrap_auroc(rnd) if rnd else None)


def corpus_counts(recs, subset=None):
    rs = [r for r in recs if subset is None or r["subset"] == subset]
    ev = [e for r in rs for e in r["events"]]
    ng = [n for r in rs for n in r["negatives"]]
    return dict(in_sample=len(rs), candidates=len(ev),
                confirmed=sum(e["status"] == "confirmed" for e in ev),
                contradicted=sum(e["status"] == "contradicted" for e in ev),
                unconfirmed=sum(e["status"] == "unconfirmed" for e in ev),
                confirmed_l2_v0rule=sum(e["status_l2"] == "confirmed" for e in ev),
                confirmed_both_rules=sum(e["status"] == "confirmed" and e["status_l2"] == "confirmed" for e in ev),
                multi_wrap=sum(len(r["multi_wrap"]) for r in rs),
                negatives_confirmed=sum(n["status"] == "confirmed" for n in ng),
                negatives_other=sum(n["status"] != "confirmed" for n in ng),
                neg_mm_confirmed=sum(n["len_mm"] for n in ng if n["status"] == "confirmed"),
                scored_patches=len(scored(rs)),
                event_patches=len({r["patch"] for r in rs for e in r["events"] if e["status"] == "confirmed"}),
                max_events_per_patch=max((sum(e["status"] == "confirmed" for e in r["events"]) for r in rs), default=0))


MATCHED = "random (FA-matched to the C1 doctor alarms)"


def add_fa_matched_random(recs, ev_rows, patch_rows, density):
    """Added after the authors' framing note (2026-09-26): compare random only at a matched false-alarm rate.
    Random alarms are drawn (seed [20260925, 1], patches sorted by name) at the density that scales the
    density-matched baseline's pooled false-alarm rate (1 mm) to the C1 doctor alarms' rate."""
    doc = "tifxyz-doctor (coherent-normal-step)"
    fa_d = sum(x["fa"][doc][1.0] for x in patch_rows)
    fa_r = sum(x["fa"]["random"][1.0] for x in patch_rows)
    dm = density * fa_d / fa_r if fa_r else 0.0
    rng = np.random.default_rng([SEED, 1])
    by_patch = {x["patch"]: x for x in patch_rows}
    evi = {}
    for x in ev_rows:
        evi.setdefault(x["patch"], []).append(x)
    for r in sorted(scored(recs), key=lambda x: x["patch"]):
        P, N, meta = patch_geom(r["patch"])
        valid = np.argwhere(np.isfinite(P).all(-1))
        area = len(valid) * (20 / MM) ** 2
        k = rng.poisson(dm * area)
        pick = valid[rng.choice(len(valid), min(k, len(valid)), replace=False)] if k else np.zeros((0, 2), int)
        A = np.array([P[tuple(x)] for x in pick]).reshape(-1, 3)
        Ad = fast_dedup(A)
        all_ev = (np.concatenate([evaluate.event_points(e) for e in r["events"]]).reshape(-1, 3)
                  if r["events"] else np.zeros((0, 3)))
        pr = by_patch[r["patch"]]
        pr["verdict"][MATCHED] = True
        pr["fa"][MATCHED] = {rr: 0 for rr in RADII}
        for n in r["negatives"]:
            if n["status"] != "confirmed" or not len(Ad):
                continue
            V = np.array([P[tuple(v)] for v in n["verts"]])
            for rr in RADII:
                on_run = near_any(Ad, V, rr)
                off_ev = ~near_any(Ad, all_ev, rr) if len(all_ev) else np.ones(len(Ad), bool)
                pr["fa"][MATCHED][rr] += int((on_run & off_ev).sum())
        ev_by_i = {e["i"]: e for e in r["events"]}
        for x in evi.get(r["patch"], []):
            X = evaluate.event_points(ev_by_i[x["i"]])
            x["hit"][MATCHED] = {rr: bool(near_any(X, A, rr).any()) for rr in RADII}
    return dm


def main():
    t0 = time.time()
    recs = load_pooled()
    ev_rows, patch_rows, density = build_rows(recs)
    dens_matched = add_fa_matched_random(recs, ev_rows, patch_rows, density)
    tools = sorted({t for x in patch_rows for t in x["fa"]})
    subsets = {"pooled": None, "new": "new", "v0_prefix": "v0"}
    res = dict(generated_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), random_density_per_mm2=density,
               random_fa_matched_density_per_mm2=dens_matched,
               corpus={k: corpus_counts(recs, v) for k, v in subsets.items()}, tools={})
    for t in tools:
        res["tools"][t] = {}
        for sk, sv in subsets.items():
            d = {}
            for rr in RADII:
                d[f"r{rr}"] = dict(capped=recall_stats(ev_rows, t, sv, True, rr),
                                   uncapped=recall_stats(ev_rows, t, sv, False, rr),
                                   fa=fa_stats(patch_rows, t, sv, rr))
            d["both_sides_1mm_capped"] = recall_stats(ev_rows, t, sv, True, 1.0, lambda x: x["both_sides_1mm"])
            d["also_confirmed_by_v0_rule_capped"] = recall_stats(ev_rows, t, sv, True, 1.0,
                                                                 lambda x: x["status_l2"] == "confirmed")
            res["tools"][t][sk] = d
    sel = cap_selection(scored(recs))
    res["gen_avg_cost"] = {sk: gen_avg_cost(recs, sv) for sk, sv in subsets.items()}
    res["gen_avg_cost_capped"] = {sk: gen_avg_cost(recs, sv, sel) for sk, sv in subsets.items()}
    res["seamcheck_winding_verdicts"] = {}
    for x in patch_rows:
        v = x["extra"]["seamcheck_winding"]
        res["seamcheck_winding_verdicts"][v] = res["seamcheck_winding_verdicts"].get(v, 0) + 1
    res["doctor_patches_with_capped_cue"] = sum(1 for x in patch_rows if x["extra"]["doctor_capped_cues"])
    res["elapsed_s"] = time.time() - t0
    json.dump(dict(summary=res, ev_rows=ev_rows, patch_rows=patch_rows), open(V1 / "evaluation_v1.json", "w"),
              default=float)
    return res


if __name__ == "__main__":
    r = main()
    for t, d in r["tools"].items():
        c = d["pooled"]["r1.0"]["capped"]
        print(f"{t[:60]:60s} {c['hits']}/{c['n_events']} boot {c['boot95']}")
