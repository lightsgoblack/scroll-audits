# Add your detector to the SwitchBench leaderboard

Anyone can submit. Every submission is scored with the same kit on the same corpus, and gets a row whatever the result.

## 1. Score it yourself

Follow "Score your detector in three commands" in the README, and keep the JSON that `score --json my_score.json` writes.

## 2. Open a "Detector submission" issue

Include:
- the tool's public repository and the exact commit you ran;
- the mode: **default** (the tool's own defaults), **author-intended** (settings the tool's author recommends for this task) or **tuned** (anything else; say what was tuned and on which data);
- the exact command(s) that produced the alarms from the fetched patches;
- the alarms file (attach it or link a gist);
- the kit version (`python -m tools.switchbench_kit --version`) and the table `score` printed.

## 3. What happens next

We re-run `score` on your alarms file against the pinned corpus. If our numbers differ from yours, we reply on the issue before anything is published. Then the row goes on the leaderboard with your tool, commit and mode. We never edit an alarms file: it is committed next to the leaderboard so anyone can re-score it.

## Rules

- One row per tool, commit and mode. A new commit gets a new row, and older rows stay.
- The corpus events file is public. Tuning on it is allowed, but the row is marked **tuned on the test corpus**.
- Coverage is shown next to recall so you can tell scope from performance. The recall number itself still counts an event on a no-verdict patch as a miss (that's how "hits / all confirmed events" works) -- coverage is what tells you how much of a low recall is "didn't look" rather than "looked and missed."

## Code changes

Bug reports and pull requests are welcome. Run `python -m pytest -q tools/switchbench_kit/tests` first. A change to the scorer that alters any published number must say which numbers change and why.
