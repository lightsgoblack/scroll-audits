"""Write the corpus label file (coordinates only, no images): vault/results/switchbench_natural_events.json."""
from __future__ import annotations

import json

from . import geom


def main():
    out = dict(scroll="PHercParis4", frame="level-2 voxels (x, y, z) of volume 20260411134726 (9.6 um/vx)",
               source="HF bucket scrollprize/datasets spiral/PHercParis4 unverified_patches (seeded order 20260925)",
               events=[], negatives=[], multi_wrap=[])
    for f in sorted((geom.DATA / "corpus").glob("*.json")):
        r = json.load(open(f))
        if not r.get("in_sample"):
            continue
        for e in r["events"]:
            out["events"].append(dict(patch=r["patch"], status=e["status"], xyz=[round(v, 1) for v in e["xyz"]],
                                      delta_signs=e["delta_signs"],
                                      transitions=[dict(axis=m["axis"], rc_a=m["rc_a"], rc_b=m["rc_b"],
                                                        len_a_mm=round(m["len_a_mm"], 2), len_b_mm=round(m["len_b_mm"], 2))
                                                   for m in e["members"]]))
        for n in r["negatives"]:
            out["negatives"].append(dict(patch=r["patch"], status=n["status"], axis=n["axis"],
                                         rc0=n["verts"][0], rc1=n["verts"][-1], len_mm=round(n["len_mm"], 2),
                                         xyz0=[round(v, 1) for v in n["xyz0"]], xyz1=[round(v, 1) for v in n["xyz1"]]))
        for m in r.get("multi_wrap", []):
            out["multi_wrap"].append(dict(patch=r["patch"], xyz=[round(v, 1) for v in m["xyz"]], delta_signs=m["delta_signs"]))
    p = geom.REPO / "vault" / "results" / "switchbench_natural_events.json"
    json.dump(out, open(p, "w"), separators=(",", ":"))
    print(p, p.stat().st_size / 1e6, "MB", len(out["events"]), len(out["negatives"]))


if __name__ == "__main__":
    main()
