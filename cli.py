"""Command line entry point: ``micromethods``."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import profiles as profile_store
from . import readers, render
from .gaps import find_gaps
from .prompt import (ChainPrompter, CLIPrompter, MappingPrompter, NullPrompter,
                     instrument_answers, run)
from .schema import Record


def build_record(path: Path, *, series: int = 0, extra_profiles: list[Path] | None = None
                 ) -> tuple[Record, object]:
    record = readers.read(path, series=series)
    profile = profile_store.apply_best(record, extra_profiles)
    return record, profile


def _load_answers(path: Path) -> dict:
    text = path.read_text()
    if path.suffix.lower() in (".yaml", ".yml"):
        import yaml
        return yaml.safe_load(text) or {}
    return json.loads(text)


def cmd_report(args: argparse.Namespace) -> int:
    path = Path(args.path).expanduser()
    record, profile = build_record(path, series=args.series,
                                   extra_profiles=[Path(p) for p in args.profile])
    if profile:
        print(f"Instrument profile: {profile.key} ({profile.label or profile.source_path})")

    report = find_gaps(record, include_recommended=not args.no_recommended)

    prompters = []
    if args.answers:
        prompters.append(MappingPrompter(_load_answers(Path(args.answers))))
    prompters.append(NullPrompter() if args.non_interactive else CLIPrompter())
    questions = report.questions if args.ask_all else report.blocking
    answers = run(record, questions, ChainPrompter(*prompters))

    report = find_gaps(record, include_recommended=not args.no_recommended)

    if args.save_profile:
        stable = instrument_answers(answers)
        if stable:
            written = profile_store.write_profile(
                args.save_profile, stable,
                label=f"Saved from {path.name}",
                match={"instrument_key": [record.instrument_key]} if record.instrument_key
                else None)
            print(f"\nSaved {len(stable)} instrument-level answer(s) to {written}")
        else:
            print("\nNo instrument-level answers to save.")

    markdown = render.report_markdown(record, report)
    if args.stdout:
        print("\n" + markdown)
    else:
        outdir = Path(args.output or path.parent).expanduser()
        outdir.mkdir(parents=True, exist_ok=True)
        stem = path.name.split(".")[0]
        md_path = outdir / f"{stem}_methods.md"
        json_path = outdir / f"{stem}_metadata.json"
        md_path.write_text(markdown)
        json_path.write_text(render.metadata_json(record, report))
        print(f"\nMethods report: {md_path}")
        print(f"Metadata sidecar: {json_path}")

    print(f"Checklist coverage: {report.completeness * 100:.0f}% "
          f"({len(report.blocking)} required field(s) still missing)")
    for warning in report.warnings:
        print(f"  ! {warning}")
    return 0 if not report.blocking else 2


def cmd_inspect(args: argparse.Namespace) -> int:
    record = readers.read(Path(args.path).expanduser(), series=args.series)
    payload = {k: v for k, v in record.vendor_raw.items() if k != "fingerprint"}
    if args.grep:
        needle = args.grep.lower()
        payload = {
            top: {k: v for k, v in sub.items() if needle in str(k).lower()
                  or needle in str(v).lower()} if isinstance(sub, dict) else sub
            for top, sub in payload.items()
        }
    print(json.dumps(payload, indent=2, ensure_ascii=False, default=str))
    return 0


def cmd_profiles(args: argparse.Namespace) -> int:
    found = profile_store.discover()
    if not found:
        print("No instrument profiles found.")
        return 0
    for p in found:
        print(f"{p.key:<24} {p.label or '-':<45} {p.source_path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="micromethods",
        description="Extract microscopy metadata and draft a methods section "
                    "that satisfies the QUAREP-LiMi bare minimal reporting checklist.")
    sub = parser.add_subparsers(dest="command", required=True)

    rep = sub.add_parser("report", help="generate a methods report for a dataset")
    rep.add_argument("path", help="path to the image file")
    rep.add_argument("-o", "--output", help="output directory (default: alongside the file)")
    rep.add_argument("-s", "--series", type=int, default=0,
                     help="series/image index inside a container (default: 0)")
    rep.add_argument("--profile", action="append", default=[],
                     help="extra instrument profile YAML (repeatable)")
    rep.add_argument("--answers", help="YAML/JSON file of pre-supplied answers")
    rep.add_argument("--non-interactive", action="store_true",
                     help="never prompt; leave gaps marked as MISSING")
    rep.add_argument("--ask-all", action="store_true",
                     help="also prompt for recommended, modality-specific fields")
    rep.add_argument("--no-recommended", action="store_true",
                     help="ignore recommended fields entirely")
    rep.add_argument("--save-profile", metavar="KEY",
                     help="save instrument-level answers as a reusable profile")
    rep.add_argument("--stdout", action="store_true", help="print instead of writing files")
    rep.set_defaults(func=cmd_report)

    ins = sub.add_parser("inspect", help="dump the raw vendor metadata tree")
    ins.add_argument("path")
    ins.add_argument("-s", "--series", type=int, default=0)
    ins.add_argument("--grep", help="only show keys/values containing this string")
    ins.set_defaults(func=cmd_inspect)

    pro = sub.add_parser("profiles", help="list known instrument profiles")
    pro.set_defaults(func=cmd_profiles)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except readers.ReaderError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except FileNotFoundError as exc:
        print(f"error: file not found: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
