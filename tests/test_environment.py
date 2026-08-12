"""Checks on the installation itself.

These run everywhere, with no imaging dependencies, and are the first thing to
look at when the suite behaves oddly. They exist because a test run that skips
most of itself still reports success, which once hid a broken install.
"""

from __future__ import annotations

import importlib.metadata as md

import pytest

from tests.conftest import REQUIRED, _missing_required


def test_package_is_importable():
    import micromethods

    assert micromethods.__version__


def test_declared_dependencies_match_what_the_suite_requires():
    """If pyproject stops declaring something the tests need, say so here
    rather than as a confusing skip later."""
    requires = md.requires("micromethods") or []
    declared = {r.split()[0].split(">")[0].split("=")[0].split("[")[0].lower()
                for r in requires}
    for name in REQUIRED:
        assert name.replace("_", "-").lower() in declared, (
            f"{name} is required by the tests but not declared in pyproject.toml")


@pytest.mark.skipif(bool(_missing_required()),
                    reason="dependencies missing; the guard is what is under test")
def test_required_dependencies_are_importable():
    import importlib

    for name in REQUIRED:
        importlib.import_module(name)


def test_napari_entry_point_is_registered():
    """The plugin is discovered through this entry point; without it napari
    shows nothing, however correct the code is."""
    entries = [e for e in md.entry_points(group="napari.manifest")
               if e.name == "micromethods"]
    assert entries, "napari.manifest entry point is missing"
    assert entries[0].value == "micromethods._napari:napari.yaml"


def test_napari_manifest_resolves():
    npe2 = pytest.importorskip("npe2")

    manifest = npe2.PluginManifest.from_distribution("micromethods")
    widgets = [w.display_name for w in manifest.contributions.widgets]
    assert "Methods reporter" in widgets


def test_shipped_instrument_profiles_are_loadable():
    from micromethods import profiles

    found = {p.key for p in profiles.discover()}
    assert {"miltenyi_blaze", "bruker_ultima_2p"} <= found


def test_checklist_paths_all_resolve():
    """Every requirement addresses a real field on the Record; a typo here
    would silently make a checklist item unfillable."""
    from micromethods.checklist import REQUIREMENTS
    from micromethods.schema import Record, path_get

    record = Record()
    record.channel(0)
    for requirement in REQUIREMENTS:
        for path in requirement.paths(record):
            if path.startswith("extras."):
                continue  # created on demand
            path_get(record, path)  # must not raise
