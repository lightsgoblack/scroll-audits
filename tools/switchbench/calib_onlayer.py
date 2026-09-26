"""On-layer control for the negative-run CT rule, on human ladder clicks (no corpus data).
Clicks (on a sheet) should read on-layer; midpoints between adjacent clicks (in the gap) should not.
The window half-width is chosen here by Youden margin and then frozen in confirm.ON_WIN."""
import json
import numpy as np
from . import confirm, geom
from .calibrate_ct import ladder_pairs

rng = np.random.default_rng(20260925)
adj, _ = ladder_pairs()
wins = [0.0, 0.05, 0.1, 0.15, 0.25]
on = {w: [] for w in wins}; mid = {w: [] for w in wins}
for i in rng.choice(len(adj), 150, replace=False):
    a, b = adj[i]
    d = b - a; L = float(np.linalg.norm(d)); u = d / L
    for w in wins:
        on[w].append(confirm.on_layer(a, u, L, win=w))
        mid[w].append(confirm.on_layer(a + d / 2, u, L, win=w))
f = lambda x: (lambda d: sum(d) / len(d) if d else None)([v for v in x if v is not None])
out = {str(w): dict(click_on_layer=f(on[w]), midpoint_on_layer=f(mid[w])) for w in wins}
best = max(wins, key=lambda w: f(on[w]) - f(mid[w]))
res = dict(by_window=out, chosen_window=best, n=150)
p = geom.REPO / "vault" / "results" / "switchbench_ct_calibration.json"
j = json.load(open(p)); j["on_layer_controls"] = res; json.dump(j, open(p, "w"), indent=1)
print(json.dumps(res))
