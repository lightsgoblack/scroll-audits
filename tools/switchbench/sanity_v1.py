"""SwitchBench v1 sanity checks (protocol P1 (prereg/switchbench_v1.md): failure = harness bug, no verdict).

S1-S3: the v0 checks re-run on the v1 harness (sanity.py logic, same seeds and patch selection), with
       event confirmation by the level-0 (2.4 um) rule (confirm_l0.py). S2 additionally reports the
       2.4 um verdict at each planted event (informational: the rule's ladder sensitivity is < 100%).
S4:    the uncapped doctor run (doctor_v1.py) reproduces every v0 hit on the 69 v0 doctor patches:
       (a) the pinned tool reproduces v0's stored capped alarm lists exactly;
       (b) uncapped alarms are a superset of the capped ones;
       (c) every v0 event hit (and v0 false alarm) with capped alarms is still a hit with uncapped ones.
       Also reports what the cap hid (extra hits on v0's confirmed events, extra false alarms).
Usage: python -m tools.switchbench.sanity_v1 s4 | s123
"""
from __future__ import annotations

import json
import sys
import time

import numpy as np

from . import doctor_v1, evaluate, geom, metrics

V1 = geom.REPO / "data" / "switchbench_v1"
OUT = V1 / "sanity_v1.json"


def fast_dedup(A, mm=0.5):
    """Same result as evaluate.dedup_alarms (greedy in input order), with a spatial hash."""
    A = np.asarray(A, float).reshape(-1, 3)
    h = mm * geom.MM
    grid, keep = {}, []
    for a in A:
        k = tuple(np.floor(a / h).astype(int))
        ok = True
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for dz in (-1, 0, 1):
                    for b in grid.get((k[0] + dx, k[1] + dy, k[2] + dz), ()):
                        if np.linalg.norm(a - b) <= h:
                            ok = False
                            break
                    if not ok:
                        break
                if not ok:
                    break
            if not ok:
                break
        if ok:
            keep.append(a)
            grid.setdefault(k, []).append(a)
    return np.array(keep).reshape(-1, 3)


def score_patch(P, rec_corpus, alarms_raw, mm=metrics.MATCH_MM):
    """Per confirmed event hit flags and false alarms on confirmed negatives.

    v1 harness fix (found by S4): an event is hit if ANY alarm location lies within mm of it (raw
    alarms, D10 as written). v0 matched against 0.5 mm-deduplicated alarm representatives, and with the
    larger uncapped sets a representative can shift more than 1 mm away from an event whose own alarm is
    within 1 mm. Deduplication (a cue band counts once) is kept for false-alarm counting only.
    Returns (hits, false_alarms, negative_mm, hits_v0_style)."""
    alarms_raw = np.asarray(alarms_raw, float).reshape(-1, 3)
    alarms_dd = fast_dedup(alarms_raw)
    evs = [e for e in rec_corpus["events"] if e["status"] == "confirmed"]
    all_ev = (np.concatenate([evaluate.event_points(e) for e in rec_corpus["events"]]).reshape(-1, 3)
              if rec_corpus["events"] else np.zeros((0, 3)))
    hits = [bool(evaluate.near(evaluate.event_points(e), alarms_raw, mm).any()) if len(alarms_raw) else False
            for e in evs]
    hits_v0 = [bool(evaluate.near(evaluate.event_points(e), alarms_dd, mm).any()) if len(alarms_dd) else False
               for e in evs]
    fa, neg_mm = 0, 0.0
    for n in rec_corpus["negatives"]:
        if n["status"] != "confirmed":
            continue
        V = np.array([P[tuple(v)] for v in n["verts"]])
        if len(alarms_dd):
            on_run = evaluate.near(V, alarms_dd, mm)
            off_ev = ~evaluate.near(all_ev, alarms_dd, mm) if len(all_ev) else np.ones(len(alarms_dd), bool)
            fa += int((on_run & off_ev).sum())
        neg_mm += n["len_mm"]
    return hits, fa, neg_mm, hits_v0


VARIANTS = {  # name -> (doctor_v1 record key, role)
    "prim_capped": "alarms_primary_capped", "prim_union": "alarms_primary", "prim_mask": "mask_primary",
    "prim_alledges": "alarms_primary_alledges",
    "any_capped": "alarms_any_capped", "any_union": "alarms_any", "any_mask": "mask_any",
    "any_allflagged": "alarms_any_allflagged",
}


