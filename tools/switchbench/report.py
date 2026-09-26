"""Assemble vault/results/switchbench_natural.json from sanity, calibration, corpus and evaluation outputs,
and apply the frozen PASS / KILL / INCONCLUSIVE rule mechanically."""
from __future__ import annotations

import json
import shutil
import time

from . import corpus, geom

RES = geom.REPO / "vault" / "results"


def du(p):
    return sum(f.stat().st_size for f in p.rglob("*") if f.is_file())


def verdict(n_conf, ev):
    run = {k: v for k, v in ev["detectors"].items() if k not in ("random", "tifxyz-doctor (any cue)")}
    cond_i = [k for k, v in run.items() if v["published_planted_recall"] is not None and v["recall"] is not None
              and v["recall"] < v["published_planted_recall"] and v["ci_excludes_published"]]
    g = (ev.get("gen_avg_cost") or {}).get("auroc") or {}
    cond_ii = bool(g.get("point") is not None and g["point"] >= 0.65 and g.get("lo") is not None and g["lo"] > 0.55)
    all_high = all(v["recall_ci95"][0] is not None and v["recall_ci95"][0] >= 0.90 for v in run.values()) if run else False
    if n_conf < 30:
        return "KILL", f"fewer than 30 confirmed natural events ({n_conf})", cond_i, cond_ii
    if all_high:
        return "KILL", "every run detector has natural recall CI lower bound >= 0.90", cond_i, cond_ii
    if cond_i or cond_ii:
        why = []
        if cond_i:
            why.append("(i) natural recall below published planted recall with CI excluding it: " + ", ".join(cond_i))
        if cond_ii:
            why.append("(ii) gen_avg_cost AUROC >= 0.65 with CI lower bound > 0.55")
        return "PASS", "; ".join(why), cond_i, cond_ii
    return "INCONCLUSIVE", "30+ events but neither (i) nor (ii) holds", cond_i, cond_ii


def main():
    sanity = json.load(open(RES / "switchbench_sanity.json"))
    calib = json.load(open(RES / "switchbench_ct_calibration.json"))
    ev = json.load(open(geom.DATA / "evaluation.json"))
    summ = corpus.summary()
    v, why, ci, cii = verdict(summ["events_confirmed"], ev)
    out = dict(
        bet="SwitchBench-natural (IDEAS.md section 5, criteria approved 2026-09-26)",
        start_first_code_utc=corpus.T_START, written_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        verdict=v, verdict_reason=why, prior_art_recheck="not re-checked in this session (scout re-checks at release)",
        corpus=summ,
        sanity=dict(S1=dict(passed=sanity["S1"]["passed"], events=[x["events"] for x in sanity["S1"]["patches"]]),
                    S2=dict(passed=sanity["S2"]["passed"], cases=sanity["S2"]["cases"]),
                    S3={k: v2 for k, v2 in sanity["S3"].items() if k != "patches"}),
        ct_calibration=calib,
        evaluation={k: v2 for k, v2 in ev.items() if k != "events"},
        scored_events=ev.get("events"),
        disk=dict(data_paris4_gb=du(geom.DATA) / 2**30, free_gb=shutil.disk_usage(geom.DATA).free / 2**30),
    )
    # label-noise bound: CT rule rates on human ladder controls (tune_ct best rule)
    b = calib["best"]
    sens, fp = b["adjacent"], max(b["two_apart"], b["same_wrap"])
    dec = summ["events_confirmed"] + summ["events_contradicted"]
    f = summ["events_confirmed"] / dec if dec else None
    pi = min(1.0, max(0.0, (f - fp) / (sens - fp))) if f is not None else None
    prec = (sens * pi / f) if (f and pi is not None) else None
    s3 = sanity["S3"]["patches"]
    out["label_noise"] = dict(
        ct_sensitivity_ladder=sens, ct_false_pass_ladder=fp, pass_fraction_among_decided_geometry_events=f,
        est_true_switch_fraction_among_geometry_events=pi, est_precision_of_confirmed_events=prec,
        verified_S3_geometry_events=sum(x["events_geom"] for x in s3),
        verified_S3_confirmed=sum(x["events_confirmed"] for x in s3),
        verified_S3_contradicted=sum(x["events_contradicted"] for x in s3),
        min_precision_to_explain_gap={k: (v["recall_ci95"][1] / v["published_planted_recall"])
                                      for k, v in ev["detectors"].items()
                                      if v.get("published_planted_recall") and v["recall_ci95"][1] is not None})
    # recall with a patch-block bootstrap (events cluster in patches; Wilson assumes independence)
    import numpy as np
    rows = ev.get("events") or []
    pats = sorted({r["patch"] for r in rows})
    rng = np.random.default_rng(20260925)
    boot = {}
    for t in ev["detectors"]:
        by = {p: [r[t] for r in rows if r["patch"] == p] for p in pats}
        vals = []
        for _ in range(2000):
            pick = rng.choice(len(pats), len(pats), replace=True)
            h = [x for i in pick for x in by[pats[i]]]
            if h:
                vals.append(sum(h) / len(h))
        boot[t] = [float(np.percentile(vals, 2.5)), float(np.percentile(vals, 97.5))] if vals else None
    out["recall_patch_block_bootstrap_ci95"] = boot
    out["events_per_patch_max"] = max((sum(1 for r in rows if r["patch"] == p) for p in pats), default=0)
    out["n_event_patches"] = len(pats)
    json.dump(out, open(RES / "switchbench_natural.json", "w"), indent=1, default=float)
    print(v, why)
    return out


if __name__ == "__main__":
    main()
