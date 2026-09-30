# P7 result: detector false alarms on the verified (switch-free) patches -- V1_FA_CONSISTENT

**Protocol:** prereg/fa_verified.md (sha256 bc55e3aa..., posted in #robots as P7 on 2026-09-30 before any
run). Deviations D1 and D2 (below) were logged with the protocol history; both were written down after the detector run finished and
before any score was computed. Numbers: results/fa_verified.json. Code: tools/fa_verified/run.py.

## In plain English

The Vesuvius team says the human-verified patches used for spiral fitting are, for practical purposes, free of
sheet switches. So any alarm a detector raises on them is a false alarm. We ran the most-used detector,
tifxyz-doctor, on all of them. It cried wolf at about the same rate as our v1 benchmark measured. That means v1's
false-alarm number was not inflated by real switches our automated answer key missed, so the "provisional" label
comes off, as the pre-registered rule says.

## Result (primary detector: tifxyz-doctor coherent-normal-step, default)

| | patches | area | false alarms | per cm2 [95% CI] | per 100 mm [95% CI] |
|---|---|---|---|---|---|
| **Primary, as frozen** (meta `area_cm2`) | 798 | 3,503 cm2 | 650 | 0.186 [0.136, 0.239] | **0.37 [0.27, 0.48]** |
| Secondary (grid area, all patches) | 4,921 | 5,307 cm2 | 1,621 | 0.305 [0.233, 0.391] | 0.61 [0.47, 0.78] |
| v1 benchmark (provisional) | 237 | -- | -- | -- | 0.43 [0.14, 0.83] |

**Verdict (pre-registered rule): V1_FA_CONSISTENT.** The primary interval [0.27, 0.48] overlaps v1's [0.14, 0.83].
The secondary gives the same verdict.

Descriptive, tifxyz-doctor any cue: 0.85 [0.60, 1.09] per 100 mm (primary set), 1.92 [1.42, 2.56] (all patches).
Alarms were on 73 of 798 patches (primary, coherent-normal-step) and 234 of 4,921 (all).

## Deviations

- **D1.** The frozen count of 4,923 included `backups/`, a folder of backup copies, not a patch. It errored in the
  pipeline and is excluded: 4,922 real patches, 0 skipped for no valid points, 0 not run.
- **D2.** Only 798 of the 4,922 patches carry the frozen denominator field `area_cm2` (697 carry only `area_vx2`,
  3,427 carry neither). This was not checked before freezing. The primary number uses those 798 as frozen; the
  secondary uses every patch with area measured from its own vertex grid. On the 798, grid area / `area_cm2` has
  median 0.89 (5th-95th percentile 0.08-1.00), so the grid measure tends to under-count area and the secondary
  rate leans high.

## Limits

- The per-100-mm figure converts an area rate using the kit's 2 mm matching corridor (2 x M1); it is not a re-run
  of v1's run-based rule.
- Verified patches are human-curated and may be smoother than auto-grown traces, so this is a clean-surface
  reference, not a replica of v1's negative runs.
- "Very very close to switch-free" is not zero; any residual real switch would push these rates up, against the
  detector.
- Secondary detectors (windcheck patch mode, seamcheck) listed in the protocol were not run in this pass; they
  are reported as not run.