def s4():
    """S4 on the 69 v0 doctor patches. Primary = union (mask + CLI examples), per the post-freeze call."""
    t0 = time.time()
    v0_dir = geom.DATA / "detect" / "tifxyz_doctor"
    names = sorted(f.stem for f in v0_dir.glob("*.json"))
    rows, fails = [], []
    tot = {f"hits_{k}": 0 for k in VARIANTS} | {f"fa_{k}": 0 for k in VARIANTS} | dict(n_events=0, neg_mm=0.0)
    hit_class = []
    for nm in names:
        v0 = json.load(open(v0_dir / f"{nm}.json"))
        r1 = doctor_v1.run(nm)
        same = (r1.get("alarms_primary_capped") == v0.get("alarms_primary")
                and r1.get("alarms_any_capped") == v0.get("alarms_any")
                and r1.get("findings") == v0.get("findings"))
        sets = {k: {tuple(x) for x in r1.get(v, [])} for k, v in VARIANTS.items()}
        sup = sets["prim_capped"] <= sets["prim_union"] and sets["any_capped"] <= sets["any_union"]
        P, N, _ = evaluate.patch_geom(nm)
        cr = json.load(open(geom.DATA / "corpus" / f"{nm}.json"))
        row = dict(patch=nm, reproduces_v0_output=same, union_superset_of_capped=sup,
                   capped_emitted_cues=r1.get("capped_emitted_cues"),
                   n_alarms={k: len(v) for k, v in sets.items()})
        hits = {}
        for k, key in VARIANTS.items():
            A = metrics.cells_to_xyz(P, r1.get(key, []))
            h, fa, nmm, h_v0 = score_patch(P, cr, A)
            hits[k] = h
            hits[k + "_v0match"] = h_v0
            row[f"hits_{k}"], row[f"fa_{k}"], row[f"hits_{k}_v0match"] = sum(h), fa, sum(h_v0)
            tot[f"hits_{k}"] += sum(h)
            tot[f"hits_{k}_v0match"] = tot.get(f"hits_{k}_v0match", 0) + sum(h_v0)
            tot[f"fa_{k}"] += fa
        tot["n_events"] += len(hits["prim_capped"])
        tot["neg_mm"] += nmm
        for fam in ("prim", "any"):
            # every v0 hit (v0 matching on the capped examples) must be a hit of the union
            lost = [i for i, (a, b) in enumerate(zip(hits[f"{fam}_capped_v0match"], hits[f"{fam}_union"])) if a and not b]
            if lost:
                fails.append((nm, fam, f"union loses v0 hits {lost}"))
            if row[f"fa_{fam}_union"] < row[f"fa_{fam}_capped"]:
                fails.append((nm, fam, "union has fewer false alarms than v0 capped"))
        for i, a in enumerate(hits["prim_capped_v0match"]):
            if a:
                hit_class.append(dict(patch=nm, event=i, in_mask=bool(hits["prim_mask"][i]),
                                      in_alledges=bool(hits["prim_alledges"][i])))
        if not (same and sup):
            fails.append((nm, "output", "tool output differs from v0, or union is not a superset of capped"))
        rows.append(row)
    out = dict(passed=not fails, rule="union (mask + CLI examples) reproduces every v0 hit; tool output identical to v0",
               n_patches=len(names), failures=fails, totals=tot,
               v0_primary_hits_classified=hit_class,
               v0_primary_hits_in_mask=sum(h["in_mask"] for h in hit_class),
               v0_primary_hits_subcomponent_only=sum(not h["in_mask"] for h in hit_class),
               patches_with_capped_emitted_cue=sum(1 for r in rows if r["capped_emitted_cues"]),
               patches_capped_primary=sum(1 for r in rows if "coherent-normal-step" in (r["capped_emitted_cues"] or [])),
               rows=rows, elapsed_s=time.time() - t0)
    j = json.load(open(OUT)) if OUT.exists() else {}
    j["S4"] = out
    json.dump(j, open(OUT, "w"), indent=1)
    print(json.dumps({k: v for k, v in out.items() if k not in ("rows",)}, indent=1))
    return out


def _l0_event(sampler, params, P, N, e, st, asg):
    """Level-0 verdict for one geometry event (member geometry exactly as the corpus stage)."""
    from . import confirm_l0, corpus_v1
    geo = corpus_v1.member_geometry(P, N, e, st, asg)
    votes = [confirm_l0.member_verdict(sampler, g, params)[0] for g in geo]
    return confirm_l0.event_verdict(votes), votes


