"""Zeiss CZI and Leica LIF metadata-block parsing.

These exercise the XML walk directly, so they run without pylibCZIrw or
readlif installed - only the *retrieval* of that XML needs the vendor
libraries, not its interpretation.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET

import pytest

import fixture_data
from micromethods import render
from micromethods.gaps import find_gaps
from micromethods.readers import czi, lif
from micromethods.schema import Record, raw


@pytest.fixture(scope="module")
def czi_record() -> Record:
    rec = Record(file_format="CZI (Zeiss)")
    czi._parse(ET.fromstring(fixture_data.CZI_XML), rec)
    return rec


@pytest.fixture(scope="module")
def lif_record() -> Record:
    rec = Record(file_format="Leica LIF")
    lif._parse(ET.fromstring(fixture_data.LIF_XML), rec)
    return rec


# --- Zeiss ---------------------------------------------------------------

@pytest.mark.parametrize("path, expected", [
    ("stand.model", "LSM 980"),
    ("stand.stand_type", "inverted"),
    ("stand.modality", "point-scanning confocal"),
    ("objective.na", 1.4),
    ("objective.magnification", 63.0),
    ("objective.immersion", "oil"),
    ("acquisition.pixel_size_x_um", 0.065),
    ("acquisition.z_step_um", 0.28),
    ("acquisition.pixel_dwell_us", 2.06),
    ("acquisition.line_averaging", 2),
    ("acquisition.channel_mode", "sequential"),
    ("software.version", "3.9.023"),
])
def test_czi_fields(czi_record, path, expected):
    from micromethods.schema import path_get
    assert raw(path_get(czi_record, path)) == expected


def test_czi_z_range_is_derived(czi_record):
    # 21 planes at 0.28 µm spacing spans 20 intervals, not 21.
    assert raw(czi_record.acquisition.z_range_um) == pytest.approx(5.6)


def test_czi_channels(czi_record):
    assert len(czi_record.channels) == 2
    first, second = czi_record.channels
    assert raw(first.pinhole_au) == 1.02
    assert raw(first.detection_range_nm) == (493, 556)
    assert raw(second.detector.model) == "GaAsP-PMT2"


def test_czi_methods_text_mentions_the_essentials(czi_record):
    text = render.methods_text(czi_record)
    for fragment in ("LSM 980", "63x/1.4", "oil", "488 and 561 nm",
                     "1.02 AU pinhole", "0.065 µm/pixel", "0.28 µm z-step"):
        assert fragment in text, fragment
    assert find_gaps(czi_record).completeness > 0.8


# --- Leica ---------------------------------------------------------------

@pytest.mark.parametrize("path, expected", [
    ("stand.model", "STELLARIS 8"),
    ("stand.modality", "point-scanning confocal"),
    ("objective.na", 1.4),
    ("objective.immersion", "oil"),
    ("objective.refractive_index", 1.518),
    ("acquisition.z_step_um", 0.3),
    ("acquisition.tile_overlap_percent", 10.0),
    ("software.version", "4.5.0.25531"),
])
def test_lif_fields(lif_record, path, expected):
    from micromethods.schema import path_get
    assert raw(path_get(lif_record, path)) == expected


def test_lif_pixel_size_spans_intervals_not_pixels(lif_record):
    # Leica stores the total length; the step is length / (N - 1).
    assert raw(lif_record.acquisition.pixel_size_x_um) == pytest.approx(0.113763, abs=1e-6)


def test_lif_spectral_detection(lif_record):
    assert len(lif_record.channels) == 2
    first, second = lif_record.channels
    assert raw(first.detection_range_nm) == (498, 545)
    assert raw(first.fluorophore) == "Alexa 488"
    assert raw(second.detector.kind) == "HyD hybrid detector"
    assert raw(first.pinhole_au) == 1.0


def test_lif_laser_lines(lif_record):
    lines = sorted(raw(ls.wavelength_nm) for ls in lif_record.light_sources)
    assert lines == [488, 552]


def test_lif_objective_designation_is_parsed(lif_record):
    assert raw(lif_record.objective.correction) == "Plan Apochromat"
