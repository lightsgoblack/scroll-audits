# SwitchBench-natural: results v0 (2026-09-26)

Bet: protocol A (prereg/switchbench_natural.md), criteria approved 2026-09-26 and frozen. Builder run, first line of bet code 2026-09-26T03:47:00Z, this file written 2026-09-26T06:44:25Z (well inside the 3-day corpus cap and 5-day total cap). $0, CPU only. No ink maps used, no images produced anywhere (CT read as numeric 1-D profiles only; tifxyz-doctor run with `--json` only). Nothing text-like was seen.

## Verdict

**PASS** under the frozen rule: (i) natural recall below published planted recall with CI excluding it: tifxyz-doctor (coherent-normal-step), windaudit.

Rule text (protocol A (prereg/switchbench_natural.md)): *PASS: >= 30 confirmed natural events AND at least one of: (i) a detector's natural recall is below its published planted recall with the 95% CI excluding the planted value; (ii) gen_avg_cost AUROC >= 0.65 with CI lower bound > 0.55.* Here: 54 confirmed events (>= 30). (i) holds for: tifxyz-doctor (coherent-normal-step), windaudit. (ii) gen_avg_cost AUROC 0.322 [0.160, 0.505]: does not hold. KILL prior-art clause: not re-checked in this session (scout re-checks at release).

**Read this before using the PASS.** windaudit meets (i) only because it is structurally silent here: its patch-graph check needs >= 2 human annotation points on the unverified patch (7 of 67 scored patches qualify). windcheck (no published planted recall) refuses patches under 5,000 cells by default (13 of 67 qualify). The informative comparison is tifxyz-doctor, the only tool that returns a verdict on every patch: natural recall 0.111 [0.052, 0.222] vs 124/128 = 0.969 planted. Its natural recall is not distinguishable from random alarms placed at its own alarm density (0.093 [0.040, 0.199]), although it raises far fewer false alarms (0.063 vs 1.038 per 100 mm). The corpus labels are noisy (section Label quality): at the estimated precision of confirmed events (0.696) the tifxyz-doctor gap is not explained by label noise (it would need precision below 0.229).

## Numbers

| Item | Value |
|---|---|
| Unverified patches processed (seeded order 20260925, fixed prefix) | 3000 |
| In sample (>= 5% of vertices on a verified wrap) | 803 |
| Candidate events (verified-geometry reference only) | 184 |
| **Confirmed events (geometry + numeric CT)** | **54** |
| Contradicted by CT (logged, not scored) | 115 |
| Unconfirmed, no CT verdict (logged, not scored) | 15 |
| Multi-wrap jumps (|dw| >= 2, logged, not scored) | 7 |
| Confirmed negative runs (>= 10 mm on one wrap) | 594 runs, 7896 mm |
| Negative runs not confirmed / not CT-checked | 703 |
| Patches carrying scored events or negatives | 67 |

| Detector (default params) | Natural recall (95% Wilson CI) | Hits / events | False alarms per 100 mm | Patches with a verdict | Published planted recall | Gap | CI excludes planted? |
|---|---|---|---|---|---|---|---|
| tifxyz-doctor (coherent-normal-step) | 0.111 [0.052, 0.222] | 6/54 | 0.063 (5 in 7896 mm) | 67/67 | 0.969 | -0.858 | yes |
| tifxyz-doctor (any cue) | 0.111 [0.052, 0.222] | 6/54 | 0.063 (5 in 7896 mm) | 67/67 | none published | n/a | n/a |
| windcheck | 0.000 [0.000, 0.066] | 0/54 | 0.000 (0 in 7896 mm) | 13/67 | none published | n/a | n/a |
| windaudit | 0.000 [0.000, 0.066] | 0/54 | 0.000 (0 in 7896 mm) | 7/67 | 0.573 | -0.573 | yes |
| #1621-style annotation check | 0.000 [0.000, 0.066] | 0/54 | 0.000 (0 in 7896 mm) | 3/67 | none published | n/a | n/a |
| random | 0.093 [0.040, 0.199] | 5/54 | 1.038 (82 in 7896 mm) | 67/67 | none published | n/a | n/a |

Events cluster in patches (39 patches, up to 10 events in one), so Wilson intervals are optimistic. Patch-block bootstrap 95% intervals for recall (B = 2000, seed 20260925): tifxyz-doctor (coherent-normal-step) [0.024, 0.189]; tifxyz-doctor (any cue) [0.038, 0.191]; windcheck [0.000, 0.000]; windaudit [0.000, 0.000]; #1621-style annotation check [0.000, 0.000]; random [0.022, 0.161].

Published planted numbers (fixed in `tools/switchbench/metrics.py`, commit cc897bd, before any detector output was scored):

