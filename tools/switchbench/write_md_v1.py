"""Write results/switchbench_natural_v1.md from results/switchbench_natural_v1.json (numbers only come from the JSON)."""
from __future__ import annotations

import json

from . import geom

RES = geom.REPO / "vault" / "results"
DOCTOR = "tifxyz-doctor (coherent-normal-step)"


def f3(x):
    return "n/a" if x is None else f"{x:.3f}"


def ci(c):
    return "[n/a]" if c is None or c[0] is None else f"[{c[0]:.3f}, {c[1]:.3f}]"


def rate(r):
    return f"{r['rate']:.3f} ({r['passed']}/{r['decided']}) {ci(r['ci95'])}"


def frontier_note(lab):
    fr = lab["frontier_on_tune"]
    ok = sorted(float(k) for k in fr)
    if not ok:
        return "No rule in the grid keeps both false-pass rates at or below 15% on the tuning half."
    return (f"The lowest false-pass ceiling any rule in the {lab['grid_size']}-variant grid meets on the tuning half is "
            f"{ok[0]:.0%} (adjacent pass there {fr[str(ok[0]) if str(ok[0]) in fr else [k for k in fr if float(k) == ok[0]][0]]['tune']['adjacent']:.2f}).")


def main():
    j = json.load(open(RES / "switchbench_v1.json"))
    c1, c2, lab, cor = j["C1"], j["C2"], j["labels"], j["corpus"]["counts"]
    s = j["sanity"]
    t = lab["rates"]["test"]
    P, N = c1["pooled"], c1["new"]
    L = []
    L.append("# SwitchBench-natural v1: results (paused for blind review)")
    L.append("")
    L.append(f"Bet: protocol P1 (prereg/switchbench_v1.md), frozen at 45934b5 (prereg/switchbench_v1.md, SHA-256 {j['prereg']['sha256'][:16]}..., "
             f"matches the posted commitment: {j['prereg']['sha256_matches_commitment']}). Post-freeze operational calls: {j['post_freeze_calls']}. "
             f"v1 start {j['v1_start_utc']}; this file {j['written_utc']}. $0, CPU only. No ink maps and no images anywhere: CT was read "
             "as numeric 1-D profiles only, detectors wrote numeric JSON only. Nothing was posted outside this repo. Nothing text-like was seen.")
    L.append("")
    L.append("## Plain-language summary")
    L.append("")
    L.append(f"- **Status: paused for the authors' blind review. There is no C1 verdict yet.** The frozen rule says the headline "
             "claim needs strong labels, and ours are not strong. Even at 2.4 um, the CT check that confirms a switch passes "
             f"{t['adjacent']['rate']:.0%} of true adjacent-wrap pairs, but it also passes {t['two_apart']['rate']:.0%} of two-wraps-apart "
             f"pairs and {t['same_sheet']['rate']:.0%} of same-sheet pairs (held-out human ladders). STRONG needs both false-pass "
             "rates at or below 5% and adjacent pass at or above 70%. " + frontier_note(lab) + " So the "
             "frozen plan's blind review is triggered: results/switchbench_natural_v1_blind_review.md (30 locations, about 1 hour in VC3D).")
    L.append(f"- **The corpus grew {cor['pooled']['confirmed'] / max(1, cor['v0_prefix']['confirmed']):.1f}x.** Pooled (patches 1-10,000): "
             f"{cor['pooled']['candidates']} candidates, {cor['pooled']['confirmed']} confirmed by the 2.4 um rule in "
             f"{cor['pooled']['event_patches']} patches, {cor['pooled']['negatives_confirmed']} confirmed negative runs "
             f"({cor['pooled']['neg_mm_confirmed']:.0f} mm). New patches alone: {cor['new']['confirmed']} confirmed events.")
    s3 = j["sanity"]["S3"]
    L.append(f"- **Why a blind review matters here.** On human-verified patches, where switches should be rare, the 2.4 um rule confirms "
             f"{s3['confirmed_l0']} of {s3['geometry_events']} geometry-only candidates (v0's 9.6 um rule: {s3['confirmed_l2_v0rule']}). "
             f"S3 still passes ({s3['frac_with_confirmed_events']:.1%} of verified patches, limit 5%), but false confirmations are real. "
             f"Concentration: one legacy full-size patch carries {cor['pooled']['max_events_per_patch']} confirmed events; the per-patch cap "
             "counts at most 3 of them toward recall.")
    L.append(f"- **tifxyz-doctor, uncapped, {'still misses most natural switches' if (P['recall'] or 0) < 0.5 else 'catches most natural switches'}**: {P['hits']}/{P['n_events']} = {f3(P['recall'])} "
             f"(patch-block 95% CI {ci(P['boot95'])}) pooled, per-patch cap 3. New patches alone: {N['hits']}/{N['n_events']} = {f3(N['recall'])} "
             f"{ci(N['boot95'])}. C1 is an absolute bound, so it needs no planted comparator. Do not read this against the tool's published 124/128 "
             "planted recall: that was measured on 12.5-voxel-grid traces, and the doctor divides its score by grid step, so on 20-voxel traces "
             "like ours its defaults catch the planted 8-voxel step only 6/128 (EXPLORATORY, results/switchbench_explore.md).")
    need = c1["precision_lower_bound_needed_for_supported"]
    k = c1["blind_review_switch_marks_needed_of_15"]
    L.append(f"- **What the review decides.** The FAILS branch (CI lower bound > 0.85) is already ruled out on both sets. "
             f"SUPPORTED needs the review's precision lower bound above {f3(need)}, which means at least {k} of the 15 confirmed "
             "events marked \"switch\" if none is marked \"can't tell\". Otherwise the result is INCONCLUSIVE (dataset and descriptive numbers only, with the authors' approval).")
    c4s = j["C4"]
    if "tools" in c4s:
        dd = c4s["tools"]["tifxyz-doctor (coherent-normal-step)"]; rr4 = c4s["tools"]["random"]
        L.append(f"- **C4, second sample (PHerc0500P2, report-only):** {dd['r1.0_capped']['n_events']} capped events on {c4s['counts']['in_sample']} traces. "
                 f"The doctor's union alarms catch {dd['r1.0_capped']['hits']}, at {dd['fa']['fa_per_100mm']:.0f} false alarms per 100 mm; random alarms at a similar "
                 f"false-alarm rate catch {rr4['r1.0_capped']['hits']}. Labels there are weaker; small sample; no claim either way.")
    hn = [t for t, r in c2.items() if not t.startswith("random") and r.get("handles_natural_switches")]
    L.append("- **Fair coverage (C2):** " + ("no tool reaches the 0.80 recall lower bound in its author-intended mode." if not hn
             else "tools that reach the 0.80 recall lower bound in their author-intended mode (this weakens the headline): " + ", ".join(hn) + "."))
    L.append("")
    L.append("## C1 headline test (frozen rule, quoted)")
    L.append("")
    L.append("> tifxyz-doctor natural recall on confirmed events, patch-block bootstrap 95% CI (B = 2000, seed 20260925), per-patch cap 3. "
             "**Precision-corrected upper bound** = CI upper / precision lower bound (measured if blind review ran, else the ladder mixture estimate). "
             "**SUPPORTED** if the corrected upper bound < 0.60 on the pooled corpus AND on the new patches alone. **FAILS** if the CI lower bound > 0.85. "
             "Otherwise INCONCLUSIVE: release as dataset + descriptive numbers only, with the authors' approval.")
    L.append("")
    L.append("| Set | Hits / events (patches) | Recall | Patch-block 95% CI | Wilson 95% CI | FAILS branch (lower > 0.85) |")
    L.append("|---|---|---|---|---|---|")
    for nm, d in (("Pooled (1-10,000)", P), ("New only (3,001-10,000)", N)):
        L.append(f"| {nm} | {d['hits']}/{d['n_events']} ({d['n_patches']}) | {f3(d['recall'])} | {ci(d['boot95'])} | {ci(d['wilson95'])} | "
                 f"{'met' if d['boot95'][0] is not None and d['boot95'][0] > 0.85 else 'not met'} |")
    L.append("")
    mx = c1["ladder_mixture_precision_info_only"]
    L.append(f"Precision lower bound: from the blind review (pending). SUPPORTED requires it to exceed max(CI upper) / 0.60 = {f3(need)}. "
             f"For information only (not the verdict input, because the review was triggered): the ladder mixture estimate with the "
             f"held-out ladder rates puts the precision of the confirmed set at {f3(mx['est_precision'])} (pass fraction among decided "
             f"candidates {f3(mx['pass_fraction_candidates'])}, false-pass {f3(mx['false_pass_test'])}, sensitivity {f3(mx['sens_test'])}).")
    L.append("")
    L.append("## Sanity (failure = harness bug, no verdict)")
    L.append("")
    L.append("| Check | Rule | Result |")
    L.append("|---|---|---|")
    L.append(f"| S1 | verified patch vs itself = 0 events | {'PASS' if s['S1']['passed'] else 'FAIL'}: events per patch {s['S1']['events']} (the 10 v0 patches) |")
    s2 = s["S2"]
    L.append(f"| S2 | planted one-wrap jump = exactly 1 event at the right place | {'PASS' if s2['passed'] else 'FAIL'}: {s2['n']}/{s2['n']} planted patches give exactly 1 event at the planted column, dw = +1. The 2.4 um rule confirms {s2['planted_events_confirmed_l0']} of {s2['planted_events_l0_decided']} planted events (informational; its ladder sensitivity is {t['adjacent']['rate']:.2f}) |")
    s3 = s["S3"]
    L.append(f"| S3 | labeler on verified patches: > 5% with confirmed events = broken | {'PASS' if s3['passed'] else 'FAIL'}: {s3['frac_with_confirmed_events']:.1%} of {s3['n_evaluable']} evaluable verified patches have a 2.4 um-confirmed event ({s3['confirmed_l0']} of {s3['geometry_events']} geometry-only candidates confirmed, {s3['contradicted_l0']} contradicted; v0 rule: {s3['confirmed_l2_v0rule']}). Geometry-only candidates on {s3['frac_with_geometry_only_events']:.1%} |")
    s4 = s["S4"]
    tt = s4["totals"]
    L.append(f"| S4 | uncapped doctor reproduces every v0 hit on the 69 v0 doctor patches | {'PASS' if s4['passed'] else 'FAIL'}: the pinned tool reproduces v0's stored output exactly on all {s4['n_patches']} patches; the union keeps all {tt['hits_prim_capped_v0match']} v0 hits (v0 labels) and adds {tt['hits_prim_union'] - tt['hits_prim_capped_v0match']}; false alarms {tt['fa_prim_capped']} -> {tt['fa_prim_union']} in {tt['neg_mm']:.0f} mm |")
    L.append("")
    L.append(f"**What the cap hid (S4, v0 labels and v0 patches).** The doctor's CLI hard-codes its example lists (25 per direction, 50 per cue); "
             f"{s4['patches_with_capped_emitted_cue']} of the 69 patches had a capped emitted cue, all on coherent-normal-step. Uncapped, the tool's "
             f"own coherent-cell mask plus the CLI examples find {tt['hits_prim_union']}/54 v0 events (v0 reported 6/54) and raise "
             f"{tt['fa_prim_union']} false alarms (v0: {tt['fa_prim_capped']}). Every flagged candidate edge (a wider reading, reported as sensitivity) "
             f"finds {tt['hits_prim_alledges']}/54 with {tt['fa_prim_alledges']} false alarms. All {s4['v0_primary_hits_in_mask']} v0 hits lie inside the "
             "tool's own mask. S4 first FAILED on one v0 hit; the cause was a harness artifact (see deviation V5), fixed before any v1 number was read.")
    L.append("")
    L.append("## Labels: the 2.4 um rule (human ladder controls only)")
    L.append("")
    L.append(f"Rule chosen on the tuning half of the ladder collections ({lab['objective']}): {lab['rule']}. Held-out half decides STRONG.")
    L.append("")
    L.append("| Controls | Adjacent pass | Two-apart false pass | Same-sheet false pass |")
    L.append("|---|---|---|---|")
    for sp, nm in (("tune", "2.4 um rule, tuning half"), ("test", "2.4 um rule, held-out half"), ("all", "2.4 um rule, all ladders")):
        r = lab["rates"][sp]
        L.append(f"| {nm} | {rate(r['adjacent'])} | {rate(r['two_apart'])} | {rate(r['same_sheet'])} |")
    for key, nm in (("v0_rule_level2_same_controls", "v0 rule at 9.6 um, held-out half"), ("v0_rule_level0_same_controls", "v0 rule at 2.4 um, held-out half")):
        r = lab[key]["test"]
        L.append(f"| {nm} | {rate(r['adjacent'])} | {rate(r['two_apart'])} | {rate(r['same_sheet'])} |")
    L.append("")
    L.append(f"**STRONG: {'yes' if lab['strong'] else 'no'}** (rule: {lab['strong_rule']}; judged on all ladders instead: {'yes' if lab['strong_if_judged_on_all_ladders'] else 'no'}). "
             "Best adjacent pass on the tuning half at a given false-pass ceiling: " + "; ".join(
                 f"<= {float(k):.0%}: {v['tune']['adjacent']:.2f} (held-out {v['test']['adjacent']:.2f}, false passes {v['test']['two_apart']:.2f} / {v['test']['same_sheet']:.2f})"
                 for k, v in lab["frontier_on_tune"].items()) + (" (no variant reaches both false-pass rates <= 10%)" if "0.1" not in lab["frontier_on_tune"] else "") + ".")
    L.append("")
    L.append("## Corpus")
    L.append("")
    L.append("| Item | Pooled | New (3,001-10,000) | v0 prefix (1-3,000) |")
    L.append("|---|---|---|---|")
    rows = [("In sample (>= 5% of vertices on a verified wrap)", "in_sample"), ("Candidate events (geometry)", "candidates"),
            ("**Confirmed (2.4 um rule)**", "confirmed"), ("Contradicted by CT (not scored)", "contradicted"),
            ("No CT verdict (not scored)", "unconfirmed"), ("Confirmed by v0's 9.6 um rule (comparison)", "confirmed_l2_v0rule"),
            ("Confirmed by both rules", "confirmed_both_rules"), ("Multi-wrap jumps (not scored)", "multi_wrap"),
            ("Confirmed negative runs", "negatives_confirmed"), ("Confirmed negative length (mm)", "neg_mm_confirmed"),
            ("Scored patches", "scored_patches"), ("Patches with confirmed events", "event_patches"), ("Most events in one patch", "max_events_per_patch")]
    for nm, k in rows:
        v = [cor[x][k] for x in ("pooled", "new", "v0_prefix")]
        L.append(f"| {nm} | " + " | ".join(f"{x:.0f}" if isinstance(x, float) else str(x) for x in v) + " |")
    L.append("")
    pr = j["corpus"]["new_patches_processed"]
    L.append(f"New patches processed: {pr.get('processed')} of 7,000 (seeded order 20260925, indices 3,001-10,000), finished {pr.get('finished_utc', 'n/a')}, before the corpus close {j['corpus']['close_utc']}.")
    L.append("")
    L.append("## C2 coverage (both modes; recall per-patch cap 3, 1 mm)")
    L.append("")
    L.append("| Tool | Mode | Recall pooled (hits/events) | Wilson 95% CI | Patch-block 95% CI | FA per 100 mm | Patches with a verdict | Recall new only |")
    L.append("|---|---|---|---|---|---|---|---|")
    for tool, row in c2.items():
        if tool.startswith("random"):
            continue
        for mode in ("default", "intended"):
            if mode not in row:
                continue
            if mode == "intended" and row["intended"]["name"] == row.get("default", {}).get("name"):
                continue
            d = row[mode]
            r, fa = d["pooled"]["recall"], d["pooled"]["fa"]
            rn = d["new"]["recall"]
            nm = d["name"] if mode == "intended" else tool
            L.append(f"| {nm} | {mode if not (mode == 'default' and tool.startswith(('tifxyz', '#1621'))) else 'default (= intended)'} | {f3(r['recall'])} ({r['hits']}/{r['n_events']}) | {ci(r['wilson95'])} | {ci(r['boot95'])} | "
                     f"{f3(fa['fa_per_100mm'])} ({fa['false_alarms']} in {fa['negative_mm']:.0f} mm) | {fa['patches_with_verdict']}/{fa['n_patches']} | {f3(rn['recall'])} ({rn['hits']}/{rn['n_events']}) |")
    rr = c2["random"]
    L.append(f"| random at the doctor's any-cue alarm density (frozen sensitivity) | baseline | {f3(rr['pooled']['recall']['recall'])} ({rr['pooled']['recall']['hits']}/{rr['pooled']['recall']['n_events']}) | "
             f"{ci(rr['pooled']['recall']['wilson95'])} | {ci(rr['pooled']['recall']['boot95'])} | {f3(rr['pooled']['fa']['fa_per_100mm'])} | all | "
             f"{f3(rr['new']['recall']['recall'])} |")
    h = [t for t, r in c2.items() if not t.startswith("random") and r.get("handles_natural_switches")]
    rm = c2["random_fa_matched"]
    L.append(f"| random at the C1 doctor alarms' false-alarm rate (added, see note) | baseline | {f3(rm['pooled']['recall']['recall'])} ({rm['pooled']['recall']['hits']}/{rm['pooled']['recall']['n_events']}) | "
             f"{ci(rm['pooled']['recall']['wilson95'])} | {ci(rm['pooled']['recall']['boot95'])} | {f3(rm['pooled']['fa']['fa_per_100mm'])} | all | "
             f"{f3(rm['new']['recall']['recall'])} |")
    L.append("")
    L.append("**Random baselines.** The frozen sensitivity places random alarms at the doctor's alarm *density*. That baseline raises far more false "
             "alarms than the doctor, so it is not a fair yardstick for recall. Following the authors' framing note, random is compared only at a matched "
             "false-alarm rate (second random row: density scaled so its false-alarm rate matches the C1 doctor alarms; seed [20260925, 1]).")
    L.append("")
    L.append("**Planted comparators (caveat).** The published planted recalls are 124/128 for tifxyz-doctor, 55/96 for windaudit and 0.667 for "
             "sheet-topo-bench. None was measured on traces like ours. For tifxyz-doctor the gap is known: its 124/128 used 12.5-voxel-grid traces, and its "
             "score is divided by grid step. On 20-voxel traces its defaults catch the planted 8-voxel step only 6/128. EXPLORATORY, v0 data "
             "(results/switchbench_explore.md): at the threshold that restores 124/128 on 20-voxel traces, natural recall is 14/54 = 0.26 "
             "[0.16-0.39] at 1.9 false alarms per 100 mm, and all of its default hits are abrupt events.")
    L.append("")
    L.append(f"Tools that handle natural switches (intended-mode recall lower bound >= 0.80 under either CI): {', '.join(h) if h else 'none'}. "
             f"seamcheck's companion winding check gives patch-level verdicts only (no locations), so it has no recall: " + ", ".join(f"{k} {v}" for k, v in sorted(j['seamcheck_winding_patch_verdicts'].items(), key=lambda x: -x[1])) + " patches.")
    L.append("")
    g = j["C3"]["uncapped_as_v0"]
    L.append("## C3 early warning (report only)")
    L.append("")
    L.append("| Set | gen_avg_cost AUROC (patch-block 95% CI) | Event / negative windows (patches) | Random score AUROC |")
    L.append("|---|---|---|---|")
    for sk in ("pooled", "new", "v0_prefix"):
        a = g[sk]
        if a["auroc"]:
            L.append(f"| {sk} | {f3(a['auroc']['point'])} {ci([a['auroc']['lo'], a['auroc']['hi']])} | {a['n_event_windows']} / {a['n_negative_windows']} ({a['n_patches']}) | "
                     f"{f3(a['random_score_auroc']['point'])} |")
    L.append("")
    L.append("## Sensitivity (tifxyz-doctor)")
    L.append("")
    L.append("| Alarm set | Set | r = 0.5 mm | r = 1 mm | r = 2 mm | Uncapped events (1 mm) | FA per 100 mm (1 mm) |")
    L.append("|---|---|---|---|---|---|---|")
    for name, d in j["sensitivity"].items():
        for sk in ("pooled", "new", "v0_prefix"):
            x = d[sk]
            cells = [f"{f3(x[f'r{r}']['capped']['recall'])} ({x[f'r{r}']['capped']['hits']}/{x[f'r{r}']['capped']['n_events']})" for r in (0.5, 1.0, 2.0)]
            u = x["r1.0"]["uncapped"]
            L.append(f"| {name} | {sk} | " + " | ".join(cells) + f" | {f3(u['recall'])} ({u['hits']}/{u['n_events']}) | {f3(x['r1.0']['fa']['fa_per_100mm'])} |")
    L.append("")
    d = j["sensitivity"][DOCTOR]["pooled"]
    L.append(f"Doctor, pooled, events that hold both wraps for >= 1 mm: {f3(d['both_sides_1mm']['recall'])} ({d['both_sides_1mm']['hits']}/{d['both_sides_1mm']['n_events']}); "
             f"events also confirmed by v0's 9.6 um rule: {f3(d['also_confirmed_by_v0_rule']['recall'])} ({d['also_confirmed_by_v0_rule']['hits']}/{d['also_confirmed_by_v0_rule']['n_events']}).")
    L.append("")
    L.append(tail(j))
    (RES / "switchbench_v1.md").write_text("\n".join(L))


