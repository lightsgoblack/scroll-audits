# SwitchBench-natural v0: exploratory robustness check (abruptness, mesh resolution, operating point)

> **EXPLORATORY.** Not pre-registered in `prereg/`, not part of protocol A (prereg/switchbench_natural.md) or 5b. It changes no v0 or v1 verdict, file or code path. The analysis plan was committed before any number was computed (6a0765e); two deviations were logged before the numbers they affect (X1 c4fd704, X2 655503d). Builder + reviewer, 2026-09-26. Numeric geometry only: no images, no ink maps, nothing posted outside the repo.

## Plain-language summary

The critique tested: *"tifxyz-doctor catching 11% of natural sheet switches vs 97% of planted ones is definitional (natural switches are gradual, the planted proxy is an abrupt 8-voxel step), and it is just the operating point (lower the threshold and it catches them)."*

1. **The 97% was measured on finer meshes than ours.** Neither half of the critique raises this, and it is the biggest single problem with the comparison. The doctor's own benchmark traces have a 12.5-voxel grid step. Our natural corpus traces have a 20-voxel step (same 9.6 um voxels). The doctor divides each step by the grid spacing, so one 8-voxel step scores about 0.38 on its benchmark meshes but about 0.25 on ours, right at its 0.25 threshold. We ran the doctor's own injector and detection rule on 128 human-verified 20-voxel traces. At its defaults it catches the planted 8-voxel step **6/128 times (5%, 95% CI 2-10%)**, and a 16-voxel step 125/128 times. On its own 12.5-voxel holdout we reproduce its published 124/128 exactly.
2. **Natural switches are narrow, and only about half are abrupt.** The trace moves from one wrap to the next in a median of 2 grid steps (0.4 mm; IQR 2-4 steps), crossing about 13 voxels. About half the events contain a single-step jump of at least 8 voxels relative to the sheets, which is as abrupt as the planted proxy: 44% [32-58%] or 52% [39-65%] depending on the offset measure. The rest are gradual. By the pre-stated rule, "mostly gradual" is **UNRESOLVED**. Seen through the doctor's own per-edge score, though, only 28% [18-41%] of events reach the score a planted 8-voxel step gets on a flat 20-voxel grid (0.20).
3. **The doctor catches abrupt switches only.** All 6 default hits from its uncapped API mask are abrupt events: 6/24 abrupt vs 0/30 gradual, Fisher p = 0.005 (sheet-frame measure; 5/28 vs 1/26 under the planned measure). Random alarms show no such split (2/24 vs 3/30). For 38 of the 54 events, no edge within 1 mm reaches the default threshold. For 9 more, some edges reach it but never form the 8-cell band the tool requires.
4. **Lowering the threshold helps, but mainly for the abrupt half.** Take the threshold at which the planted 8-voxel step on 20-voxel meshes is caught 124/128 times (ratio 0.17, which restores the published rate). There, natural recall is **0.26 [0.16-0.39]** at 1.9 false alarms per 100 mm: 11/24 abrupt and 3/30 gradual. The best of all 144 settings reaches 0.26 at no more than 1 false alarm per 100 mm, and 0.41 [0.29-0.54] at no more than 5. Both were picked on the same data, so they are optimistic. Random alarms at the same false-alarm rates catch 0.02 and 0.13. Reaching 0.67 costs 17 false alarms per 100 mm, with 15% of clean trace flagged. By the pre-stated rule, "no threshold rescues it" is **UNRESOLVED**.
5. **What survives and what does not.** What survives: at matched resolution and a 5x looser operating point, natural recall (0.26) is still far below the planted rate (0.97). The gradual half stays nearly invisible at any tolerable false-alarm rate. What does not survive:
   - The "11% vs 97%" contrast as stated.
   - v0's line that the doctor is "not distinguishable from random". That random baseline matched the doctor's alarm density, not its false-alarm rate, and ran at 16x the doctor's false alarms. At a matched false-alarm rate, the doctor clearly beats random: 0.11 vs at most 0.015 at its default.

**Limits.** Label precision is about 0.70 (a mixture estimate, not measured). There are 54 events in 39 patches, 10 of them in one patch. Only one mesh resolution is covered. This is an exploratory analysis with many sub-analyses and no correction for multiple comparisons.