def s123(n3=100):
    """S1-S3 exactly as v0 (sanity.py seeds and patch selection), events confirmed by the 2.4 um rule."""
    from scipy.ndimage import generic_filter  # noqa: F401  (used by sanity.plant)
    from . import confirm, confirm_l0, label, sanity
    from .ct0 import Sampler
    t0 = time.time()
    params = confirm_l0.load_rule()
    sampler = Sampler(0, max_chunks=320)
    vi = geom.VerifiedIndex()
    rng = np.random.default_rng(sanity.SEED)
    sizes = {p.split("/")[-2]: sz for p, sz in json.load(open(geom.DATA / "verified_files.json"))
             if p.endswith("/x.tif") and "/backups/" not in p}
    order = [n for n in rng.permutation(vi.names) if sizes.get(n, 1e9) <= 60_000]
    out = {"seed": sanity.SEED, "rule_l0": params}
    out["S1"] = sanity.s1(vi, order[:10])
    out["S1"] = dict(passed=out["S1"]["passed"], events=[x["events"] for x in out["S1"]["patches"]],
                     patches=[x["patch"] for x in out["S1"]["patches"]])
    print("S1", out["S1"]["passed"], out["S1"]["events"], flush=True)
    # S2: v0 sanity.s2 logic, plus the informational 2.4 um verdict at each planted event
    res = []
    for nm in order[10:400]:
        P, N, _ = vi.patch(nm)
        if P.shape[1] < 30 or P.shape[0] < 5:
            continue
        Q, moved, cstar = sanity.plant(vi, nm)
        left = np.isfinite(P[:, :cstar]).all(-1)
        good = [moved[r, cstar:cstar + 12].all() and left[r, cstar - 12:].all() for r in range(P.shape[0])]
        best, cur = (0, 0), None
        for r, g in enumerate(good + [False]):
            if g and cur is None:
                cur = r
            elif not g and cur is not None:
                if r - cur > best[1] - best[0]:
                    best = (cur, r)
                cur = None
        if best[1] - best[0] < 3:
            continue
        rows = list(range(*best))
        keep = np.zeros(P.shape[:2], bool)
        keep[rows, cstar - 12:cstar + 12] = True
        Q[~keep] = np.nan
        NQ = geom.orient_outward(Q, geom.grid_normals(Q))
        lo = np.nanmin(Q.reshape(-1, 3), 0)
        hi = np.nanmax(Q.reshape(-1, 3), 0)
        cl = vi.local_cloud(lo, hi, pad=160.0)
        r = label.label_patch(Q, NQ, cl)
        truth = np.nanmean(np.concatenate([Q[rows, cstar - 1], Q[rows, cstar]]), 0)
        ev = r["events"]
        near_col = [all(abs(m["rc_a"][1] - (cstar - 1)) <= 2 and abs(m["rc_b"][1] - cstar) <= 2
                        for m in e["members"]) for e in ev]
        ok = len(ev) == 1 and near_col[0] and ev[0]["delta_signs"] == [1]
        l0 = [_l0_event(sampler, params, Q, NQ, e, r["stacks"], r["asg"])[0] for e in ev]
        l2 = [confirm.confirm_event(Q, NQ, e, r["stacks"], r["asg"])[0] for e in ev]
        res.append(dict(patch=nm, rows=[rows[0], rows[-1]], cstar=cstar, n_events=len(ev),
                        event_dist_mm=[float(np.linalg.norm(np.array(e["xyz"]) - truth) / geom.MM) for e in ev],
                        at_planted_column=near_col, delta_signs=[e["delta_signs"] for e in ev],
                        ct_l0=l0, ct_l2_v0rule=l2, passed=ok))
        if len(res) >= 5:
            break
    out["S2"] = dict(passed=bool(res) and all(x["passed"] for x in res), n=len(res), cases=res,
                     planted_events_confirmed_l0=sum(1 for x in res for v in x["ct_l0"] if v),
                     planted_events_l0_decided=sum(1 for x in res for v in x["ct_l0"] if v is not None))
    print("S2", out["S2"]["passed"], [(c["n_events"], c["at_planted_column"], c["ct_l0"]) for c in res], flush=True)
    # S3: labeler on verified patches (same-lineage excluded); confirmed = 2.4 um rule
    res = []
    for nm in order[400:400 + n3]:
        P, N, _ = vi.patch(nm)
        r, _ = sanity.run_patch(vi, P, N, exclude=sanity.same_lineage(vi, nm))
        l0 = [_l0_event(sampler, params, P, N, e, r["stacks"], r["asg"])[0] for e in r["events"]]
        l2 = [confirm.confirm_event(P, N, e, r["stacks"], r["asg"])[0] for e in r["events"]]
        res.append(dict(patch=nm, events_geom=len(r["events"]), n_assigned=r["stats"]["n_assigned"],
                        n_valid=r["stats"]["n_valid"], ct_l0=l0, ct_l2_v0rule=l2,
                        events_confirmed=sum(1 for v in l0 if v), events_contradicted=sum(1 for v in l0 if v is False),
                        events_undecided=sum(1 for v in l0 if v is None)))
    ev = [x for x in res if x["n_assigned"] > 0]
    frac_c = sum(1 for x in ev if x["events_confirmed"] > 0) / max(1, len(ev))
    frac_g = sum(1 for x in ev if x["events_geom"] > 0) / max(1, len(ev))
    out["S3"] = dict(passed=frac_c <= 0.05, frac_with_confirmed_events=frac_c, frac_with_geometry_only_events=frac_g,
                     n=len(res), n_evaluable=len(ev),
                     geometry_events=sum(x["events_geom"] for x in res),
                     confirmed_l0=sum(x["events_confirmed"] for x in res),
                     contradicted_l0=sum(x["events_contradicted"] for x in res),
                     confirmed_l2_v0rule=sum(1 for x in res for v in x["ct_l2_v0rule"] if v),
                     patches=res)
    print("S3", out["S3"]["passed"], frac_c, frac_g, out["S3"]["n_evaluable"], flush=True)
    out["elapsed_s"] = time.time() - t0
    j = json.load(open(OUT)) if OUT.exists() else {}
    j.update({k: v for k, v in out.items()})
    json.dump(j, open(OUT, "w"), indent=1, default=lambda o: o.tolist() if hasattr(o, "tolist") else str(o))
    return out


if __name__ == "__main__":
    {"s4": s4, "s123": s123}[sys.argv[1]]()
