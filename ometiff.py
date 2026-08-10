"""OME-TIFF reader.

Covers generic OME-TIFF plus the two writers used in the unit:
  * Miltenyi Biotec UltraMicroscope Blaze (Imspector/LaVision lineage)
  * Bruker Ultima 2P (PrairieView; enriched from the companion XML)

Only ``tifffile`` is strictly required.  If ``ome-types`` is installed it is
used to validate the XML, but parsing is done on the raw OME-XML so that
non-conformant vendor files still yield something useful.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path
from statistics import median

from ..schema import (Acquisition, Channel, Detector, LightSource, OpticalFilter,
                      Record, Source, fv, raw)
from ..units import airy_units_auto, to_seconds, to_um
from .base import (MissingDependency, Reader, as_float, as_int, attr_of, findall,
                   flatten_xml, strip_ns, unique)

_OME_DETECTOR_KIND = {
    "CCD": "CCD camera", "EMCCD": "EMCCD camera", "CMOS": "sCMOS camera",
    "CAMERA": "camera", "PMT": "PMT", "PHOTODIODE": "photodiode",
    "APD": "avalanche photodiode", "CORRELATIONSPECTROSCOPY": "correlation detector",
    "SPECTROSCOPY": "spectral detector", "LIFETIMEIMAGING": "lifetime detector",
    "ANALOG-VIDEO": "analogue video",
}

_LASER_TYPE = {
    "SolidState": "solid-state", "Gas": "gas", "MetalVapor": "metal-vapour",
    "Dye": "dye", "Semiconductor": "diode", "FreeElectron": "free-electron",
    "Excimer": "excimer", "Other": "",
}

_LIGHT_KIND = {
    "Laser": "laser", "Arc": "arc lamp", "Filament": "filament lamp",
    "LightEmittingDiode": "LED", "GenericExcitationSource": "light source",
}

# Fuzzy mapping of vendor key/value dumps onto reportable extras.
_VENDOR_HINTS = [
    ("extras.lightsheet.sheet_na", ("sheet", "na")),
    ("extras.lightsheet.sheet_na", ("lightsheet", "numerical")),
    ("extras.lightsheet.sheet_width", ("sheet", "width")),
    ("extras.lightsheet.sheet_thickness", ("sheet", "thickness")),
    ("extras.lightsheet.illumination_sides", ("sheet", "side")),
    ("extras.lightsheet.dynamic_focus", ("dynamic", "focus")),
    ("extras.lightsheet.illumination_sides", ("illumination", "direction")),
    ("extras.optics.zoom_body", ("zoom", "body")),
    ("extras.illumination.laser_power", ("laser", "power")),
]

# Hints that only make sense for a given modality.
_HINT_SCOPE = {"lightsheet": lambda rec: "sheet" in str(raw(rec.stand.modality, "")).lower()}


class OmeTiffReader(Reader):
    name = "ome-tiff"
    extensions = (".ome.tif", ".ome.tiff", ".ome.btf", ".tif", ".tiff")

    def read(self, path: Path, series: int = 0) -> Record:
        try:
            import tifffile
        except ImportError as exc:  # pragma: no cover
            raise MissingDependency("tifffile", "core") from exc

        rec = Record(file_path=str(path), file_format="OME-TIFF", reader=self.name)
        xml_text = _load_ome_xml(path, tifffile)
        page_desc: list[str] = []
        with tifffile.TiffFile(str(path)) as tif:
            rec.vendor_raw["is_ome"] = bool(tif.is_ome)
            for page in tif.pages[:2]:
                desc = getattr(page, "description", None)
                if desc and not desc.lstrip().startswith("<?xml"):
                    page_desc.append(desc)
            if not tif.is_ome:
                rec.file_format = "TIFF"
                rec.notes.append(
                    "File does not carry an OME-XML header; only TIFF tags and "
                    "companion files could be used."
                )

        if xml_text:
            root = ET.fromstring(xml_text.encode("utf-8", "ignore"))
            _parse_ome(root, rec, series)
            rec.vendor_raw["ome"] = flatten_xml(root, limit=1500)

        # Vendor extras from page descriptions and sidecar text files
        kv = {}
        for desc in page_desc:
            kv.update(_parse_kv_block(desc))
        for sidecar in _sidecars(path):
            kv.update(_parse_kv_block(sidecar.read_text(errors="ignore")))
        _detect_vendor(rec, kv, page_desc)
        if kv:
            rec.vendor_raw["vendor_kv"] = kv
            _apply_vendor_hints(kv, rec)
        _finalise(rec)
        return rec


# --------------------------------------------------------------------------


def _load_ome_xml(path: Path, tifffile) -> str | None:
    with tifffile.TiffFile(str(path)) as tif:
        if tif.ome_metadata:
            return tif.ome_metadata
    for candidate in path.parent.glob("*.companion.ome"):
        return candidate.read_text(errors="ignore")
    return None


def _sidecars(path: Path) -> list[Path]:
    """Vendor metadata files that ship next to the images."""
    out: list[Path] = []
    stem = path.name.split(".")[0]
    patterns = [f"{stem}*.txt", f"{stem}*.ini", f"{stem}*.env"]
    for pattern in patterns:
        for hit in sorted(path.parent.glob(pattern))[:4]:
            if hit.is_file() and hit.stat().st_size < 4_000_000:
                out.append(hit)
    return unique(out)


def _parse_kv_block(text: str) -> dict[str, str]:
    """Harvest ``key = value`` / ``key: value`` lines from a metadata blob."""
    out: dict[str, str] = {}
    if not text or text.lstrip().startswith("<"):
        return out
    section = ""
    for line in text.splitlines()[:4000]:
        line = line.strip()
        if not line or line.startswith(("#", ";")):
            continue
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1].strip()
            continue
        m = re.match(r"^([^=:]{1,80}?)\s*[=:]\s*(.+)$", line)
        if m:
            key = m.group(1).strip()
            out[f"{section}/{key}" if section else key] = m.group(2).strip()
    return out


def _apply_vendor_hints(kv: dict[str, str], rec: Record) -> None:
    for target, needles in _VENDOR_HINTS:
        group = target.split(".")[1]
        gate = _HINT_SCOPE.get(group)
        if gate is not None and not gate(rec):
            continue
        for key, val in kv.items():
            low = key.lower()
            if all(n in low for n in needles):
                node = rec.extras
                parts = target.split(".")[1:]
                for part in parts[:-1]:
                    node = node.setdefault(part, {})
                node.setdefault(parts[-1], fv(val, Source.FILE, f"vendor key '{key}'"))
                break


def _parse_ome(root, rec: Record, series: int) -> None:
    images = findall(root, "Image")
    if not images:
        return
    img = images[min(series, len(images) - 1)]
    rec.image_name = fv(attr_of(img, "Name"), Source.FILE, "Image@Name")

    creator = attr_of(root, "Creator")
    if creator:
        rec.vendor_raw["creator"] = creator
        name, version = _split_software(creator)
        rec.software.name = fv(name, Source.FILE, "OME@Creator")
        rec.software.version = fv(version, Source.FILE, "OME@Creator")

    acq_date = None
    for elem in findall(img, "AcquisitionDate"):
        acq_date = (elem.text or "").strip()
    rec.acquisition.acquisition_date = fv(acq_date, Source.FILE, "AcquisitionDate")

    # ---- instrument -----------------------------------------------------
    instrument = _instrument_for(root, img)
    if instrument is not None:
        scope = next(iter(findall(instrument, "Microscope")), None)
        if scope is not None:
            rec.stand.manufacturer = fv(attr_of(scope, "Manufacturer"), Source.FILE,
                                        "Instrument/Microscope@Manufacturer")
            rec.stand.model = fv(attr_of(scope, "Model"), Source.FILE,
                                 "Instrument/Microscope@Model")
            rec.stand.stand_type = fv(_stand_type(attr_of(scope, "Type")), Source.FILE,
                                      "Instrument/Microscope@Type")
        for src in findall(instrument, "LightSource"):
            rec.light_sources.append(_light_source(src))
        for det in findall(instrument, "Detector"):
            rec.detectors.append(_detector(det))
        obj = next(iter(findall(instrument, "Objective")), None)
        if obj is not None:
            o = rec.objective
            o.magnification = fv(as_float(attr_of(obj, "NominalMagnification")),
                                 Source.FILE, "Objective@NominalMagnification", "x")
            o.na = fv(as_float(attr_of(obj, "LensNA")), Source.FILE, "Objective@LensNA")
            o.immersion = fv(_immersion(attr_of(obj, "Immersion")), Source.FILE,
                             "Objective@Immersion")
            o.correction = fv(attr_of(obj, "Correction"), Source.FILE, "Objective@Correction")
            o.manufacturer = fv(attr_of(obj, "Manufacturer"), Source.FILE,
                                "Objective@Manufacturer")
            o.model = fv(attr_of(obj, "Model"), Source.FILE, "Objective@Model")
            wd = as_float(attr_of(obj, "WorkingDistance"))
            o.working_distance_mm = fv(
                to_um(wd, attr_of(obj, "WorkingDistanceUnit") or "µm") / 1000
                if wd is not None else None,
                Source.FILE, "Objective@WorkingDistance", "mm")

    settings = next(iter(findall(img, "ObjectiveSettings")), None)
    if settings is not None:
        rec.objective.refractive_index = fv(
            as_float(attr_of(settings, "RefractiveIndex")), Source.FILE,
            "ObjectiveSettings@RefractiveIndex")
        rec.objective.immersion_medium = fv(attr_of(settings, "Medium"), Source.FILE,
                                            "ObjectiveSettings@Medium")

    # ---- pixels ---------------------------------------------------------
    pixels = next(iter(findall(img, "Pixels")), None)
    if pixels is None:
        return
    a: Acquisition = rec.acquisition
    a.size_x = fv(as_int(attr_of(pixels, "SizeX")), Source.FILE, "Pixels@SizeX")
    a.size_y = fv(as_int(attr_of(pixels, "SizeY")), Source.FILE, "Pixels@SizeY")
    a.size_z = fv(as_int(attr_of(pixels, "SizeZ")), Source.FILE, "Pixels@SizeZ")
    a.size_c = fv(as_int(attr_of(pixels, "SizeC")), Source.FILE, "Pixels@SizeC")
    a.size_t = fv(as_int(attr_of(pixels, "SizeT")), Source.FILE, "Pixels@SizeT")
    a.dimension_order = fv(attr_of(pixels, "DimensionOrder"), Source.FILE,
                           "Pixels@DimensionOrder")
    a.bit_depth = fv(_bit_depth(attr_of(pixels, "Type")), Source.FILE, "Pixels@Type", "bit")

    for axis, target in (("X", "pixel_size_x_um"), ("Y", "pixel_size_y_um"),
                         ("Z", "z_step_um")):
        val = as_float(attr_of(pixels, f"PhysicalSize{axis}"))
        unit = attr_of(pixels, f"PhysicalSize{axis}Unit") or "µm"
        um = to_um(val, unit)
        setattr(a, target, fv(um, Source.FILE, f"Pixels@PhysicalSize{axis}", "µm"))

    inc = as_float(attr_of(pixels, "TimeIncrement"))
    a.time_increment_s = fv(to_seconds(inc, attr_of(pixels, "TimeIncrementUnit") or "s"),
                            Source.FILE, "Pixels@TimeIncrement", "s")

    planes = findall(pixels, "Plane")
    _from_planes(planes, rec)

    for idx, chan in enumerate(findall(pixels, "Channel")):
        _channel(chan, rec, idx)

    # tiles: count distinct XY stage positions
    positions = {(attr_of(p, "PositionX"), attr_of(p, "PositionY")) for p in planes}
    positions.discard((None, None))
    if len(positions) > 1:
        a.tiles = fv(len(positions), Source.DERIVED,
                     "distinct Plane@PositionX/Y values")


def _instrument_for(root, img):
    instruments = findall(root, "Instrument")
    if not instruments:
        return None
    ref = next(iter(findall(img, "InstrumentRef")), None)
    ref_id = attr_of(ref, "ID") if ref is not None else None
    for inst in instruments:
        if ref_id and attr_of(inst, "ID") == ref_id:
            return inst
    return instruments[0]


def _light_source(src) -> LightSource:
    ls = LightSource()
    kind, wavelength = None, None
    for child in src:
        tag = strip_ns(child.tag)
        if tag in _LIGHT_KIND:
            kind = _LIGHT_KIND[tag]
            if tag == "Laser":
                wavelength = as_float(attr_of(child, "Wavelength"))
                medium = attr_of(child, "LaserMedium")
                laser_type = _LASER_TYPE.get(attr_of(child, "Type") or "",
                                            attr_of(child, "Type"))
                bits = [b for b in (laser_type, medium) if b]
                if bits:
                    kind = f"{' '.join(bits)} laser"
    ls.kind = fv(kind, Source.FILE, "Instrument/LightSource")
    ls.wavelength_nm = fv(wavelength, Source.FILE, "Laser@Wavelength", "nm")
    ls.manufacturer = fv(attr_of(src, "Manufacturer"), Source.FILE, "LightSource@Manufacturer")
    ls.model = fv(attr_of(src, "Model"), Source.FILE, "LightSource@Model")
    ls.name = fv(attr_of(src, "ID"), Source.FILE, "LightSource@ID")
    return ls


def _detector(det) -> Detector:
    d = Detector()
    kind = (attr_of(det, "Type") or "").upper()
    d.kind = fv(_OME_DETECTOR_KIND.get(kind, kind.title() or None), Source.FILE,
                "Detector@Type")
    d.manufacturer = fv(attr_of(det, "Manufacturer"), Source.FILE, "Detector@Manufacturer")
    d.model = fv(attr_of(det, "Model"), Source.FILE, "Detector@Model")
    d.name = fv(attr_of(det, "ID"), Source.FILE, "Detector@ID")
    d.gain = fv(as_float(attr_of(det, "Gain")), Source.FILE, "Detector@Gain")
    return d


def _channel(chan, rec: Record, idx: int) -> None:
    c: Channel = rec.channel(idx)
    c.name = fv(attr_of(chan, "Name"), Source.FILE, "Channel@Name")
    c.fluorophore = fv(attr_of(chan, "Fluor"), Source.FILE, "Channel@Fluor")
    c.illumination_type = fv(attr_of(chan, "IlluminationType"), Source.FILE,
                             "Channel@IlluminationType")
    c.acquisition_mode = fv(attr_of(chan, "AcquisitionMode"), Source.FILE,
                            "Channel@AcquisitionMode")
    ex = as_float(attr_of(chan, "ExcitationWavelength"))
    em = as_float(attr_of(chan, "EmissionWavelength"))
    c.excitation_nm = fv(ex, Source.FILE, "Channel@ExcitationWavelength", "nm")
    c.emission_nm = fv(em, Source.FILE, "Channel@EmissionWavelength", "nm")
    pin = as_float(attr_of(chan, "PinholeSize"))
    c.pinhole_um = fv(to_um(pin, attr_of(chan, "PinholeSizeUnit") or "µm"), Source.FILE,
                      "Channel@PinholeSize", "µm")

    settings = next(iter(findall(chan, "LightSourceSettings")), None)
    if settings is not None:
        wl = as_float(attr_of(settings, "Wavelength"))
        if wl and not c.excitation_nm:
            c.excitation_nm = fv(wl, Source.FILE, "LightSourceSettings@Wavelength", "nm")
        att = as_float(attr_of(settings, "Attenuation"))
        if att is not None:
            c.laser_power = fv(round((1 - att) * 100, 2), Source.DERIVED,
                               "100 x (1 - LightSourceSettings@Attenuation)", "%")
        ref = attr_of(settings, "ID")
        for ls in rec.light_sources:
            if ref and raw(ls.name) == ref:
                c.light_source = ls

    dset = next(iter(findall(chan, "DetectorSettings")), None)
    if dset is not None:
        ref = attr_of(dset, "ID")
        for det in rec.detectors:
            if ref and raw(det.name) == ref:
                c.detector = det
        c.gain = fv(as_float(attr_of(dset, "Gain")), Source.FILE, "DetectorSettings@Gain")
        binning = attr_of(dset, "Binning")
        if binning and binning.lower() != "other":
            c.detector.binning = fv(binning, Source.FILE, "DetectorSettings@Binning")
    if c.detector.kind is None and rec.detectors:
        c.detector = rec.detectors[min(idx, len(rec.detectors) - 1)]

    fref = next(iter(findall(chan, "FilterSetRef")), None)
    if fref is not None:
        c.filter_set = fv(attr_of(fref, "ID"), Source.FILE, "FilterSetRef@ID")


def _from_planes(planes, rec: Record) -> None:
    if not planes:
        return
    per_channel: dict[int, list[float]] = {}
    deltas: list[float] = []
    for plane in planes[:20000]:
        ch = as_int(attr_of(plane, "TheC")) or 0
        exp = as_float(attr_of(plane, "ExposureTime"))
        if exp is not None:
            unit = attr_of(plane, "ExposureTimeUnit") or "s"
            ms = to_seconds(exp, unit)
            if ms is not None:
                per_channel.setdefault(ch, []).append(ms * 1000)
        dt = as_float(attr_of(plane, "DeltaT"))
        if dt is not None and as_int(attr_of(plane, "TheZ")) in (0, None) \
                and as_int(attr_of(plane, "TheC")) in (0, None):
            deltas.append(to_seconds(dt, attr_of(plane, "DeltaTUnit") or "s"))
    for ch, values in per_channel.items():
        rec.channel(ch).exposure_time_ms = fv(round(median(values), 4), Source.FILE,
                                              "Plane@ExposureTime", "ms")
    if len(deltas) > 1 and rec.acquisition.time_increment_s is None:
        gaps = [b - a for a, b in zip(deltas, deltas[1:]) if b > a]
        if gaps:
            rec.acquisition.time_increment_s = fv(
                round(median(gaps), 4), Source.DERIVED,
                "median difference between Plane@DeltaT values", "s")


def _detect_vendor(rec: Record, kv: dict[str, str], descriptions: list[str]) -> None:
    """Identify the acquisition system so the right profile can be applied."""
    blob = " ".join(filter(None, [
        str(rec.vendor_raw.get("creator", "")),
        raw(rec.stand.manufacturer, ""), raw(rec.stand.model, ""),
        raw(rec.software.name, ""), rec.file_path,
        " ".join(list(kv.keys())[:200]), " ".join(list(kv.values())[:200]),
        " ".join(descriptions)[:20000],
    ])).lower()
    rec.vendor_raw["fingerprint"] = blob[:4000]

    if any(k in blob for k in ("blaze", "ultramicroscope", "imspector", "lavision",
                               "miltenyi")):
        rec.instrument_key = "miltenyi_blaze"
        rec.stand.modality = rec.stand.modality or fv(
            "light-sheet fluorescence microscopy", Source.DERIVED,
            "vendor fingerprint (Miltenyi/Imspector)")
    elif any(k in blob for k in ("prairie", "bruker", "ultima")):
        rec.instrument_key = "bruker_ultima_2p"
        rec.stand.modality = rec.stand.modality or fv(
            "two-photon laser-scanning microscopy", Source.DERIVED,
            "vendor fingerprint (Bruker/PrairieView)")


def _finalise(rec: Record) -> None:
    """Derived quantities that the checklist asks for explicitly."""
    a = rec.acquisition
    nz, step = raw(a.size_z), raw(a.z_step_um)
    if nz and step and nz > 1 and a.z_range_um is None:
        a.z_range_um = fv(round((nz - 1) * step, 4), Source.DERIVED,
                          "(SizeZ - 1) x z-step", "µm")
    nt, inc = raw(a.size_t), raw(a.time_increment_s)
    if nt and inc and nt > 1 and a.total_time_s is None:
        a.total_time_s = fv(round((nt - 1) * inc, 3), Source.DERIVED,
                            "(SizeT - 1) x time increment", "s")
    na = raw(rec.objective.na)
    mag = raw(rec.objective.magnification)
    for c in rec.channels:
        if c.pinhole_au is None and raw(c.pinhole_um) and na:
            em = raw(c.emission_nm) or raw(c.excitation_nm)
            au, note = airy_units_auto(raw(c.pinhole_um), em, na, mag)
            if au:
                c.pinhole_au = fv(au, Source.DERIVED,
                                  f"pinhole / (1.22 x lambda_em / NA), {note}", "AU")
            else:
                rec.notes.append(f"Channel {c.index}: pinhole in AU not derived - {note}")

    if rec.stand.modality is None:
        modes = {str(raw(c.acquisition_mode, "")).lower().replace(" ", "")
                 for c in rec.channels}
        table = [("airyscan", "confocal (Airyscan)"),
                 ("spinningdisk", "spinning-disk confocal"),
                 ("laserscanningconfocal", "point-scanning confocal"),
                 ("sweptfieldconfocal", "swept-field confocal"),
                 ("multiphoton", "two-photon laser-scanning microscopy"),
                 ("lightsheet", "light-sheet fluorescence microscopy"),
                 ("spim", "light-sheet fluorescence microscopy"),
                 ("totalinternalreflection", "TIRF"),
                 ("structuredillumination", "structured illumination microscopy"),
                 ("widefield", "wide-field fluorescence")]
        for needle, label in table:
            if any(needle in m for m in modes):
                rec.stand.modality = fv(label, Source.FILE, "Channel@AcquisitionMode")
                break


def _split_software(creator: str) -> tuple[str, str | None]:
    m = re.match(r"^(.*?)[\s,;/]+v?(\d[\d.\-a-zA-Z]*)\s*$", creator.strip())
    if m:
        return m.group(1).strip(" ,;/"), m.group(2)
    return creator.strip(), None


def _stand_type(value: str | None) -> str | None:
    if not value:
        return None
    low = value.lower()
    if "invert" in low:
        return "inverted"
    if "upright" in low:
        return "upright"
    return value


def _immersion(value: str | None) -> str | None:
    if not value:
        return None
    mapping = {"oil": "oil", "water": "water", "waterdipping": "water-dipping",
               "air": "air", "glycerol": "glycerol", "multi": "multi-immersion",
               "other": None, "unknown": None}
    return mapping.get(value.lower().replace(" ", ""), value)


def _bit_depth(pixel_type: str | None) -> int | None:
    if not pixel_type:
        return None
    m = re.search(r"(\d+)", pixel_type)
    return int(m.group(1)) if m else None
