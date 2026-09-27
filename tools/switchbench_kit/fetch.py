"""Fetch only the patch files a corpus needs: x/y/z.tif (+ mask.tif, meta.json where they exist)
of every scored patch, as single-file downloads from the Hugging Face bucket (never a bucket sync).

Source: the corpus's optional "patch_source" {bucket, prefix}; otherwise the v0 layout of
tools/switchbench/pull.py: bucket scrollprize/datasets, prefix spiral/PHercParis4/unverified_patches.
Files already in --out with the bucket's size are kept; files in a local mirror (default:
data/paris4/unverified_patches when present) are copied instead of downloaded. mask.tif changes which
vertices are valid, so the bucket listing is checked (not guessed) and written to a manifest.
"""
from __future__ import annotations

import json
import shutil
import time
from pathlib import Path

from .corpus import LOCAL_MIRROR, read_corpus, scored_patch_ids, sha256_file

REQUIRED = ("x.tif", "y.tif", "z.tif")
OPTIONAL = ("mask.tif", "meta.json")
MANIFEST = "switchbench_kit_fetch.json"
WAITS = (2, 4, 8, 16)           # network retry back-off, seconds
MIN_FREE = 1 << 30              # keep >= 1 GB free after the download
CHUNK = 400


class FetchError(RuntimeError):
    pass


def patch_source(raw: dict) -> tuple[str, str]:
    ps = raw.get("patch_source") or {}
    if "bucket" in ps and "prefix" in ps:
        return ps["bucket"], ps["prefix"].rstrip("/")
    from tools.switchbench import pull as v0pull   # v0 single-file puller: bucket and root
    return ps.get("bucket", v0pull.BUCKET), ps.get("prefix", f"{v0pull.ROOT}/unverified_patches").rstrip("/")


def _retry(fn, what, log):
    last = None
    for w in (0,) + WAITS:
        if w:
            log(f"  {what} failed ({last!r}); retrying in {w} s")
            time.sleep(w)
        try:
            return fn()
        except Exception as e:  # network errors surface as many exception types
            last = e
    raise FetchError(f"{what} failed after {len(WAITS) + 1} attempts: {last!r}")


def fetch(corpus: Path | str, out: Path | str, mirror: str | Path | None = "auto", log=print) -> dict:
    raw = read_corpus(corpus)
    patches = scored_patch_ids(raw)
    bucket, prefix = patch_source(raw)
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    if mirror == "auto":
        mirror = LOCAL_MIRROR if LOCAL_MIRROR.is_dir() else None
    elif mirror in (None, "none", ""):
        mirror = None
    else:
        mirror = Path(mirror)
    want = [(p, f) for p in patches for f in REQUIRED + OPTIONAL]
    rpath = lambda p, f: f"{prefix}/{p}/{f}"
    try:
        from huggingface_hub import get_bucket_paths_info
        infos = _retry(lambda: list(get_bucket_paths_info(bucket, [rpath(p, f) for p, f in want], token=False)),
                       "bucket listing", log)
        remote, listed = {i.path: int(i.size) for i in infos}, True
    except (FetchError, ImportError) as e:
        remote, listed = {}, False
        log(f"WARNING: could not list the bucket ({e}); using local files only, unverified against the bucket")
    if listed:
        lost = [rpath(p, f) for p, f in want if f in REQUIRED and rpath(p, f) not in remote]
        if lost:
            raise FetchError(f"{len(lost)} required files are not in bucket {bucket} (first: {lost[0]})")
    have, copy, get, absent = [], [], [], []
    for p, f in want:
        dest, rp = out / p / f, rpath(p, f)
        size = remote.get(rp)
        if listed and size is None:
            absent.append(f"{p}/{f}")            # e.g. a patch without mask.tif
            continue
        if dest.exists() and (size is None or dest.stat().st_size == size):
            have.append((p, f))
        elif mirror is not None and (mirror / p / f).exists() and (size is None or (mirror / p / f).stat().st_size == size):
            copy.append((p, f))
        elif listed:
            get.append((p, f))
        elif f in REQUIRED:
            raise FetchError(f"cannot reach the bucket and {p}/{f} is not available locally")
        else:
            absent.append(f"{p}/{f} (unknown: bucket not reachable)")
    need = sum(remote[rpath(p, f)] for p, f in get)
    free = shutil.disk_usage(out).free
    if free - need < MIN_FREE:
        raise FetchError(f"not enough disk: {need / 2**20:.1f} MB to download, {free / 2**30:.1f} GB free at {out}")
    for p, f in copy:
        (out / p).mkdir(parents=True, exist_ok=True)
        shutil.copy2(mirror / p / f, out / p / f)
    if get:
        from huggingface_hub import download_bucket_files
        for i in range(0, len(get), CHUNK):
            part = get[i:i + CHUNK]
            for p, _ in part:
                (out / p).mkdir(parents=True, exist_ok=True)
            pairs = [(rpath(p, f), str(out / p / f)) for p, f in part]
            _retry(lambda: download_bucket_files(bucket, pairs, raise_on_missing_files=True, token=False),
                   f"download of files {i + 1}-{i + len(part)}", log)
            log(f"  downloaded {min(i + CHUNK, len(get))}/{len(get)} files")
    bad = [f"{p}/{f}" for p, f in get + copy
           if not (out / p / f).exists() or (listed and (out / p / f).stat().st_size != remote[rpath(p, f)])]
    if bad:
        raise FetchError(f"{len(bad)} files are missing or have the wrong size after fetching (first: {bad[0]})")
    manifest = dict(corpus=str(corpus), corpus_sha256=sha256_file(corpus), bucket=bucket, prefix=prefix,
                    verified_against_bucket=listed, generated_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    patches={p: sorted(f for f in REQUIRED + OPTIONAL if (out / p / f).exists()) for p in patches},
                    absent_in_bucket=absent)
    (out / MANIFEST).write_text(json.dumps(manifest, indent=1) + "\n")
    summ = dict(patches=len(patches), files_present=len(have), copied_from_mirror=len(copy), downloaded=len(get),
                downloaded_mb=need / 2**20, absent=len(absent), out=str(out), mirror=str(mirror) if mirror else None,
                verified_against_bucket=listed)
    log(f"{len(patches)} scored patches -> {out}: {len(have)} files already there, {len(copy)} copied from "
        f"{mirror}, {len(get)} downloaded ({need / 2**20:.2f} MB), {len(absent)} not in the bucket (e.g. no mask.tif)")
    return summ
