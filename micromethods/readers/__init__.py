"""Format dispatch."""

from __future__ import annotations

from pathlib import Path

from ..schema import Record
from .base import MissingDependency, Reader, ReaderError
from .czi import CziReader
from .lif import LifReader
from .ometiff import OmeTiffReader

READERS: list[type[Reader]] = [CziReader, LifReader, OmeTiffReader]

SUPPORTED = sorted({ext for r in READERS for ext in r.extensions})


def get_reader(path: Path) -> Reader:
    for cls in READERS:
        if cls.can_read(path):
            return cls()
    raise ReaderError(
        f"No reader for '{path.name}'. Supported extensions: {', '.join(SUPPORTED)}. "
        "Convert the file to OME-TIFF (e.g. with bfconvert) to use the generic reader."
    )


def read(path: str | Path, series: int = 0) -> Record:
    """Read a dataset and enrich it with any companion vendor metadata."""
    path = Path(path).expanduser()
    if not path.exists():
        raise FileNotFoundError(path)
    record = get_reader(path).read(path, series=series)

    from . import prairieview
    if record.instrument_key == "bruker_ultima_2p" or not record.software.name:
        try:
            prairieview.apply(path, record)
        except Exception as exc:  # companion parsing must never be fatal
            record.notes.append(f"PrairieView companion parsing failed: {exc}")
    return record


__all__ = ["READERS", "SUPPORTED", "get_reader", "read", "Reader", "ReaderError",
           "MissingDependency", "Record"]
