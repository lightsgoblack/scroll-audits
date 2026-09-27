## 5. SwitchBench-natural (replacement bet D, proposed 2026-09-26)
- **Analog:** a safety recall audit. Crash-test ratings come from staged crashes; this checks how the ratings hold up on real crashes.
- **What it does:** builds the first corpus of sheet switches that happened for real in production GrowPatch traces (PHercParis4 unverified vs verified patches, with human winding annotations), then measures the recall and precision of the existing public detectors on it. Also tests whether GrowPatch's own per-generation cost (`gen_avg_cost`, already in every meta.json) predicts where switches occur.
- **Why it's valuable:** at least 8 public detectors exist and every one reports only planted or synthetic switches (Scout Report #6). The Open Problems page asks for "conservative failure detection", and the prize rewards "detecting failure-cases of existing methods on real scroll data". It helps every tool rather than competing with them.
- **Status:** TESTING. Criteria APPROVED by Colin 2026-09-26, frozen at this commit.

### Pre-registered kill criteria (skeptic, 2026-09-26, APPROVED)
| Item | Specification |
|------|---------------|
| Data | HF `spiral/PHercParis4`: verified_patches, unverified_patches, relative_windings.json, same_windings.json, abs_winding.json, umbilicus.json, patch-overlap-pcls.json. Single-file pulls only, <= 5 GB total disk. Optional numeric-only CT single-chunk reads from S3. No ink maps, no images. |
| Sample | Unverified patches that overlap verified coverage (from patch-overlap-pcls.json), in a seeded random order (seed 20260925), processed until the corpus cap (below). |
| Natural switch event | Along a connected run of an unverified patch: the surface lies on verified wrap w (within 0.25 x local inter-wrap spacing, spacing measured from adjacent verified patches), then within the same run lies on wrap w +/- 1 for >= 1 mm. The wrap identity on both sides needs **two independent references**: verified-patch geometry AND a human winding annotation, or either one plus a numeric CT profile. Single-reference events are logged as "unconfirmed" and not scored. |
| Negatives | Runs of >= 10 mm on unverified patches that stay on one confirmed wrap, same confirmation rule. Used for precision / false-alarm rate. |
| Detectors | Every public detector that builds on CPU within a 1-day build cap: windcheck, tifxyz-doctor, sheet-topo-bench v1 (frozen), windaudit, a #1621-style annotation check. Default parameters only, no tuning. A detector that fails to build is reported "not run" with the error, never dropped silently. Baselines: random, and gen_avg_cost (AUROC only, no threshold tuning). |
| Metrics | Per detector: recall on confirmed natural events (95% Wilson CI), false alarms per 100 mm on negatives, and the gap vs that tool's own published planted-switch recall. gen_avg_cost: AUROC of event vs negative windows, block bootstrap by patch (B = 2000, seed 20260925). |
| PASS (worth releasing) | >= 30 confirmed natural events AND at least one of: (i) a detector's natural recall is below its published planted recall with the 95% CI excluding the planted value; (ii) gen_avg_cost AUROC >= 0.65 with CI lower bound > 0.55 (a free early warning). |
| KILL | Fewer than 30 confirmed events at the corpus cap; OR every run detector has natural recall CI lower bound >= 0.90 (nothing to report); OR a public natural-switch recall benchmark appears before our release (prior art, scout re-checks at release). |
| INCONCLUSIVE | Anything else (e.g. >= 30 events but every CI straddles the planted value). No retry: report the corpus as a dataset-only release only if Colin approves. |
| Sanity (failure = harness bug) | Verified patch vs itself = 0 events. A synthetic one-wrap jump planted into a verified patch = exactly 1 event at the right place. Labeler run on verified patches: > 5% with events means the labeler is broken. |
| Caps | Corpus cap: 3 days from the first line of code. Total cap: 5 days. $0, CPU only. Hours logged in LEDGER.md. |
| Text rule | PHercParis4 is a read scroll; no ink maps are used, so rule exposure is minimal. CT checks are numeric only; save no images. |
| Prior art to cite | growpatch-sheet-switch-detection, sheet-topo-bench, TIFXYZ Doctor, windaudit, windcheck, vesuvius-ruled, Stevens pipeline9, villa satisfaction_metrics / #1621. |