## What this means for the headline (for the authors; no other file was changed)

- **Do not release "11% natural vs 97% planted" as is.** Suggested wording, resolution-matched and on v0 data: *"On 20-voxel GrowPatch traces from PHercParis4, tifxyz-doctor at its defaults flags 6 of 54 natural sheet switches (11%). At the same mesh resolution, its defaults flag 6 of 128 planted 8-voxel steps and 125 of 128 planted 16-voxel steps. At the threshold that restores its published 97% on planted 8-voxel steps, it flags 14 of 54 natural switches (26%, 95% CI 16-39%) at 1.9 false alarms per 100 mm: 11 of 24 abrupt switches and 3 of 30 gradual ones."*
- The v0 verdict stands under its frozen rule, and nothing here touches it. Note, however, that criterion (i) compares natural recall with a planted recall measured at a different mesh resolution, and v1 reuses that published comparator. At the matched point on v0 data, the precision-corrected upper bound is 0.39 / 0.696 = 0.56. That is below v1's C1 bar of 0.60, so the qualitative gap may survive. This is a v0-data observation, not a v1 result. The v1 lead may want to report a resolution-matched planted number next to the published one; `explore_doctor.py planted20` does this in about 5 minutes of CPU.
- For the tool author (per the v1 contact rule): the doctor's docs never claimed natural recall ("It does not measure recall on naturally occurring sheet switches ... gradual transitions remain largely unsolved"). The useful message for them is that the 0.25 ratio depends on the grid step. On 20-voxel traces it corresponds to steps of roughly 10 voxels, and a spacing-aware threshold would restore the published planted sensitivity.

## A. How abrupt are natural switches?

Scope: the 54 confirmed v0 events. Each event is a switch seam crossed by several grid rows and columns ("member crossings"). All 809 member crossings of the 54 confirmed and 115 CT-contradicted events were reproduced exactly from v0's labeler. v0 stacks were recomputed along each crossing's grid run, and the run's chain splits at the same `rc_a` -> `rc_b` with the same wrap delta.

**How abruptness is measured.** Per crossing, the transition width is the distance along the trace from `rc_a` to `rc_b`. `rc_a` is the last vertex within 0.25 x spacing of wrap w, and `rc_b` is the first such vertex on w +/- 1. Sheets A (wrap w) and B (w +/- 1) are tracked vertex by vertex along the run. Two offset measures are used:
- **Planned measure:** the distance from A toward B.
- **Sheet-frame measure (X1):** the change in fractional position between A and B, times the local A-B gap. The planned measure also moves when the two sheets diverge while the trace follows B, which is why X1 was added.

An event's max step is the largest one-grid-step (0.192 mm) offset change in any of its crossings.

**Definition of "abrupt".** An event is ABRUPT if its max step is at least 8 voxels. This matches the planted proxy "8 voxels, transition width 1 cell", which moves one side of a seam by 8 voxels between two adjacent grid vertices (41.7 voxels/mm).

| Natural events (n = 54) | Median | IQR | p10 - p90 |
|---|---|---|---|
| Transition width (median over crossings) | 0.40 mm = 2 grid steps | 2 - 4 steps (0.39 - 0.77 mm) | 0.32 - 1.27 mm |
| Total offset crossed, sheet frame | 12.7 vx | 8.6 - 16.2 | 7.1 - 20.5 |
| A-B sheet gap at `rc_b` | 15.5 vx | 12.8 - 21.5 | 10.0 - 24.6 |
| Max single-step offset, sheet frame | 7.1 vx | 4.9 - 13.0 | 3.2 - 16.4 |
| Max single-step offset, planned | 8.3 vx | 5.9 - 12.7 | 3.9 - 20.8 |
| Max offset rate, sheet frame | 37 vx/mm | 26 - 62 | 17 - 93 |
| Doctor's own edge score on the crossing (rc_a-1 .. rc_b+1) | 0.14 (about 2.8 vx) | 0.09 - 0.20 | 0.06 - 0.33 |
| Doctor's max edge score within 1 mm of the event | 0.175 | 0.146 - 0.280 | 0.10 - 0.42 |

Width bins (grid steps): 1 step: 4; 2: 25; 3-5: 18; 6-10: 5; >10: 2.