- **tifxyz-doctor**: 124/128 abrupt 8-voxel normal-offset proxies (sealed holdout). Source: https://github.com/aviad12g/tifxyz-doctor/blob/main/docs/reviewed-same-wrap-benchmark.md.
- **windaudit**: 55/96 planted sheet switches raise an alarm (annotation corpus). Source: https://github.com/sergeievland/windaudit/blob/main/README.md (sec. 4).
- **windcheck**: none published for the released self-crossing census. Source: https://github.com/joe-carr-data/windcheck/blob/main/docs/HISTORY.md (sec. 3.4: planted-defect precision/recall belong to the retired proximity-era detector and are not release claims).
- **sheet-topo-bench**: frozen v1, switch family S, recall@N 0.667 [0.48-0.86] on held-out A (Paris 4 bands >= 100). Source: https://github.com/tonclap/sheet-topo-bench/blob/main/pipeline/HELDOUT_RESULTS.md.
- **#1621-style annotation check**: our implementation of the check described in villa#1621 (a patch's own winding must agree with the human annotations it touches); no published planted recall exists.

gen_avg_cost: AUROC 0.322 (patch-block bootstrap B = 2000, seed 20260925: [0.160, 0.505]) over 38 event windows and 7354 negative 1-mm windows in 57 patches. Random score: 0.481 [0.393, 0.557]. Below 0.5 means event windows carry *lower* per-generation cost than negative windows; with the generation proxy (D6) this is weak evidence and not an early warning.

Sensitivity (D4): 19 of 54 confirmed events hold both wraps for >= 1 mm; tifxyz-doctor catches 3/19 of those.

Concentration: 10 of the confirmed events come from one legacy full-size patch in the sample (auto_grown_w20231031143852, 434 x 554 cells; its 326 negative runs were CT-checked only up to the per-patch cap of 20, D8). It carries no gen_avg_cost, so the gen_avg_cost windows cover fewer events than the recall table.

Effort: about 3.1 agent-hours of wall time from first line of code to this file, $0.

## Sanity checks (all pass; run before any corpus verdict)

| Check | Rule | Result |
|---|---|---|
| S1 | verified patch vs itself = 0 events | PASS: events per patch [0, 0, 0, 0, 0, 0, 0, 0, 0, 0] (10 seeded verified patches) |
| S2 | planted one-wrap jump = exactly 1 event at the right place | PASS: 5/5 planted patches give exactly 1 event, at the planted column, dw = +1 |
| S3 | labeler on verified patches: > 5% with events = broken | PASS: 0.0% of 83 evaluable verified patches have a confirmed event; geometry-only candidates on 10.8% (9 candidates: 8 contradicted by CT, 0 confirmed) |

S3 failed twice before passing (40% of verified patches with events on the first harness, 22% with confirmed events on the second). Both were harness bugs, fixed on verified data only: (1) crossings of two different wraps of one multi-turn verified patch were merged into one sheet; (2) local spacing was taken from sparse coverage (gaps up to 115 vx, i.e. missing wraps), which inflated the 0.25 x spacing tolerance, and the wrap difference was read from one side only. Fix: spacing must be <= 40 vx (90th percentile of human ladder spacing) and <= 1.5 x the local stack median; the wrap difference must be measured from both sides with the same answer.

## Label quality (read with the verdict)

The CT reference is weak at 9.6 um. On human ladder controls (relative_windings.json; no corpus data) the chosen rule passes 58% of adjacent-wrap pairs and falsely passes 16% of two-apart pairs and 15% of same-sheet pairs (4.8 um level-1 reads did not help: 0.40 vs 0.42 margin). Of decided candidates, 0.320 pass. A two-class mixture with the ladder rates puts 0.384 of candidates as true switches and the precision of the confirmed set at about 0.696. On verified patches (S3), 0 of 9 geometry-only candidates were confirmed. So roughly 3 confirmed events in 10 may not be real switches. That depresses every detector's measured recall by up to that fraction; it cannot by itself produce the tifxyz-doctor gap (see Verdict).

## Deviations from the frozen criteria (none silent)

