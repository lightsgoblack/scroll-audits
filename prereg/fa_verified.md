## 5e. SwitchBench FA-on-verified: pre-registered criteria (draft P7, 2026-09-30)
**Status: APPROVED by Colin 2026-09-30 7:54am PT ("criteria approved"), frozen at this commit, before any detector runs on verified patches or any score exists. The draft wording below is kept verbatim.**

**In plain English:** Paul (Vesuvius admin) says the human-verified patches used by spiral fitting are
switch-free for practical purposes. So any alarm a detector raises on them is a false alarm. We count those alarms
to get a trustworthy "cries wolf" rate, and check whether v1's provisional false-alarm number was inflated by
real switches our automated answer key missed.

**Population.** Every patch under `spiral/PHercParis4/verified_patches/` (the set fit_spiral reads), as already
pulled to data/paris4/verified_patches/: 4,923 patches (sha256 of the sorted name list 48ab1b28fbd4fac1...).
3,467 names contain `_sel_` (selections derived from a parent patch); all are scored, and the bootstrap blocks by
parent stem (the name before `_sel_`) so overlapping copies are not treated as independent. Patches with no valid
points are skipped and counted. Ground truth, per Paul (2026-09-30): these patches are switch-free, so every
alarm on them is a false alarm. No human or model adjudicates individual alarms.

**Detectors and settings.** Exactly the leaderboard configurations at the pinned commits, run through the
switchbench kit adapters. PRIMARY: tifxyz-doctor coherent-normal-step, default (the headline row).
SECONDARY (descriptive): tifxyz-doctor any cue; windcheck author-intended patch mode; seamcheck. EXCLUDED as
circular: windaudit and the #1621-style check (both use the human annotations / verified geometry this test
treats as ground truth). A secondary detector that fails to run is reported as "not run", not retried with new
settings.

**Measures.**
- M1 (primary): false alarms per cm2 of verified surface = alarms after the kit's greedy 0.5 mm de-duplication,
  divided by summed patch area (meta.json `area_cm2`), pooled; 95% patch-block bootstrap (B = 2,000,
  seed 20260930, blocks = parent stems).
- M2 (leaderboard-comparable): M1 converted to false alarms per 100 mm, by multiplying by the kit's matching
  corridor (2 x match_mm = 2 mm wide): a 2 mm x 100 mm corridor covers 2 cm2, so FA/100 mm = 2 x M1.
  Labelled as a conversion, not a re-run of the v1 run-based rule.

**Decision rule (primary detector only), comparing M2 to v1's provisional 0.43 FA/100 mm (95% CI [0.14, 0.83]):**
- M2 upper 95% bound < 0.14: **v1 FA overstated.** Most v1 "false alarms" likely sat on missed real switches;
  the README says so and the leaderboard FA column is replaced by the verified-surface rate.
- M2 CI overlaps [0.14, 0.83]: **v1 FA consistent.** The provisional label is lifted, citing this test.
- M2 lower 95% bound > 0.83: **v1 FA understated on clean surface.** Reported as is; the verified-surface rate
  becomes the headline FA number.

**Known confound (stated up front).** Verified patches are human-curated and may be smoother than auto-grown
traces, so their alarm rate is a clean-surface reference, not a like-for-like replica of the v1 negative runs.
"Very very close to switch-free" is not zero: a handful of alarms may sit on real residual switches; that
would bias M1 up, i.e. against the detector, and is reported as a limit.

**Compute and gates.** CPU only, $0, nice -n 10, one job at a time. Order: a seeded shuffle of the sorted names
(seed 20260930). If the first 100 patches project more than 10 h wall for the primary detector, run the
largest seeded prefix that fits and report N; nothing is chosen by looking at results. Numbers only: no CT is
read and no images are made. The v1 blind key is never opened. Runs only after Colin replies
"criteria approved" and the hash is posted in #robots as P7.
