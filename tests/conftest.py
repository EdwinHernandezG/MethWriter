"""Shared pytest fixtures and environment checks.

Two things this file guards against, both learned the hard way:

* **Silent skipping.** Optional readers may legitimately be absent in a
  minimal local install, so those tests skip. But `tifffile` and `numpy` are
  *declared dependencies*: if they are missing, the installation is broken and
  a run reporting "62 skipped, 36 passed" is worse than useless, because it is
  green. Under CI (or `MICROMETHODS_STRICT_DEPS=1`) their absence is an error.

* **Testing the wrong code.** Manipulating `sys.path` would let the suite
  import the package straight from the source tree, so a broken
  `pip install -e .` would go unnoticed. There is no such fallback here: the
  suite tests what is installed, which is what users run.
"""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path

import pytest

# Declared in pyproject.toml; their absence means the install is broken.
REQUIRED = ("numpy", "tifffile")

STRICT = bool(os.environ.get("CI") or os.environ.get("MICROMETHODS_STRICT_DEPS"))

_LOCATION = pytest.StashKey[Path]()


def _missing_required() -> list[str]:
    return [name for name in REQUIRED if importlib.util.find_spec(name) is None]


def pytest_configure(config: pytest.Config) -> None:
    """Refuse to run a misleading test session."""
    try:
        import micromethods
    except ImportError as exc:
        raise pytest.UsageError(
            f"micromethods is not importable ({exc}). Install it first, from "
            "the directory holding both pyproject.toml and micromethods/:\n"
            '    python -m pip install -e ".[test]"'
        ) from exc

    config.stash[_LOCATION] = Path(micromethods.__file__).resolve().parent

    # Importability is not proof of installation: running pytest from the
    # repository root puts the source tree on sys.path, so `import
    # micromethods` succeeds even when nothing was installed. Distribution
    # metadata is the real test - and it is exactly what napari needs in order
    # to find the plugin, so checking it here catches a broken install before
    # a user discovers it as a missing menu entry.
    if STRICT:
        _require_real_installation(config)

    missing = _missing_required()
    if missing and STRICT:
        raise pytest.UsageError(
            f"Required dependencies are missing: {', '.join(missing)}. They are "
            "declared in pyproject.toml, so the install did not complete. Most "
            "of the suite would skip and the run would look green.\n"
            '    python -m pip install -e ".[test]"'
        )


def _distribution_locations(name: str = "micromethods") -> list[Path]:
    """Every on-disk metadata directory the environment has for ``name``.

    Returns an empty list when the distributions exist but expose no path,
    which some editable-install finders do; callers must treat that as
    "unknown", not as "missing".
    """
    import importlib.metadata as md

    found: list[Path] = []
    for dist in md.distributions():
        try:
            dist_name = (dist.metadata["Name"] or "")
        except Exception:  # a malformed distribution elsewhere in site-packages
            continue
        if dist_name.lower().replace("-", "_") != name:
            continue
        path = getattr(dist, "_path", None)
        if path is not None:
            found.append(Path(str(path)).resolve())
    return found


def _site_packages_evidence(name: str = "micromethods") -> list[str]:
    """Evidence in site-packages that the environment knows about ``name``.

    Covers all three install styles, because failing a working build is worse
    than missing a broken one:

    * modern:  ``name-VERSION.dist-info/`` plus an ``__editable__*.pth``;
    * legacy:  ``name.egg-link`` referencing the source tree;
    * plain:   an installed ``name/`` package directory.
    """
    import site
    import sys

    candidates: list[Path] = []
    for getter in ("getsitepackages", "getusersitepackages"):
        try:
            value = getattr(site, getter)()
        except Exception:
            continue
        candidates.extend(Path(v) for v in ([value] if isinstance(value, str) else value))
    candidates.append(Path(sys.prefix) / "lib" / "site-packages")

    hits: list[str] = []
    for folder in candidates:
        if not folder.is_dir():
            continue
        try:
            entries = list(folder.iterdir())
        except OSError:
            continue
        for entry in entries:
            lowered = entry.name.lower()
            if lowered.startswith(f"{name}-") and lowered.endswith(".dist-info"):
                hits.append(str(entry))
            elif lowered in (f"{name}.egg-link", f"{name}.pth"):
                hits.append(str(entry))
            elif lowered.startswith("__editable__") and name in lowered:
                hits.append(str(entry))
            elif entry.name == name and entry.is_dir():
                hits.append(str(entry))
    return hits


def _environment_summary(config: pytest.Config) -> str:
    """Everything needed to diagnose an install problem from a CI log alone."""
    import shutil
    import sys

    import micromethods

    lines = [
        f"    python      {sys.executable}",
        f"    prefix      {sys.prefix}",
        f"    rootdir     {config.rootpath}",
        f"    imported    {Path(micromethods.__file__).resolve().parent}",
        f"    console     {shutil.which('micromethods') or 'not on PATH'}",
    ]
    locations = _distribution_locations()
    if locations:
        for location in locations:
            lines.append(f"    metadata    {location}")
    else:
        lines.append("    metadata    none found on sys.path")
    for evidence in _site_packages_evidence():
        lines.append(f"    installed   {evidence}")
    return "\n".join(lines)


