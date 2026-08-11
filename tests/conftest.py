"""Shared pytest fixtures.

The suite is written to run against the *installed* package, which is what CI
and users actually exercise. The sys.path fallback below only exists so that
`pytest` also works in a checkout where nobody has run `pip install -e .` yet.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import fixture_data  # noqa: E402  (tests dir is on sys.path via pytest)

# Formats that need an optional dependency are skipped rather than failed, so
# a minimal install still gets a meaningful test run.
tifffile = pytest.importorskip


@pytest.fixture(scope="session")
def blaze_file(tmp_path_factory) -> Path:
    """A Blaze OME-TIFF: empty Image block, metadata in StructuredAnnotations."""
    pytest.importorskip("tifffile")
    pytest.importorskip("numpy")
    folder = tmp_path_factory.mktemp("blaze")
    return fixture_data.write_tiff(
        folder / "10-13-53_demo_Blaze_C00.ome.tif", fixture_data.BLAZE_OME)


@pytest.fixture(scope="session")
def confocal_file(tmp_path_factory) -> Path:
    """A well-populated OME-TIFF with a full Instrument block."""
    pytest.importorskip("tifffile")
    pytest.importorskip("numpy")
    folder = tmp_path_factory.mktemp("confocal")
    return fixture_data.write_tiff(folder / "confocal_demo.ome.tif",
                                   fixture_data.RICH_OME, shape=(24, 64, 64))


@pytest.fixture(scope="session")
def legacy_blaze_file(tmp_path_factory) -> Path:
    """An older light-sheet OME-TIFF whose extras live in a text sidecar."""
    pytest.importorskip("tifffile")
    pytest.importorskip("numpy")
    folder = tmp_path_factory.mktemp("legacy")
    path = fixture_data.write_tiff(folder / "blaze_legacy.ome.tif",
                                   fixture_data.LEGACY_BLAZE_OME, shape=(8, 64, 64))
    (folder / "blaze_legacy_MetaData.txt").write_text(fixture_data.SIDECAR)
    return path
