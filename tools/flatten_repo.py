#!/usr/bin/env python3
"""Flatten the repository into the layout the packaging expects.

Run once, from the repository root:

    python tools/flatten_repo.py            # show what would change
    python tools/flatten_repo.py --apply    # do it

Why this exists: `pyproject.toml` declares the package as `micromethods`, so
setuptools looks for a `micromethods/` directory *next to* it. If the package
lives one level down (in `micromethods-tool/`), `pip install -e .` still
reports success but installs metadata with no code — the console script and
the napari plugin both silently fail. Loose copies of package modules or test
files at the repository root cause a second class of failure: pytest imports
two files with the same basename and aborts collection.

The script promotes everything in `micromethods-tool/` to the root, deletes
stray duplicates at the root, and verifies the result.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

WRAPPER = "micromethods-tool"

# Files that belong *inside* the package or the test suite and must never sit
# at the repository root. Anything listed here is deleted from the root only.
STRAY_ROOT_FILES = [
    # package modules
    "__init__.py", "base.py", "checklist.py", "cli.py", "czi.py", "gaps.py",
    "imspector.py", "lif.py", "ometiff.py", "prairieview.py", "profiles.py",
    "prompt.py", "render.py", "schema.py", "units.py", "widget.py",
    # test suite
    "conftest.py", "fixture_data.py", "make_fixtures.py",
    "test_blaze.py", "test_ometiff.py", "test_parsers.py",
    # data files that belong in the package
    "napari.yaml", "miltenyi_blaze.yaml", "bruker_ultima_2p.yaml",
]

REQUIRED_AFTER = ["pyproject.toml", "micromethods/__init__.py",
                  "micromethods/_napari/napari.yaml", "tests"]


def git(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], capture_output=True, text=True, check=check)


def plan(root: Path) -> tuple[list[Path], list[tuple[Path, Path]]]:
    """Return (files to delete, (source, destination) moves)."""
    deletions = [root / name for name in STRAY_ROOT_FILES if (root / name).is_file()]

    moves: list[tuple[Path, Path]] = []
    wrapper = root / WRAPPER
    if wrapper.is_dir():
        for source in sorted(wrapper.rglob("*")):
            if source.is_dir() or "__pycache__" in source.parts:
                continue
            moves.append((source, root / source.relative_to(wrapper)))
    return deletions, moves


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true",
                        help="perform the changes (default is a dry run)")
    parser.add_argument("--check", action="store_true",
                        help="exit non-zero if the layout needs fixing (for CI)")
    args = parser.parse_args()

    root = Path.cwd()
    if not (root / "pyproject.toml").exists() and not (root / WRAPPER).exists():
        print("error: run this from the project root — no pyproject.toml and no "
              f"{WRAPPER}/ directory here", file=sys.stderr)
        return 1

    deletions, moves = plan(root)
    if not deletions and not moves:
        print("Layout is already flat: no wrapper directory, no stray root files.")
        if args.check:
            return 0
    for path in deletions:
        print(f"  delete  {path.relative_to(root)}")
    for source, destination in moves:
        marker = " (overwrites)" if destination.exists() else ""
        print(f"  move    {source.relative_to(root)} -> "
              f"{destination.relative_to(root)}{marker}")

    if args.check:
        print("\nRepository layout is wrong: the package must sit next to "
              "pyproject.toml. Run: python tools/flatten_repo.py --apply")
        return 1

    if not args.apply:
        print("\nDry run. Re-run with --apply to make these changes.")
        return 0

    for path in deletions:
        path.unlink()
    for source, destination in moves:
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            destination.unlink()
        shutil.move(str(source), str(destination))
    wrapper = root / WRAPPER
    if wrapper.is_dir():
        shutil.rmtree(wrapper)

    git("add", "-A", check=False)

    print("\nVerifying layout:")
    ok = True
    for required in REQUIRED_AFTER:
        exists = (root / required).exists()
        ok &= exists
        print(f"  {'found  ' if exists else 'MISSING'} {required}")
    if (root / WRAPPER).exists():
        ok = False
        print(f"  STILL PRESENT {WRAPPER}")

    if not ok:
        print("\nLayout is still wrong — do not commit yet.", file=sys.stderr)
        return 1

    print("\nLayout is correct. Next:\n"
          "    pip install -e \".[test]\"\n"
          "    micromethods doctor\n"
          "    pytest\n"
          "    git commit -m \"Flatten repository layout\"")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
