"""Command line: python -m tools.switchbench_kit {list,fetch,score,leaderboard} ... (see README.md)."""
from __future__ import annotations

import argparse
import os
import sys

from . import __version__

CORPUS_HELP = "corpus file, e.g. results/switchbench_natural_v0_events.json"


def _parser():
    ap = argparse.ArgumentParser(prog="python -m tools.switchbench_kit",
                                 description="SwitchBench scorer kit: score a sheet-switch detector on the natural "
                                             "sheet-switch corpus.")
    ap.add_argument("--version", action="version", version=f"switchbench_kit {__version__}")
    sub = ap.add_subparsers(dest="cmd", required=True)

    ls = sub.add_parser("list", help="print the scored patch ids (the patches to run your detector on)")
    ls.add_argument("--corpus", required=True, help=CORPUS_HELP)

    f = sub.add_parser("fetch", help="download only the patch files the corpus needs")
    f.add_argument("--corpus", required=True, help=CORPUS_HELP)
    f.add_argument("--out", required=True, help="directory for <patch_id>/{x,y,z,mask}.tif")
    f.add_argument("--mirror", default="auto",
                   help="local copy to reuse instead of downloading ('auto' = data/paris4/unverified_patches if "
                        "present, 'none' = always download)")

    s = sub.add_parser("score", help="score an alarms file (JSON) or mask directory")
    s.add_argument("--corpus", required=True, help=CORPUS_HELP)
    s.add_argument("--alarms", required=True,
                   help="JSON {patch_id: [[x,y,z],...]} or {patch_id: [[row,col],...]}, or a directory of "
                        "<patch_id>.npz boolean masks")
    s.add_argument("--format", default="auto", choices=["auto", "xyz", "grid", "masks"],
                   help="alarm format (default: detected)")
    s.add_argument("--patches-dir", default=None,
                   help="directory holding <patch_id>/x.tif ... (from fetch; default: the repo's "
                        "data/paris4/unverified_patches if present)")
    s.add_argument("--match-mm", type=float, default=None, help="match radius, mm (default 1.0)")
    s.add_argument("--per-patch-cap", type=int, default=None,
                   help="count at most N confirmed events per patch toward recall (default: no cap; 0 = no cap)")
    s.add_argument("--bootstrap", type=int, default=None, help="patch-block bootstrap draws B (default 2000)")
    s.add_argument("--seed", type=int, default=None, help="RNG seed for bootstrap and cap (default 20260925)")
    s.add_argument("--fa-dedup-mm", type=float, default=None,
                   help="merge alarms closer than this before counting false alarms (default 0.5; 0 = off)")
    s.add_argument("--name", default=None, help="detector name for the report (default: from the file)")
    s.add_argument("--per-event", action="store_true", help="also print the per-event hit list")
    s.add_argument("--json", dest="json_out", default=None, help="write the full result as JSON here")

    lb = sub.add_parser("leaderboard", help="score several detectors and write leaderboard.{md,json,html}")
    lb.add_argument("--corpus", required=True, help=CORPUS_HELP)
    lb.add_argument("--entries", required=True,
                    help='JSON {"entries": [{"name", "alarms", "tool", "mode", "notes"}, ...]}')
    lb.add_argument("--patches-dir", default=None, help="as for score")
    lb.add_argument("--strata", default=None, help='optional JSON {"<patch>|<x>,<y>,<z>": "abrupt"|"gradual"} (xyz rounded to 0.1 voxel)')
    lb.add_argument("--out", required=True, help="output directory")

    from .adapters import check1621, seamcheck, tifxyz_doctor, windaudit, windcheck
    ADAPTER_MODS = {"tifxyz-doctor": tifxyz_doctor, "windcheck": windcheck, "windaudit": windaudit,
                    "seamcheck": seamcheck, "check1621": check1621}
    ad = sub.add_parser("adapt", help="convert a public detector's native output to the kit's alarms JSON")
    adsub = ad.add_subparsers(dest="tool", required=True)
    for name, mod in ADAPTER_MODS.items():
        p = adsub.add_parser(name, help=(mod.__doc__ or "").splitlines()[2].strip() if mod.__doc__ else name)
        p.add_argument("native_output_path", help="the tool's own output file/directory (see the kit README)")
        p.add_argument("--out", required=True, help="alarms JSON to write")
        mod.add_args(p)
    return ap


def main(argv=None) -> int:
    args = _parser().parse_args(argv)
    from .alarms import AlarmsError
    from .corpus import CorpusError
    try:
        if args.cmd == "list":
            from .corpus import read_corpus, scored_patch_ids
            ids = scored_patch_ids(read_corpus(args.corpus))
            try:
                print("\n".join(ids), flush=True)
            except BrokenPipeError:            # e.g. piped into head
                sys.stdout = open(os.devnull, "w")
                return 0
            print(f"{len(ids)} scored patches", file=sys.stderr)
            return 0
        if args.cmd == "fetch":
            from .fetch import FetchError, fetch
            try:
                fetch(args.corpus, args.out, mirror=args.mirror, log=lambda m: print(m, file=sys.stderr))
            except FetchError as e:
                print(f"error: {e}", file=sys.stderr)
                return 2
            return 0
        if args.cmd == "adapt":
            from .adapters import AdapterError, check1621, seamcheck, tifxyz_doctor, windaudit, windcheck
            mod = {"tifxyz-doctor": tifxyz_doctor, "windcheck": windcheck, "windaudit": windaudit,
                   "seamcheck": seamcheck, "check1621": check1621}[args.tool]
            kwargs = {k: v for k, v in vars(args).items()
                      if k not in ("cmd", "tool", "native_output_path", "out")}
            try:
                alarms = mod.run(args.native_output_path, args.out, **kwargs)
            except AdapterError as e:
                print(f"error: {e}", file=sys.stderr)
                return 2
            n = sum(len(v) for v in alarms.values())
            print(f"wrote {args.out}: {len(alarms)} patch(es), {n} alarm(s)", file=sys.stderr)
            return 0
        if args.cmd == "leaderboard":
            import json
            from .leaderboard import run, to_markdown, write
            entries = json.loads(open(args.entries).read())["entries"]
            board = run(entries, args.corpus, args.patches_dir, args.strata)
            paths = write(board, args.out)
            print(to_markdown(board))
            print("wrote " + ", ".join(paths.values()), file=sys.stderr)
            return 0
        from .alarms import load_alarms
        from .corpus import load_benchmark
        from .report import format_report, write_json
        from .scoring import score
        bench = load_benchmark(args.corpus, args.patches_dir)
        alarms = load_alarms(args.alarms, bench, fmt=args.format, detector=args.name)
        res = score(bench, alarms, match_mm=args.match_mm, per_patch_cap=args.per_patch_cap, bootstrap=args.bootstrap,
                    seed=args.seed, fa_dedup_mm=args.fa_dedup_mm)
        print(format_report(res, per_event=args.per_event))
        if args.json_out:
            write_json(res, args.json_out)
            print(f"\nwrote {args.json_out}")
        return 0
    except (CorpusError, AlarmsError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
