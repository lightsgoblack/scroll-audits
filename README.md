# scroll-audits

Pre-registered audits of Vesuvius Challenge data and tools. Every test here had its pass/fail rules frozen before it ran, and the SHA-256 hashes of those rules were posted publicly before any score or verdict existed, so anyone can check that nothing moved.

## SwitchBench-natural: real sheet switches vs the detectors built to catch them

> **In plain English:** the Herculaneum scrolls are rolled-up papyrus, burned by Vesuvius, that can only be read by
> scanning them and unrolling them digitally. Software traces each papyrus layer through the 3D scan. Sometimes the
> tracer slips and jumps onto the neighbouring layer (a "sheet switch"), which scrambles the text you'd read there.
> Tools exist to catch these slips, but they were only ever tested on fake slips their authors planted. We collected
> real slips from the scans and measured how many each tool actually catches. Anyone can re-run the test on their own tool.

A *sheet switch* is where an automatically grown surface trace jumps from one wrap of the scroll to the next. Public detectors for this error are validated on switches planted by their authors. SwitchBench-natural tests them on 213 switches that happened on their own in auto-grown PHercParis4 traces, each confirmed two independent ways (verified-surface geometry and CT intensity profiles).

**Result (pre-registered claim C1: SUPPORTED).** Run with its published defaults (CPU only) on 213 confirmed natural switches in PHercParis4, tifxyz-doctor, the most-used public sheet-switch detector, caught 11% (24/213). After correcting for label errors measured in a blind review (precision 83%, one reviewer), its natural recall is at most 29% (upper 95% bound). It caught 25% (22/89) of abrupt switches but only 2% (2/122) of gradual ones. Its author's own validation reports 97% on planted switches, measured on a finer voxel grid than ours, so the two figures are not a side-by-side comparison.

*In plain English:* the most-used slip checker misses most real slips in this scroll, and it almost never notices a slow drift from one layer to the next. Its high published score came from a different setup, so there is no contradiction; it is why a test on real slips was needed.

