"""Reader interface and shared XML helpers."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Iterable

from ..schema import Record


class ReaderError(RuntimeError):
    pass


class MissingDependency(ReaderError):
    def __init__(self, package: str, extra: str):
        super().__init__(
            f"'{package}' is required to read this format. "
            f"Install it with: pip install micromethods[{extra}]"
        )
        self.package = package


class Reader:
    """Base class. Subclasses turn one file format into a Record."""

    name = "base"
    extensions: tuple[str, ...] = ()

    @classmethod
    def can_read(cls, path: Path) -> bool:
        return path.suffix.lower() in cls.extensions or "".join(
            path.suffixes[-2:]
        ).lower() in cls.extensions

    def read(self, path: Path, series: int = 0) -> Record:  # pragma: no cover
        raise NotImplementedError


# --------------------------------------------------------------------------
# XML helpers shared by the CZI, LIF and PrairieView parsers
# --------------------------------------------------------------------------

def strip_ns(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def findall(elem, tag: str) -> list:
    """Namespace-agnostic recursive search by local tag name."""
    if elem is None:
        return []
    return [e for e in elem.iter() if strip_ns(e.tag) == tag]


def find(elem, tag: str):
    hits = findall(elem, tag)
    return hits[0] if hits else None


def text_of(elem, *tags: str) -> str | None:
    """First non-empty text among the given descendant tag names."""
    for tag in tags:
        for hit in findall(elem, tag):
            if hit.text and hit.text.strip():
                return hit.text.strip()
    return None


def attr_of(elem, *names: str) -> str | None:
    if elem is None:
        return None
    for name in names:
        for key, val in elem.attrib.items():
            if strip_ns(key).lower() == name.lower() and str(val).strip():
                return str(val).strip()
    return None


def as_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    m = re.search(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?", str(value))
    return float(m.group()) if m else None


def as_int(value: Any) -> int | None:
    f = as_float(value)
    return None if f is None else int(round(f))


def flatten_xml(elem, prefix: str = "", out: dict | None = None,
                limit: int = 4000) -> dict[str, str]:
    """Flatten an XML tree into dotted key -> value, for `inspect` and for
    profile matching on vendor strings."""
    out = {} if out is None else out
    if elem is None or len(out) >= limit:
        return out
    key = prefix or strip_ns(elem.tag)
    for name, val in elem.attrib.items():
        out[f"{key}@{strip_ns(name)}"] = str(val)
    if elem.text and elem.text.strip():
        out[key] = elem.text.strip()
    counts: dict[str, int] = {}
    for child in elem:
        ctag = strip_ns(child.tag)
        counts[ctag] = counts.get(ctag, 0) + 1
    seen: dict[str, int] = {}
    for child in elem:
        ctag = strip_ns(child.tag)
        seen[ctag] = seen.get(ctag, 0) + 1
        ckey = f"{key}/{ctag}" if counts[ctag] == 1 else f"{key}/{ctag}[{seen[ctag] - 1}]"
        flatten_xml(child, ckey, out, limit)
    return out


def unique(seq: Iterable) -> list:
    seen, out = set(), []
    for item in seq:
        k = str(item)
        if k not in seen:
            seen.add(k)
            out.append(item)
    return out
