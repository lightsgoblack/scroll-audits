# scroll-audits (STAGING, private until release)

Pre-registered audits of Vesuvius Challenge data and tools. Every test has its pass/fail rules frozen, and their SHA-256 committed, before any result exists.

## Contents (staging)
| Path | What it is |
|---|---|
| `tools/switchbench/` | **SwitchBench-natural**: builds a corpus of sheet switches that occurred naturally in auto-grown traces, confirmed by two independent references (verified-surface geometry plus numeric CT profiles). Scores public sheet-switch detectors on it, next to their published planted-switch recall. |
| `tools/harness/` | Disk-frugal, single-file pulls from the scrollprize Hugging Face bucket (never syncs folders or zarr trees). |
| `tools/lie_detector_v0/geometry.py` | Held-out geometry audit of the published ink segments (validation-mask erosion by model footprint, tile counts, supervision overlap). |

## Status
Staging only. Results, the one-command reproduce and the frozen protocol texts are added at release. Paths to data and external tool clones are still hard-coded and will be parametrized before release.

## Rules we follow
- No scan data, and no images of PHerc.1667, in this repo.
- Derived label files are released under CC BY-NC 4.0 (Vesuvius Challenge data terms). The code is MIT.
- Every detector is run from its own public source at a pinned commit with default parameters; author-intended modes are reported beside the defaults.

## License
MIT (code). Data derivatives: CC BY-NC 4.0.
