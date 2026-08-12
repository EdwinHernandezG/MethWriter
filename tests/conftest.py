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


def _require_real_installation(config: pytest.Config) -> None:
    """Fail unless the package is genuinely installed in this environment.

    Two things masquerade as an installation and must not be accepted:

    * running pytest from the repository root puts the source tree on
      sys.path, so ``import micromethods`` succeeds regardless;
    * a leftover ``micromethods.egg-info/`` directory from an earlier build
      provides distribution metadata even after an uninstall.

    Neither gives a working console script or a discoverable napari plugin, so
    accepting them would let CI pass on an installation that fails for users.
    """
    import importlib.metadata as md

    root = Path(str(config.rootpath)).resolve()
    locations = []
    for dist in md.distributions():
        if (dist.metadata["Name"] or "").lower().replace("-", "_") != "micromethods":
            continue
        path = getattr(dist, "_path", None)
        if path is not None:
            locations.append(Path(str(path)).resolve())

    if not locations:
        raise pytest.UsageError(
            "micromethods imports from the source tree but is not installed "
            "in this environment: there is no distribution metadata, so the "
            "console script and the napari plugin will not work.\n"
            '    python -m pip install -e ".[test]"'
        )

    # An editable install legitimately leaves an .egg-info directory in the
    # source tree *as well as* a .dist-info in site-packages. Only the latter
    # proves the environment knows about the package; if the in-tree residue
    # is all there is, the install did not happen (or was uninstalled and the
    # residue left behind, which is what makes this failure so confusing).
    if all(location.parent == root for location in locations):
        names = ", ".join(sorted(p.name for p in locations))
        raise pytest.UsageError(
            f"The only distribution metadata found is build residue in the "
            f"repository root ({names}), not an installation in this "
            "environment. Remove it and install properly:\n"
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
