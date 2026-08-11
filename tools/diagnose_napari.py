#!/usr/bin/env python3
"""Diagnose why the napari plugin does not appear.

Standalone on purpose: it imports nothing from micromethods, so it still works
when the installation is broken. Run it with the *same* Python that runs
napari:

    conda activate micromethods
    python tools/diagnose_napari.py

Paste the whole output when asking for help — it identifies which of the four
possible causes is in play:

  A. micromethods is not installed in this environment at all
  B. it is installed but has no importable code (pip installed metadata only,
     because it was run from a directory that lacks the micromethods/ folder)
  C. the code is fine but napari or the Qt binding is in a different
     environment
  D. everything resolves, and the plugin should be in the Plugins menu
"""

from __future__ import annotations

import importlib
import importlib.metadata as md
import json
import sys
from pathlib import Path

LINE = "-" * 72


def section(title: str) -> None:
    print(f"\n{title}\n{LINE}")


def main() -> int:
    problems: list[str] = []

    section("1. Interpreter")
    print(f"python      {sys.version.split()[0]}")
    print(f"executable  {sys.executable}")
    print(f"prefix      {sys.prefix}")

    section("2. micromethods distribution")
    dist = None
    try:
        dist = md.distribution("micromethods")
        print(f"version     {dist.version}")
        print(f"location    {dist.locate_file('')}")
        # An editable install records where the source tree lives.
        try:
            direct = dist.read_text("direct_url.json")
            if direct:
                info = json.loads(direct)
                url = info.get("url", "")
                editable = info.get("dir_info", {}).get("editable", False)
                print(f"source      {url}  (editable: {editable})")
                if url.startswith("file://"):
                    source = Path(url[7:].lstrip("/") if sys.platform == "win32"
                                  else url[7:])
                    package = source / "micromethods" / "__init__.py"
                    print(f"            package present at source: {package.exists()}")
                    if not package.exists():
                        problems.append(
                            "B. Installed from a directory with no micromethods/ "
                            f"folder ({source}). pip reported success but installed "
                            "no code. Reinstall from the folder that contains both "
                            "pyproject.toml and micromethods/.")
        except Exception:
            pass
    except md.PackageNotFoundError:
        print("NOT INSTALLED in this environment")
        problems.append("A. micromethods is not installed in the environment this "
                        "Python belongs to. Activate the right environment, or "
                        "install it here.")

    section("3. Importability")
    try:
        module = importlib.import_module("micromethods")
        print(f"import      OK -> {Path(module.__file__).parent}")
        manifest_path = Path(module.__file__).parent / "_napari" / "napari.yaml"
        print(f"napari.yaml on disk: {manifest_path.exists()}  ({manifest_path})")
        if not manifest_path.exists():
            problems.append("The package imports but napari.yaml is missing from "
                            "micromethods/_napari/ — reinstall the package.")
    except Exception as exc:
        print(f"import      FAILS -> {type(exc).__name__}: {exc}")
        if not any(p.startswith(("A.", "B.")) for p in problems):
            problems.append(f"B. micromethods cannot be imported ({exc}).")

    section("4. napari and Qt")
    napari_module = None
    try:
        napari_module = importlib.import_module("napari")
        napari_path = Path(napari_module.__file__).parent
        print(f"napari      {napari_module.__version__}")
        print(f"            {napari_path}")
        same_env = str(napari_path).startswith(str(Path(sys.prefix)))
        print(f"            same environment as this Python: {same_env}")
        if not same_env:
            problems.append("C. napari lives outside this environment. Plugins are "
                            "only visible to the napari installed alongside them.")
    except ImportError as exc:
        print(f"napari      NOT IMPORTABLE ({exc})")
        problems.append("C. napari is not installed in this environment, so it "
                        "cannot see the plugin. Install napari here, or run this "
                        "script with the Python that runs napari.")

    bindings = [name for name in ("PySide6", "PyQt6", "PyQt5", "PySide2")
                if importlib.util.find_spec(name) is not None]
    print(f"qt bindings {', '.join(bindings) if bindings else 'NONE FOUND'}")
    if napari_module is not None and not bindings:
        problems.append("napari has no Qt binding; conda install -c conda-forge pyside6")
    if len(bindings) > 1:
        print("            WARNING: more than one Qt binding installed; napari "
              "picks one unpredictably")

    section("5. Plugin registration")
    entries = list(md.entry_points(group="napari.manifest"))
    if entries:
        for entry in entries:
            print(f"entry point {entry.name} = {entry.value}")
    else:
        print("entry point NONE registered in this environment")
        if not problems:
            problems.append("No napari.manifest entry points at all — nothing is "
                            "installed for napari to discover.")
    ours = [e for e in entries if e.name == "micromethods"]
    if entries and not ours:
        problems.append("Other plugins are registered but micromethods is not; "
                        "its metadata was not installed here.")

    if ours:
        try:
            from npe2 import PluginManifest
            manifest = PluginManifest.from_distribution("micromethods")
            widgets = [w.display_name for w in manifest.contributions.widgets]
            print(f"manifest    loads OK, widgets: {widgets or 'NONE DECLARED'}")
            if not widgets:
                problems.append("The manifest declares no widgets.")
        except ImportError:
            print("manifest    npe2 not installed, cannot verify "
                  "(pip install npe2)")
        except Exception as exc:
            print(f"manifest    FAILS TO LOAD -> {type(exc).__name__}: {exc}")
            problems.append(
                "napari sees the entry point but cannot load the manifest. This is "
                "exactly what makes the plugin silently absent from the Plugins "
                "menu; the cause is almost always that the package itself is not "
                "importable (see section 3).")

    section("6. What napari itself would discover")
    try:
        from npe2 import PluginManager

        pm = PluginManager.instance()
        pm.discover()
        names = sorted(pm._manifests) if hasattr(pm, "_manifests") else []
        print(f"discovered  {', '.join(names) if names else 'nothing'}")
        if names and "micromethods" not in names:
            problems.append("npe2 discovery ran but did not register micromethods.")
    except ImportError:
        print("npe2 not installed; skipping (pip install npe2)")
    except Exception as exc:
        print(f"discovery failed: {type(exc).__name__}: {exc}")

    section("7. Current directory layout")
    cwd = Path.cwd()
    print(f"cwd         {cwd}")
    for name in ("pyproject.toml", "micromethods", "micromethods/__init__.py",
                 "micromethods-tool", "tests"):
        path = cwd / name
        print(f"  {'yes' if path.exists() else 'no ':<4} {name}")
    if (cwd / "micromethods-tool").exists() and not (cwd / "micromethods").exists():
        problems.append(
            "The package is inside micromethods-tool/ rather than next to "
            "pyproject.toml. Run: python tools/flatten_repo.py --apply")

    section("Verdict")
    if problems:
        for i, problem in enumerate(problems, 1):
            print(f"{i}. {problem}")
        return 1
    print("Everything resolves. The plugin should appear under "
          "Plugins > Methods reporter.\nIf it does not, restart napari "
          "completely — manifests are read once at startup.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
