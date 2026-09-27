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