Max-step bins (sheet frame, vx): <2.75: 2; 2.75-5: 13; 5-8: 15; 8-16: 16; >=16: 8.

| Fraction ABRUPT (Wilson 95% CI) | Value |
|---|---|
| **Primary, sheet frame** (max step >= 8 vx) | **24/54 = 0.44 [0.32, 0.58]** |
| **Primary, planned measure** | **28/54 = 0.52 [0.39, 0.65]** |
| s1: median crossing >= 8 vx (sheet frame / planned) | 18/54 = 0.33 [0.22, 0.47] / 24/54 = 0.44 [0.32, 0.58] |
| s2: whole transition in one grid step | 4/54 = 0.07 [0.03, 0.18] |
| s3: doctor edge score >= 0.20 (the score of an 8 vx one-cell step on a flat 20 vx grid) | 15/54 = 0.28 [0.18, 0.41] |
| s4: doctor edge score >= 0.25 (its default candidate threshold) | 10/54 = 0.19 [0.10, 0.31] |

**The planted proxy on the same yardstick.** Both columns below use the doctor's own injector and its detection rule: new coherent-normal-step cells in the one-cell band.

| Planted proxy | Max step / grid step | Steps | Published holdout (12.5 vx, any cue) | Replicated here (12.5 vx, this cue) | Same proxy, 128 verified 20 vx traces, default | 20 vx, ratio 0.17 |
|---|---|---|---|---|---|---|
| 4 vx x 1 cell | 4.0 | 1 | 0/128 | 0/128 | 0/128 | 2/128 |
| **8 vx x 1 cell** | **8.0** | **1** | **124/128** | **124/128** | **6/128 (0.05 [0.02, 0.10])** | **124/128** |
| 16 vx x 1 cell | 16.0 | 1 | 128/128 | 128/128 | 125/128 (0.98 [0.93, 0.99]) | 126/128 |
| 8 vx x 4 cells | 2.75 | 4 | 0/128 | 0/128 | 0/128 | 0/128 |
| 16 vx x 4 cells | 5.5 | 4 | 2/128 | 0/128 | 0/128 | 0/128 |
| 8 vx x 12 cells | 0.99 | 12 | 2/128 | 2/128 | 1/128 | 0/128 |
| 16 vx x 12 cells | 1.98 | 12 | 8/128 | 1/128 | 1/128 | 0/128 |
| **Natural events (n = 54)** | **median 7.1 (IQR 4.9-13.0)** | **median 2 (2-4)** | n/a | n/a | **6/54 (0.11)** | **14/54 (0.26)** |

- **Grid steps.** The doctor's holdout traces (same_wrap*, meta scale 0.08) have a median grid step of 12.6 vx. The corpus traces and the 128 verified auto_grown traces (scale 0.05) have 20.0 - 20.3 vx.
- **Seam scores.** On the planted 8 vx one-cell seam, the median max score is 0.378 at 12.5 vx vs 0.251 at 20 vx; the flat 20 vx grid gives 0.204.
- **Rows that differ from the published holdout.** In the gradual rows, the published numbers count any new cue while ours count this cue only, so small differences there are expected.
- **Seam length.** Planted seams span the whole trace (median 58 cells at 20 vx). Natural seams are short: a median of 2 member crossings.

**Checks on the abruptness numbers:**
- **Measurement noise.** On the confirmed negative runs, where the trace stays on one sheet, the per-step offset change has a median of 0.5 vx and a p99 of 4.8 vx (sheet frame) or 6.9 vx (planned). Steps of 8 vx or more occur in 0.22% (sheet frame) or 0.72% (planned) of steps. Given each event's number of step measurements, noise alone would be expected to create 1.8 (sheet frame) or 5.2 (planned) of the 24 / 28 ABRUPT calls.
- **Max over crossings.** ABRUPT rises with the number of crossings: 1 crossing: 6/26; 2-5: 6/12; 6+: 12/16 (sheet frame). Part of this is more chances to catch a big step. Part is real, since long seams are often abrupt somewhere along their length. The median-crossing variant (s1) gives 0.33 - 0.44.
- **Label noise.** CT-contradicted candidates are less often abrupt (36/111 = 0.32 sheet frame, 38/111 = 0.34 planned) than confirmed ones. With v0's mixture precisions (0.696 confirmed, 0.237 contradicted), the estimated ABRUPT fraction among *true* switches is 0.52 [0.31, 0.76] (sheet frame) or 0.64 [0.41, 0.86] (planned). Label noise therefore makes the corpus look more gradual, not less. This estimate is indicative only.

