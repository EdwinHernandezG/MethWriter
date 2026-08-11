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


def test_annotations_on_a_later_page_are_still_found(tmp_path):
    """Not every writer keeps the whole OME-XML in the first IFD."""
    import numpy as np
    import tifffile

    from tests import fixture_data

    full = fixture_data.BLAZE_OME
    minimal = full[:full.index("<StructuredAnnotations>")] + "</OME>"
    minimal = minimal.replace(
        '<AnnotationRef ID="Annotation:CustomAttributes1"/>', "")

    path = tmp_path / "split.ome.tif"
    data = np.zeros((3, 32, 32), "uint16")
    with tifffile.TiffWriter(str(path)) as writer:
        writer.write(data[0], description=minimal, photometric="minisblack")
        writer.write(data[1], description="", photometric="minisblack")
        writer.write(data[2], description=full, photometric="minisblack")

    rec = readers.read(path)
    assert raw(rec.objective.designation) == "LVBT 4x"
    assert raw(rec.extras["lightsheet"]["sheet_na"]) == 0.0597
    assert any("page 2" in note for note in rec.notes)


def test_malformed_xml_degrades_instead_of_crashing(tmp_path):
    """tifffile rejects a broken OME header outright (is_ome becomes False), so
    the reader must say the header is unusable rather than raise. This is also
    how to tell the two situations apart in a report: a file whose XML is
    broken says so, while a file with a *valid but sparse* header says
    nothing and simply reports fewer fields."""
    import numpy as np
    import tifffile

    path = tmp_path / "broken.ome.tif"
    tifffile.imwrite(str(path), np.zeros((2, 16, 16), "uint16"),
                     description='<?xml version="1.0"?><OME><Image ID="Image:0">',
                     photometric="minisblack")
    rec = readers.read(path)
    assert rec.file_format == "TIFF"
    assert any("does not carry an OME-XML header" in note or
               "not well formed" in note for note in rec.notes)


# --- OME 2008-02 -----------------------------------------------------------

@pytest.fixture(scope="module")
def blaze_2008(blaze_2008_file) -> Record:
    rec = readers.read(blaze_2008_file)
    profile_store.apply_best(rec)
    return rec


def test_2008_schema_is_recognised(blaze_2008):
    assert blaze_2008.vendor_raw["ome_schema"] == "2008-02"
    assert any("2008-02 schema" in note for note in blaze_2008.notes)


def test_2008_custom_attributes_are_read(blaze_2008):
    """ca:CustomAttributes is the 2008 equivalent of StructuredAnnotations."""
    assert raw(blaze_2008.software.name) == "Imspector Pro"
    assert raw(blaze_2008.software.version) == "7.7.2"
    assert raw(blaze_2008.extras["instrument"]["serial_number"]) == "UM-3095"


def test_2008_logical_channel_is_read(blaze_2008):
    """<LogicalChannel ExWave=.. EmWave=..> is a sibling of <Pixels> in 2008."""
    channel = blaze_2008.channels[0]
    assert raw(channel.excitation_nm) == 640.0
    assert raw(channel.emission_nm) == 680.0
    assert raw(channel.detection_range_nm) == (665, 695)
    assert raw(channel.exposure_time_ms) == pytest.approx(20.099998)


def test_2008_properties_reach_the_report(blaze_2008):
    assert raw(blaze_2008.objective.designation) == "LVBT 4x"
    assert raw(blaze_2008.objective.immersion_medium) == "ethyl cinnamate (ECI)"
    assert raw(blaze_2008.acquisition.tiles) == 33
    assert raw(blaze_2008.extras["lightsheet"]["sheet_na"]) == 0.0597


def test_2008_plane_timing_child_element(blaze_2008):
    # 2008 puts exposure in <PlaneTiming>, not on <Plane> itself.
    assert raw(blaze_2008.channels[0].exposure_time_ms) is not None


def test_2008_coverage_is_comparable_to_2016(blaze_2008, blaze):
    from micromethods.gaps import find_gaps
    assert find_gaps(blaze_2008).completeness >= find_gaps(blaze).completeness - 0.05
