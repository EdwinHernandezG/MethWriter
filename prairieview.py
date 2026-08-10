"""Bruker Ultima (PrairieView) companion metadata.

PrairieView writes the acquisition state to a sibling ``*.xml`` (plus ``.env``)
as a list of ``<PVStateValue key="..." value="..."/>`` entries.  Almost none of
this survives conversion to OME-TIFF, so it is harvested separately and merged
into the record with ``Source.COMPANION``.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from ..schema import Detector, LightSource, Record, Source, fv, raw
from .base import as_float, as_int, attr_of, findall


def find_companion(path: Path) -> Path | None:
    """Locate the PrairieView XML that belongs to an image file."""
    candidates: list[Path] = []
    stem = path.name.split(".")[0]
    for pattern in (f"{stem}.xml", f"{stem}*.xml", "*.xml"):
        candidates.extend(sorted(path.parent.glob(pattern)))
        if candidates:
            break
    for candidate in candidates[:10]:
        try:
            head = candidate.open("rb").read(4096).decode("utf-8", "ignore")
        except OSError:
            continue
        if "PVScan" in head or "PVStateValue" in head:
            return candidate
    return None


def state_values(root) -> dict[str, object]:
    """Flatten PVStateValue entries, including indexed values."""
    out: dict[str, object] = {}
    for sv in findall(root, "PVStateValue"):
        key = attr_of(sv, "key")
        if not key:
            continue
        value = attr_of(sv, "value")
        indexed = findall(sv, "IndexedValue") + findall(sv, "SubindexedValue")
        if indexed:
            for item in indexed:
                index = attr_of(item, "index") or attr_of(item, "subindex") or ""
                desc = attr_of(item, "description")
                label = f"{key}[{desc or index}]"
                out[label] = attr_of(item, "value")
        if value is not None:
            out[key] = value
    return out


def apply(path: Path, rec: Record) -> bool:
    """Merge PrairieView state into ``rec``. Returns True if anything applied."""
    companion = find_companion(path)
    if companion is None:
        return False
    try:
        root = ET.parse(str(companion)).getroot()
    except ET.ParseError:
        return False

    sv = state_values(root)
    rec.vendor_raw["prairieview"] = {k: str(v) for k, v in sv.items()}
    rec.notes.append(f"PrairieView metadata read from {companion.name}")
    src = Source.COMPANION
    a = rec.acquisition

    rec.stand.manufacturer = rec.stand.manufacturer or fv("Bruker", src, "PrairieView")
    version = attr_of(root, "version")
    rec.software.name = rec.software.name or fv("PrairieView", src, "PVScan@version")
    rec.software.developer = rec.software.developer or fv("Bruker", src, "PrairieView")
    rec.software.version = rec.software.version or fv(version, src, "PVScan@version")
    rec.acquisition.acquisition_date = rec.acquisition.acquisition_date or fv(
        attr_of(root, "date"), src, "PVScan@date")

    mode = str(sv.get("activeMode", "")).lower()
    if "resonant" in mode:
        a.scan_speed = a.scan_speed or fv("resonant galvo scanning", src, "activeMode")
    if rec.stand.modality is None:
        rec.stand.modality = fv("two-photon laser-scanning microscopy", src,
                                "PrairieView / Ultima")

    o = rec.objective
    o.designation = o.designation or fv(sv.get("objectiveLens"), src, "objectiveLens")
    o.magnification = o.magnification or fv(as_float(sv.get("objectiveLensMag")), src,
                                            "objectiveLensMag", "x")
    o.na = o.na or fv(as_float(sv.get("objectiveLensNA")), src, "objectiveLensNA")

    zoom = as_float(sv.get("opticalZoom"))
    a.zoom = a.zoom or fv(zoom, src, "opticalZoom")
    a.size_x = a.size_x or fv(as_int(sv.get("pixelsPerLine")), src, "pixelsPerLine")
    a.size_y = a.size_y or fv(as_int(sv.get("linesPerFrame")), src, "linesPerFrame")
    a.bit_depth = a.bit_depth or fv(as_int(sv.get("bitDepth")), src, "bitDepth", "bit")

    for key, target in (("micronsPerPixel[XAxis]", "pixel_size_x_um"),
                        ("micronsPerPixel[YAxis]", "pixel_size_y_um"),
                        ("micronsPerPixel[ZAxis]", "z_step_um")):
        val = as_float(sv.get(key))
        if val and getattr(a, target) is None:
            setattr(a, target, fv(round(val, 6), src, key, "µm"))

    dwell = as_float(sv.get("dwellTime"))
    a.pixel_dwell_us = a.pixel_dwell_us or fv(dwell, src, "dwellTime", "µs")
    frame_period = as_float(sv.get("framePeriod"))
    if frame_period and a.time_increment_s is None and (raw(a.size_t) or 1) > 1:
        a.time_increment_s = fv(round(frame_period, 4), src, "framePeriod", "s")
    a.line_averaging = a.line_averaging or fv(as_int(sv.get("rastersPerFrame")), src,
                                              "rastersPerFrame")

    # z-series step from the sequence, if present
    if a.z_step_um is None:
        zs = [as_float(attr_of(f, "absoluteZ") or "") for f in findall(root, "Frame")]
        zs = [z for z in zs if z is not None]
        if len(zs) > 1:
            steps = [round(abs(b - a_), 4) for a_, b in zip(zs, zs[1:]) if b != a_]
            if steps:
                a.z_step_um = fv(min(steps), Source.DERIVED,
                                 "difference between consecutive Frame@absoluteZ", "µm")

    # lasers and PMTs
    for key, val in sv.items():
        low = key.lower()
        if low.startswith("laserwavelength"):
            wl = as_float(val)
            if wl:
                rec.light_sources.append(LightSource(
                    kind=fv("tuneable Ti:sapphire / OPO laser (two-photon)", src, key),
                    wavelength_nm=fv(wl, src, key, "nm"),
                    name=fv(key, src, key)))
        elif low.startswith("laserpower"):
            power = as_float(val)
            if power is not None:
                rec.extras.setdefault("multiphoton", {})["power"] = fv(
                    f"{power} (PrairieView units; calibrate to mW at the objective)",
                    src, key)
        elif low.startswith("pmtgain"):
            det = Detector(kind=fv("PMT", src, key),
                           name=fv(key, src, key),
                           gain=fv(as_float(val), src, key),
                           manufacturer=fv("Bruker", src, "Ultima detection unit"))
            rec.detectors.append(det)

    for idx, det in enumerate(rec.detectors):
        if idx < len(rec.channels) and rec.channels[idx].detector.kind is None:
            rec.channels[idx].detector = det
    if rec.light_sources and rec.channels:
        for c in rec.channels:
            c.light_source = c.light_source if raw(c.light_source.kind) else rec.light_sources[0]

    rec.instrument_key = rec.instrument_key or "bruker_ultima_2p"
    return True
