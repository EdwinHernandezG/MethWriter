"""Miltenyi Blaze OME-TIFF: metadata carried in OME StructuredAnnotations.

The Blaze writes a nearly empty <Image> block. Everything reportable lives in
a CustomAttributes annotation plus several hundred <prop fname=".."/> entries
inside the same file - no sidecar, no companion XML.
"""

from __future__ import annotations

import pytest

from micromethods import profiles as profile_store
from micromethods import readers, render
from micromethods.gaps import find_gaps
from micromethods.schema import Record, path_get, raw


@pytest.fixture(scope="module")
def blaze(blaze_file) -> Record:
    rec = readers.read(blaze_file)
    profile_store.apply_best(rec)
    return rec


def test_identified_as_a_blaze(blaze):
    assert blaze.instrument_key == "miltenyi_blaze"
    assert raw(blaze.stand.modality) == "light-sheet fluorescence microscopy"
    assert raw(blaze.extras["instrument"]["serial_number"]) == "UM-3095"


@pytest.mark.parametrize("path, expected", [
    ("software.name", "Imspector Pro"),
    ("software.version", "7.7.2"),
    ("objective.designation", "LVBT 4x"),
    ("objective.magnification", 4.0),
    ("objective.immersion_medium", "ethyl cinnamate (ECI)"),
    ("objective.refractive_index", 1.558),
    ("stand.magnification_changer", "zoom body set to 0.6x"),
    ("acquisition.pixel_size_x_um", 2.708333),
    ("acquisition.z_step_um", 5.0),
    ("acquisition.tiles", 33),
    ("acquisition.tile_overlap_percent", 11.0),
])
def test_annotation_fields(blaze, path, expected):
    assert raw(path_get(blaze, path)) == expected


def test_z_range(blaze):
    assert raw(blaze.acquisition.z_range_um) == pytest.approx(5220.0)


def test_channel_resolved_from_the_configured_filter_table(blaze):
    # The props describe ten configured laser/filter slots; only the one
    # matching the OME channel's Ex/Em pair was acquired.
    channel = blaze.channels[0]
    assert raw(channel.excitation_nm) == 640.0
    assert raw(channel.detection_range_nm) == (665, 695)
    assert raw(channel.filter_set) == "680/30 bandpass emission filter"
    assert raw(channel.exposure_time_ms) == pytest.approx(20.099998)
    assert raw(channel.laser_power) == 21.0
    assert raw(channel.light_source.manufacturer) == "Lasos beam combiner"
    assert raw(channel.detector.kind) == "sCMOS camera"
    assert raw(channel.detector.binning) == "1x1"


@pytest.mark.parametrize("key, expected", [
    ("sheet_na", 0.0597),
    ("sheet_thickness", 6.111),
    ("sheet_width", 50.0),
])
def test_light_sheet_geometry(blaze, key, expected):
    assert raw(blaze.extras["lightsheet"][key]) == expected


def test_pyramid_levels_are_not_mistaken_for_datasets(blaze):
    assert raw(blaze.extras["image_data"]["pyramid_levels"]) == 3
    assert any("resolution pyramid" in note for note in blaze.notes)


def test_processing_history_is_captured(blaze):
    assert "ImStitcher" in str(raw(blaze.extras["processing"]["steps"], ""))


def test_contradictory_objective_na_is_flagged_not_guessed(blaze):
    # 'Blaze ObjectiveNA' says 0.1; the PSF calibration block says 0.35.
    assert any("Objective NA is ambiguous" in note for note in blaze.notes)


def test_profile_override_can_correct_a_wrong_vendor_field(blaze_file, tmp_path):
    import yaml

    profile = tmp_path / "blaze_override.yaml"
    profile.write_text(yaml.safe_dump({
        "key": "miltenyi_blaze",
        "match": {"instrument_key": ["miltenyi_blaze"]},
        "overrides": {"objective.na": 0.35},
    }))
    rec = readers.read(blaze_file)
    profile_store.apply_best(rec, [profile])
    assert raw(rec.objective.na) == 0.35
    assert any("overrode objective.na" in note for note in rec.notes)


def test_binary_only_stub_follows_the_dataset_master(blaze_file, tmp_path):
    """Multi-file datasets keep the annotations in one master file only."""
    import numpy as np
    import tifffile

    master = tmp_path / blaze_file.name
    master.write_bytes(blaze_file.read_bytes())
    stub = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<OME xmlns="http://www.openmicroscopy.org/Schemas/OME/2016-06">'
        f'<BinaryOnly MetadataFile="{master.name}" UUID="urn:uuid:1234"/></OME>')
    tile = tmp_path / "tile07.ome.tif"
    tifffile.imwrite(str(tile), np.zeros((2, 16, 16), "uint16"),
                     description=stub, photometric="minisblack")

    rec = readers.read(tile)
    assert raw(rec.objective.designation) == "LVBT 4x"
    assert any("BinaryOnly" in note for note in rec.notes)


def test_methods_text_reads_like_methods(blaze):
    text = render.methods_text(blaze)
    for fragment in ("UltraMicroscope Blaze", "light-sheet", "640 nm",
                     "665 and 695 nm", "20.1 ms exposure", "2.708 µm/pixel",
                     "33 tiles", "Imspector Pro"):
        assert fragment in text, fragment
    assert find_gaps(blaze).completeness > 0.8
