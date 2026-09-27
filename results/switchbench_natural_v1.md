# SwitchBench-natural v1: results (blind review scored -- C1: SUPPORTED)

Bet: protocol P1 (prereg/switchbench_v1.md), frozen at 45934b5 (prereg/switchbench_v1.md, SHA-256 821144c5c69b17a2..., matches the posted commitment: True). Post-freeze operational calls: protocol P1 (prereg/switchbench_v1.md) addendum (commit 52469c7, Scout Report #8): doctor uncapped = API mask UNION CLI examples (primary) and mask only; seamcheck secondary (C2 only); C4 source PHerc0500P2. v1 start 2026-09-26T13:15:26Z; this file 2026-09-26T16:39:58Z. $0, CPU only. No ink maps and no images anywhere: CT was read as numeric 1-D profiles only, detectors wrote numeric JSON only. Nothing was posted outside this repo. Nothing text-like was seen.

## Blind review outcome (added 2026-09-27; the rest of this file, below, is the pre-review record and is unchanged)

**In plain English:** the section right below this one ("Status: paused...") was written before the authors' blind
review came back. It is kept as-is, for the audit trail, but it is no longer current -- read this box first.

The review scored on 2026-09-27: **C1 is SUPPORTED**, on both the pooled corpus and the new-patches-only set.
Full numbers, the reviewer's answers by kind, and every caveat that ships with this result:
[switchbench_v1_blind_review_score.md](results/switchbench_natural_v1_blind_review_score.md). Headline: measured precision
0.833 (10/12 decided, Wilson 95% [0.552, 0.953]); precision-corrected upper bound on natural recall 0.287
pooled / 0.322 new (< 0.60, the SUPPORTED bar).

Caveats that carry forward into every public mention of this result, not just the internal one:
- **One reviewer, one round.** 15 confirmed events, judged by the authors alone, in a second round -- round 1 (all
  30 answers "switch") could not discriminate anything and is not scored (the reviewer was re-briefed and
  re-did the same 30 views with clearer instructions). The precision interval above reflects one person's
  judgement on one pass; it is wide, and the verdict is checked for robustness to that width (see the
  Robustness row in the linked file).
- **CT-contradicted candidates split 7/10 toward "switch."** On the 10 candidates our CT-intensity check
  had ruled out, the reviewer called 7 of them a switch anyway. This does not change C1 (which scores
  confirmed events only), but it is an open disagreement between the CT check and human judgement worth
  flagging every place this corpus's confirmation method is described, not just here.
- **One scroll (PHercParis4), CPU-only detectors, run with each tool's own published defaults.** Every
  recall number in this file and in the public summary is "as configured": the tool's default settings, on
  this one scroll's traces, on ordinary CPU hardware -- not a ceiling on what the tool could do re-tuned, on
  a different scroll, or on a GPU.

## Plain-language summary (pre-review; kept for the record, see the box above for the current verdict)

- **Status: paused for the authors' blind review. There is no C1 verdict yet.** The frozen rule says the headline claim needs strong labels, and ours are not strong. Even at 2.4 um, the CT check that confirms a switch passes 59% of true adjacent-wrap pairs, but it also passes 11% of two-wraps-apart pairs and 20% of same-sheet pairs (held-out human ladders). STRONG needs both false-pass rates at or below 5% and adjacent pass at or above 70%. The lowest false-pass ceiling any rule in the 540-variant grid meets on the tuning half is 15% (adjacent pass there 0.50). So the frozen plan's blind review is triggered: results/switchbench_natural_v1_blind_review.md (30 locations, about 1 hour in VC3D).
- **The corpus grew 4.5x.** Pooled (patches 1-10,000): 892 candidates, 294 confirmed by the 2.4 um rule in 175 patches, 1261 confirmed negative runs (16414 mm). New patches alone: 229 confirmed events.
- **Why a blind review matters here.** On human-verified patches, where switches should be rare, the 2.4 um rule confirms 3 of 9 geometry-only candidates (v0's 9.6 um rule: 0). S3 still passes (3.6% of verified patches, limit 5%), but false confirmations are real. Concentration: one legacy full-size patch carries 73 confirmed events; the per-patch cap counts at most 3 of them toward recall.
- **tifxyz-doctor, uncapped, still misses most natural switches**: 24/213 = 0.113 (patch-block 95% CI [0.071, 0.159]) pooled, per-patch cap 3. New patches alone: 19/156 = 0.122 [0.072, 0.178]. C1 is an absolute bound, so it needs no planted comparator. Do not read this against the tool's published 124/128 planted recall: that was measured on 12.5-voxel-grid traces, and the doctor divides its score by grid step, so on 20-voxel traces like ours its defaults catch the planted 8-voxel step only 6/128 (EXPLORATORY, results/switchbench_explore.md).
- **What the review decides.** The FAILS branch (CI lower bound > 0.85) is already ruled out on both sets. SUPPORTED needs the review's precision lower bound above 0.297, which means at least 8 of the 15 confirmed events marked "switch" if none is marked "can't tell". Otherwise the result is INCONCLUSIVE (dataset and descriptive numbers only, with the authors' approval).
- **C4, second sample (PHerc0500P2, report-only):** 23 capped events on 8 traces. The doctor's union alarms catch 6, at 24 false alarms per 100 mm; random alarms at a similar false-alarm rate catch 9. Labels there are weaker; small sample; no claim either way.
- **Fair coverage (C2):** no tool reaches the 0.80 recall lower bound in its author-intended mode.

## C1 headline test (frozen rule, quoted)

> tifxyz-doctor natural recall on confirmed events, patch-block bootstrap 95% CI (B = 2000, seed 20260925), per-patch cap 3. **Precision-corrected upper bound** = CI upper / precision lower bound (measured if blind review ran, else the ladder mixture estimate). **SUPPORTED** if the corrected upper bound < 0.60 on the pooled corpus AND on the new patches alone. **FAILS** if the CI lower bound > 0.85. Otherwise INCONCLUSIVE: release as dataset + descriptive numbers only, with the authors' approval.

| Set | Hits / events (patches) | Recall | Patch-block 95% CI | Wilson 95% CI | FAILS branch (lower > 0.85) |
|---|---|---|---|---|---|
| Pooled (1-10,000) | 24/213 (175) | 0.113 | [0.071, 0.159] | [0.077, 0.162] | not met |
| New only (3,001-10,000) | 19/156 (126) | 0.122 | [0.072, 0.178] | [0.079, 0.182] | not met |

Precision lower bound: from the blind review (pending). SUPPORTED requires it to exceed max(CI upper) / 0.60 = 0.297. For information only (not the verdict input, because the review was triggered): the ladder mixture estimate with the held-out ladder rates puts the precision of the confirmed set at 0.621 (pass fraction among decided candidates 0.342, false-pass 0.202, sensitivity 0.592).

## Sanity (failure = harness bug, no verdict)

| Check | Rule | Result |
|---|---|---|
| S1 | verified patch vs itself = 0 events | PASS: events per patch [0, 0, 0, 0, 0, 0, 0, 0, 0, 0] (the 10 v0 patches) |
| S2 | planted one-wrap jump = exactly 1 event at the right place | PASS: 5/5 planted patches give exactly 1 event at the planted column, dw = +1. The 2.4 um rule confirms 3 of 5 planted events (informational; its ladder sensitivity is 0.59) |
| S3 | labeler on verified patches: > 5% with confirmed events = broken | PASS: 3.6% of 83 evaluable verified patches have a 2.4 um-confirmed event (3 of 9 geometry-only candidates confirmed, 6 contradicted; v0 rule: 0). Geometry-only candidates on 10.8% |
| S4 | uncapped doctor reproduces every v0 hit on the 69 v0 doctor patches | PASS: the pinned tool reproduces v0's stored output exactly on all 69 patches; the union keeps all 6 v0 hits (v0 labels) and adds 1; false alarms 5 -> 29 in 7896 mm |

**What the cap hid (S4, v0 labels and v0 patches).** The doctor's CLI hard-codes its example lists (25 per direction, 50 per cue); 4 of the 69 patches had a capped emitted cue, all on coherent-normal-step. Uncapped, the tool's own coherent-cell mask plus the CLI examples find 7/54 v0 events (v0 reported 6/54) and raise 29 false alarms (v0: 5). Every flagged candidate edge (a wider reading, reported as sensitivity) finds 9/54 with 65 false alarms. All 6 v0 hits lie inside the tool's own mask. S4 first FAILED on one v0 hit; the cause was a harness artifact (see deviation V5), fixed before any v1 number was read.

## Labels: the 2.4 um rule (human ladder controls only)

Rule chosen on the tuning half of the ladder collections (no variant met the 5% false-pass limits on the tune half: max margin (v0 objective)): {'sigma': 1.5, 'end_zone': 0.15, 'min_dark': 3.0, 'q': 30, 'mid_bias': 0.15}. Held-out half decides STRONG.

| Controls | Adjacent pass | Two-apart false pass | Same-sheet false pass |
|---|---|---|---|
| 2.4 um rule, tuning half | 0.591 (547/925) [0.559, 0.623] | 0.146 (116/795) [0.123, 0.172] | 0.206 (188/914) [0.181, 0.233] |
| 2.4 um rule, held-out half | 0.592 (535/904) [0.559, 0.623] | 0.106 (83/781) [0.087, 0.130] | 0.202 (181/896) [0.177, 0.230] |
| 2.4 um rule, all ladders | 0.592 (1082/1829) [0.569, 0.614] | 0.126 (199/1576) [0.111, 0.144] | 0.204 (369/1810) [0.186, 0.223] |
| v0 rule at 9.6 um, held-out half | 0.523 (474/907) [0.490, 0.555] | 0.099 (79/797) [0.080, 0.122] | 0.137 (125/911) [0.116, 0.161] |
| v0 rule at 2.4 um, held-out half | 0.531 (483/910) [0.498, 0.563] | 0.104 (82/791) [0.084, 0.127] | 0.145 (132/913) [0.123, 0.169] |

**STRONG: no** (rule: test-half two-apart <= 5% and same-sheet <= 5% and adjacent >= 70%; judged on all ladders instead: no). Best adjacent pass on the tuning half at a given false-pass ceiling: <= 15%: 0.50 (held-out 0.53, false passes 0.11 / 0.12) (no variant reaches both false-pass rates <= 10%).

## Corpus

| Item | Pooled | New (3,001-10,000) | v0 prefix (1-3,000) |
|---|---|---|---|
| In sample (>= 5% of vertices on a verified wrap) | 2636 | 1833 | 803 |
| Candidate events (geometry) | 892 | 708 | 184 |
| **Confirmed (2.4 um rule)** | 294 | 229 | 65 |
| Contradicted by CT (not scored) | 566 | 452 | 114 |
| No CT verdict (not scored) | 32 | 27 | 5 |
| Confirmed by v0's 9.6 um rule (comparison) | 206 | 152 | 54 |
| Confirmed by both rules | 167 | 122 | 45 |
| Multi-wrap jumps (not scored) | 41 | 34 | 7 |
| Confirmed negative runs | 1261 | 667 | 594 |
| Confirmed negative length (mm) | 16414 | 8518 | 7896 |
| Scored patches | 237 | 162 | 75 |
| Patches with confirmed events | 175 | 126 | 49 |
| Most events in one patch | 73 | 73 | 11 |

New patches processed: 7000 of 7,000 (seeded order 20260925, indices 3,001-10,000), finished 2026-09-26T15:41:06Z, before the corpus close 2026-09-30T23:59:00Z.

## C2 coverage (both modes; recall per-patch cap 3, 1 mm)

| Tool | Mode | Recall pooled (hits/events) | Wilson 95% CI | Patch-block 95% CI | FA per 100 mm | Patches with a verdict | Recall new only |
|---|---|---|---|---|---|---|---|
| tifxyz-doctor (coherent-normal-step) | default (= intended) | 0.113 (24/213) | [0.077, 0.162] | [0.071, 0.159] | 0.426 (70 in 16414 mm) | 237/237 | 0.122 (19/156) |
| tifxyz-doctor (any cue) | default (= intended) | 0.117 (25/213) | [0.081, 0.168] | [0.075, 0.164] | 0.433 (71 in 16414 mm) | 237/237 | 0.128 (20/156) |
| windcheck | default | 0.000 (0/213) | [0.000, 0.018] | [0.000, 0.000] | 0.000 (0 in 16414 mm) | 28/237 | 0.000 (0/156) |
| windcheck [intended: patch mode, no cell floor] | intended | 0.005 (1/213) | [0.001, 0.026] | [0.000, 0.014] | 0.000 (0 in 16414 mm) | 237/237 | 0.006 (1/156) |
| windaudit | default | 0.000 (0/213) | [0.000, 0.018] | [0.000, 0.000] | 0.000 (0 in 16414 mm) | 31/237 | 0.000 (0/156) |
| windaudit [intended: attachment 0.45 D] | intended | 0.000 (0/213) | [0.000, 0.018] | [0.000, 0.000] | 0.037 (6 in 16414 mm) | 48/237 | 0.000 (0/156) |
| #1621-style annotation check | default (= intended) | 0.000 (0/213) | [0.000, 0.018] | [0.000, 0.000] | 0.000 (0 in 16414 mm) | 13/237 | 0.000 (0/156) |
| seamcheck [secondary, added after freeze] | intended | 0.000 (0/213) | [0.000, 0.018] | [0.000, 0.000] | 0.000 (0 in 16414 mm) | 236/237 | 0.000 (0/156) |
| random at the doctor's any-cue alarm density (frozen sensitivity) | baseline | 0.061 (13/213) | [0.036, 0.102] | [0.025, 0.100] | 4.819 | all | 0.058 |
| random at the C1 doctor alarms' false-alarm rate (added, see note) | baseline | 0.014 (3/213) | [0.005, 0.041] | [0.000, 0.033] | 0.317 | all | 0.019 |

**Random baselines.** The frozen sensitivity places random alarms at the doctor's alarm *density*. That baseline raises far more false alarms than the doctor, so it is not a fair yardstick for recall. Following the authors' framing note, random is compared only at a matched false-alarm rate (second random row: density scaled so its false-alarm rate matches the C1 doctor alarms; seed [20260925, 1]).

**Planted comparators (caveat).** The published planted recalls are 124/128 for tifxyz-doctor, 55/96 for windaudit and 0.667 for sheet-topo-bench. None was measured on traces like ours. For tifxyz-doctor the gap is known: its 124/128 used 12.5-voxel-grid traces, and its score is divided by grid step. On 20-voxel traces its defaults catch the planted 8-voxel step only 6/128. EXPLORATORY, v0 data (results/switchbench_explore.md): at the threshold that restores 124/128 on 20-voxel traces, natural recall is 14/54 = 0.26 [0.16-0.39] at 1.9 false alarms per 100 mm, and all of its default hits are abrupt events.

Tools that handle natural switches (intended-mode recall lower bound >= 0.80 under either CI): none. seamcheck's companion winding check gives patch-level verdicts only (no locations), so it has no recall: SKIP 176, WATCH 30, REVIEW 16, OK 15 patches.

## C3 early warning (report only)

| Set | gen_avg_cost AUROC (patch-block 95% CI) | Event / negative windows (patches) | Random score AUROC |
|---|---|---|---|
| pooled | 0.364 [0.273, 0.463] | 175 / 14311 (202) | 0.485 |
| new | 0.444 [0.353, 0.538] | 127 / 6957 (137) | 0.469 |
| v0_prefix | 0.291 [0.145, 0.453] | 48 / 7354 (65) | 0.535 |

## Sensitivity (tifxyz-doctor)

| Alarm set | Set | r = 0.5 mm | r = 1 mm | r = 2 mm | Uncapped events (1 mm) | FA per 100 mm (1 mm) |
|---|---|---|---|---|---|---|
| tifxyz-doctor (coherent-normal-step) | pooled | 0.099 (21/213) | 0.113 (24/213) | 0.141 (30/213) | 0.136 (40/294) | 0.426 |
| tifxyz-doctor (coherent-normal-step) | new | 0.109 (17/156) | 0.122 (19/156) | 0.160 (25/156) | 0.140 (32/229) | 0.481 |
| tifxyz-doctor (coherent-normal-step) | v0_prefix | 0.070 (4/57) | 0.088 (5/57) | 0.088 (5/57) | 0.123 (8/65) | 0.367 |
| tifxyz-doctor (any cue) | pooled | 0.103 (22/213) | 0.117 (25/213) | 0.146 (31/213) | 0.139 (41/294) | 0.433 |
| tifxyz-doctor (any cue) | new | 0.115 (18/156) | 0.128 (20/156) | 0.167 (26/156) | 0.144 (33/229) | 0.493 |
| tifxyz-doctor (any cue) | v0_prefix | 0.070 (4/57) | 0.088 (5/57) | 0.088 (5/57) | 0.123 (8/65) | 0.367 |
| random | pooled | 0.023 (5/213) | 0.061 (13/213) | 0.192 (41/213) | 0.143 (42/294) | 4.819 |
| random | new | 0.019 (3/156) | 0.058 (9/156) | 0.186 (29/156) | 0.162 (37/229) | 4.309 |
| random | v0_prefix | 0.035 (2/57) | 0.070 (4/57) | 0.211 (12/57) | 0.077 (5/65) | 5.369 |
| random (FA-matched to the C1 doctor alarms) | pooled | 0.005 (1/213) | 0.014 (3/213) | 0.014 (3/213) | 0.041 (12/294) | 0.317 |
| random (FA-matched to the C1 doctor alarms) | new | 0.006 (1/156) | 0.019 (3/156) | 0.019 (3/156) | 0.048 (11/229) | 0.481 |
| random (FA-matched to the C1 doctor alarms) | v0_prefix | 0.000 (0/57) | 0.000 (0/57) | 0.000 (0/57) | 0.015 (1/65) | 0.139 |
| tifxyz-doctor (any cue) capped examples (v0 D10) | pooled | 0.099 (21/213) | 0.108 (23/213) | 0.141 (30/213) | 0.095 (28/294) | 0.183 |
| tifxyz-doctor (any cue) capped examples (v0 D10) | new | 0.109 (17/156) | 0.122 (19/156) | 0.160 (25/156) | 0.096 (22/229) | 0.294 |
| tifxyz-doctor (any cue) capped examples (v0 D10) | v0_prefix | 0.070 (4/57) | 0.070 (4/57) | 0.088 (5/57) | 0.092 (6/65) | 0.063 |
| tifxyz-doctor (any cue) mask only | pooled | 0.094 (20/213) | 0.108 (23/213) | 0.131 (28/213) | 0.133 (39/294) | 0.317 |
| tifxyz-doctor (any cue) mask only | new | 0.103 (16/156) | 0.115 (18/156) | 0.147 (23/156) | 0.135 (31/229) | 0.270 |
| tifxyz-doctor (any cue) mask only | v0_prefix | 0.070 (4/57) | 0.088 (5/57) | 0.088 (5/57) | 0.123 (8/65) | 0.367 |
| tifxyz-doctor (cns) all candidate edges | pooled | 0.108 (23/213) | 0.122 (26/213) | 0.164 (35/213) | 0.235 (69/294) | 0.987 |
| tifxyz-doctor (cns) all candidate edges | new | 0.122 (19/156) | 0.135 (21/156) | 0.173 (27/156) | 0.262 (60/229) | 1.139 |
| tifxyz-doctor (cns) all candidate edges | v0_prefix | 0.070 (4/57) | 0.088 (5/57) | 0.140 (8/57) | 0.138 (9/65) | 0.823 |
| tifxyz-doctor (cns) capped examples (v0 D10) | pooled | 0.094 (20/213) | 0.103 (22/213) | 0.136 (29/213) | 0.092 (27/294) | 0.183 |
| tifxyz-doctor (cns) capped examples (v0 D10) | new | 0.103 (16/156) | 0.115 (18/156) | 0.154 (24/156) | 0.092 (21/229) | 0.294 |
| tifxyz-doctor (cns) capped examples (v0 D10) | v0_prefix | 0.070 (4/57) | 0.070 (4/57) | 0.088 (5/57) | 0.092 (6/65) | 0.063 |
| tifxyz-doctor (cns) mask only | pooled | 0.089 (19/213) | 0.103 (22/213) | 0.127 (27/213) | 0.129 (38/294) | 0.305 |
| tifxyz-doctor (cns) mask only | new | 0.096 (15/156) | 0.109 (17/156) | 0.141 (22/156) | 0.131 (30/229) | 0.247 |
| tifxyz-doctor (cns) mask only | v0_prefix | 0.070 (4/57) | 0.088 (5/57) | 0.088 (5/57) | 0.123 (8/65) | 0.367 |

Doctor, pooled, events that hold both wraps for >= 1 mm: 0.143 (10/70); events also confirmed by v0's 9.6 um rule: 0.117 (15/128).

## Deviations and operational choices (none silent)

| # | Frozen text | What was done | Why |
|---|---|---|---|
| V1 | Labels: constants tuned only on human ladder controls; report the ladder rates | Tuned on a seeded half of the 300 ladder collections (split by collection); STRONG judged on the held-out half; tuning-half and all-ladder rates reported too | A 540-variant grid scored on its own tuning data would overstate the rates; the held-out half is the stricter reading |
| V2 | Labels: 2.4 um rule (no rule given) | v0's adjacent-wrap rule on level-0 profiles (step = 1 level-0 voxel) plus one knob, mid_bias (a faint middle sheet also blocks a pass). Objective: most adjacent passes with both false-pass rates <= 5% on the tuning half, else v0's margin. Grid and objective committed (a9bc7e8) before the first run | v0 D8 practice; the frozen text gives no rule |
| V3 | Re-confirm every candidate with level-0 CT | Candidate events re-confirmed at level 0 (members and profile geometry exactly as v0). Negative runs keep v0's on-layer rule at 9.6 um (<= 20 seeded runs per patch, v0 D8). Level-0 coordinates = 4 x level-2 (OME-Zarr scale metadata, no translation) | The frozen text re-confirms candidates; negatives stay v0's rule as run |
| V4 | tifxyz-doctor runs uncapped (raise the cap if the CLI allows, else record per-cue counts and flag capped cues) | The CLI has no cap option (hard-coded). Post-freeze call (protocol P1 (prereg/switchbench_v1.md) addendum, Scout #8): primary = public API mask coherent_normal_step_cells UNION the CLI examples; mask only, the CLI examples alone (v0) and every flagged candidate edge are sensitivities. doctor_wrap.py runs the unmodified default CLI path in the tool's venv; every count is cross-checked against the tool's report, the CLI config equals AuditConfig() defaults, and per-cue counts and capped flags are recorded | Cap hard-coded; the tool's own 124/128 was scored on the mask |
| V5 | v0 D10: an alarm matches an event within 1 mm | Events are matched against every raw alarm location; the 0.5 mm deduplication (v0: a cue band counts once) is used only for false-alarm counts and the random density | S4 caught it: v0's greedy dedup replaced an alarm 0.77 mm from a v0 event by a representative 1.01 mm away once the uncapped mask added hundreds of nearby cells. Harness fix; v0's own numbers are unchanged (6/54 either way) |
| V6 | Doctor any-cue alarm set (v0 D10) | review_cue_mask UNION the CLI examples of every emitted cue | v0's cue map filed five distortion cues under anisotropic-cells only and left nonlocal-proximity unlocalized |
| V7 | windcheck at the smallest min-cells its docs allow | bench/patch_audit.py audit_one: the both-diagonal engine census with no cell floor (docs/PATCH-AUDIT.md; its smallest censused patch had 164 valid cells), threads 1, default parameters; alarms = both quads of each transverse contact | Its docs define no minimum for patches |
| V8 | windaudit with the attachment gap widened per its docs | The docs fix the patch attachment tolerance at 2.5 vx (not tuned) and document one attachment-gap setting, WIDE_ATTACHMENT_GAP=1, which v0 already used. Intended mode widens the tolerance to 0.45 D = 10.485 vx, the widest same-sheet tolerance its docs use (METHODS.md sweep {0.25, 0.35, 0.45} D; D = 23.30 vx), via a generated copy of the harness with only that constant changed | Closest documented reading of 'widened' |
| V9 | Detector list | seamcheck (hwkim3330/seamcheck 6d6bc2d) added as SECONDARY after the freeze (Scout #8, lead call): C2 only, never C1. Its neighbour-step test is scored (every flagged step of a REVIEW/WATCH patch; SPARSE = no verdict); its winding check has patch-level verdicts only | Added after freeze on Scout #8 |
| V10 | sheet-topo-bench via an input adapter if buildable within 1 day | Not run. Its natural-data mode (corpus B) differences production meshes against a verified multi-turn banner with a surface-prediction volume; the unverified patches are sub-turn crops with no banner counterpart, and building one from verified patches is not a 1-day adapter | 1-day cap |
| V11 | Blind review: 15 confirmed events, 10 CT-contradicted candidates, 5 negative runs | Confirmed events are drawn from the capped set that counts toward recall; a negative run's location is its midpoint vertex; all 30 are described in one format (centre point, grid direction, a fixed 12-cell span shifted inward at grid edges) | Precision must describe the scored set; the format hides each location's kind |
| V12 | Per-patch cap 3 (seeded pick) | One RNG (seed 20260925) over patches sorted by name; a patch's confirmed events sorted by position | Procedure not specified |
| V13 | Random alarms at the doctor's density | Density of the doctor's any-cue union alarms (0.5 mm-deduplicated) per mm^2; v0 used the capped examples | Uncapped alarms |
| V14 | C2: 'handles natural switches' if the intended-mode recall CI lower bound >= 0.80 | Flagged if either the Wilson or the patch-block lower bound reaches 0.80 | CI type not specified; the inclusive reading errs against our headline |
| V15 | Events file results/switchbench_natural_v1_events.json | Withheld from the repo until the blind review is scored (written to data/switchbench_v1/); its SHA-256 is committed now | It carries the labels of the 30 review locations |
| V16 | S1-S3 re-run including the 2.4 um rule | S2 passes on geometry as in v0; the 2.4 um verdict at each planted event is reported, not required | The rule's sensitivity is below 1 by construction |
| V17 | C3 as in v0 | Uncapped as v0; per-patch-capped windows reported beside it |  |
| V18 | Sensitivity: random alarms at the doctor's density | Kept as frozen, plus a second random baseline at the C1 doctor alarms' false-alarm rate; random is compared to the doctor only at matched false-alarm rate | Lead's framing note (2026-09-26): the density-matched baseline runs at a much higher false-alarm rate |
| V19 | Comparisons with published planted recall | Never headlined; every mention carries the grid-spacing caveat and the EXPLORATORY matched-spacing numbers (results/switchbench_explore.md) | Lead's framing note: the doctor's 124/128 was measured on 12.5-voxel traces; C1 is an absolute bound and is unaffected |
| V20 | Corpus: patches 3,001-10,000 | All 7,000 processed. One legacy full-size trace (#5,072 of the seeded order, 783,586 valid vertices) was OOM-killed in the 3-worker pool and re-run alone under a hard 9 GB address-space cap with the verified-surface speed cache trimmed (a 6 GB cap ran out after the stacks were built) | Shared-box memory; the cache does not change results |
| V21 | C4: same pipeline, report-only | PHerc0500P2 (lead's call): the 7 numbered layers are the reference surfaces (layer = wrap); label.py constants rescaled by physical size (x 2.224 for 4.317 um; grid-count lengths too), except the duplicate-merge MIN_SPACING, capped at half the 10th percentile of adjacent-layer spacing (7.6 vx) measured on the layers alone; raw grid normals (no umbilicus). CT: the Paris4 rule converted to physical units, not re-tuned; its rates on layer-derived controls reported. Negatives: v0's on-layer rule at the median layer spacing. Independence rule fixed before the check: a pairing is dependent if on-layer offsets have median < 1 vx or >= 50% within 0.5 vx. Sanity analog: each layer labeled against the other six | No human ladders or annotations on this sample; constants must be converted to its voxel size |

v0 rules carried over unchanged as frozen rules: D1 (in-sample: >= 5% of vertices on a verified wrap), D3 (9.6 um frame), D4 (event runs and segment coverage), D5 (spacing trust and bilateral wrap difference), D6 (generation proxy), D8 (on-layer negative rule, 20-run CT cap), D9 (windaudit harness and #1621-style check as run), D11 (random baseline form).

## Detectors: build and run log

| Tool | Commit | Build | Run |
|---|---|---|---|
| tifxyz-doctor | aviad12g/tifxyz-doctor 5ca0444 | v0 venv (pip install -e .[tiff]) | doctor_wrap.py: default CLI path + API arrays (uncapped) |
| windcheck | joe-carr-data/windcheck 2b0fb2f | v0 (uv sync; selfcross engine built from source with clang++) | `check` (default) and patch mode (V7) |
| windaudit | sergeievland/windaudit aba5633 | v0 venv | patch-graph harness, default and widened tolerance (V8) |
| seamcheck | hwkim3330/seamcheck 6d6bc2d | own venv from requirements.txt (numpy, tifffile, imagecodecs) | seamcheck_run.py, default parameters (V9) |
| sheet-topo-bench | tonclap/sheet-topo-bench 9fdfeef | cloned, pure Python | **not run** (V10) |
| #1621-style check | ours, tools/switchbench/annot.py | n/a | every scored patch |

All clones live in $SWITCHBENCH_EXT (default ./ext) (outside the repo). No downloaded binary was executed.

## C4 second scroll (PHerc0500P2, report-only)

Source: the authors' call on Scout Report #8. 25 GrowPatch consensus traces (`z_dbg_gen_*`) against the 7 numbered layers -2..4 as reference surfaces (layer = wrap), 4.317 um frame, numeric CT from the 4.317 um volume. 0500P2 is an unread sample: no ink-detection file was read, no image was made, nothing text-like can arise.

- Independence check: 0 trace-layer pairings share geometry (none excluded); on-layer offsets are a few voxels and no vertex is copied.
- Transferred 2.4 um rule on layer-derived controls (report only, no tuning): adjacent pass 0.428 (145), two-apart false pass 0.235, same-layer false pass 0.056.
- Layer sanity (each layer labeled against the other six): 28 geometry candidates, 6 confirmed, on 2 in-sample layers.
- Corpus: 25 traces, 8 in sample, 276 candidates, **92 confirmed**, 181 contradicted, 3 undecided, 10 multi-layer jumps; 42 confirmed negative runs (524 mm).

| Tool | Recall, cap 3, 1 mm (hits/events) | Wilson 95% CI | Patch-block 95% CI | FA per 100 mm |
|---|---|---|---|---|
| tifxyz-doctor (coherent-normal-step) | 0.261 (6/23) | [0.125, 0.465] | [0.095, 0.417] | 24.029 |
| tifxyz-doctor (any cue) | 0.304 (7/23) | [0.156, 0.509] | [0.130, 0.500] | 38.523 |
| tifxyz-doctor (cns) capped examples (v0 D10) | 0.000 (0/23) | [0.000, 0.143] | [0.000, 0.000] | 3.433 |
| windcheck | 0.000 (0/23) | [0.000, 0.143] | [0.000, 0.000] | 0.572 |
| windcheck [patch mode] | 0.000 (0/23) | [0.000, 0.143] | [0.000, 0.000] | 0.572 |
| seamcheck | 0.043 (1/23) | [0.008, 0.210] | [0.000, 0.130] | 4.386 |
| random | 0.391 (9/23) | [0.222, 0.592] | [0.208, 0.609] | 22.122 |

**Reading.** This is a small, weak replication: 23 capped events on 8 traces, and labels weaker than on Paris4 (see the controls and the layer check above). The doctor's union alarms reach 6/23, but only by flagging these traces densely (24.0 false alarms per 100 mm). Random alarms at its density run at a similar false-alarm rate (22.1 per 100 mm) and catch 9/23, so on this sample the doctor does not beat chance at matched false alarms. Its capped CLI examples alone (v0's reading) catch 0/23. windcheck and seamcheck stay near zero. The replication does not contradict low natural recall, but its numbers cannot carry a claim.

Not applicable on PHerc0500P2: windaudit: no human winding annotations on PHerc0500P2; #1621-style check: no human winding annotations; C3: no gen_avg_cost or generations in trace meta.json; sheet-topo-bench: not run (as on Paris4, V10).

Kit-compatible labeled events: results/switchbench_natural_v1_0500p2_events.json (own frame, voxel_mm 0.004317, S3 patch_source; not part of the blind review).

## Prior art

Not triggered on the preliminary re-check (Scout Report #8); the formal re-check is at release. Near misses to cite: tifxyz-doctor PR #2 (open draft, 2026-07-30: the frozen cue run on natural collections, 'not natural sheet-switch recall', no per-event labels) and vc-segqa (2026-09-13: one natural switch between official PHerc0139 wraps, no recall). Also growpatch-sheet-switch-detection, sheet-topo-bench (corpus B on PHercParis4: 0 confirmed real errors), windaudit, windcheck, seamcheck, vesuvius-ruled, villa#1641, Stevens pipeline9 and villa satisfaction_metrics / #1621. Wording for release: the first per-event natural-switch corpus with detector recall, not the first natural-data probe.

## Files

- Code (v0 modules untouched, so v0 stays reproducible): tools/switchbench/ ct0, ladder_l0, rule_l0, tune_l0, corpus_v1, confirm_l0, doctor_wrap, doctor_v1, wc_patchmode, seamcheck_run, run_windaudit_v1, detectors_v1, sanity_v1, evaluate_v1, blind_review, blind_review_score, report_v1, write_md_v1.
- results/switchbench_natural_v1.json (all numbers), switchbench_v1_blind_review.md (the packet, no labels).
- Answer key data/switchbench_v1/blind_key.json (gitignored), SHA-256 `835f1836c7758e6548b3f1c716ba12bf3610611e5f9205a8877f5804b1857f7a`.
- Labeled events file (withheld until the review, V15): data/switchbench_v1/switchbench_v1_events.json, SHA-256 `e244a9074017924ff8ceb5a156bad9044f0e902de4f0352570da46caf8036b5a`.
- Disk: v1 data (data/paris4 + data/switchbench_v1) 1.81 GB (cap 10 GB), free 22.8 GB. CT chunks and profiles were streamed into memory; only numeric profiles were stored.

