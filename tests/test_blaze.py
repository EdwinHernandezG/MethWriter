"""Miltenyi Blaze OME-TIFF: metadata carried in OME StructuredAnnotations.

The Blaze writes a nearly empty <Image> block. Everything reportable lives in
a CustomAttributes annotation plus several hundred <prop fname=".."/> entries
inside the same file - no sidecar, no companion XML.
"""

from __future__ import annotations

import pytest

from tests.conftest import needs_imaging

from micromethods import profiles as profile_store
from micromethods import readers, render
from micromethods.gaps import find_gaps
from micromethods.schema import Record, Source, path_get, raw


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
    ("objective.immersion_medium", "ECI"),
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
    assert raw(blaze_2008.objective.immersion_medium) == "ECI"
    assert raw(blaze_2008.acquisition.tiles) == 33
    assert raw(blaze_2008.extras["lightsheet"]["sheet_na"]) == 0.0597


def test_2008_plane_timing_child_element(blaze_2008):
    # 2008 puts exposure in <PlaneTiming>, not on <Plane> itself.
    assert raw(blaze_2008.channels[0].exposure_time_ms) is not None


def test_2008_coverage_is_comparable_to_2016(blaze_2008, blaze):
    from micromethods.gaps import find_gaps
    assert find_gaps(blaze_2008).completeness >= find_gaps(blaze).completeness - 0.05


# --- a real two-colour mosaic ----------------------------------------------

@pytest.fixture(scope="module")
def twocolour(blaze_twocolour_file) -> Record:
    rec = readers.read(blaze_twocolour_file)
    profile_store.apply_best(rec)
    return rec


def test_both_channels_are_recovered(twocolour):
    """The OME <Channel> elements are bare, so the channel count and the
    wavelengths both have to come from Blaze FilterInMeasurement flags."""
    assert len(twocolour.channels) == 2
    pairs = {(raw(c.excitation_nm), raw(c.emission_nm)) for c in twocolour.channels}
    assert pairs == {(561.0, 595.0), (488.0, 525.0)}


def test_each_channel_gets_its_own_filter_and_power(twocolour):
    by_excitation = {raw(c.excitation_nm): c for c in twocolour.channels}
    assert raw(by_excitation[488.0].detection_range_nm) == (500, 550)
    assert raw(by_excitation[561.0].detection_range_nm) == (590, 650)
    assert raw(by_excitation[488.0].laser_power) == 20.0
    assert raw(by_excitation[561.0].laser_power) == 10.0


def test_global_exposure_applies_to_every_channel(twocolour):
    # 'Blaze IndividualExpTimes = 0' means one exposure for all channels.
    exposures = {raw(c.exposure_time_ms) for c in twocolour.channels}
    assert len(exposures) == 1


def test_corrupt_overlap_property_is_rejected(twocolour):
    """'UserRequestedOverlapInPercent' holds 1092616192 in this file; the
    per-axis properties hold the real 10%."""
    assert raw(twocolour.acquisition.tile_overlap_percent) == 10.0
    assert raw(twocolour.acquisition.tiles) == 4


def test_blaze_objectives_report_dynamic_chromatic_correction(twocolour):
    correction = str(raw(twocolour.objective.correction, ""))
    assert "dynamic chromatic correction" in correction
    assert "[MISSING" not in render.methods_text(twocolour)


def test_acronyms_survive_label_generation(twocolour):
    text = render.methods_text(twocolour)
    assert "sheet NA" in text
    assert "sheet na" not in text


def test_acknowledgement_names_facility_and_instrument(twocolour):
    text = render.acknowledgement(twocolour)
    assert "Ci2A MASTER Core Facility" in text
    assert "Miltenyi Biotec UltraMicroscope Blaze" in text
    assert "UM-3140" in text
    assert "[core facility name]" not in text and "[instrument]" not in text


def test_channel_order_is_flagged_as_inferred(twocolour):
    assert any("acquisition order" in note for note in twocolour.notes)


def test_imaging_medium_uses_the_vendors_own_name(twocolour):
    """The user selected 'MACS IS' in Imspector and that is what their protocol
    says, so it is what the methods text should say - once."""
    text = render.methods_text(twocolour)
    assert "dipping objective (LVBT 4x) in MACS IS" in text
    assert text.count("MACS IS") == 1
    assert "MACS Imaging Solution (Miltenyi Biotec)" not in text
    # The expansion is still available for the checklist's name-and-manufacturer
    # requirement.
    assert raw(twocolour.specimen.mounting_medium_manufacturer) == "Miltenyi Biotec"


def test_objective_correction_gets_its_own_clause(twocolour):
    text = render.methods_text(twocolour)
    assert "The objective provides dynamic chromatic correction." in text


def test_dipping_system_has_no_cover_glass_or_mountant(twocolour):
    """The sample is submerged in the imaging chamber, so the cover-glass and
    mounting-medium requirements are answered by that fact rather than left
    open or answered wrongly."""
    text = render.methods_text(twocolour)
    assert "cover glass" not in text
    assert raw(twocolour.specimen.mounting_medium) == "MACS IS"
    assert "not applicable" in str(raw(twocolour.specimen.coverglass_no, ""))


def test_channels_are_ordered_by_ascending_excitation(twocolour):
    """Imspector stores slots longest-wavelength-first but acquires shortest
    first, so C00 of a 488/561 experiment is the 488 nm stack."""
    excitations = [raw(c.excitation_nm) for c in twocolour.channels]
    assert excitations == [488.0, 561.0]


def test_channel_mode_is_sequential_on_a_single_light_path(twocolour):
    assert raw(twocolour.acquisition.channel_mode) == "sequential"
    assert "Channels were acquired sequentially" in render.methods_text(twocolour)


