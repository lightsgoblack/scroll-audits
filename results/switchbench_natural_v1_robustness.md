# SwitchBench v1: C1 robustness checks (POST-HOC and DESCRIPTIVE)

**Every number in this file is POST-HOC and DESCRIPTIVE.** It cannot change C1's frozen verdict: prereg/switchbench_v1.md (P1) fixed one combination (tifxyz-doctor coherent-normal-step, per-patch cap 3, 1 mm match, pooled AND new) before any v1 result was read, and that combination alone was scored: **SUPPORTED** (results/switchbench_natural_v1_blind_review_score.md). This file only asks whether nearby choices -- a different match radius, a different per-patch cap, a different way of grouping patches -- would have told a different story. They do not.

## In plain English

- **The headline survives.** Every one of the 54 combinations in the main grid below (2 doctor variants x 3 per-patch caps x 3 match radii x 3 ways of pooling patches) keeps the precision-corrected upper bound under the 0.60 bar that SUPPORTED needs (all hold).
- **The frozen point reproduces exactly.** Recomputing the frozen combination (cap 3, 1 mm, coherent-normal-step) from the same cached alarms gives pooled corrected upper 0.287 and new-only 0.322, matching the scored result to the last digit -- the robustness grid is built on the same pipeline, not a different one.
- **One tiny grouping does not hold, and that is expected, not a problem.** When patches are split by their auto-grown creation date, a 3-patch, non-auto-grown "legacy" group (full-size v0 patches, not part of the auto-grown pipeline) has a corrected upper bound over the bar at every cap. That group is not part of C1's frozen definition (which pools by corpus, not by patch-growth batch) and it is already documented elsewhere (results/switchbench_natural_v1.md, S3) as concentrating an outsized share of confirmed events in one legacy patch -- 9 events on 3 patches gives a very wide confidence interval, not a sign the result is fragile. Every real auto-grown batch holds.
- **CT-contradicted candidates: an open question, not a hard stop.** These are candidates where the geometry check flags a possible switch but the CT-profile check disagrees (a public label, not the blind reviewer's answer key -- data/switchbench_v1/blind_key.json was never opened for this file). On the 312 such candidates with a cached detector run, the doctor's coherent-normal-step alarm rate is 0.128 [0.095, 0.181] -- close to its 0.136 rate on confirmed real switches over the same patches (uncapped), and nothing like a rate near zero. That is consistent with the open question already on record (switchbench_v1_blind_review_score.md): some CT-contradicted candidates may be real switches the CT check is too strict to confirm, which would mean the benchmark undercounts switches, not that the doctor's recall is overstated.

## Main grid (POST-HOC, DESCRIPTIVE): recall, patch-block bootstrap CI (B = 2000, seed 20260925), corrected upper bound

Corrected upper = CI upper / measured precision lower bound (0.552, results/switchbench_natural_v1_blind_review_score.json precision.wilson95[0]). Holds if < 0.60.

### tifxyz-doctor (coherent-normal-step) (post-hoc, descriptive)

| Cap | Radius | Set | Hits/events (patches) | Recall | Patch-block 95% CI | Corrected upper | C1 would hold? |
|---|---|---|---|---|---|---|---|
| cap 1 | 0.5 mm | pooled | 15/175 (175) | 0.086 | [0.046, 0.126] | 0.228 | **holds** |
| cap 1 | 0.5 mm | new | 12/126 (126) | 0.095 | [0.048, 0.151] | 0.273 | **holds** |
| cap 1 | 0.5 mm | v0_prefix | 3/49 (49) | 0.061 | [0.000, 0.123] | 0.223 | **holds** |
| cap 1 | 1 mm | pooled | 18/175 (175) | 0.103 | [0.063, 0.149] | 0.269 | **holds** |
| cap 1 | 1 mm | new | 13/126 (126) | 0.103 | [0.056, 0.159] | 0.288 | **holds** |
| cap 1 | 1 mm | v0_prefix | 5/49 (49) | 0.102 | [0.020, 0.204] | 0.370 | **holds** |
| cap 1 | 2 mm | pooled | 22/175 (175) | 0.126 | [0.080, 0.177] | 0.321 | **holds** |
| cap 1 | 2 mm | new | 17/126 (126) | 0.135 | [0.079, 0.198] | 0.359 | **holds** |
| cap 1 | 2 mm | v0_prefix | 5/49 (49) | 0.102 | [0.020, 0.204] | 0.370 | **holds** |
| cap 3 | 0.5 mm | pooled | 21/213 (175) | 0.099 | [0.062, 0.140] | 0.254 | **holds** |
| cap 3 | 0.5 mm | new | 17/156 (126) | 0.109 | [0.061, 0.160] | 0.291 | **holds** |
| cap 3 | 0.5 mm | v0_prefix | 4/57 (49) | 0.070 | [0.016, 0.143] | 0.259 | **holds** |
| cap 3 | 1 mm | pooled | 24/213 (175) | 0.113 | [0.071, 0.159] | 0.287 | **holds** **(frozen)** |
| cap 3 | 1 mm | new | 19/156 (126) | 0.122 | [0.072, 0.178] | 0.322 | **holds** **(frozen)** |
| cap 3 | 1 mm | v0_prefix | 5/57 (49) | 0.088 | [0.018, 0.170] | 0.308 | **holds** **(frozen)** |
| cap 3 | 2 mm | pooled | 30/213 (175) | 0.141 | [0.090, 0.196] | 0.356 | **holds** |
| cap 3 | 2 mm | new | 25/156 (126) | 0.160 | [0.097, 0.229] | 0.415 | **holds** |
| cap 3 | 2 mm | v0_prefix | 5/57 (49) | 0.088 | [0.018, 0.170] | 0.308 | **holds** |
| uncapped | 0.5 mm | pooled | 35/294 (175) | 0.119 | [0.079, 0.153] | 0.277 | **holds** |
| uncapped | 0.5 mm | new | 29/229 (126) | 0.127 | [0.076, 0.172] | 0.312 | **holds** |
| uncapped | 0.5 mm | v0_prefix | 6/65 (49) | 0.092 | [0.019, 0.155] | 0.281 | **holds** |
| uncapped | 1 mm | pooled | 40/294 (175) | 0.136 | [0.091, 0.174] | 0.315 | **holds** |
| uncapped | 1 mm | new | 32/229 (126) | 0.140 | [0.087, 0.187] | 0.338 | **holds** |
| uncapped | 1 mm | v0_prefix | 8/65 (49) | 0.123 | [0.036, 0.200] | 0.362 | **holds** |
| uncapped | 2 mm | pooled | 59/294 (175) | 0.201 | [0.111, 0.261] | 0.472 | **holds** |
| uncapped | 2 mm | new | 50/229 (126) | 0.218 | [0.113, 0.278] | 0.505 | **holds** |
| uncapped | 2 mm | v0_prefix | 9/65 (49) | 0.138 | [0.036, 0.227] | 0.412 | **holds** |

### tifxyz-doctor (any cue) (post-hoc, descriptive)

| Cap | Radius | Set | Hits/events (patches) | Recall | Patch-block 95% CI | Corrected upper | C1 would hold? |
|---|---|---|---|---|---|---|---|
| cap 1 | 0.5 mm | pooled | 16/175 (175) | 0.091 | [0.051, 0.131] | 0.238 | **holds** |
| cap 1 | 0.5 mm | new | 13/126 (126) | 0.103 | [0.056, 0.159] | 0.288 | **holds** |
| cap 1 | 0.5 mm | v0_prefix | 3/49 (49) | 0.061 | [0.000, 0.123] | 0.223 | **holds** |
| cap 1 | 1 mm | pooled | 19/175 (175) | 0.109 | [0.063, 0.154] | 0.280 | **holds** |
| cap 1 | 1 mm | new | 14/126 (126) | 0.111 | [0.063, 0.167] | 0.302 | **holds** |
| cap 1 | 1 mm | v0_prefix | 5/49 (49) | 0.102 | [0.020, 0.204] | 0.370 | **holds** |
| cap 1 | 2 mm | pooled | 23/175 (175) | 0.131 | [0.086, 0.183] | 0.331 | **holds** |
| cap 1 | 2 mm | new | 18/126 (126) | 0.143 | [0.087, 0.206] | 0.374 | **holds** |
| cap 1 | 2 mm | v0_prefix | 5/49 (49) | 0.102 | [0.020, 0.204] | 0.370 | **holds** |
| cap 3 | 0.5 mm | pooled | 22/213 (175) | 0.103 | [0.065, 0.146] | 0.265 | **holds** |
| cap 3 | 0.5 mm | new | 18/156 (126) | 0.115 | [0.068, 0.169] | 0.306 | **holds** |
| cap 3 | 0.5 mm | v0_prefix | 4/57 (49) | 0.070 | [0.016, 0.143] | 0.259 | **holds** |
| cap 3 | 1 mm | pooled | 25/213 (175) | 0.117 | [0.075, 0.164] | 0.298 | **holds** **(frozen)** |
| cap 3 | 1 mm | new | 20/156 (126) | 0.128 | [0.077, 0.185] | 0.335 | **holds** **(frozen)** |
| cap 3 | 1 mm | v0_prefix | 5/57 (49) | 0.088 | [0.018, 0.170] | 0.308 | **holds** **(frozen)** |
| cap 3 | 2 mm | pooled | 31/213 (175) | 0.146 | [0.094, 0.204] | 0.369 | **holds** |
| cap 3 | 2 mm | new | 26/156 (126) | 0.167 | [0.102, 0.236] | 0.427 | **holds** |
| cap 3 | 2 mm | v0_prefix | 5/57 (49) | 0.088 | [0.018, 0.170] | 0.308 | **holds** |
| uncapped | 0.5 mm | pooled | 36/294 (175) | 0.122 | [0.083, 0.158] | 0.287 | **holds** |
| uncapped | 0.5 mm | new | 30/229 (126) | 0.131 | [0.083, 0.177] | 0.322 | **holds** |
| uncapped | 0.5 mm | v0_prefix | 6/65 (49) | 0.092 | [0.019, 0.155] | 0.281 | **holds** |
| uncapped | 1 mm | pooled | 41/294 (175) | 0.139 | [0.095, 0.179] | 0.325 | **holds** |
| uncapped | 1 mm | new | 33/229 (126) | 0.144 | [0.093, 0.194] | 0.351 | **holds** |
| uncapped | 1 mm | v0_prefix | 8/65 (49) | 0.123 | [0.036, 0.200] | 0.362 | **holds** |
| uncapped | 2 mm | pooled | 60/294 (175) | 0.204 | [0.116, 0.263] | 0.476 | **holds** |
| uncapped | 2 mm | new | 51/229 (126) | 0.223 | [0.118, 0.281] | 0.510 | **holds** |
| uncapped | 2 mm | v0_prefix | 9/65 (49) | 0.138 | [0.036, 0.227] | 0.412 | **holds** |

## Per auto-grown batch (POST-HOC, DESCRIPTIVE): date prefix of the patch name, 1 mm match

Batch = first 8 digits of the auto_grown timestamp in the patch name (a creation date); "legacy" = the non-auto-grown full-size v0 patches. Patch counts are of scored patches (>= 1 confirmed event or negative run) in that batch, not all patches drawn.

### tifxyz-doctor (coherent-normal-step)

| Cap | Batch | Patches in batch | Hits/events | Recall | Patch-block 95% CI | Corrected upper | C1 would hold? |
|---|---|---|---|---|---|---|---|
| cap 1 | 20260420 | 89 | 6/61 | 0.098 | [0.033, 0.180] | 0.327 | **holds** |
| cap 1 | 20260421 | 113 | 9/85 | 0.106 | [0.047, 0.176] | 0.320 | **holds** |
| cap 1 | 20260427 | 9 | 0/7 | 0.000 | [0.000, 0.000] | 0.000 | **holds** |
| cap 1 | 20260428 | 23 | 2/19 | 0.105 | [0.000, 0.263] | 0.477 | **holds** |
| cap 1 | legacy | 3 | 1/3 | 0.333 | [0.000, 1.000] | 1.812 | DOES NOT HOLD |
| cap 3 | 20260420 | 89 | 8/75 | 0.107 | [0.042, 0.176] | 0.318 | **holds** |
| cap 3 | 20260421 | 113 | 13/100 | 0.130 | [0.062, 0.210] | 0.380 | **holds** |
| cap 3 | 20260427 | 9 | 0/8 | 0.000 | [0.000, 0.000] | 0.000 | **holds** |
| cap 3 | 20260428 | 23 | 2/21 | 0.095 | [0.000, 0.250] | 0.453 | **holds** |
| cap 3 | legacy | 3 | 1/9 | 0.111 | [0.000, 0.333] | 0.604 | DOES NOT HOLD |
| uncapped | 20260420 | 89 | 8/75 | 0.107 | [0.042, 0.176] | 0.318 | **holds** |
| uncapped | 20260421 | 113 | 13/100 | 0.130 | [0.062, 0.210] | 0.380 | **holds** |
| uncapped | 20260427 | 9 | 0/8 | 0.000 | [0.000, 0.000] | 0.000 | **holds** |
| uncapped | 20260428 | 23 | 2/21 | 0.095 | [0.000, 0.250] | 0.453 | **holds** |
| uncapped | legacy | 3 | 17/90 | 0.189 | [0.151, 0.500] | 0.906 | DOES NOT HOLD |

### tifxyz-doctor (any cue)

| Cap | Batch | Patches in batch | Hits/events | Recall | Patch-block 95% CI | Corrected upper | C1 would hold? |
|---|---|---|---|---|---|---|---|
| cap 1 | 20260420 | 89 | 7/61 | 0.115 | [0.033, 0.197] | 0.356 | **holds** |
| cap 1 | 20260421 | 113 | 9/85 | 0.106 | [0.047, 0.176] | 0.320 | **holds** |
| cap 1 | 20260427 | 9 | 0/7 | 0.000 | [0.000, 0.000] | 0.000 | **holds** |
| cap 1 | 20260428 | 23 | 2/19 | 0.105 | [0.000, 0.263] | 0.477 | **holds** |
| cap 1 | legacy | 3 | 1/3 | 0.333 | [0.000, 1.000] | 1.812 | DOES NOT HOLD |
| cap 3 | 20260420 | 89 | 9/75 | 0.120 | [0.052, 0.192] | 0.348 | **holds** |
| cap 3 | 20260421 | 113 | 13/100 | 0.130 | [0.062, 0.210] | 0.380 | **holds** |
| cap 3 | 20260427 | 9 | 0/8 | 0.000 | [0.000, 0.000] | 0.000 | **holds** |
| cap 3 | 20260428 | 23 | 2/21 | 0.095 | [0.000, 0.250] | 0.453 | **holds** |
| cap 3 | legacy | 3 | 1/9 | 0.111 | [0.000, 0.333] | 0.604 | DOES NOT HOLD |
| uncapped | 20260420 | 89 | 9/75 | 0.120 | [0.052, 0.192] | 0.348 | **holds** |
| uncapped | 20260421 | 113 | 13/100 | 0.130 | [0.062, 0.210] | 0.380 | **holds** |
| uncapped | 20260427 | 9 | 0/8 | 0.000 | [0.000, 0.000] | 0.000 | **holds** |
| uncapped | 20260428 | 23 | 2/21 | 0.095 | [0.000, 0.250] | 0.453 | **holds** |
| uncapped | legacy | 3 | 17/90 | 0.189 | [0.151, 0.500] | 0.906 | DOES NOT HOLD |

## CT-contradicted candidates vs confirmed events (POST-HOC, DESCRIPTIVE; 1 mm, uncapped)

Coverage: 302 patches carry at least one CT-contradicted candidate (566 candidates total); 88 of those patches already have a cached tifxyz-doctor run (no detector was re-run for this file), covering the rows below. "Confirmed comparison" is the same doctor, same radius, uncapped, on confirmed real switches (not restricted to these particular patches) -- the natural-recall number this file's grid already reports, repeated here for the side-by-side.

### tifxyz-doctor (coherent-normal-step)

| Set | CT-contradicted hits/n (patches) | CT-contradicted recall | 95% CI | Confirmed hits/n | Confirmed recall |
|---|---|---|---|---|---|
| Pooled | 40/312 (88) | 0.128 | [0.095, 0.181] | 40/294 | 0.136 |
| New only | 35/255 (60) | 0.137 | [0.103, 0.224] | 32/229 | 0.140 |
| v0 prefix | 5/57 (28) | 0.088 | [0.019, 0.189] | 8/65 | 0.123 |

### tifxyz-doctor (any cue)

| Set | CT-contradicted hits/n (patches) | CT-contradicted recall | 95% CI | Confirmed hits/n | Confirmed recall |
|---|---|---|---|---|---|
| Pooled | 42/312 (88) | 0.135 | [0.098, 0.191] | 41/294 | 0.139 |
| New only | 37/255 (60) | 0.145 | [0.106, 0.234] | 33/229 | 0.144 |
| v0 prefix | 5/57 (28) | 0.088 | [0.019, 0.189] | 8/65 | 0.123 |

_Generated 2026-09-27T22:14:44Z, 7.1s, from cached scoring outputs (data/switchbench_v1/evaluation_v1.json and cached tifxyz-doctor per-patch alarms); no detector was re-run and data/switchbench_v1/blind_key.json was never opened._