DEVIATIONS = [
    ("V1", "Labels: constants tuned only on human ladder controls; report the ladder rates",
     "Tuned on a seeded half of the 300 ladder collections (split by collection); STRONG judged on the held-out half; tuning-half and all-ladder rates reported too",
     "A 540-variant grid scored on its own tuning data would overstate the rates; the held-out half is the stricter reading"),
    ("V2", "Labels: 2.4 um rule (no rule given)",
     "v0's adjacent-wrap rule on level-0 profiles (step = 1 level-0 voxel) plus one knob, mid_bias (a faint middle sheet also blocks a pass). Objective: most adjacent passes with both false-pass rates <= 5% on the tuning half, else v0's margin. Grid and objective committed (a9bc7e8) before the first run",
     "v0 D8 practice; the frozen text gives no rule"),
    ("V3", "Re-confirm every candidate with level-0 CT",
     "Candidate events re-confirmed at level 0 (members and profile geometry exactly as v0). Negative runs keep v0's on-layer rule at 9.6 um (<= 20 seeded runs per patch, v0 D8). Level-0 coordinates = 4 x level-2 (OME-Zarr scale metadata, no translation)",
     "The frozen text re-confirms candidates; negatives stay v0's rule as run"),
    ("V4", "tifxyz-doctor runs uncapped (raise the cap if the CLI allows, else record per-cue counts and flag capped cues)",
     "The CLI has no cap option (hard-coded). Post-freeze call (protocol P1 (prereg/switchbench_v1.md) addendum, Scout #8): primary = public API mask coherent_normal_step_cells UNION the CLI examples; mask only, the CLI examples alone (v0) and every flagged candidate edge are sensitivities. doctor_wrap.py runs the unmodified default CLI path in the tool's venv; every count is cross-checked against the tool's report, the CLI config equals AuditConfig() defaults, and per-cue counts and capped flags are recorded",
     "Cap hard-coded; the tool's own 124/128 was scored on the mask"),
    ("V5", "v0 D10: an alarm matches an event within 1 mm",
     "Events are matched against every raw alarm location; the 0.5 mm deduplication (v0: a cue band counts once) is used only for false-alarm counts and the random density",
     "S4 caught it: v0's greedy dedup replaced an alarm 0.77 mm from a v0 event by a representative 1.01 mm away once the uncapped mask added hundreds of nearby cells. Harness fix; v0's own numbers are unchanged (6/54 either way)"),
    ("V6", "Doctor any-cue alarm set (v0 D10)",
     "review_cue_mask UNION the CLI examples of every emitted cue",
     "v0's cue map filed five distortion cues under anisotropic-cells only and left nonlocal-proximity unlocalized"),
    ("V7", "windcheck at the smallest min-cells its docs allow",
     "bench/patch_audit.py audit_one: the both-diagonal engine census with no cell floor (docs/PATCH-AUDIT.md; its smallest censused patch had 164 valid cells), threads 1, default parameters; alarms = both quads of each transverse contact",
     "Its docs define no minimum for patches"),
    ("V8", "windaudit with the attachment gap widened per its docs",
     "The docs fix the patch attachment tolerance at 2.5 vx (not tuned) and document one attachment-gap setting, WIDE_ATTACHMENT_GAP=1, which v0 already used. Intended mode widens the tolerance to 0.45 D = 10.485 vx, the widest same-sheet tolerance its docs use (METHODS.md sweep {0.25, 0.35, 0.45} D; D = 23.30 vx), via a generated copy of the harness with only that constant changed",
     "Closest documented reading of 'widened'"),
    ("V9", "Detector list",
     "seamcheck (hwkim3330/seamcheck 6d6bc2d) added as SECONDARY after the freeze (Scout #8, lead call): C2 only, never C1. Its neighbour-step test is scored (every flagged step of a REVIEW/WATCH patch; SPARSE = no verdict); its winding check has patch-level verdicts only",
     "Added after freeze on Scout #8"),
    ("V10", "sheet-topo-bench via an input adapter if buildable within 1 day",
     "Not run. Its natural-data mode (corpus B) differences production meshes against a verified multi-turn banner with a surface-prediction volume; the unverified patches are sub-turn crops with no banner counterpart, and building one from verified patches is not a 1-day adapter",
     "1-day cap"),
    ("V11", "Blind review: 15 confirmed events, 10 CT-contradicted candidates, 5 negative runs",
     "Confirmed events are drawn from the capped set that counts toward recall; a negative run's location is its midpoint vertex; all 30 are described in one format (centre point, grid direction, a fixed 12-cell span shifted inward at grid edges)",
     "Precision must describe the scored set; the format hides each location's kind"),
    ("V12", "Per-patch cap 3 (seeded pick)", "One RNG (seed 20260925) over patches sorted by name; a patch's confirmed events sorted by position", "Procedure not specified"),
    ("V13", "Random alarms at the doctor's density", "Density of the doctor's any-cue union alarms (0.5 mm-deduplicated) per mm^2; v0 used the capped examples", "Uncapped alarms"),
    ("V14", "C2: 'handles natural switches' if the intended-mode recall CI lower bound >= 0.80", "Flagged if either the Wilson or the patch-block lower bound reaches 0.80", "CI type not specified; the inclusive reading errs against our headline"),
    ("V15", "Events file results/switchbench_natural_v1_events.json", "Withheld from the repo until the blind review is scored (written to data/switchbench_v1/); its SHA-256 is committed now", "It carries the labels of the 30 review locations"),
    ("V16", "S1-S3 re-run including the 2.4 um rule", "S2 passes on geometry as in v0; the 2.4 um verdict at each planted event is reported, not required", "The rule's sensitivity is below 1 by construction"),
    ("V17", "C3 as in v0", "Uncapped as v0; per-patch-capped windows reported beside it", ""),
    ("V18", "Sensitivity: random alarms at the doctor's density", "Kept as frozen, plus a second random baseline at the C1 doctor alarms' false-alarm rate; random is compared to the doctor only at matched false-alarm rate", "Lead's framing note (2026-09-26): the density-matched baseline runs at a much higher false-alarm rate"),
    ("V19", "Comparisons with published planted recall", "Never headlined; every mention carries the grid-spacing caveat and the EXPLORATORY matched-spacing numbers (results/switchbench_explore.md)", "Lead's framing note: the doctor's 124/128 was measured on 12.5-voxel traces; C1 is an absolute bound and is unaffected"),
    ("V20", "Corpus: patches 3,001-10,000", "All 7,000 processed. One legacy full-size trace (#5,072 of the seeded order, 783,586 valid vertices) was OOM-killed in the 3-worker pool and re-run alone under a hard 9 GB address-space cap with the verified-surface speed cache trimmed (a 6 GB cap ran out after the stacks were built)", "Shared-box memory; the cache does not change results"),
    ("V21", "C4: same pipeline, report-only", "PHerc0500P2 (lead's call): the 7 numbered layers are the reference surfaces (layer = wrap); label.py constants rescaled by physical size (x 2.224 for 4.317 um; grid-count lengths too), except the duplicate-merge MIN_SPACING, capped at half the 10th percentile of adjacent-layer spacing (7.6 vx) measured on the layers alone; raw grid normals (no umbilicus). CT: the Paris4 rule converted to physical units, not re-tuned; its rates on layer-derived controls reported. Negatives: v0's on-layer rule at the median layer spacing. Independence rule fixed before the check: a pairing is dependent if on-layer offsets have median < 1 vx or >= 50% within 0.5 vx. Sanity analog: each layer labeled against the other six", "No human ladders or annotations on this sample; constants must be converted to its voxel size"),
]


