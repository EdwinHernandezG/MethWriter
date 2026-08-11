"""micromethods - microscopy metadata to publication-ready methods text.

Extracts acquisition metadata from Leica (.lif/.lof/.xlef), Zeiss (.czi) and
OME-TIFF datasets, checks it against the QUAREP-LiMi WG11 bare minimal
microscopy reporting requirements checklist, asks the user for whatever the
file does not contain, and writes a methods paragraph plus a machine-readable
sidecar.
"""

from .schema import Record, Source, Value  # noqa: F401
from .gaps import find_gaps, Report, Question  # noqa: F401
from .checklist import REQUIREMENTS, Requirement, Level, Scope  # noqa: F401

__version__ = "0.1.0"


def read(path, series: int = 0):
    """Read a dataset into a Record (lazy import to keep startup fast)."""
    from .readers import read as _read
    return _read(path, series=series)


def report(path, series: int = 0, prompter=None, extra_profiles=None):
    """One-call convenience API used by the napari plugin.

    Returns ``(record, gap_report, markdown)``.
    """
    from . import profiles as profile_store
    from . import render
    from .prompt import NullPrompter, run

    record = read(path, series=series)
    profile_store.apply_best(record, extra_profiles)
    gaps = find_gaps(record)
    run(record, gaps.blocking, prompter or NullPrompter())
    gaps = find_gaps(record)
    return record, gaps, render.report_markdown(record, gaps)
