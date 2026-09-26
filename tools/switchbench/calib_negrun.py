"""Negative-run CT rule calibration on verified surfaces (no corpus data): per-run on-layer fraction
and longest off-layer streak along 10 mm (52-vertex) row segments of verified patches (seed 20260925)."""
import json
import numpy as np
from . import confirm, geom

rng = np.random.default_rng(20260925)
vi = geom.VerifiedIndex()
fr, streak = [], []
for nm in rng.permutation(vi.names):
    if len(fr) >= 30:
        break
    P, N, _ = vi.patch(nm)
    ok = np.isfinite(P).all(-1) & np.isfinite(N).all(-1)
    rows = [r for r in range(P.shape[0]) if ok[r].sum() >= 60]
    if not rows:
        continue
    r = rows[rng.integers(len(rows))]
    cols = np.nonzero(ok[r])[0]
    run = None
    for c0 in cols:
        if ok[r, c0:c0 + 52].all() and c0 + 52 <= P.shape[1]:
            run = [(r, c) for c in range(c0, c0 + 52)]
            break
    if run is None:
        continue
    flags = [confirm.on_layer(P[rc], N[rc], 20.0) for rc in run]
    f = [x for x in flags if x is not None]
    if len(f) < 40:
        continue
    fr.append(sum(f) / len(f))
    s = m = 0
    for x in flags:
        s = s + 1 if x is False else 0
        m = max(m, s)
    streak.append(m)
    print(nm[:50], round(fr[-1], 2), m, flush=True)
out = dict(n_runs=len(fr), on_fraction_pct=np.percentile(fr, [5, 10, 25, 50]).tolist(),
           max_off_streak_pct=np.percentile(streak, [50, 75, 90, 95]).tolist(), fr=fr, streak=streak)
p = geom.REPO / "vault" / "results" / "switchbench_ct_calibration.json"
j = json.load(open(p)); j["negative_run_controls_verified"] = out; json.dump(j, open(p, "w"), indent=1)
print({k: v for k, v in out.items() if k not in ("fr", "streak")})
