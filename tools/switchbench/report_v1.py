"""Assemble results/switchbench_natural_v1.json (protocol P1 (prereg/switchbench_v1.md)) from sanity, label, corpus, detector and
evaluation outputs, and apply the frozen rules mechanically.

While the blind review is pending (labels not STRONG), the C1 verdict is not issued; this file then
records what the review must show (the precision lower bound needed for SUPPORTED), the parts of C1 that
do not depend on precision (the FAILS branch), and everything else. Per-event coordinates and labels are
withheld from the committed JSON until the review is done (blinding); the labeled events file is written
to data/switchbench_v1/ and only its SHA-256 is committed.
Usage: python -m tools.switchbench.report_v1
"""
from __future__ import annotations

import hashlib
import json
import shutil
import time

import numpy as np

from . import corpus_v1, evaluate_v1, geom, metrics, pull

RES = geom.REPO / "vault" / "results"
V1 = geom.REPO / "data" / "switchbench_v1"
DOCTOR = "tifxyz-doctor (coherent-normal-step)"
PREREG = geom.REPO / "vault" / "prereg" / "switchbench_v1.md"
FREEZE_SHA = "821144c5c69b17a217fdbc12f4f11e7a95f423b09ff5749eef5e99b2d6bce592"


def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def wilson_needed(p_needed, n=15):
    """Smallest k of n confirmed events marked 'switch' (none 'can't tell') whose Wilson LB exceeds p_needed."""
    for k in range(n + 1):
        if metrics.wilson(k, n)[1] > p_needed:
            return k
    return None


def events_file(recs):
    """Labeled corpus file, scorer-kit compatible (tools/switchbench_kit): events[] patch, status, xyz,
    transitions[] {rc_a, rc_b}; negatives[] patch, status, axis, rc0, rc1, len_mm, xyz0, xyz1; plus scoring,
    frame, voxel_mm, patch_source and geometry_sha256 (the kit's fingerprint of the scored patches' grids,
    computed with the kit's own loader, which also checks every centre and run length)."""
    out = dict(scroll="PHercParis4", frame="level-2 voxels (x, y, z) of volume 20260411134726 (9.6 um/vx)",
               voxel_mm=0.0096,
               patch_source=dict(bucket="scrollprize/datasets", prefix="spiral/PHercParis4/unverified_patches"),
               source="HF bucket scrollprize/datasets spiral/PHercParis4 unverified_patches, seeded order 20260925, "
                      "patches 1-10,000 (v0 prefix 1-3,000 + v1 3,001-10,000)",
               labels="status = level-0 (2.4 um) CT rule of SwitchBench v1; status_v0rule = v0's 9.6 um rule",
               scoring=dict(per_patch_cap=3, match_mm=1.0, fa_dedup_mm=0.5, bootstrap=2000, seed=20260925),
               events=[], negatives=[], multi_wrap=[])
    for r in recs:
        for e in r["events"]:
            out["events"].append(dict(patch=r["patch"], subset=r["subset"], status=e["status"], status_v0rule=e["status_l2"],
                                      xyz=[round(v, 1) for v in e["xyz"]], delta_signs=e["delta_signs"],
                                      transitions=[dict(axis=m["axis"], rc_a=m["rc_a"], rc_b=m["rc_b"],
                                                        len_a_mm=round(m["len_a_mm"], 2), len_b_mm=round(m["len_b_mm"], 2))
                                                   for m in e["members"]]))
        for n in r["negatives"]:
            out["negatives"].append(dict(patch=r["patch"], subset=r["subset"], status=n["status"], axis=n["axis"],
                                         rc0=n["verts"][0], rc1=n["verts"][-1], len_mm=round(n["len_mm"], 2),
                                         xyz0=[round(v, 1) for v in n["xyz0"]], xyz1=[round(v, 1) for v in n["xyz1"]]))
        for m in r["multi_wrap"]:
            out["multi_wrap"].append(dict(patch=r["patch"], xyz=[round(v, 1) for v in m["xyz"]], delta_signs=m["delta_signs"]))
    p = V1 / "switchbench_v1_events.json"
    p.write_text(json.dumps(out, separators=(",", ":")))
    from tools.switchbench_kit import corpus as kit_corpus
    b = kit_corpus.load_benchmark(p, patches_dir=geom.DATA / "unverified_patches")
    out["geometry_sha256"] = b.geometry_sha256
    p.write_text(json.dumps(out, separators=(",", ":")))
    return p