def tail(j):
    L = []
    L.append("## Deviations and operational choices (none silent)")
    L.append("")
    L.append("| # | Frozen text | What was done | Why |")
    L.append("|---|---|---|---|")
    for d in DEVIATIONS:
        L.append("| " + " | ".join(d) + " |")
    L.append("")
    L.append("v0 rules carried over unchanged as frozen rules: D1 (in-sample: >= 5% of vertices on a verified wrap), D3 (9.6 um frame), "
             "D4 (event runs and segment coverage), D5 (spacing trust and bilateral wrap difference), D6 (generation proxy), D8 (on-layer "
             "negative rule, 20-run CT cap), D9 (windaudit harness and #1621-style check as run), D11 (random baseline form).")
    L.append("")
    L.append("## Detectors: build and run log")
    L.append("")
    L.append("| Tool | Commit | Build | Run |")
    L.append("|---|---|---|---|")
    L.append("| tifxyz-doctor | aviad12g/tifxyz-doctor 5ca0444 | v0 venv (pip install -e .[tiff]) | doctor_wrap.py: default CLI path + API arrays (uncapped) |")
    L.append("| windcheck | joe-carr-data/windcheck 2b0fb2f | v0 (uv sync; selfcross engine built from source with clang++) | `check` (default) and patch mode (V7) |")
    L.append("| windaudit | sergeievland/windaudit aba5633 | v0 venv | patch-graph harness, default and widened tolerance (V8) |")
    L.append("| seamcheck | hwkim3330/seamcheck 6d6bc2d | own venv from requirements.txt (numpy, tifffile, imagecodecs) | seamcheck_run.py, default parameters (V9) |")
    L.append("| sheet-topo-bench | tonclap/sheet-topo-bench 9fdfeef | cloned, pure Python | **not run** (V10) |")
    L.append("| #1621-style check | ours, tools/switchbench/annot.py | n/a | every scored patch |")
    L.append("")
    L.append("All clones live in $SWITCHBENCH_EXT (default ./ext) (outside the repo). No downloaded binary was executed.")
    L.append("")
    L.append("## C4 second scroll (PHerc0500P2, report-only)")
    L.append("")
    c4 = j["C4"]
    if "counts" not in c4:
        L.append(c4["status"] + ".")
    else:
        c, ls, cc = c4["counts"], c4["layer_sanity"], c4["ct_controls"]
        L.append("Source: the authors' call on Scout Report #8. 25 GrowPatch consensus traces (`z_dbg_gen_*`) against the 7 numbered "
                 "layers -2..4 as reference surfaces (layer = wrap), 4.317 um frame, numeric CT from the 4.317 um volume. "
                 "0500P2 is an unread sample: no ink-detection file was read, no image was made, nothing text-like can arise.")
        L.append("")
        L.append(f"- Independence check: {c4['independence_dependent_pairings']} trace-layer pairings share geometry (none excluded); "
                 "on-layer offsets are a few voxels and no vertex is copied.")
        L.append(f"- Transferred 2.4 um rule on layer-derived controls (report only, no tuning): adjacent pass {f3(cc['adjacent']['rate'])} "
                 f"({cc['adjacent']['decided']}), two-apart false pass {f3(cc['two_apart']['rate'])}, same-layer false pass {f3(cc['same_layer']['rate'])}.")
        L.append(f"- Layer sanity (each layer labeled against the other six): {ls['candidates']} geometry candidates, {ls['confirmed']} confirmed, "
                 f"on {ls['in_sample']} in-sample layers.")
        L.append(f"- Corpus: {c['traces']} traces, {c['in_sample']} in sample, {c['candidates']} candidates, **{c['confirmed']} confirmed**, "
                 f"{c['contradicted']} contradicted, {c['unconfirmed']} undecided, {c['multi_wrap']} multi-layer jumps; "
                 f"{c['negatives_confirmed']} confirmed negative runs ({c['neg_mm']:.0f} mm).")
        L.append("")
        L.append("| Tool | Recall, cap 3, 1 mm (hits/events) | Wilson 95% CI | Patch-block 95% CI | FA per 100 mm |")
        L.append("|---|---|---|---|---|")
        for t, d in c4["tools"].items():
            r = d["r1.0_capped"]
            L.append(f"| {t} | {f3(r['recall'])} ({r['hits']}/{r['n_events']}) | {ci(r['wilson95'])} | {ci(r['boot95'])} | {f3(d['fa']['fa_per_100mm'])} |")
        L.append("")
        T4 = c4["tools"]
        d4, r4 = T4["tifxyz-doctor (coherent-normal-step)"], T4["random"]
        cp4 = T4.get("tifxyz-doctor (cns) capped examples (v0 D10)")
        L.append(f"**Reading.** This is a small, weak replication: {d4['r1.0_capped']['n_events']} capped events on {c['in_sample']} traces, and labels "
                 "weaker than on Paris4 (see the controls and the layer check above). The doctor's union alarms reach "
                 f"{d4['r1.0_capped']['hits']}/{d4['r1.0_capped']['n_events']}, but only by flagging these traces densely "
                 f"({d4['fa']['fa_per_100mm']:.1f} false alarms per 100 mm). Random alarms at its density run at a similar false-alarm rate "
                 f"({r4['fa']['fa_per_100mm']:.1f} per 100 mm) and catch {r4['r1.0_capped']['hits']}/{r4['r1.0_capped']['n_events']}, so on this sample the doctor "
                 "does not beat chance at matched false alarms."
                 + (f" Its capped CLI examples alone (v0's reading) catch {cp4['r1.0_capped']['hits']}/{cp4['r1.0_capped']['n_events']}." if cp4 else "")
                 + " windcheck and seamcheck stay near zero. The replication does not contradict low natural recall, but its numbers cannot carry a claim.")
        L.append("")
        L.append("Not applicable on PHerc0500P2: " + "; ".join(f"{k}: {v}" for k, v in c4["not_applicable"].items()) + ".")
        L.append("")
        L.append("Kit-compatible labeled events: results/switchbench_natural_v1_0500p2_events.json (own frame, voxel_mm 0.004317, S3 patch_source; not part of the blind review).")
    L.append("")
    L.append("## Prior art")
    L.append("")
    L.append("Not triggered on the preliminary re-check (Scout Report #8); the formal re-check is at release. Near misses to cite: "
             "tifxyz-doctor PR #2 (open draft, 2026-07-30: the frozen cue run on natural collections, 'not natural sheet-switch recall', no per-event labels) "
             "and vc-segqa (2026-09-13: one natural switch between official PHerc0139 wraps, no recall). Also growpatch-sheet-switch-detection, "
             "sheet-topo-bench (corpus B on PHercParis4: 0 confirmed real errors), windaudit, windcheck, seamcheck, vesuvius-ruled, villa#1641, Stevens pipeline9 "
             "and villa satisfaction_metrics / #1621. Wording for release: the first per-event natural-switch corpus with detector recall, "
             "not the first natural-data probe.")
    L.append("")
    L.append("## Files")
    L.append("")
    L.append("- Code (v0 modules untouched, so v0 stays reproducible): tools/switchbench/ ct0, ladder_l0, rule_l0, tune_l0, corpus_v1, confirm_l0, "
             "doctor_wrap, doctor_v1, wc_patchmode, seamcheck_run, run_windaudit_v1, detectors_v1, sanity_v1, evaluate_v1, blind_review, "
             "blind_review_score, report_v1, write_md_v1.")
    L.append("- results/switchbench_natural_v1.json (all numbers), switchbench_v1_blind_review.md (the packet, no labels).")
    L.append(f"- Answer key data/switchbench_v1/blind_key.json (gitignored), SHA-256 `{j['blind_review']['answer_key_sha256']}`.")
    L.append(f"- Labeled events file (withheld until the review, V15): data/switchbench_v1/switchbench_v1_events.json, SHA-256 `{j['events_file']['sha256']}`.")
    L.append(f"- Disk: v1 data (data/paris4 + data/switchbench_v1) {j['disk']['v1_data_gb']:.2f} GB (cap 10 GB), free {j['disk']['free_gb']:.1f} GB. "
             "CT chunks and profiles were streamed into memory; only numeric profiles were stored.")
    L.append("")
    L.append("## Where this stops / what's next")
    L.append("")
    L.append("1. **the authors:** fill in results/switchbench_natural_v1_blind_review.md (about 1 hour in VC3D) and send back the 30 answers.")
    L.append("2. **Builder:** `python -m tools.switchbench.blind_review_score answers.json` checks the key's SHA-256 against the committed value, "
             "computes the measured precision (Wilson 95% CI) and applies the frozen C1 rule. Then write the final md/json and move the events file into results.")
    L.append("3. C4 is done (report-only, above). Its events file ships now; nothing in it bears on the blind review.")
    L.append("4. Scout's formal prior-art re-check on release day; tool authors contacted the day of the prize submission.")
    L.append("")
    return "\n".join(L)


if __name__ == "__main__":
    main()