def _require_real_installation(config: pytest.Config) -> None:
    """Fail unless the package is genuinely installed in this environment.

    Two things masquerade as an installation:

    * running pytest from the repository root puts the source tree on
      sys.path, so ``import micromethods`` succeeds regardless;
    * a leftover ``micromethods.egg-info/`` directory from an earlier build
      provides metadata even after an uninstall.

    Neither gives a working console script or a discoverable napari plugin.
    The check is deliberately conservative: it only fails on positive evidence
    of a problem, because a false alarm here blocks a working build.
    """
    import importlib.metadata as md

    try:
        md.distribution("micromethods")
    except md.PackageNotFoundError:
        raise pytest.UsageError(
            "micromethods imports from the source tree but is not installed in "
            "this environment, so the console script and the napari plugin "
            "will not work.\n\n"
            f"{_environment_summary(config)}\n\n"
            "Install it from the directory holding pyproject.toml:\n"
            '    python -m pip install -e ".[test]"'
        ) from None
    except Exception:
        # Metadata exists but could not be read cleanly; not worth failing on.
        return

    locations = _distribution_locations()
    if not locations:
        # Installed, but the finder exposes no path. Nothing to verify.
        return

    # An editable install legitimately leaves an .egg-info directory in the
    # source tree *as well as* a .dist-info in site-packages. Only the latter
    # proves the environment knows about the package; if the in-tree residue is
    # all there is, the install did not happen, or was uninstalled and the
    # residue left behind - which is what makes this failure so confusing.
    root = Path(str(config.rootpath)).resolve()
    if all(location.parent == root for location in locations):
        # A legacy editable install also keeps its metadata in the source tree,
        # linking to it from site-packages. Only complain when site-packages
        # knows nothing about the package at all.
        if _site_packages_evidence():
            return
        names = ", ".join(sorted(p.name for p in locations))
        raise pytest.UsageError(
            f"The only distribution metadata is build residue in the "
            f"repository root ({names}), not an installation in this "
            "environment.\n\n"
            f"{_environment_summary(config)}\n\n"
            "Remove the residue and install properly:\n"
            f"    rm -rf {names}\n"
            '    python -m pip install -e ".[test]"'
        )


def pytest_report_header(config: pytest.Config) -> list[str]:
    optional = ("readlif", "pylibCZIrw", "aicspylibczi", "czifile", "ome_types",
                "napari", "npe2")
    names = REQUIRED + optional
    present = [n for n in names if importlib.util.find_spec(n)]
    absent = [n for n in names if not importlib.util.find_spec(n)]
    lines = [f"micromethods: {config.stash.get(_LOCATION, None)}",
             f"available: {', '.join(present) or 'none'}"]
    if absent:
        lines.append(f"absent:    {', '.join(absent)}")
    return lines


# --------------------------------------------------------------------------
# Dependency guard for tests that write or read a real TIFF.
#
# Outside CI this skips; under CI pytest_configure has already failed the run,
# so the mark can never hide a broken install.
# --------------------------------------------------------------------------

needs_imaging = pytest.mark.skipif(
    bool(_missing_required()),
    reason=f"requires {' and '.join(REQUIRED)} (declared dependencies)",
)


def _write(tmp_path_factory, folder: str, filename: str, xml_attr: str,
           **kwargs) -> Path:
    from tests import fixture_data

    target = tmp_path_factory.mktemp(folder) / filename
    return fixture_data.write_tiff(target, getattr(fixture_data, xml_attr), **kwargs)


@pytest.fixture(scope="session")
def blaze_file(tmp_path_factory) -> Path:
    """A Blaze OME-TIFF: sparse Image block, metadata in StructuredAnnotations."""
    return _write(tmp_path_factory, "blaze",
                  "10-13-53_demo_Blaze_C00.ome.tif", "BLAZE_OME")


@pytest.fixture(scope="session")
def blaze_2008_file(tmp_path_factory) -> Path:
    """A Blaze OME-TIFF written against the older OME 2008-02 schema."""
    return _write(tmp_path_factory, "blaze2008",
                  "10-13-53_spaomtest1_Blaze_C00.ome.tif", "BLAZE_2008_OME")


@pytest.fixture(scope="session")
def blaze_twocolour_file(tmp_path_factory) -> Path:
    """A real two-colour Blaze mosaic: SizeC=2 with bare <Channel> elements."""
    return _write(tmp_path_factory, "twocolour",
                  "11-14-17_Alg_tl_4X_1Z_2Colormosaic_Blaze_C00.ome.tif",
                  "BLAZE_TWOCOLOUR_OME")


@pytest.fixture(scope="session")
def confocal_file(tmp_path_factory) -> Path:
    """A well-populated OME-TIFF with a full Instrument block."""
    return _write(tmp_path_factory, "confocal", "confocal_demo.ome.tif",
                  "RICH_OME", shape=(24, 64, 64))


@pytest.fixture(scope="session")
def legacy_blaze_file(tmp_path_factory) -> Path:
    """An older light-sheet OME-TIFF whose extras live in a text sidecar."""
    from tests import fixture_data

    folder = tmp_path_factory.mktemp("legacy")
    path = fixture_data.write_tiff(folder / "blaze_legacy.ome.tif",
                                   fixture_data.LEGACY_BLAZE_OME, shape=(8, 64, 64))
    (folder / "blaze_legacy_MetaData.txt").write_text(fixture_data.SIDECAR)
    return path