def main(blind_review_pending=True):
    ev = json.load(open(V1 / "evaluation_v1.json"))["summary"]
    san = json.load(open(V1 / "sanity_v1.json"))
    rule = json.load(open(V1 / "ct_rule_l0.json"))
    recs = evaluate_v1.load_pooled()
    T = ev["tools"]
    # ---------------- C1
    c1 = {}
    for sk in ("pooled", "new"):
        c = T[DOCTOR][sk]["r1.0"]["capped"]
        c1[sk] = dict(hits=c["hits"], n_events=c["n_events"], n_patches=c["n_patches"], recall=c["recall"],
                      boot95=c["boot95"], wilson95=c["wilson95"])
    his = [c1[sk]["boot95"][1] for sk in ("pooled", "new")]
    los = [c1[sk]["boot95"][0] for sk in ("pooled", "new")]
    fails_branch = {sk: (c1[sk]["boot95"][0] is not None and c1[sk]["boot95"][0] > 0.85) for sk in ("pooled", "new")}
    need = max(his) / 0.60 if all(h is not None for h in his) else None
    t = rule["chosen_rates"]["test"]
    sens, fp = t["adjacent"]["rate"], max(t["two_apart"]["rate"], t["same_sheet"]["rate"])
    cc = ev["corpus"]["pooled"]
    f = cc["confirmed"] / max(1, cc["confirmed"] + cc["contradicted"])
    pi = min(1.0, max(0.0, (f - fp) / (sens - fp))) if sens > fp else None
    prec_mix = (sens * pi / f) if (pi is not None and f > 0) else None
    c1.update(
        detector=DOCTOR + ", uncapped union (API coherent_normal_step_cells mask + CLI examples), per-patch cap 3, 1 mm",
        rule="corrected upper = boot95 upper / precision lower bound; SUPPORTED if < 0.60 on pooled AND new; "
             "FAILS if boot95 lower > 0.85; else INCONCLUSIVE",
        precision_source="blind review (labels not STRONG)",
        fails_branch_met=fails_branch,
        precision_lower_bound_needed_for_supported=need,
        blind_review_switch_marks_needed_of_15=wilson_needed(need) if need is not None else None,
        ladder_mixture_precision_info_only=dict(sens_test=sens, false_pass_test=fp, pass_fraction_candidates=f,
                                                est_true_switch_fraction=pi, est_precision=prec_mix),
        verdict="PENDING BLIND REVIEW" if blind_review_pending else None)
    if not blind_review_pending:
        raise NotImplementedError("post-review C1 is computed by blind_review_score.py")
    # ---------------- C2
    modes = {"tifxyz-doctor (coherent-normal-step)": ("default", "default"),
             "tifxyz-doctor (any cue)": ("default", "default"),
             "windcheck": ("default", "windcheck [intended: patch mode, no cell floor]"),
             "windaudit": ("default", "windaudit [intended: attachment 0.45 D]"),
             "#1621-style annotation check": ("default", "default"),
             "seamcheck [secondary, added after freeze]": (None, "seamcheck [secondary, added after freeze]")}
    c2 = {}
    for tool, (dmode, imode) in modes.items():
        row = {}
        for label, name in (("default", tool if dmode else None), ("intended", tool if imode == "default" else imode)):
            if name is None:
                continue
            d = T[name]
            row[label] = dict(name=name, **{sk: dict(recall=d[sk]["r1.0"]["capped"], fa=d[sk]["r1.0"]["fa"])
                                             for sk in ("pooled", "new")})
        it = row["intended"]["pooled"]["recall"]
        row["handles_natural_switches"] = bool((it["wilson95"][0] or 0) >= 0.80 or (it["boot95"][0] or 0) >= 0.80)
        c2[tool] = row
    c2["random"] = {sk: dict(recall=T["random"][sk]["r1.0"]["capped"], fa=T["random"][sk]["r1.0"]["fa"]) for sk in ("pooled", "new")}
    M = evaluate_v1.MATCHED
    c2["random_fa_matched"] = {sk: dict(recall=T[M][sk]["r1.0"]["capped"], fa=T[M][sk]["r1.0"]["fa"]) for sk in ("pooled", "new")}
    c2["random_fa_matched"]["density_per_mm2"] = ev["random_fa_matched_density_per_mm2"]
    # ---------------- sensitivity
    sens_tab = {}
    for name in [DOCTOR, "tifxyz-doctor (any cue)", "random", evaluate_v1.MATCHED] + [k for k in T if k.startswith("tifxyz-doctor (") and k not in (DOCTOR, "tifxyz-doctor (any cue)")]:
        d = T[name]
        sens_tab[name] = {sk: {f"r{r}": dict(capped=d[sk][f"r{r}"]["capped"], uncapped=d[sk][f"r{r}"]["uncapped"],
                                             fa=d[sk][f"r{r}"]["fa"]) for r in (0.5, 1.0, 2.0)}
                          | dict(both_sides_1mm=d[sk]["both_sides_1mm_capped"],
                                 also_confirmed_by_v0_rule=d[sk]["also_confirmed_by_v0_rule_capped"])
                          for sk in ("pooled", "new", "v0_prefix")}
    # ---------------- files, disk, key
    evf = events_file(recs)
    key = V1 / "blind_key.json"
    prog = json.load(open(V1 / "corpus_progress.json")) if (V1 / "corpus_progress.json").exists() else {}
    out = dict(
        bet="SwitchBench-natural v1 (protocol P1 (prereg/switchbench_v1.md), frozen at 45934b5; prereg/switchbench_v1.md)",
        prereg=dict(file="prereg/switchbench_v1.md", sha256=sha(PREREG), sha256_matches_commitment=sha(PREREG) == FREEZE_SHA),
        post_freeze_calls="protocol P1 (prereg/switchbench_v1.md) addendum (commit 52469c7, Scout Report #8): doctor uncapped = API mask UNION CLI "
                          "examples (primary) and mask only; seamcheck secondary (C2 only); C4 source PHerc0500P2",
        v1_start_utc=open(V1 / "v1_start_utc.txt").read().strip(),
        written_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        status="PAUSED FOR BLIND REVIEW: labels not STRONG; C1 verdict waits for the authors' review" if blind_review_pending else "final",
        sanity=dict(S1=san["S1"], S2={k: v for k, v in san["S2"].items() if k != "cases"} | dict(
                        cases=[{k: v for k, v in c.items() if k in ("n_events", "at_planted_column", "delta_signs", "ct_l0", "ct_l2_v0rule", "passed", "event_dist_mm")} for c in san["S2"]["cases"]]),
                    S3={k: v for k, v in san["S3"].items() if k != "patches"},
                    S4={k: v for k, v in san["S4"].items() if k not in ("rows", "v0_primary_hits_classified")}),
        labels=dict(rule=rule["chosen"], objective=rule["objective"], grid=rule["grid"], grid_size=rule["grid_size"],
                    n_controls=rule["n_controls"], rates=rule["chosen_rates"], strong=rule["strong"],
                    strong_rule=rule["strong_rule"], strong_if_judged_on_all_ladders=rule["strong_if_judged_on_all_ladders"],
                    v0_rule_level2_same_controls=rule["v0_rule_level2"], v0_rule_level0_same_controls=rule["v0_rule_level0"],
                    frontier_on_tune=rule["frontier_on_tune"]),
        corpus=dict(counts=ev["corpus"], new_patches_processed=prog, close_utc=corpus_v1.CORPUS_CLOSE_UTC,
                    random_density_per_mm2=ev["random_density_per_mm2"]),
        C1=c1, C2=c2,
        planted_comparison_caveat=dict(
            note="Framing correction (lead, 2026-09-26; results/switchbench_explore.md, commits 039db99 / 1c479e8): "
                 "tifxyz-doctor's published 124/128 planted recall was measured on 12.5-voxel-grid traces and its score is "
                 "divided by grid step; on 20-voxel traces like ours its defaults catch the planted 8-voxel step only 6/128. "
                 "Natural recall vs 0.969 planted is not like-for-like and is not a headline. C1 is an absolute bound and is unaffected.",
            exploratory_v0_matched_spacing="EXPLORATORY (v0 data): at the threshold that catches the planted 8-voxel step 124/128 on "
                                           "20-voxel traces (ratio 0.17), natural recall 14/54 = 0.26 [0.16-0.39] at 1.9 FA/100 mm; "
                                           "all default hits are abrupt events (6/24 abrupt vs 0/30 gradual)",
            published_planted_recall=dict(doctor=124 / 128, windaudit=55 / 96, sheet_topo_bench=0.667)),
        C3=dict(uncapped_as_v0=ev["gen_avg_cost"], capped=ev["gen_avg_cost_capped"]),
        C4=c4_summary(),
        sensitivity=sens_tab,
        seamcheck_winding_patch_verdicts=ev["seamcheck_winding_verdicts"],
        doctor_patches_with_capped_cue=ev["doctor_patches_with_capped_cue"],
        blind_review=dict(triggered=True, packet="results/switchbench_natural_v1_blind_review.md",
                          answer_key="data/switchbench_v1/blind_key.json (gitignored)",
                          answer_key_sha256=sha(key) if key.exists() else None,
                          composition="15 confirmed (capped set) + 10 CT-contradicted + 5 negative runs, seeded 20260925, shuffled"),
        events_file=dict(path_after_review="results/switchbench_natural_v1_events.json",
                         withheld_until_review_at="data/switchbench_v1/switchbench_v1_events.json",
                         sha256=sha(evf), bytes=evf.stat().st_size),
        disk=dict(v1_data_gb=(pull.du(geom.DATA) + pull.du(V1)) / 2**30, free_gb=shutil.disk_usage(geom.DATA).free / 2**30),
    )
    json.dump(out, open(RES / "switchbench_v1.json", "w"), indent=1, default=float)
    return out


