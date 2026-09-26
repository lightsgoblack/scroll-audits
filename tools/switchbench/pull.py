"""Single-file pulls of PHercParis4 spiral-input patch geometry (x/y/z.tif + meta.json [+ mask.tif]).

Never syncs the bucket. Stops if free disk < 6 GB or data/paris4 exceeds the 5 GB bet cap.
Usage:
  python -m tools.switchbench.pull verified          # all verified patch geometry (~1.05 GB)
  python -m tools.switchbench.pull unverified NAME.. # given unverified patches
"""
from __future__ import annotations
import json, shutil, sys
from pathlib import Path
from huggingface_hub import download_bucket_files

BUCKET = "scrollprize/datasets"
ROOT = "spiral/PHercParis4"
REPO = Path(__file__).resolve().parents[2]
DATA = REPO / "data" / "paris4"
CAP = 5 * 2**30
MIN_FREE = 6 * 2**30


def du(p: Path) -> int:
    return sum(f.stat().st_size for f in p.rglob("*") if f.is_file())


def check_disk():
    free = shutil.disk_usage(DATA).free
    if free < MIN_FREE:
        raise SystemExit(f"STOP: free disk {free/2**30:.1f} GB < 6 GB")
    used = du(DATA)
    if used > CAP:
        raise SystemExit(f"STOP: data/paris4 {used/2**30:.2f} GB > 5 GB cap")
    return used


def pull(pairs, chunk=400):
    pairs = [(r, l) for r, l in pairs if not Path(l).exists()]
    for i in range(0, len(pairs), chunk):
        check_disk()
        part = pairs[i:i + chunk]
        for _, l in part:
            Path(l).parent.mkdir(parents=True, exist_ok=True)
        download_bucket_files(BUCKET, part, raise_on_missing_files=False, token=False)
        print(f"  pulled {min(i+chunk, len(pairs))}/{len(pairs)}", flush=True)


def pull_verified():
    fs = json.load(open(DATA / "verified_files.json"))
    want = {"x.tif", "y.tif", "z.tif", "meta.json"}
    pairs = []
    for p, _ in fs:
        rel = p[len(ROOT) + 1:]
        if rel.split("/")[-1] in want:
            pairs.append((p, str(DATA / rel)))
    pull(pairs)


def pull_unverified(names, files=("x.tif", "y.tif", "z.tif", "meta.json", "mask.tif")):
    pairs = [(f"{ROOT}/unverified_patches/{n}/{f}", str(DATA / "unverified_patches" / n / f))
             for n in names for f in files]
    pull(pairs)


if __name__ == "__main__":
    if sys.argv[1] == "verified":
        pull_verified()
    else:
        pull_unverified(sys.argv[2:])
    print(f"data/paris4 = {du(DATA)/2**30:.2f} GB, free = {shutil.disk_usage(DATA).free/2**30:.1f} GB")
