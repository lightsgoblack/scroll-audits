# SwitchBench scorer kit

Score any sheet-switch detector on **SwitchBench-natural**, a corpus of *natural* sheet switches: places
where an auto-grown PHercParis4 trace (GrowPatch `unverified_patches`) jumps from one wrap of the scroll to
the adjacent one on its own, not switches planted by an author. You bring your detector's alarm locations.
The kit reports recall with confidence intervals, false alarms per 100 mm of confirmed switch-free trace,
and coverage (how much of the corpus your detector returned a verdict on). Given the same patch files
(checked by a fingerprint), it gives the same numbers on any machine, and it reproduces the v0 detector
table exactly (see [Reproducibility](#reproducibility)).

v0 corpus (`results/switchbench_natural_v0_events.json`): 54 confirmed switch events in 39 patches, and
594 confirmed negative runs (7,896.5 mm) in 67 scored patches, about 7 MB of patch geometry.

## Score your detector in three commands

You need Python 3.10+ with `numpy`, `scipy` and `tifffile`, plus `huggingface_hub` for `fetch`. Run from
the repository root.

```bash
# 1. Pull only the 67 patches the corpus needs (x/y/z.tif + mask.tif; single-file downloads, ~7 MB)
python -m tools.switchbench_kit fetch --corpus results/switchbench_natural_v0_events.json \
    --out data/switchbench_kit/patches

# 2. Run your detector on each data/switchbench_kit/patches/<patch_id>/ folder (a standard tifxyz
#    patch) and write alarms.json:  {"<patch_id>": [[x, y, z], ...], ...}   (format a, below)

# 3. Score
python -m tools.switchbench_kit score --corpus results/switchbench_natural_v0_events.json \
    --alarms alarms.json --patches-dir data/switchbench_kit/patches --json my_score.json
```

`python -m tools.switchbench_kit list --corpus ...` prints the 67 patch ids. Add `--per-event` to
`score` to list every event with its hit and the distance to your nearest alarm. What `score` prints
(tifxyz-doctor, coherent-normal-step cue, v0 run):

```
| Metric | Value |
|---|---|
| Recall (hits / events) | 0.111 (6/54) |
| 95% Wilson CI | [0.052, 0.222] |
| 95% patch-block bootstrap CI (39 patches) | [0.024, 0.189] |
| False alarms per 100 mm | 0.063 (5 in 7896.5 mm of confirmed negative runs) |
| Coverage: patches with a verdict | 67/67 |
| Coverage: events, negative mm | 54/54 events, 7896.5/7896.5 mm |
| Recall on patches with a verdict | 0.111 (6/54) |
```

Warnings follow the table: patch ids the corpus does not know, alarms far from their patch's surface
(usually a frame or axis-order mistake), grid alarms on invalid vertices, and patches with no verdict.

## Frame and units

- **Coordinates** are level-2 voxels **(x, y, z)** of PHercParis4 volume `20260411134726`: **9.6 um per voxel**
  (2.4 um x 4), so **1 mm = 104.17 voxels**. This is the frame of the patches' own `x.tif`, `y.tif`, `z.tif`,
  so points you read from those files are already in it. Order is x, y, z (not z, y, x).
- **Patch grid**: `x.tif[row, col]` etc., one vertex every 20 voxels (0.19 mm). A vertex is invalid if any
  coordinate is -1 or not finite, if all three are <= 0, or if `mask.tif` is 0 there.
- **Distances** are 3D Euclidean distances in that frame.

## Alarm formats

Give one entry per patch you ran on. **A patch with an empty list has a verdict and raised no alarm. A
patch you leave out (or set to `null`) has no verdict.** The kit reports it under coverage and never
reads it as "no alarm". Patch ids are the folder names (`list` prints them).

**(a) xyz**: corpus-frame points, as JSON.
```json
{"auto_grown_20260420141348215_region_000": [[3966.2, 2242.7, 7444.2]],
 "auto_grown_20260420144817585_region_000": []}
```

**(b) grid**: integer `[row, col]` vertex indices into the patch's tifxyz grid, as JSON. Each alarm sits on
that vertex. Alarms on invalid vertices are dropped and counted.
```json
{"auto_grown_20260420141348215_region_000": [[30, 38]],
 "auto_grown_20260420144817585_region_000": []}
```

**(c) masks**: a directory of `<patch_id>.npz` files, each holding one boolean array with the grid's shape
(`x.tif`'s shape). Every `True` valid vertex is an alarm.
```python
import numpy as np, tifffile
pid = "auto_grown_20260420141348215_region_000"
shape = tifffile.imread(f"data/switchbench_kit/patches/{pid}/x.tif").shape
m = np.zeros(shape, bool); m[30, 38] = True
np.savez_compressed(f"my_masks/{pid}.npz", mask=m)   # then: score --alarms my_masks/
```

A JSON file may also carry a name and declare its format:
`{"detector": "my-detector v2", "format": "xyz", "alarms": {...}}`. Otherwise the format is detected
from the point length (3 numbers = xyz, 2 = grid). You can override it with `--format`. From Python:

```python
from tools.switchbench_kit import load_benchmark, from_xyz, load_alarms, score, format_report
bench = load_benchmark("results/switchbench_natural_v0_events.json", "data/switchbench_kit/patches")
res = score(bench, from_xyz(bench, {"<patch_id>": [[x, y, z]]}))      # or load_alarms(path, bench)
print(format_report(res))
```

## Scoring rules

All of these are SwitchBench-natural's frozen rules (v0 results D10, `tools/switchbench/evaluate.py`), and
the kit applies them identically to every detector.

- **Event points.** Each confirmed event has one or more *transitions*: grid vertices `rc_a` (last vertex
  on the old wrap) and `rc_b` (first vertex on the new wrap) along a grid row or column. A transition
  point is the midpoint of the two vertices. The event centre is the mean of its transition points.
  Those two vertices are usually 1 to 4 grid steps apart (0.2 to 0.8 mm). In 2 of the 54 v0 events,
  though, even the narrowest transition spans more than 10 steps (16 and 133): the trace crosses
  vertices that could not be assigned to a wrap. The match point is still the midpoint, so an alarm at
  either end vertex of such a transition can miss.
- **Match (hit).** A confirmed event is hit if **any** alarm of its patch lies **within 1 mm (3D)** of any
  of its transition points or its centre (`--match-mm`). Recall = hit events / confirmed events.
- **False alarms.** A confirmed negative run is a stretch of >= 10 mm along one grid row or column that
  stays on one wrap. First, the patch's alarms are de-duplicated greedily in the order given: an alarm
  within 0.5 mm of an alarm already kept is dropped (`--fa-dedup-mm`, 0 = off). Every kept alarm within
  1 mm of a vertex of a confirmed run then counts one false alarm for that run, unless it lies within
  1 mm of any candidate event of the patch (confirmed or not). Row and column runs cross, so one alarm
  can count once for each run it touches. Rate = 100 x false alarms / total confirmed run length (mm).
  Hits always use every alarm you submit. The de-dup affects the false-alarm count only.
- **Coverage.** Scored patches are those with >= 1 confirmed event or confirmed run. On a patch with no
  verdict, events count as **misses** (as in v0) and no false alarm can occur. The report gives patches,
  events and run-mm with a verdict, plus recall restricted to patches with a verdict. So leaving patches
  out never helps, and the coverage line shows how much it cost.
- **Per-patch cap** (`--per-patch-cap N`, default none). Counts at most N confirmed events per patch
  toward recall. One RNG (seed) runs over patches sorted by name and picks N of a patch's events, sorted by
  centre, when it has more (SwitchBench v1 rule; v1's headline uses N = 3).
- **Confidence intervals.** Two intervals are reported. The first is a Wilson score 95% interval
  (z = 1.95996). The second is a **patch-block bootstrap** 95% interval: the patches that carry counted
  events are resampled with replacement, B = 2000 times (`--bootstrap`). Each draw's recall is its pooled
  hits / pooled events, and the interval is the 2.5 and 97.5 percentiles (numpy linear). Events cluster in
  patches (up to 10 in one), so the Wilson interval is optimistic: quote the bootstrap. Every run starts a
  fresh RNG seeded **20260925** (`--seed`), so identical hits always give identical intervals.
- **Settings precedence.** A command-line flag beats the corpus file's optional `scoring` block
  (`match_mm`, `per_patch_cap`, `bootstrap`, `seed`, `fa_dedup_mm`), which beats the kit defaults. The JSON
  output records every effective setting and where it came from.

## Output

The text table is shown above. `--json out.json` writes the full result:
- `corpus`: path, sha256, geometry fingerprint check
- `detector`: format, alarm counts, ignored ids, dropped and off-surface alarms
- `settings`
- `recall`: `hits`, `events`, `recall`, `wilson95`, `bootstrap95`
- `false_alarms`: `count`, `negative_mm`, `per_100mm`
- `coverage`
- `events`: one row per confirmed event, with `event_index` (its position in the corpus file), `hit`,
  `nearest_alarm_mm` and `verdict`
- `patches`: per-patch alarms, hits and false alarms

## Reproducibility

- **Geometry checks.** Scoring loads each scored patch and rebuilds every transition point and run from
  the grid with v0's own arithmetic. It then refuses to score if a rebuilt event centre, run end or run
  length disagrees with the corpus file. Separately, it fingerprints the loaded grids (SHA-256) and
  compares the result with the fingerprint the corpus was released on. v0:
  `5efaf7ac4b2ba34a6a018fba88e37e83d438ccc4fbee39a00a47577d714852c9`. The check reads `match` in the header.
  A missing `mask.tif` or a re-exported patch shows `MISMATCH`.
- **Fetch.** `fetch` checks the bucket listing, so a patch that has no `mask.tif` is known rather than
  guessed. It skips files already present with the right size, copies from a local mirror when one exists
  (`--mirror`, default `data/paris4/unverified_patches`), and writes `switchbench_kit_fetch.json`.
- **Regression against v0.** `python -m tools.switchbench_kit.regression` rebuilds the six v0 alarm sets
  from the stored v0 detector outputs with v0's own harness code, scores them through the kit and compares
  every field. It writes `results/switchbench_kit_regression.json`. Result: an **exact match** for all six
  rows under v0 semantics, down to every per-event hit: tifxyz-doctor 6/54 with 5 false alarms in
  7896.5 mm; random 5/54 with 82; windcheck, windaudit and #1621-style 0/54; the same Wilson and bootstrap
  intervals. v0 semantics means counting the alarms exactly as v0's harness passed them (`--fa-dedup-mm 0`)
  and drawing the six bootstrap intervals from one shared stream in table order. Kit defaults change only
  what v0 did inconsistently:
  - v0 drew all six bootstrap intervals from **one** RNG stream, so a row's interval depended on its table
    position. For example, tifxyz-doctor any-cue has exactly the same hits as coherent-normal-step, yet v0
    printed [0.038, 0.191] for it against [0.024, 0.189]. The kit restarts the stream per detector, as v1
    does.
  - v0 de-duplicated the doctor, windcheck and windaudit alarms but not the random ones. With the uniform
    rule, random scores **81** false alarms instead of 82, because two random alarms 0.38 mm apart share a
    negative run.
- **Tests.** `python -m pytest tools/switchbench_kit/tests` (pytest needed). They cover synthetic
  matching, radius, false-alarm, coverage and format cases, equivalence with the v0 helpers, `fetch`
  against a fake bucket, and the v0 regression when `data/paris4` is present.

Reference: what the kit prints for the v0 detector runs (defaults; 54 events, 7896.5 mm of runs).

| Detector | Recall (hits) | Wilson 95% | Bootstrap 95% | FA / 100 mm (count) | Verdict: patches (events) |
|---|---|---|---|---|---|
| tifxyz-doctor (coherent-normal-step) | 0.111 (6/54) | [0.052, 0.222] | [0.024, 0.189] | 0.063 (5) | 67/67 (54) |
| tifxyz-doctor (any cue) | 0.111 (6/54) | [0.052, 0.222] | [0.024, 0.189] | 0.063 (5) | 67/67 (54) |
| windcheck | 0.000 (0/54) | [0.000, 0.066] | [0.000, 0.000] | 0.000 (0) | 13/67 (11) |
| windaudit | 0.000 (0/54) | [0.000, 0.066] | [0.000, 0.000] | 0.000 (0) | 7/67 (11) |
| #1621-style annotation check | 0.000 (0/54) | [0.000, 0.066] | [0.000, 0.000] | 0.000 (0) | 3/67 (10) |
| random at the doctor's alarm density | 0.093 (5/54) | [0.040, 0.199] | [0.022, 0.161] | 1.026 (81) | 67/67 (54) |

## Honest limits

- **The labels are noisy.** v0 confirmed events rest on verified-geometry references plus a numeric CT
  profile at 9.6 um, which is weak evidence. A two-class mixture using human-ladder rates puts their
  precision at about **0.70**: roughly 3 in 10 "confirmed" events may not be real switches. A detector that
  finds every real switch and nothing else would be expected to score about 0.70, not 1.0. Compare
  detectors with each other and with the random baseline, not with 1.0.
- **Small and clustered.** 54 events in 39 patches; one legacy full-size patch holds 10 of them.
  Intervals are wide, and the Wilson interval understates them.
- **False alarms are measured on the easy part.** Negatives are >= 10 mm single-wrap runs along grid
  rows and columns, and at most 20 runs per patch were CT-checked. The false-alarm rate is a floor on
  what a detector does elsewhere, not a precision measurement.
- **Where a switch is.** An event is located by the midpoint of its transition vertices. For 2 of 54
  events those vertices are more than 10 grid steps apart, so the location is uncertain by more than the
  1 mm match radius.
- **Scope.** One scroll (PHercParis4), auto-grown GrowPatch traces, adjacent-wrap switches only (7
  multi-wrap jumps were logged but are not scored, and are not excluded from false alarms).
- **This corpus is v0; v1 is the current headline.** v1 (results/switchbench_natural_v1.md) has more patches,
  labels re-confirmed at 2.4 um, and per-patch cap 3 as the default. The kit reads the v1 file with the same
  field names, plus optional `scoring` and `geometry_sha256` blocks; pass `--per-patch-cap 3` if a v1 file has
  no `scoring` block. v1's own honest limits differ from v0's above -- notably measured (not mixture-estimated)
  label precision of 0.833 from a single reviewer's blind review, and an open 7/10 split where the reviewer and
  the CT check disagree on 10 "contradicted" candidates that are not scored either way: see
  results/switchbench_natural_v1_blind_review_score.md.

## Corpus file fields the kit reads

`events[]`: `patch`, `status` (only `confirmed` counts), `transitions[]` with `rc_a`, `rc_b`, and `xyz`
(checked, rounded to 0.1 vx). `negatives[]`: `patch`, `status`, `axis` (`row` or `col`), `rc0`, `rc1` (run
ends, inclusive), plus `len_mm`, `xyz0` and `xyz1` (checked). Optional: `scroll`, `frame`, `voxel_mm`
(default 0.0096), `patch_source` `{bucket, prefix}` (default: HF bucket `scrollprize/datasets`,
`spiral/PHercParis4/unverified_patches`), `scoring`, `geometry_sha256`.

## Files

`__main__.py` (CLI), `corpus.py` (corpus and geometry checks), `geometry.py` (tifxyz loading, event points,
run lengths, fingerprint), `alarms.py` (the three input formats), `scoring.py` (matching, false alarms,
coverage, intervals), `report.py` (table and JSON), `fetch.py` (patch download), `regression.py` (v0
reproduction), `tests/`. Scoring needs nothing from `tools/switchbench`. `fetch` takes v0's bucket layout
from `tools/switchbench/pull.py` unless the corpus names its own `patch_source`. The regression and
equivalence tests run v0's code. The kit produces no images.

## Adapters: converting a detector's own output to alarms JSON

**In plain English:** each public sheet-switch checker (tifxyz-doctor, windcheck, windaudit, seamcheck,
the #1621-style check) prints its results in its own private format. You don't have to hand-write the
`{"patch_id": [[x,y,z], ...]}` file yourself -- run the tool as normal, then run one command to convert
its own output into what `score`/`leaderboard` read:

```bash
python -m tools.switchbench_kit adapt <tool> <native_output_path> --out alarms.json
```

`<tool>` is one of `tifxyz-doctor`, `windcheck`, `windaudit`, `seamcheck`, `check1621`. `--help` on each
(`python -m tools.switchbench_kit adapt tifxyz-doctor --help`) lists its extra flags:

- **tifxyz-doctor**: `<native_output_path>` is a directory of `<patch_id>.json` files, each the CLI's own
  `tifxyz-doctor audit <patch> --json <out>` report. `--mode cli` (default) reads the report's own
  "coherent-normal-step" example list, exactly as v0's leaderboard did. `--mode api-mask --side <dir>`
  additionally unions in the tool's internal `coherent_normal_step_cells` mask (the "API mask" variant
  used for v1; `--side` points at a directory of doctor_wrap.py's captured "side" JSON, one per patch).
  Output alarms are grid cells `[row, col]`; score with `--patches-dir` so the kit can locate them in 3-D.
- **windcheck**: `<native_output_path>` is a directory holding one subdirectory per patch, each windcheck's
  own `check <patch> --out <dir>` output (its `*_points.json` files). `--mode patch` instead reads the raw
  JSON written by the author-documented small-patch call (`bench/patch_audit.py: audit_one`, no cell-count
  floor), one `<patch_id>.json` file per patch.
- **windaudit**: `<native_output_path>` is a directory of one subdirectory per patch, each windaudit's own
  output (`measured_edges.json`, `after_full.json`). Needs `--patches-dir` (the root of `<patch_id>/x.tif`
  etc.) to look up the alarm point's 3-D coordinates.
- **seamcheck**: `<native_output_path>` is a directory of `<patch_id>.json` files, each seamcheck's own
  verdict + flagged-step list; alarms are the flagged steps of a REVIEW/WATCH patch.
- **check1621**: `<native_output_path>` is a directory of `<patch_id>.json` files, each the #1621-style
  check's own output; alarms are both points of every flagged pair.

Every adapter's parsing rule is copied from the exact code that scored that tool for the v0/v1
leaderboards (`tools/switchbench/detectors_v1.py`, `doctor_v1.py`, `run_windaudit_v1.py`,
`seamcheck_run.py`, `wc_patchmode.py`) -- an adapted file scores the same alarms those did. v0 itself
never kept the raw tool output on disk (only the already-parsed alarm records survive under
`data/paris4/detect/`), so `tests/test_adapters.py` checks the adapters against small fixture files
shaped like each tool's real output, and against that inline v0 logic directly, rather than replaying a
stored native file.

## Strata (abrupt vs. gradual switches)

`leaderboard --strata strata.json` shows recall split by whether each confirmed event was an abrupt
(sudden, one-step) or gradual (drifting) sheet switch. Build that file with:

```bash
python -m tools.switchbench_kit.strata_gen --explore results/switchbench_explore.json --out strata.json
```

**In plain English:** it doesn't invent a new rule for "abrupt" -- it reads back the classification
tools/switchbench/explore_abruptness.py already worked out per event (the sheet-frame definition:
whether the trace's largest single-step offset, measured in the sheet's own local frame, crosses 8
voxels) and reshapes it into the leaderboard's strata format. On the v0 corpus this reproduces the
exploratory report exactly: tifxyz-doctor 5/24 recall on abrupt switches, 1/30 on gradual ones.

For v1, `explore_abruptness.py` takes a `--v1` flag (with `EXPLORE_MODE=v1` set; see the module's own
docstring) that points it at the pooled v1 corpus instead of v0's, and its `report` stage there writes
only the abrupt/gradual classification (no doctor operating-point sweep, out of scope for this):

```bash
EXPLORE_MODE=v1 EXPLORE_DIR=data/switchbench_v1/explore_abruptness nice -n 10 \
    python -m tools.switchbench.explore_abruptness geom --v1     # resumable, checkpoints per patch
EXPLORE_MODE=v1 EXPLORE_DIR=data/switchbench_v1/explore_abruptness \
    python -m tools.switchbench.explore_abruptness report --v1
python -m tools.switchbench_kit.strata_gen --explore results/switchbench_natural_v1_abruptness.json \
    --out results/switchbench_natural_v1_leaderboard/strata_sf.json
```

## Leaderboard (several detectors at once)

```bash
python -m tools.switchbench_kit leaderboard --corpus <events.json> --entries entries.json \
    [--strata strata.json] --out leaderboard/
```

`entries.json` lists detectors: `{"entries": [{"name": "...", "alarms": "path/to/alarms.json", "tool": "repo@commit",
"mode": "default" | "author-intended" | "tuned", "notes": "..."}]}`. The optional `strata.json` maps events to
strata, keyed by coordinates (event numbering is not stable across tools):
`{"<patch>|<x>,<y>,<z>": "abrupt" | "gradual"}`, with xyz rounded to 0.1 voxel. The command writes
`leaderboard.md`, `leaderboard.json` and a self-contained `leaderboard.html` (light and dark mode). Rows sort by
recall, then fewer false alarms. Coverage sits next to recall, because a detector with few verdicts is limited in
scope, not wrong. Every row equals what `score` prints for the same inputs.