**Why this matters.** The Vesuvius Challenge lists sheet switches as a named pipeline bottleneck, with "conservative failure detection" as what would help ([2026 Open Problems](https://scrollprize.org/2026_open_problems)). A detector can only be trusted on real scroll data once it has been measured on real, naturally occurring switches; this benchmark provides that measurement.
In plain English: the organisers have said slips between layers are one of the main things holding the pipeline back; this is the first test that shows how well the slip-catchers actually work on real slips.

# SwitchBench-natural leaderboard (PHercParis4)

Generated 2026-09-27T20:01:11Z with switchbench_kit 1.0.0. Corpus sha256 `e244a9074017924f...`; matching 1.0 mm; per-patch cap 3; false alarms deduplicated at 0.5 mm.

| Detector | Mode | Recall | 95% CI (Wilson) | False alarms / 100 mm | FA 95% CI (bootstrap) | Patches with a verdict | Scope | Recall: abrupt | Recall: gradual | Tool @ commit |
|---|---|---|---|---|---|---|---|---|---|---|
| tifxyz-doctor (any cue) | default | 12% (25/213) | [8%, 17%] | 0.43 | [0.15, 0.84] | 237/237 | Full | 26% (23/89) | 2% (2/122) | tifxyz-doctor@5ca0444 |
| tifxyz-doctor (coherent-normal-step) | default | 11% (24/213) | [8%, 16%] | 0.43 | [0.14, 0.83] | 237/237 | Full | 25% (22/89) | 2% (2/122) | tifxyz-doctor@5ca0444 |
| windcheck [author-intended: patch mode, no cell floor] | author-intended | 0% (1/213) | [0%, 3%] | 0.00 | [0.00, 0.00] | 237/237 | Full | 1% (1/89) | 0% (0/122) | windcheck@2b0fb2f |
| seamcheck [secondary, added after freeze] | author-intended | 0% (0/213) | [0%, 2%] | 0.00 | [0.00, 0.00] | 236/237 | Full | 0% (0/89) | 0% (0/122) | seamcheck@6d6bc2d |
| windcheck | default | 0% (0/213) | [0%, 2%] | 0.00 | [0.00, 0.00] | 28/237 | Limited scope | 0% (0/89) | 0% (0/122) | windcheck@2b0fb2f |
| windaudit | default | 0% (0/213) | [0%, 2%] | 0.00 | [0.00, 0.00] | 31/237 | Limited scope | 0% (0/89) | 0% (0/122) | windaudit@aba5633 |
| #1621-style annotation check | default | 0% (0/213) | [0%, 2%] | 0.00 | [0.00, 0.00] | 13/237 | Limited scope | 0% (0/89) | 0% (0/122) | ours (annot.check_1621) |
| windaudit [author-intended: attachment 0.45 D] | author-intended | 0% (0/213) | [0%, 2%] | 0.04 | [0.00, 0.10] | 48/237 | Limited scope | 0% (0/89) | 0% (0/122) | windaudit@aba5633 |

Coverage matters: a detector with few patches with a verdict is limited in scope here, not wrong -- it's flagged **Limited scope** (fewer than half the patches got a verdict) and sorted after full-coverage detectors at the same recall, so a 0% false-alarm rate on a sliver of the corpus doesn't rank above a detector that covered it all. Every row is reproducible with `python -m tools.switchbench_kit score` on the same inputs.


tifxyz-doctor (coherent-normal-step) caught 25% (22/89) of abrupt switches but only 2% (2/122) of gradual ones.

Full results, sanity checks and every deviation: [results/switchbench_natural_v1.md](results/switchbench_natural_v1.md). The
blind-review scoring behind the verdict above (measured precision, the reviewer's answers by kind, and caveats
including a 7/10 split on CT-contradicted candidates and the one-reviewer/one-round limit):
[results/switchbench_natural_v1_blind_review_score.md](results/switchbench_natural_v1_blind_review_score.md). Limits: Small, single-scroll corpus (PHercParis4), CPU-only detectors, and a held-out label rule whose false-pass ceiling is reported alongside every recall number.

### Known limits of the answer key (added Sep 30, 2026, after review feedback)

> **In plain English:** a benchmark is only as trustworthy as its answer key. Ours was built with automated
> rules plus a small human spot-check, not by a person checking every switch. That is enough for the headline
> recall number, but not yet for the false-alarm column.

The pre-registered results above are unchanged; this section adds context on how far to trust each number.

- **Recall (the headline)** depends only on the labelled events being real switches (label precision), not on
  having found every switch. A blind human spot-check found 10 of 12 real (one reviewer, 12 events, so a small
  sample). Allowing for label errors, tifxyz-doctor's natural recall stays at or below 29% (upper 95% bound).
- **False alarms / 100 mm are provisional.** They are counted only on surface our rules marked clean, but those
  rules are automated, not an exhaustive human annotation. A real switch the rules missed would count against a
  detector as a false alarm, so these rates may be too high. Treat them as rough estimates, not ground truth.
- **Fix in progress:** SwitchBench v1.1 will add a fully human-verified subset: segments where every switch is
  annotated and every annotation is checked. Pointers to segments that are already exhaustively annotated are very
  welcome (please open an issue).

Thanks to Paul (pmh47) on the Vesuvius Challenge Discord for pointing out that a trustworthy signal needs a
close to 100% human-verified answer key.


## Score your detector in three commands

**Download size:** `switchbench fetch` pulls about 30 MB of small patch files, typically under a minute
on an ordinary connection. Nothing else in either route downloads anything larger.

**In plain English:** you don't need to clone this repo to try your detector against SwitchBench --
one `pip install` line gets you a `switchbench` command. Cloning instead is only for reading the code
or the other tools (the corpus builder, the harness). Pick one:

```bash
# route 1: install only (no local copy of the code)
python -m pip install git+https://github.com/lightsgoblack/scroll-audits
switchbench fetch --corpus results/switchbench_natural_v1_events.json --out data/patches

# route 2: clone, then install
git clone https://github.com/lightsgoblack/scroll-audits && cd scroll-audits
python -m pip install -e .
switchbench fetch --corpus results/switchbench_natural_v1_events.json --out data/patches
```

Either way, run your detector on each `data/patches/<patch_id>/` (a standard tifxyz patch), write
`alarms.json`, then score it:

```bash
switchbench score --corpus results/switchbench_natural_v1_events.json --alarms alarms.json --patches-dir data/patches
```

(`switchbench` is a shorthand for `python -m tools.switchbench_kit`; both work identically.)

Alarm formats, the coordinate frame and every option: [tools/switchbench_kit/README.md](tools/switchbench_kit/README.md).
Converting a public detector's own output straight into `alarms.json`:
[tools/switchbench_kit/README.md#adapters-converting-a-detectors-own-output-to-alarms-json](tools/switchbench_kit/README.md#adapters-converting-a-detectors-own-output-to-alarms-json).

## Reproduce the leaderboard table above, byte for byte

**In plain English:** the table earlier on this page (recall, false alarms, coverage for every
detector) was not hand-typed -- it is the direct output of one command below, run on the alarm
files this repo ships. You don't need to install any of the detectors to check our numbers.

```bash
switchbench fetch --corpus results/switchbench_natural_v1_events.json --out data/patches
switchbench leaderboard --corpus results/switchbench_natural_v1_events.json \
    --entries results/switchbench_natural_v1_leaderboard/entries.json \
    --strata results/switchbench_natural_v1_leaderboard/strata_sf.json \
    --patches-dir data/patches \
    --out /tmp/leaderboard_check
diff -I '^Generated ' results/switchbench_natural_v1_leaderboard/leaderboard.md /tmp/leaderboard_check/leaderboard.md
```

An empty `diff` means every row reproduced exactly (the `-I` skips only the timestamp line; everything else,
including every number, must match verbatim or `diff` will print it). `results/switchbench_natural_v1_leaderboard/alarms/`
holds the raw alarm coordinates each detector produced on the corpus (what `entries.json` points to);
`strata_sf.json` is the abrupt/gradual split used for the last two columns.

## Get on the leaderboard

Open a **Detector submission** issue with your alarms file and the exact command you ran. We re-score it with the same kit and add a row, whatever the result. See [CONTRIBUTING.md](CONTRIBUTING.md).

## Verify the pre-registration

```bash
sh prereg/verify_prereg.sh
```

Each protocol file in `prereg/` must match the SHA-256 posted in the Vesuvius Challenge Discord (#robots) on Sep 26, 2026, before any score or verdict existed: [#robots hash log](https://discord.com/channels/1079907749569237093/1553425799162372096/1553425799162372096). Discord message IDs encode their creation time, so the post's time can be checked independently: its ID decodes to 2026-09-26 15:19:31 UTC.

## Related work (and what is new here)

**In plain English:** plenty of people are building sheet-switch detectors or checking traces for them. What
was missing was a set of switches that happened for real, each one confirmed, against which any detector's hit
rate can be measured. That set is the new part here. The closest projects are listed below so you can judge
the difference yourself.

- [tifxyz-doctor](https://github.com/aviad12g/tifxyz-doctor), [windcheck](https://github.com/joe-carr-data/windcheck),
  [windaudit](https://github.com/sergeievland/windaudit): switch detectors, validated by their authors on planted
  switches. tifxyz-doctor's draft PR #2 ran its cue on natural collections and says itself that this is not natural
  sheet-switch recall. All are scored on the leaderboard above.
- [sheet-topo-bench](https://github.com/tonclap/sheet-topo-bench): a benchmark for topological errors. Its natural
  corpus compares 2026 PHercParis4 production meshes against the human-verified 2023 banner; its own census of those
  zones found no confirmed real errors, so it reports no hit rate on confirmed natural switches.
- [vc-segqa](https://github.com/Wadoekeani/vc-segqa): label-free segment QA; found one natural switch between official
  PHerc0139 wraps, with no detector hit rate.
- [growpatch-sheet-switch-detection](https://github.com/slade870/growpatch-sheet-switch-detection): PHercParis4
  cross-run disagreement with CT spot checks, no precision or recall.
- [seamcheck](https://github.com/hwkim3330/seamcheck): winding-number / neighbour-step continuity checks; on the
  leaderboard as a secondary entry, added after the freeze.
- [villa#1641](https://github.com/ScrollPrize/villa/issues/1641): a conservative seam-darkening detector, tested on one
  planted displacement.

If we have missed or misdescribed your work, open an issue and we will fix it.

## What's here

| Path | What it is |
|---|---|
| `tools/switchbench_kit/` | The scorer kit: `list`, `fetch`, `score`, `leaderboard` |
| `tools/switchbench/` | The corpus builder and the detector runners behind the results |
| `tools/harness/` | Single-file pulls from the scrollprize Hugging Face bucket (never syncs whole folders) |
| `tools/lie_detector_v0/geometry.py` | Held-out geometry audit of the published PHerc.1667 ink segments |
| `results/` | Result reports (md) and all numbers (json): v0, v1 and the exploratory analysis |
| `prereg/` | The frozen protocol texts, their hashes and the verify script |

## Rules we follow

- No scan data and no images of PHerc.1667 in this repo.
- Every detector runs from its own public source at a pinned commit with default parameters. Author-intended modes are reported beside the defaults.
- Tool authors received the results on release day, with a right of reply.

## Citation and license

**Data.** This work uses scans from *Vesuvius Challenge – CT Scans of Herculaneum Papyri* (PHercParis4, 2026 ESRF scan 20260411134726). Please cite:
Giorgio Angelotti, Stephen Parsons, Sean Johnson, Elian Rafael Dal Prà, Johannes Rudolph, Paul Tafforeau, Alessandro Mirone,
Paul Henderson, Hendrik Schilling, Forrest McDonald, David Josey, Youssef Nader, C. Seth Parker, W. Brent Seales.
*Vesuvius Challenge – CT Scans of Herculaneum Papyri.* Vesuvius Challenge. Data are licensed CC BY-NC 4.0 and hosted at
`s3://vesuvius-challenge-open-data/` (see https://scrollprize.org/data).
In plain English: the scans belong to the Vesuvius Challenge dataset; if you use this work, credit the people who made the scans too.


Code: MIT. Derived label files: CC BY-NC 4.0 (Vesuvius Challenge data terms). To cite this work, use [CITATION.cff](CITATION.cff).

Analysis built with Claude; I directed it and checked the results.
