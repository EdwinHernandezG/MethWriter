"""Generic OME-TIFF handling, plus the sidecar path used by older writers."""

from __future__ import annotations

import pytest

from tests.conftest import needs_imaging

from micromethods import readers, render
from micromethods.gaps import find_gaps
from micromethods.schema import Record, Source, raw


@pytest.fixture(scope="module")
def confocal(confocal_file) -> Record:
    return readers.read(confocal_file)


def test_instrument_block_is_read(confocal):
    assert raw(confocal.stand.model) == "Axio Observer 7"
    assert raw(confocal.stand.stand_type) == "inverted"
    assert raw(confocal.objective.magnification) == 63.0
    assert raw(confocal.objective.na) == 1.4
    assert raw(confocal.objective.immersion) == "oil"


def test_modality_inferred_from_acquisition_mode(confocal):
    assert raw(confocal.stand.modality) == "point-scanning confocal"


def test_pinhole_conversion_picks_the_plausible_convention(confocal):
    # 44.2 µm at 63x/1.4 is ~1.6 AU in the image plane and ~100 AU if read as
    # object space, so only one interpretation is physically possible.
    au = raw(confocal.channels[0].pinhole_au)
    assert 0.5 < au < 5
    assert confocal.channels[0].pinhole_au.source is Source.DERIVED


def test_derived_values_are_marked_as_derived(confocal):
    z_range = confocal.acquisition.z_range_um
    assert raw(z_range) == pytest.approx(3.08)
    assert z_range.source is Source.DERIVED


def test_attenuation_becomes_laser_power(confocal):
    assert raw(confocal.channels[0].laser_power) == pytest.approx(2.0)


def test_gaps_are_reported_not_invented(confocal):
    report = find_gaps(confocal)
    missing = {q.path for q in report.blocking}
    assert "specimen.labels" in missing
    assert "channels[0].detection_range_nm" in missing
    text = render.methods_text(confocal)
    assert "[MISSING:" in text


def test_sidecar_metadata_is_picked_up(legacy_blaze_file):
    rec = readers.read(legacy_blaze_file)
    assert rec.instrument_key == "miltenyi_blaze"
    sheet = rec.extras.get("lightsheet", {})
    assert "sheet_na" in sheet


def test_sidecar_of_a_different_dataset_is_ignored(confocal_file, tmp_path):
    """A stray metadata file belonging to another acquisition must not leak in."""
    import shutil

    folder = tmp_path / "mixed"
    folder.mkdir()
    target = folder / confocal_file.name
    shutil.copy(confocal_file, target)
    (folder / "someone_elses_MetaData.txt").write_text(
        "[Image]\nLight sheet NA = 0.156\nSheet width = 60 %\n")

    rec = readers.read(target)
    assert "lightsheet" not in rec.extras


def test_unsupported_extension_fails_clearly(tmp_path):
    path = tmp_path / "scan.nd2"
    path.write_bytes(b"not really an nd2")
    with pytest.raises(readers.ReaderError) as excinfo:
        readers.read(path)
    assert "No reader" in str(excinfo.value)


def test_report_and_json_are_produced(confocal, confocal_file):
    report = find_gaps(confocal)
    markdown = render.report_markdown(confocal, report)
    assert "## Methods text" in markdown
    assert "LiMi-model alignment" in markdown

    import json
    payload = json.loads(render.metadata_json(confocal, report))
    assert payload["format"] == "OME-TIFF"
    na = payload["record"]["objective"]["na"]
    assert na["value"] == 1.4 and na["source"] == "file"


# Everything in this module builds or reads a real TIFF.
pytestmark = needs_imaging
