"""Score the authors' blind review and apply the frozen C1 rule (protocol P1 (prereg/switchbench_v1.md)), once his answers exist.

Input: a JSON file {"R01": "switch" | "no switch" | "can't tell", ...} (transcribed from the filled
packet). The answer key's SHA-256 must equal the committed value in results/switchbench_natural_v1.json.
Measured precision = confirmed events marked "switch" / confirmed events marked either way (Wilson 95%).
C1: corrected upper = patch-block CI upper / precision lower bound; SUPPORTED if < 0.60 on pooled AND
new; FAILS if CI lower > 0.85; else INCONCLUSIVE.
Usage: python -m tools.switchbench.blind_review_score answers.json
"""
from __future__ import annotations

import hashlib
import json
import sys

from . import geom, metrics

RES = geom.REPO / "vault" / "results"
KEY = geom.REPO / "data" / "switchbench_v1" / "blind_key.json"


def main(answers_path):
    res = json.load(open(RES / "switchbench_v1.json"))
    committed = res["blind_review"]["answer_key_sha256"]
    got = hashlib.sha256(KEY.read_bytes()).hexdigest()
    if got != committed:
        raise SystemExit(f"answer key SHA-256 {got} != committed {committed}: do not score")
    key = json.load(open(KEY))["key"]
    ans = {k: v.strip().lower() for k, v in json.load(open(answers_path)).items()}
    if set(ans) != set(key):
        raise SystemExit(f"answers must cover exactly {sorted(key)}")
    tab = {}
    for rid, k in key.items():
        tab.setdefault(k["kind"], {}).setdefault(ans[rid], 0)
        tab[k["kind"]][ans[rid]] += 1
    conf = [ans[r] for r, k in key.items() if k["kind"] == "confirmed_event"]
    ks, kn = conf.count("switch"), conf.count("no switch")
    p, lo, hi = metrics.wilson(ks, ks + kn)
    c1 = res["C1"]
    out = dict(answers_by_kind=tab, precision=dict(switch=ks, no_switch=kn, cant_tell=conf.count("can't tell"),
                                                   point=p, wilson95=[lo, hi]))
    corr = {}
    for sk in ("pooled", "new"):
        up, low = c1[sk]["boot95"][1], c1[sk]["boot95"][0]
        corr[sk] = dict(ci_upper=up, ci_lower=low, corrected_upper=(up / lo) if lo else float("inf"))
    if all(v["ci_lower"] > 0.85 for v in corr.values()):
        verdict = "FAILS"
    elif all(v["corrected_upper"] < 0.60 for v in corr.values()):
        verdict = "SUPPORTED"
    else:
        verdict = "INCONCLUSIVE"
    out.update(corrected=corr, verdict=verdict)
    print(json.dumps(out, indent=1))
    return out


if __name__ == "__main__":
    main(sys.argv[1])
