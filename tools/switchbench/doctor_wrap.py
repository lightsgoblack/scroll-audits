"""Thin wrapper around tifxyz-doctor (aviad12g/tifxyz-doctor @5ca0444) that records its uncapped cues.

Run with the doctor's own interpreter (its venv), never with ours:
  $SWITCHBENCH_EXT (default ./ext)/tifxyz-doctor/.venv/bin/python doctor_wrap.py <patch_dir> <public_json> <side_json>

The doctor's CLI has no option to raise the per-cue example cap (examples come from
audit._top_locations(limit=25) per direction, then [:50]). This wrapper runs the unmodified default CLI
path (cli.main(["audit", dir, "--json", out])), so <public_json> is byte-for-byte the default report,
and records on the side, without changing any computation:
  * every _top_locations call: the complete flagged mask the capped example list is drawn from
    (caller function, call order, flagged (r, c) list, the limit applied);
  * _nonlocal_proximity: the complete proximity vertex mask (the pair list is capped at 10,000);
  * audit_mesh's internal arrays: coherent_normal_step_cells and review_cue_mask (full, uncapped).
Only numeric grid indices are written; no image is produced.
"""
import json
import sys

import numpy as np
from tifxyz_doctor import audit as A
from tifxyz_doctor import cli

CALLS = []
PROX = {}
ARR = {}

_orig_top = A._top_locations


def _top(values, mask, *, limit=50, largest=True):
    f = sys._getframe(1)
    sel = np.argwhere(np.asarray(mask, dtype=bool))
    CALLS.append(dict(func=f.f_code.co_name, limit=int(limit), n=int(len(sel)), rc=sel.astype(int).tolist()))
    return _orig_top(values, mask, limit=limit, largest=largest)


_orig_prox = A._nonlocal_proximity


def _prox(coordinates, valid, nominal_spacing, config, cue_vertices=None):
    out = _orig_prox(coordinates, valid, nominal_spacing, config, cue_vertices=cue_vertices)
    if cue_vertices is not None:
        PROX["rc"] = np.argwhere(cue_vertices).astype(int).tolist()
    return out


_orig_audit = cli.audit_mesh


def _audit(data, config=None):
    rep = _orig_audit(data, config)
    a = rep.get("_arrays", {})
    for k in ("coherent_normal_step_cells", "review_cue_mask"):
        if k in a:
            ARR[k] = np.argwhere(np.asarray(a[k], dtype=bool)).astype(int).tolist()
    return rep


A._top_locations = _top
A._nonlocal_proximity = _prox
cli.audit_mesh = _audit

if __name__ == "__main__":
    from dataclasses import asdict
    d, pub, side = sys.argv[1:4]
    rc = cli.main(["audit", d, "--json", pub])
    order = {}
    for c in CALLS:
        c["order"] = order.get(c["func"], 0)
        order[c["func"]] = c["order"] + 1
    # the CLI's config must equal the public API default AuditConfig() (same detector definition)
    cfg = json.load(open(pub)).get("config", {})
    same_cfg = cfg == json.loads(json.dumps(asdict(A.AuditConfig())))
    json.dump(dict(returncode=rc, calls=CALLS, proximity_vertices=PROX.get("rc"), arrays=ARR,
                   config_equals_api_default=same_cfg), open(side, "w"))
    sys.exit(rc if isinstance(rc, int) else 0)