@pytest.mark.parametrize("name, expected", [
    ("11-14-17_Alg_Blaze[00 x 00]_C00_xyz-Table Z0000.ome.tif",
     {"tile_x": 0, "tile_y": 0, "channel": 0, "plane": 0}),
    ("10-13-53_x_Blaze[02 x 01]_C01_xyz-Table Z0034.ome.tif",
     {"tile_x": 2, "tile_y": 1, "channel": 1, "plane": 34}),
    ("stitched_output.ome.tif", {}),
])
def test_filename_pattern_is_parsed(name, expected):
    from micromethods.readers.imspector import parse_filename
    assert parse_filename(name) == expected


def test_tile_position_is_reported(twocolour, blaze_twocolour_file):
    # The fixture file name carries no [XX x YY] block, so nothing is claimed.
    assert "tile_position" not in twocolour.extras.get("dataset", {})


# --- camera identification --------------------------------------------------

@pytest.mark.parametrize("info, expected", [
    ("Camera: pco.edge 4.2 M CLHS rolling shutter (s/n: 61010487)  Hardware 00: "
     "(MAIN 0015001730) 0.19",
     {"manufacturer": "PCO", "model": "pco.edge 4.2 M CLHS",
      "shutter": "rolling shutter", "serial": "61010487"}),
    ("Camera: Zyla 4.2 PLUS (s/n: X-1234) Firmware 00: (A) 1.0",
     {"manufacturer": "Andor", "model": "Zyla 4.2 PLUS", "serial": "X-1234"}),
    ("Camera: ORCA-Flash4.0 V3 global shutter",
     {"manufacturer": "Hamamatsu", "model": "ORCA-Flash4.0 V3",
      "shutter": "global shutter"}),
    ("no camera line here", {}),
    (None, {}),
])
def test_camera_info_is_parsed(info, expected):
    from micromethods.readers.imspector import parse_camera_info
    assert parse_camera_info(info) == expected


def test_camera_model_comes_from_the_file_not_a_profile(twocolour):
    """'Camera Info' names the camera outright, so no facility has to type it."""
    detector = twocolour.channels[0].detector
    assert raw(detector.model) == "pco.edge 4.2 M CLHS"
    assert raw(detector.manufacturer) == "PCO"
    assert raw(detector.name) == "61010487"
    assert detector.model.source is Source.FILE


def test_camera_appears_in_the_methods_text(twocolour):
    text = render.methods_text(twocolour)
    assert "pco.edge 4.2 M CLHS sCMOS camera (PCO)" in text


def test_sensor_pitch_is_derived(twocolour):
    """13312 µm across 2048 pixels is the 6.5 µm pitch quoted for this sensor."""
    pitch = twocolour.extras["detection"]["sensor_pixel_pitch"]
    assert raw(pitch) == 6.5
    assert pitch.source is Source.DERIVED


def test_shutter_mode_is_recorded(twocolour):
    assert raw(twocolour.extras["detection"]["shutter_mode"]) == "rolling shutter"


def test_detector_model_is_no_longer_a_gap(twocolour):
    from micromethods.gaps import find_gaps
    missing = {q.path for q in find_gaps(twocolour).blocking}
    assert "channels[0].detector.model" not in missing
    assert "channels[1].detector.model" not in missing


# --- redundancy in the generated prose --------------------------------------

def test_camera_and_exposure_are_stated_once_not_per_channel(twocolour):
    """One camera, one exposure: say so once. Repeating it on every channel is
    noise a reader has to filter out."""
    text = render.methods_text(twocolour)
    assert text.count("pco.edge 4.2 M CLHS") == 1
    assert text.count("150 ms exposure") == 1
    assert "Both channels were recorded on a pco.edge 4.2 M CLHS sCMOS camera " \
           "(PCO) with 150 ms exposure." in text


def test_per_channel_settings_still_appear(twocolour):
    """Hoisting the shared parts must not lose what differs between channels."""
    text = render.methods_text(twocolour)
    assert "excited at 488 nm and detected between 500 and 550 nm with 20% laser power" in text
    assert "excited at 561 nm and detected between 590 and 650 nm with 10% laser power" in text


def test_differing_exposures_stay_on_their_channels(twocolour):
    """The moment a setting varies, it belongs back on the individual channels."""
    import copy

    from micromethods.schema import Source as S
    from micromethods.schema import Value

    rec = copy.deepcopy(twocolour)
    rec.channels[1].exposure_time_ms = Value(300.0, S.FILE, "test", "ms")
    text = render.methods_text(rec)
    assert "150 ms exposure" in text and "300 ms exposure" in text
    assert "Both channels were recorded" in text          # camera is still shared
    assert "with 150 ms exposure." not in text.split("Both channels")[1]


def test_differing_detectors_stay_on_their_channels(twocolour):
    import copy

    from micromethods.schema import Source as S
    from micromethods.schema import Value

    rec = copy.deepcopy(twocolour)
    rec.channels[1].detector = copy.deepcopy(rec.channels[1].detector)
    rec.channels[1].detector.model = Value("ORCA-Fusion", S.FILE, "test")
    text = render.methods_text(rec)
    assert "pco.edge 4.2 M CLHS" in text and "ORCA-Fusion" in text


def test_single_channel_keeps_detail_inline(blaze):
    """With one channel there is nothing to hoist, so the sentence stays whole."""
    text = render.methods_text(blaze)
    assert "Both channels" not in text
    assert "sCMOS camera" in text
    assert "20.1 ms exposure" in text


# Everything in this module builds or reads a real TIFF.
pytestmark = needs_imaging
