# SwitchBench v1: blind review scored (round 2, 2026-09-27). C1: **SUPPORTED**

**In plain English:** the authors looked at 30 spots without knowing which were which. Of the 12 real-switch
candidates the reviewer could call, the reviewer agreed 10 were real switches. Even allowing for the chance that some of our "real
switches" are mislabelled, the default slip-checker (tifxyz-doctor) catches at most about 1 in 3 of the real,
naturally occurring sheet switches (best estimate about 1 in 9). The pre-registered headline claim holds.

| Quantity | Value |
|---|---|
| Measured precision (confirmed events marked switch / marked either way) | 10/12 = 0.833, Wilson 95% [0.552, 0.953] (3 can't-tell) |
| tifxyz-doctor natural recall, pooled | 0.113 (24/213), patch-block 95% [0.071, 0.159] |
| Precision-corrected upper bound, pooled | 0.159 / 0.552 = **0.287** (< 0.60) |
| Precision-corrected upper bound, new patches only | 0.178 / 0.552 = **0.322** (< 0.60) |
| C1 (frozen rule, P1) | **SUPPORTED** on pooled AND new |
| Robustness | SUPPORTED holds for any precision lower bound >= 0.297 |

## Reviewer answers by kind (for the write-up; disclosed in full)
| Kind | Switch | No switch | Can't tell |
|---|---|---|---|
| Confirmed events (15) | 10 | 2 | 3 |
| CT-contradicted candidates (10) | 7 | 0 | 3 |
| Negative runs (5) | 1 | 4 | 0 |

Caveats that ship with the result:
- **CT-contradicted candidates were mostly marked "switch" (7/10).** On these, the reviewer and the CT-profile
  check disagree. Either the CT check is too strict (some excluded candidates are real switches, which would mean
  the benchmark undercounts switches; it does not inflate the doctor's recall) or the views over-suggest a
  switch at candidate sites. This does not enter C1, which uses confirmed events only. We report it as an open
  question about the CT-contradiction label.
- **Round 1 was not scored.** All 30 answers were "switch", which cannot discriminate. The reviewer was told the packet
  mixes switches and non-switches (not which ones, not how many per kind beyond the frozen design) and re-reviewed
  the same views with clearer instructions (a kink where the layers move together is not a switch). Only round 2 is
  scored. The pre-rendered views are a pre-approved deviation from P1's "numeric CT only" (the settled-rules file).
- One reviewer, 15 confirmed events: the precision interval is wide. The verdict is robust to that width (see Robustness).