def c4_summary():
    """C4 (PHerc0500P2) numbers if the replication has been evaluated, else its status."""
    f = V1 / "c4_0500p2" / "evaluation.json"
    if not f.exists():
        return dict(status="PHerc0500P2 source received from the authors (Scout Report #8); replication not yet evaluated")
    e = json.load(open(f))
    keep = ("tifxyz-doctor (coherent-normal-step)", "tifxyz-doctor (any cue)", "tifxyz-doctor (cns) capped examples (v0 D10)",
            "windcheck", "windcheck [patch mode]", "seamcheck", "random")
    return dict(status="evaluated (report-only replication)", counts=e["counts"], layer_sanity=e["layer_sanity"],
                independence_dependent_pairings=sum(len(v) for v in e["independence"].values()),
                ct_controls=e["ct_controls"], constants=e["constants"], not_applicable=e["not_applicable"],
                random_density_per_mm2=e["random_density_per_mm2"],
                tools={t: e["tools"][t] for t in keep if t in e["tools"]})


def interim():
    """Checkpoint written when the blind-review packet is handed over (before detector results exist):
    sanity, label strength, corpus counts, the answer key's SHA-256 and the withheld events file's SHA-256."""
    san = json.load(open(V1 / "sanity_v1.json"))
    rule = json.load(open(V1 / "ct_rule_l0.json"))
    recs = evaluate_v1.load_pooled()
    counts = {k: evaluate_v1.corpus_counts(recs, v) for k, v in {"pooled": None, "new": "new", "v0_prefix": "v0"}.items()}
    evf = events_file(recs)
    key = V1 / "blind_key.json"
    prog = json.load(open(V1 / "corpus_progress.json")) if (V1 / "corpus_progress.json").exists() else {}
    out = dict(
        bet="SwitchBench-natural v1 (protocol P1 (prereg/switchbench_v1.md), frozen at 45934b5; prereg/switchbench_v1.md)",
        prereg=dict(file="prereg/switchbench_v1.md", sha256=sha(PREREG), sha256_matches_commitment=sha(PREREG) == FREEZE_SHA),
        v1_start_utc=open(V1 / "v1_start_utc.txt").read().strip(),
        written_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        status="CHECKPOINT: blind-review packet handed over; detectors and metrics still running; no C1 verdict (waits for the review)",
        sanity=dict(S1=san["S1"], S2={k: v for k, v in san["S2"].items() if k != "cases"},
                    S3={k: v for k, v in san["S3"].items() if k != "patches"},
                    S4={k: v for k, v in san["S4"].items() if k not in ("rows", "v0_primary_hits_classified")}),
        labels=dict(rule=rule["chosen"], objective=rule["objective"], rates=rule["chosen_rates"], strong=rule["strong"],
                    strong_rule=rule["strong_rule"], v0_rule_level2_same_controls=rule["v0_rule_level2"]),
        corpus=dict(counts=counts, new_patches_processed=prog),
        blind_review=dict(triggered=True, packet="results/switchbench_natural_v1_blind_review.md",
                          answer_key="data/switchbench_v1/blind_key.json (gitignored)", answer_key_sha256=sha(key),
                          composition="15 confirmed (capped set) + 10 CT-contradicted + 5 negative runs, seeded 20260925, shuffled"),
        events_file=dict(path_after_review="results/switchbench_natural_v1_events.json",
                         withheld_until_review_at="data/switchbench_v1/switchbench_v1_events.json",
                         sha256=sha(evf), bytes=evf.stat().st_size))
    json.dump(out, open(RES / "switchbench_v1.json", "w"), indent=1, default=float)
    return out


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "interim":
        print(json.dumps(interim()["blind_review"], indent=1))
        raise SystemExit
    o = main()
    print(json.dumps(dict(C1={k: v for k, v in o["C1"].items() if k in ("pooled", "new", "fails_branch_met",
                                                                       "precision_lower_bound_needed_for_supported",
                                                                       "blind_review_switch_marks_needed_of_15")}), indent=1, default=float))
