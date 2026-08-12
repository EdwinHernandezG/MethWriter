#!/usr/bin/env python3
"""Audit GitHub Actions workflows for jobs that test an uninstalled package.

The failure this catches: a workflow runs ``pytest`` without ever installing
the project. The tests still import it from the checked-out source tree, so
they appear to run, while the console script and the napari plugin — the parts
that depend on a real installation — are never exercised. GitHub's suggested
Python starter workflow does exactly this when a repository has no
``requirements.txt``.

Usage, from the repository root:

    python tools/check_workflows.py            # report
    python tools/check_workflows.py --check    # exit non-zero if a job is broken
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

WORKFLOWS = Path(".github/workflows")

# A step that installs this project, in any of the usual spellings.
INSTALLS = re.compile(
    r"pip\s+install[^\n]*(-e\s*[\"']?\.|\s\.(\s|$|\[)|--editable)", re.IGNORECASE)
RUNS_PYTEST = re.compile(r"^\s*(-\s*)?(run:\s*)?.*\bpytest\b", re.IGNORECASE | re.MULTILINE)


def audit(path: Path) -> list[str]:
    """Return the problems found in one workflow file."""
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError as exc:
        return [f"could not be read ({exc})"]

    problems: list[str] = []
    runs_tests = bool(RUNS_PYTEST.search(text))
    installs = bool(INSTALLS.search(text))

    if runs_tests and not installs:
        problems.append(
            "runs pytest but never installs the project, so the tests would "
            "exercise the source tree rather than an installation")
    if "requirements.txt" in text and not Path("requirements.txt").exists():
        problems.append(
            "installs from requirements.txt, which does not exist in this "
            "repository (dependencies come from pyproject.toml instead)")
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true",
                        help="exit non-zero when a workflow is broken")
    args = parser.parse_args()

    if not WORKFLOWS.is_dir():
        print(f"No {WORKFLOWS}/ directory here — run this from the repository root.")
        return 0

    files = sorted(p for p in WORKFLOWS.iterdir()
                   if p.suffix in (".yml", ".yaml"))
    if not files:
        print(f"No workflow files in {WORKFLOWS}/.")
        return 0

    broken = 0
    for path in files:
        problems = audit(path)
        if problems:
            broken += 1
            print(f"{path}")
            for problem in problems:
                print(f"    problem: {problem}")
        else:
            print(f"{path}  ok")

    if broken:
        print(
            f"\n{broken} workflow file(s) would test an uninstalled package.\n"
            "Either delete them and keep ci.yml, which installs the project "
            "first, or add this step before the pytest step:\n\n"
            "      - name: Install\n"
            "        run: |\n"
            "          python -m pip install --upgrade pip\n"
            '          python -m pip install -e ".[test]"\n')
        return 1 if args.check else 0

    print(f"\nAll {len(files)} workflow file(s) install the project before testing.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