## B. Which events does the doctor catch?

| Hit set | Abrupt (sheet frame, n = 24) | Gradual (n = 30) | Fisher p |
|---|---|---|---|
| v0 doctor hits (capped CLI examples, v0 D10) | 5/24 = 0.21 [0.09, 0.40] | 1/30 = 0.03 [0.01, 0.17] | 0.08 |
| Doctor API mask, default (uncapped) | 6/24 = 0.25 [0.12, 0.45] | 0/30 = 0.00 [0.00, 0.11] | 0.005 |
| v0 random hits | 2/24 = 0.08 [0.02, 0.26] | 3/30 = 0.10 [0.03, 0.26] | 1.0 |

- **Planned measure.** Groups are 28 / 26: doctor 5/28 vs 1/26 (p = 0.19), random 4/28 vs 1/26.
- **Sample size.** The groups are not too small (n >= 24, CI widths < 0.5), but the hit counts are. Only the uncapped-mask contrast reaches p < 0.05, and only under the sheet-frame and intrinsic definitions.
- **The doctor's 6 v0 hits.** Four are clearly abrupt, with max single-step offsets of 14 - 32 vx and doctor scores of 0.33 - 0.46 on the crossing. Two are borderline (7.8 / 8.4 and 8.4 / 6.6 vx under the two measures). Both borderline hits are in the 434 x 554 legacy patch.
- **The mask and the v0 CLI hits.** The mask shares 5 of its 6 hits with the v0 CLI list. It misses one CLI hit, which was lost to v0's 0.5 mm alarm merge (without the merge the mask has 7/54). It adds one hit that the 50-example cap had hidden.
- **Random's 5 hits.** Two are abrupt and three are gradual (sheet frame).

**Why the other events are missed.** Classes are defined by the doctor's per-edge scores within 1 mm of the event:

