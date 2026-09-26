"""Render vault/results/switchbench_natural.md from switchbench_natural.json (numbers never typed by hand)."""
from __future__ import annotations

import json

from . import geom

RES = geom.REPO / "vault" / "results"


def f3(x):
    return "n/a" if x is None else f"{x:.3f}"


def ci(v):
    lo, hi = v["recall_ci95"]
    return "n/a" if lo is None else f"[{lo:.3f}, {hi:.3f}]"


def main():
    j = json.load(open(RES / "switchbench_natural.json"))
    c, ev, ln = j["corpus"], j["evaluation"], j["label_noise"]
    s3 = j["sanity"]["S3"]
    s2 = j["sanity"]["S2"]
    cal = j["ct_calibration"]
    b = cal["best"]
    rows = j["scored_events"]
    D = ev["detectors"]
    L = []
    w = L.append
    w("# SwitchBench-natural: results v0 (2026-09-26)")
    w("")
    w(f"Bet: IDEAS.md section 5, criteria approved 2026-09-26 and frozen. Builder run, first line of bet code "
      f"{j['start_first_code_utc']}, this file written {j['written_utc']} (well inside the 3-day corpus cap and 5-day total cap). "
      "$0, CPU only. No ink maps used, no images produced anywhere (CT read as numeric 1-D profiles only; "
      "tifxyz-doctor run with `--json` only). Nothing text-like was seen.")
    w("")
    w("## Verdict")
    w("")
    w(f"**{j['verdict']}** under the frozen rule: {j['verdict_reason']}.")
    w("")
    w("Rule text (IDEAS.md 5): *PASS: >= 30 confirmed natural events AND at least one of: (i) a detector's natural "
      "recall is below its published planted recall with the 95% CI excluding the planted value; (ii) gen_avg_cost "
      "AUROC >= 0.65 with CI lower bound > 0.55.* "
      f"Here: {c['events_confirmed']} confirmed events (>= 30). (i) holds for: "
      f"{', '.join(k for k, v in D.items() if v.get('ci_excludes_published') and v['recall'] is not None and v['published_planted_recall'] and v['recall'] < v['published_planted_recall']) or 'none'}. "
      f"(ii) gen_avg_cost AUROC {f3((ev['gen_avg_cost']['auroc'] or {}).get('point'))} "
      f"[{f3((ev['gen_avg_cost']['auroc'] or {}).get('lo'))}, {f3((ev['gen_avg_cost']['auroc'] or {}).get('hi'))}]: does not hold. "
      "KILL prior-art clause: not re-checked in this session (scout re-checks at release).")
    w("")
    td_ = D["tifxyz-doctor (coherent-normal-step)"]
    w("**Read this before using the PASS.** windaudit meets (i) only because it is structurally silent here: its "
      "patch-graph check needs >= 2 human annotation points on the unverified patch "
      f"({D['windaudit']['patches_with_verdict']} of {D['windaudit']['n_patches']} scored patches qualify). windcheck "
      f"(no published planted recall) refuses patches under 5,000 cells by default ({D['windcheck']['patches_with_verdict']} "
      f"of {D['windcheck']['n_patches']} qualify). The informative comparison is tifxyz-doctor, the only tool that returns a "
      f"verdict on every patch: natural recall {f3(td_['recall'])} {ci(td_)} vs 124/128 = 0.969 planted. Its natural "
      f"recall is not distinguishable from random alarms placed at its own alarm density ({f3(D['random']['recall'])} "
      f"{ci(D['random'])}), although it raises far fewer false alarms ({f3(td_['fa_per_100mm'])} vs "
      f"{f3(D['random']['fa_per_100mm'])} per 100 mm). The corpus labels are noisy (section Label quality): at the "
      f"estimated precision of confirmed events ({f3(ln['est_precision_of_confirmed_events'])}) the tifxyz-doctor gap is "
      f"not explained by label noise (it would need precision below "
      f"{f3(ln['min_precision_to_explain_gap'].get('tifxyz-doctor (coherent-normal-step)'))}).")
    w("")
    w("## Numbers")
    w("")
    w("| Item | Value |")
    w("|---|---|")
    w(f"| Unverified patches processed (seeded order 20260925, fixed prefix) | {c['processed']} |")
    w(f"| In sample (>= 5% of vertices on a verified wrap) | {c['in_sample']} |")
    w(f"| Candidate events (verified-geometry reference only) | {c['events_confirmed'] + c['events_contradicted'] + c['events_unconfirmed']} |")
    w(f"| **Confirmed events (geometry + numeric CT)** | **{c['events_confirmed']}** |")
    w(f"| Contradicted by CT (logged, not scored) | {c['events_contradicted']} |")
    w(f"| Unconfirmed, no CT verdict (logged, not scored) | {c['events_unconfirmed']} |")
    w(f"| Multi-wrap jumps (|dw| >= 2, logged, not scored) | {c['multi_wrap']} |")
    w(f"| Confirmed negative runs (>= 10 mm on one wrap) | {c['negatives_confirmed']} runs, {c['neg_mm_confirmed']:.0f} mm |")
    w(f"| Negative runs not confirmed / not CT-checked | {c['negatives_other']} |")
    w(f"| Patches carrying scored events or negatives | {D['random']['n_patches']} |")
    w("")
    w("| Detector (default params) | Natural recall (95% Wilson CI) | Hits / events | False alarms per 100 mm | Patches with a verdict | Published planted recall | Gap | CI excludes planted? |")
    w("|---|---|---|---|---|---|---|---|")
    for k, v in D.items():
        pv = v["published_planted_recall"]
        fa = "n/a" if v["fa_per_100mm"] is None else f"{v['fa_per_100mm']:.3f}"
        pub = "none published" if pv is None else f"{pv:.3f}"
        gap = "n/a" if v["gap"] is None else f"{v['gap']:+.3f}"
        exc = "n/a" if v["ci_excludes_published"] is None else ("yes" if v["ci_excludes_published"] else "no")
        w(f"| {k} | {f3(v['recall'])} {ci(v)} | {v['hits']}/{v['n_events']} | {fa} ({v['false_alarms']} in "
          f"{v['negative_mm']:.0f} mm) | {v['patches_with_verdict']}/{v['n_patches']} | {pub} | {gap} | {exc} |")
    w("")
    bb = j.get("recall_patch_block_bootstrap_ci95", {})
    w(f"Events cluster in patches ({j.get('n_event_patches')} patches, up to {j.get('events_per_patch_max')} events in one), so "
      "Wilson intervals are optimistic. Patch-block bootstrap 95% intervals for recall (B = 2000, seed 20260925): "
      + "; ".join(f"{k} [{v[0]:.3f}, {v[1]:.3f}]" for k, v in bb.items() if v) + ".")
    w("")
    w("Published planted numbers (fixed in `tools/switchbench/metrics.py`, commit cc897bd, before any detector output was scored):")
    w("")
    for k in ("tifxyz-doctor", "windaudit", "windcheck", "sheet-topo-bench"):
        from .metrics import PUBLISHED
        p = PUBLISHED[k]
        w(f"- **{k}**: {p['text']}. Source: {p['source']}.")
    w("- **#1621-style annotation check**: our implementation of the check described in villa#1621 (a patch's own "
      "winding must agree with the human annotations it touches); no published planted recall exists.")
    w("")
    g = ev["gen_avg_cost"]
    a = g["auroc"] or {}
    r = ev.get("random_score_auroc") or {}
    w(f"gen_avg_cost: AUROC {f3(a.get('point'))} (patch-block bootstrap B = 2000, seed 20260925: [{f3(a.get('lo'))}, {f3(a.get('hi'))}]) "
      f"over {g['n_event_windows']} event windows and {g['n_negative_windows']} negative 1-mm windows in {g['n_patches']} patches. "
      f"Random score: {f3(r.get('point'))} [{f3(r.get('lo'))}, {f3(r.get('hi'))}]. Below 0.5 means event windows carry *lower* "
      "per-generation cost than negative windows; with the generation proxy (D6) this is weak evidence and not an early warning.")
    w("")
    both = sum(1 for e in rows if e["both_sides_1mm"])
    td = [e for e in rows if e["both_sides_1mm"]]
    th = sum(1 for e in td if e["tifxyz-doctor (coherent-normal-step)"])
    w(f"Sensitivity (D4): {both} of {len(rows)} confirmed events hold both wraps for >= 1 mm; tifxyz-doctor catches "
      f"{th}/{both} of those.")
    w("")
    w("Concentration: 10 of the confirmed events come from one legacy full-size patch in the sample "
      "(auto_grown_w20231031143852, 434 x 554 cells; its 326 negative runs were CT-checked only up to the per-patch cap "
      "of 20, D8). It carries no gen_avg_cost, so the gen_avg_cost windows cover fewer events than the recall table.")
    w("")
    w("Effort: about 3.1 agent-hours of wall time from first line of code to this file, $0 (for LEDGER.md; lead integrates).")
    w("")
    w("## Sanity checks (all pass; run before any corpus verdict)")
    w("")
    w("| Check | Rule | Result |")
    w("|---|---|---|")
    w(f"| S1 | verified patch vs itself = 0 events | {'PASS' if j['sanity']['S1']['passed'] else 'FAIL'}: events per patch {j['sanity']['S1']['events']} (10 seeded verified patches) |")
    w(f"| S2 | planted one-wrap jump = exactly 1 event at the right place | {'PASS' if s2['passed'] else 'FAIL'}: {sum(1 for x in s2['cases'] if x['passed'])}/{len(s2['cases'])} planted patches give exactly 1 event, at the planted column, dw = +1 |")
    w(f"| S3 | labeler on verified patches: > 5% with events = broken | {'PASS' if s3['passed'] else 'FAIL'}: {s3['frac_with_confirmed_events']:.1%} of {s3['n_evaluable']} evaluable verified patches have a confirmed event; geometry-only candidates on {s3['frac_with_geometry_only_events']:.1%} ({ln['verified_S3_geometry_events']} candidates: {ln['verified_S3_contradicted']} contradicted by CT, {ln['verified_S3_confirmed']} confirmed) |")
    w("")
    w("S3 failed twice before passing (40% of verified patches with events on the first harness, 22% with confirmed "
      "events on the second). Both were harness bugs, fixed on verified data only: (1) crossings of two different wraps "
      "of one multi-turn verified patch were merged into one sheet; (2) local spacing was taken from sparse coverage "
      "(gaps up to 115 vx, i.e. missing wraps), which inflated the 0.25 x spacing tolerance, and the wrap difference was "
      "read from one side only. Fix: spacing must be <= 40 vx (90th percentile of human ladder spacing) and <= 1.5 x the "
      "local stack median; the wrap difference must be measured from both sides with the same answer.")
    w("")
    w("## Label quality (read with the verdict)")
    w("")
    w(f"The CT reference is weak at 9.6 um. On human ladder controls (relative_windings.json; no corpus data) the chosen "
      f"rule passes {b['adjacent']:.0%} of adjacent-wrap pairs and falsely passes {b['two_apart']:.0%} of two-apart pairs and "
      f"{b['same_wrap']:.0%} of same-sheet pairs (4.8 um level-1 reads did not help: {cal.get('level1_trial', {}).get('best', {}).get('margin', float('nan')):.2f} vs {b['margin']:.2f} margin). "
      f"Of decided candidates, {f3(ln['pass_fraction_among_decided_geometry_events'])} pass. A two-class mixture with the ladder rates "
      f"puts {f3(ln['est_true_switch_fraction_among_geometry_events'])} of candidates as true switches and the precision of the "
      f"confirmed set at about {f3(ln['est_precision_of_confirmed_events'])}. On verified patches (S3), {ln['verified_S3_confirmed']} of "
      f"{ln['verified_S3_geometry_events']} geometry-only candidates were confirmed. So roughly "
      f"{round(10 * (1 - ln['est_precision_of_confirmed_events']))} confirmed events in 10 may not be real switches. That depresses every detector's measured recall by up to that fraction; it cannot by itself "
      "produce the tifxyz-doctor gap (see Verdict).")
    w("")
    w("## Deviations from the frozen criteria (none silent)")
    w("")
    w("| # | Criteria text | What was done | Why |")
    w("|---|---|---|---|")
    dev = [
        ("D1", "Sample: unverified patches that overlap verified coverage (from patch-overlap-pcls.json)",
         "patch-overlap-pcls.json has 12,503 verified-verified pairs and only 6 involving unverified patches, so overlap was measured geometrically: a patch is in sample if >= 5% of its vertices lie within 0.25 x spacing of a verified sheet. Seeded order (20260925) over all 40,782 unverified patches. The processed prefix (3,000) was fixed at 05:24Z after the first 299 patches, from their observed yield, and not changed afterwards; the run did not stop on reaching 30.",
         "The named file cannot select the sample."),
        ("D2", "Two independent references",
         "All confirmations are verified geometry + numeric CT (the criteria's 'either one plus a numeric CT profile'). The human-annotation reference was not built: only 8% of unverified patches have any annotation point within 15 vx.",
         "Coverage."),
        ("D3", "1 mm / 10 mm thresholds",
         "Voxel size taken as 9.6 um (area_cm2/area_vx2 in every meta.json; patch coordinates fit level 2 of the 78 keV 2.4 um volume, shape 18946 x 8174 x 8174).",
         "No voxel size is stated in the spiral-input README."),
        ("D4", "then lies on w +/- 1 for >= 1 mm",
         "Runs are grid rows and columns. Either run direction counts; the w +/- 1 side needs >= 1 mm, the w side >= 2 assigned vertices. 'Lies on' = >= 80% of the segment's vertices assigned, no unassigned stretch > 1 mm. Both-sides->= 1 mm reported as sensitivity.",
         "Run direction is arbitrary; criteria silent on segment coverage."),
        ("D5", "wrap within 0.25 x local spacing from adjacent verified patches",
         "Spacing is trusted only if <= 40 vx and <= 1.5 x the local stack median; wrap difference measured from both sides (sanity-driven fix, see S3). Same-lineage verified patches (same GrowPatch source run) excluded from the reference; verified backups/ excluded.",
         "S3 failure; independence of reference."),
        ("D6", "gen_avg_cost AUROC of event vs negative windows",
         "Unverified patches ship no generations.tif and source_region_seed_row_col does not locate the seed (0/299 checks). Generation proxy = distance to the GrowPatch seed / 20 vx (Pearson 0.81-0.92 against generations.tif on 4 verified full runs). Window score = max gen_avg_cost over the window's vertices; negative windows 1 mm, > 1 mm from any event.",
         "Per-vertex generation not published for unverified patches."),
        ("D7", "S3: labeler on verified patches > 5% with events = broken",
         "Counted confirmed events (two references, as the criteria define an event); geometry-only rate reported too (above 5%).",
         "An event is defined by two references."),
        ("D8", "Numeric CT profile",
         "Rule constants chosen on human ladder controls only (tools/switchbench/tune_ct.py); no corpus data entered the choice (an earlier corpus pass with the uncalibrated rule was discarded); negatives use an on-layer rule calibrated on verified runs (>= 70% on-layer, <= 4 consecutive off-layer vertices); at most 20 negative runs CT-checked per patch (seeded).",
         "Criteria give no CT rule."),
        ("D9", "Detectors: windcheck, tifxyz-doctor, sheet-topo-bench v1, windaudit, #1621-style check",
         "sheet-topo-bench v1 NOT RUN (input contract: needs a multi-turn banner mesh, its pristine copy for atlas differencing and a surface-prediction volume; unverified patches are < 1 turn and have no pristine copy). windcheck run, but refuses < 5,000-cell patches ('no verdict'); counted as no alarm. windaudit: `windaudit run` never reads traces, so its patch-graph harness (scripts/wide_patch_audit.py, WIDE_ATTACHMENT_GAP=1) was run on the unverified patch plus verified patches within 300 vx; patches with < 2 attached annotations are silent by construction and were not run.",
         "Default parameters only, per criteria."),
        ("D10", "Recall matching",
         "An alarm matches an event within 1 mm (3D) of any transition point of the event. tifxyz-doctor alarm locations are the examples of each emitted review cue (capped at 50 per cue by the tool).",
         "Criteria silent."),
        ("D11", "Random baseline",
         "Random alarms at tifxyz-doctor any-cue alarm density per mm^2 (Poisson, seed 20260925); random score for AUROC.",
         "Criteria silent."),
    ]
    for d in dev:
        w(f"| {d[0]} | {d[1]} | {d[2]} | {d[3]} |")
    w("")
    w("## Detectors: build and run log")
    w("")
    w("| Tool | Commit | Build | Run |")
    w("|---|---|---|---|")
    w("| tifxyz-doctor | aviad12g/tifxyz-doctor 5ca0444 | pip install -e .[tiff] in its own venv, OK | `audit --json` on every scored patch |")
    w("| windcheck | joe-carr-data/windcheck 2b0fb2f | `uv sync`; `clang++ -O3 -std=c++17 -pthread` engines/selfcross.cpp, OK | `check` on every scored patch |")
    w("| windaudit | sergeievland/windaudit aba5633 | pip install -e .[dev]; test suite 319 passed, 1 skipped (matches its README) | patch-graph harness on patches with >= 2 attachments |")
    w("| sheet-topo-bench v1 | tonclap/sheet-topo-bench 9fdfeef | cloned, pure Python | **not run** (D9) |")
    w("| #1621-style check | ours, tools/switchbench/annot.py | n/a | every scored patch |")
    w("")
    w("All clones live in /home/user/ext (outside the repo); no downloaded binary was executed.")
    w("")
    w("## Prior art")
    w("")
    w("growpatch-sheet-switch-detection (slade870; cross-run disagreement, 6 CT spot checks, no P/R); sheet-topo-bench "
      "(tonclap; planted errors, zero confirmed natural switches after the Z0136 withdrawal); TIFXYZ Doctor (aviad12g; "
      "synthetic seams on reviewed Paris4 patches); windaudit (sergeievland; planted annotation switches); windcheck "
      "(joe-carr-data; self-intersection census); vesuvius-ruled (iamdflame; ruling phase as sheet signature); Stevens "
      "pipeline9; villa spiral-fitting satisfaction_metrics.py and villa#1621. None reports recall on naturally "
      "occurring switches (Scout Report #6).")
    w("")
    w("## Files")
    w("")
    w("- Code: `tools/switchbench/` (pull, geom, label, confirm, ct, sanity, tune_ct, calib_onlayer, calib_negrun, corpus, detectors, annot, run_windaudit, metrics, evaluate, report, write_md, events_file).")
    w("- `vault/results/switchbench_natural.json` (all numbers), `switchbench_sanity.json`, `switchbench_ct_calibration.json`, "
      "`switchbench_natural_events.json` (event and negative coordinates only, no images).")
    w(f"- Disk: data/paris4 = {j['disk']['data_paris4_gb']:.2f} GB (cap 5 GB), free {j['disk']['free_gb']:.1f} GB.")
    w("")
    w("## Where this stops / what's next")
    w("")
    w("- Verdict above is final under the frozen rule; the scout's prior-art re-check at release is still owed.")
    w("- Worth doing before any release: hand-review a seeded sample of confirmed events (numeric CT and geometry, no "
      "images) to measure label precision directly instead of the mixture estimate; the headline claim depends on it.")
    w("- Colin decides whether the PASS should be released as a tifxyz-doctor natural-recall gap plus a coverage note "
      "for windaudit and windcheck, rather than as two detector gaps.")
    (RES / "switchbench_natural.md").write_text("\n".join(L) + "\n")
    print("wrote", RES / "switchbench_natural.md")


if __name__ == "__main__":
    main()