| # | Criteria text | What was done | Why |
|---|---|---|---|
| D1 | Sample: unverified patches that overlap verified coverage (from patch-overlap-pcls.json) | patch-overlap-pcls.json has 12,503 verified-verified pairs and only 6 involving unverified patches, so overlap was measured geometrically: a patch is in sample if >= 5% of its vertices lie within 0.25 x spacing of a verified sheet. Seeded order (20260925) over all 40,782 unverified patches. The processed prefix (3,000) was fixed at 05:24Z after the first 299 patches, from their observed yield, and not changed afterwards; the run did not stop on reaching 30. | The named file cannot select the sample. |
| D2 | Two independent references | All confirmations are verified geometry + numeric CT (the criteria's 'either one plus a numeric CT profile'). The human-annotation reference was not built: only 8% of unverified patches have any annotation point within 15 vx. | Coverage. |
| D3 | 1 mm / 10 mm thresholds | Voxel size taken as 9.6 um (area_cm2/area_vx2 in every meta.json; patch coordinates fit level 2 of the 78 keV 2.4 um volume, shape 18946 x 8174 x 8174). | No voxel size is stated in the spiral-input README. |
| D4 | then lies on w +/- 1 for >= 1 mm | Runs are grid rows and columns. Either run direction counts; the w +/- 1 side needs >= 1 mm, the w side >= 2 assigned vertices. 'Lies on' = >= 80% of the segment's vertices assigned, no unassigned stretch > 1 mm. Both-sides->= 1 mm reported as sensitivity. | Run direction is arbitrary; criteria silent on segment coverage. |
| D5 | wrap within 0.25 x local spacing from adjacent verified patches | Spacing is trusted only if <= 40 vx and <= 1.5 x the local stack median; wrap difference measured from both sides (sanity-driven fix, see S3). Same-lineage verified patches (same GrowPatch source run) excluded from the reference; verified backups/ excluded. | S3 failure; independence of reference. |
| D6 | gen_avg_cost AUROC of event vs negative windows | Unverified patches ship no generations.tif and source_region_seed_row_col does not locate the seed (0/299 checks). Generation proxy = distance to the GrowPatch seed / 20 vx (Pearson 0.81-0.92 against generations.tif on 4 verified full runs). Window score = max gen_avg_cost over the window's vertices; negative windows 1 mm, > 1 mm from any event. | Per-vertex generation not published for unverified patches. |
| D7 | S3: labeler on verified patches > 5% with events = broken | Counted confirmed events (two references, as the criteria define an event); geometry-only rate reported too (above 5%). | An event is defined by two references. |
| D8 | Numeric CT profile | Rule constants chosen on human ladder controls only (tools/switchbench/tune_ct.py); no corpus data entered the choice (an earlier corpus pass with the uncalibrated rule was discarded); negatives use an on-layer rule calibrated on verified runs (>= 70% on-layer, <= 4 consecutive off-layer vertices); at most 20 negative runs CT-checked per patch (seeded). | Criteria give no CT rule. |
| D9 | Detectors: windcheck, tifxyz-doctor, sheet-topo-bench v1, windaudit, #1621-style check | sheet-topo-bench v1 NOT RUN (input contract: needs a multi-turn banner mesh, its pristine copy for atlas differencing and a surface-prediction volume; unverified patches are < 1 turn and have no pristine copy). windcheck run, but refuses < 5,000-cell patches ('no verdict'); counted as no alarm. windaudit: `windaudit run` never reads traces, so its patch-graph harness (scripts/wide_patch_audit.py, WIDE_ATTACHMENT_GAP=1) was run on the unverified patch plus verified patches within 300 vx; patches with < 2 attached annotations are silent by construction and were not run. | Default parameters only, per criteria. |
| D10 | Recall matching | An alarm matches an event within 1 mm (3D) of any transition point of the event. tifxyz-doctor alarm locations are the examples of each emitted review cue (capped at 50 per cue by the tool). | Criteria silent. |
| D11 | Random baseline | Random alarms at tifxyz-doctor any-cue alarm density per mm^2 (Poisson, seed 20260925); random score for AUROC. | Criteria silent. |

## Detectors: build and run log

| Tool | Commit | Build | Run |
|---|---|---|---|
| tifxyz-doctor | aviad12g/tifxyz-doctor 5ca0444 | pip install -e .[tiff] in its own venv, OK | `audit --json` on every scored patch |
| windcheck | joe-carr-data/windcheck 2b0fb2f | `uv sync`; `clang++ -O3 -std=c++17 -pthread` engines/selfcross.cpp, OK | `check` on every scored patch |
| windaudit | sergeievland/windaudit aba5633 | pip install -e .[dev]; test suite 319 passed, 1 skipped (matches its README) | patch-graph harness on patches with >= 2 attachments |
| sheet-topo-bench v1 | tonclap/sheet-topo-bench 9fdfeef | cloned, pure Python | **not run** (D9) |
| #1621-style check | ours, tools/switchbench/annot.py | n/a | every scored patch |

All clones live in $SWITCHBENCH_EXT (default ./ext) (outside the repo); no downloaded binary was executed.

## Prior art

growpatch-sheet-switch-detection (slade870; cross-run disagreement, 6 CT spot checks, no P/R); sheet-topo-bench (tonclap; planted errors, zero confirmed natural switches after the Z0136 withdrawal); TIFXYZ Doctor (aviad12g; synthetic seams on reviewed Paris4 patches); windaudit (sergeievland; planted annotation switches); windcheck (joe-carr-data; self-intersection census); vesuvius-ruled (iamdflame; ruling phase as sheet signature); Stevens pipeline9; villa spiral-fitting satisfaction_metrics.py and villa#1621. None reports recall on naturally occurring switches (Scout Report #6).

## Files

- Code: `tools/switchbench/` (pull, geom, label, confirm, ct, sanity, tune_ct, calib_onlayer, calib_negrun, corpus, detectors, annot, run_windaudit, metrics, evaluate, report, write_md, events_file).
- `results/switchbench_natural_v0.json` (all numbers), `switchbench_sanity.json`, `switchbench_ct_calibration.json`, `switchbench_natural_events.json` (event and negative coordinates only, no images).
- Disk: data/paris4 = 1.14 GB (cap 5 GB), free 24.4 GB.