| Class | Events |
|---|---|
| (i) No edge >= 0.25 (sub-threshold, i.e. gradual to the doctor) | 38 |
| (ii) Edges >= 0.25, but the largest candidate band touching the event is < 8 cells | 9 |
| (iii) A coherent band is present | 7 (6 hits after v0's alarm merge) |

**Abrupt vs gradual events** (sheet frame):

| | Abrupt (n = 24) | Gradual (n = 30) |
|---|---|---|
| Member crossings (median) | 5.5 | 1 |
| Events with at most 2 crossings | 8 | 23 |
| Total offset (median) | 16.0 vx | 8.7 vx |
| Doctor score on the crossing (median) | 0.21 | 0.09 |
| Miss classes (i / ii / iii) | 10 / 8 / 6 | 28 / 1 / 1 |
| Hit at the resolution-matched point | 11 | 3 |

The gradual half is mostly single-crossing, small-offset events. That is also the kind most likely to be label errors.

## C. Operating-point sweep

- **What the API exposes.** `audit_mesh(...)["_arrays"]` has no continuous score for this cue, only the binary `coherent_normal_step_cells` and an all-cue `review_score`.
- **What was swept.** The cue's operating point is set by two public parameters, which are also CLI flags: `normal_step_ratio` (default 0.25; per-edge normal component / grid step) and `normal_step_min_component_cells` (default 8). Both were swept through the API: 24 ratios (0.03 - 0.50) x 6 minimum sizes (1 - 32), on all 67 scored patches.
- **Validation.**
  - The default sweep point is identical to the default capture mask on every patch.
  - A rebuild from the captured per-edge scores, using the doctor's own rule, is also identical to both.
  - No monotonicity violations occurred.

Scoring follows v0 exactly. Alarms are flagged cell centres merged at 0.5 mm. A hit is an alarm within 1 mm of an event point. A false alarm is a merged alarm within 1 mm of a confirmed negative run and more than 1 mm from any candidate event, counted per run, per 100 mm of the 7896.5 mm of confirmed negatives.

**How to read the false-alarm unit.** Row and column runs overlap, so one false alarm per 100 mm is about 0.004 - 0.005 alarms per mm² of clean surface: roughly one alarm per 15 x 15 mm, from the random-alarm calibration. Five per 100 mm is roughly one alarm per 7 x 7 mm.

| Operating point | Ratio, min cells | Natural recall (Wilson) | Patch bootstrap | FA / 100 mm | Clean vertices within 1 mm of an alarm | Random at same FA | Abrupt / gradual hits |
|---|---|---|---|---|---|---|---|
| v0 headline (capped CLI examples) | 0.25, 8 | 6/54 = 0.11 [0.05, 0.22] | [0.02, 0.19] | 0.063 | n/a | < 0.015 | 5/24, 1/30 |
| API mask, default | 0.25, 8 | 6/54 = 0.11 [0.05, 0.22] | [0.02, 0.19] | 0.37 | 0.4% | < 0.015 | 6/24, 0/30 |
| **Resolution-matched** (planted 8 vx x 1 cell at 20 vx: 124/128) | **0.17, 8** | **14/54 = 0.26 [0.16, 0.39]** | **[0.11, 0.39]** | **1.87** | **1.6%** | **0.05** | **11/24, 3/30** |
| Best at FA <= 1 (1 of 44 eligible; optimistic) | 0.14, 32 | 14/54 = 0.26 [0.16, 0.39] | [0.11, 0.39] | 0.75 | 0.6% | 0.02 | 10/24, 4/30 |
| Best at FA <= 5 (1 of 60 eligible; optimistic) | 0.22, 1 | 22/54 = 0.41 [0.29, 0.54] | [0.25, 0.54] | 4.72 | 5.7% | 0.13 | 17/24, 5/30 |

**Recall frontier.** Best over the grid at each false-alarm cap, optimistic:

| FA cap per 100 mm | Setting | Recall | FA | Random at same FA | Abrupt / gradual |
|---|---|---|---|---|---|
| 0.1 | 0.30, 8 | 5/54 = 0.09 | 0.00 | 0.015 | 5/24, 0/30 |
| 0.25 | 0.18, 16 | 9/54 = 0.17 | 0.24 | 0.015 | 7/24, 2/30 |
| 1 | 0.14, 32 | 14/54 = 0.26 | 0.75 | 0.02 | 10/24, 4/30 |
| 2 | 0.15, 16 | 15/54 = 0.28 | 1.22 | 0.04 | 11/24, 4/30 |
| 5 | 0.22, 1 | 22/54 = 0.41 | 4.72 | 0.13 | 17/24, 5/30 |
| 10 | 0.19, 1 | 25/54 = 0.46 | 8.8 | 0.21 | 18/24, 7/30 |
| 20 | 0.15, 1 | 36/54 = 0.67 | 17.5 (15% of clean trace flagged) | 0.35 | 22/24, 14/30 |
| 50 | 0.12, 1 | 46/54 = 0.85 | 39.1 (28% flagged) | 0.59 | 24/24, 22/30 |

**Other results from the sweep:**
- **Any-cue `review_score`** does worse than the step knob: 9/54 at FA 0.99 (tau 0.5) and 11/54 at FA 2.3 (tau 0.4).
- **Per event.** The median of the highest ratio at which each event is hit (with 8-cell bands) is 0.12 (IQR 0.09 - 0.175). Every event is hit at some ratio of 0.05 or more.
- **Sensitivity, excluding the 10-event patch** (recall; FA per 100 mm where it changes): default 4/44, FA 0.13; matched 9/44, FA 0.76; best at FA <= 1: 9/44; best at FA <= 5: 16/44, FA 3.6.
- **Sensitivity, capping at 3 events per patch** (seeded): 4/47, 10/47, 11/47 and 18/47 respectively.
- **v0's random baseline.** It was one draw at the doctor's any-cue alarm density (0.0126 per mm²): 5 hits, FA 1.04. Twenty draws at a bracketing density (0.0116 per mm²) give FA 1.5 - 4.3 (median 2.7) and 1 - 8 hits. So it compared the doctor with random alarms at 16x (realized) to about 40x (typical) the doctor's false-alarm rate.

## D. Pre-stated takeaway rules and adversarial checks

**Claim G: "natural switches are mostly gradual; the planted proxy does not represent them."** Rule: SUPPORTED if the ABRUPT fraction's Wilson upper bound is < 0.5 under both offset measures, CONTRADICTED if the lower bound is > 0.5 under both, otherwise UNRESOLVED. **Verdict: UNRESOLVED** (0.44 [0.32, 0.58] and 0.52 [0.39, 0.65]).

- **For G.**
  - Measured by what the tool actually sees, most natural switches do not look like the planted proxy: 28% reach its score level and 19% reach its threshold.
  - Only 7% complete the switch in one grid step.
  - The gradual half is nearly invisible to the tool at any tolerable false-alarm rate.
  - The median-crossing variant (sheet frame) would be SUPPORTED (0.33 [0.22, 0.47]).
- **Against G.**
  - Against the reference sheets, about half the events do take an 8-voxel or larger step within one grid step.
  - Transitions are short (2 - 4 steps), unlike the planted 4- and 12-cell ramps.
  - Label noise biases the corpus toward "gradual".
  - The planted proxy fails to represent natural switches for a second reason the critique does not name: mesh resolution. At 20 voxels even the planted proxy is missed 122/128 times.

**Claim T: "no threshold rescues the detector without flooding false alarms."** Rule: SUPPORTED if the best recall at FA <= 5 per 100 mm has a Wilson upper bound < 0.5, CONTRADICTED if that recall is >= 0.5, otherwise UNRESOLVED. **Verdict: UNRESOLVED** (0.41 [0.29, 0.54]).

- **For T.** No setting reaches 0.5 recall at no more than 5 false alarms per 100 mm, even with post hoc selection. The gradual half stays at 5/30 there. 0.67 costs 17 false alarms per 100 mm.
- **Against T.** "It's the operating point" is largely right for abrupt switches at this mesh resolution: 11/24 at the matched point and 17/24 at FA <= 5. The default is conservative for 20-voxel traces, and the tool carries real signal at every false-alarm rate: about 5 - 15x random at up to 2 false alarms per 100 mm, 3x at 5.
- **Precision correction.** If every hit is a true switch, the upper bound on true-switch recall is the Wilson upper bound divided by 0.696: 0.56 at the matched point and 0.78 at the best FA <= 5 setting.

**Other adversarial checks:**
- The best-of-grid points are optimistic: 44 - 60 eligible settings, chosen on the test events. The resolution-matched point is chosen from planted data only, so it is the fairest single number.
- The v0 false-alarm rule counts one alarm once per nearby run. Row and column runs overlap, so this is a density-like measure. The flagged-fraction column is the plain reading.
- 10 of the 54 events are in one patch. Excluding that patch lowers every recall slightly and does not change any conclusion.

## Method, validation, deviations

- **Code.** `tools/switchbench/explore_abruptness.py` (project venv) and `tools/switchbench/explore_doctor.py` (the doctor's own venv, public API only; two functions wrapped only to record their arguments). v0 modules `geom`, `label` and `metrics` are imported read-only. No existing v0 or v1 file was modified.
- **Doctor harness check.** The doctor's own sealed-holdout ladder was replicated exactly on the abrupt rows (124/128 and 128/128).
- **Alarm merge.** The fast 0.5 mm merge was self-tested against v0 `evaluate.dedup_alarms`. Cell centres were checked against `metrics.cells_to_xyz`.
- **X1 (c4fd704).** The planned offset (distance from sheet A) also moves when the sheets diverge. The sheet-frame measure was added, and claim G required agreement under both measures.
- **X2 (655503d).** Added after the 12.6 vs 20 vx grid-step finding and before any 20 vx planted number: the doctor's ladder on 128 seeded verified auto_grown traces (scale 0.05; none skipped), plus the matched-sensitivity point. The rebuilt masks matched the API mask at the default on every base and planted case.
- **Compute.** About 1 CPU-hour, peak memory about 1.1 GB, no downloads (data/paris4 as on disk). Intermediates stayed in the session scratchpad and are not committed; the usage lines in the code regenerate them.

## Files

- `results/switchbench_explore.json`: plan (as committed), deviations X1 and X2, all numbers, the full sweep table, the random curve, and a per-event table (coordinates and numbers only).
- `results/switchbench_explore.md`: this file.
- `tools/switchbench/explore_abruptness.py`, `tools/switchbench/explore_doctor.py`.
