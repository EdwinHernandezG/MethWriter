"""Zeiss CZI reader.

The CZI XML block is read through whichever of pylibCZIrw / aicspylibczi /
czifile is installed, then parsed with ElementTree so that the extraction
rules live in one place.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from ..schema import Detector, LightSource, Record, Source, fv, raw
from ..units import airy_units_auto
from .base import (MissingDependency, Reader, as_float, as_int, attr_of, find,
                   findall, flatten_xml, text_of)

_DETECTOR_KIND = {
    "camera": "camera", "cmos": "sCMOS camera", "ccd": "CCD camera",
    "pmt": "PMT", "gaasp": "GaAsP PMT", "gaasppmt": "GaAsP PMT",
    "airyscan": "Airyscan detector", "spectral": "spectral detector",
    "multichannelspectral": "spectral detector array",
}


class CziReader(Reader):
    name = "czi"
    extensions = (".czi",)

    def read(self, path: Path, series: int = 0) -> Record:
        xml_text = _read_czi_xml(path)
        root = ET.fromstring(xml_text.encode("utf-8", "ignore"))
        rec = Record(file_path=str(path), file_format="CZI (Zeiss)", reader=self.name)
        rec.vendor_raw["czi"] = flatten_xml(root, limit=2000)
        _parse(root, rec)
        rec.instrument_key = _instrument_key(rec)
        return rec


def _read_czi_xml(path: Path) -> str:
    errors = []
    try:
        from pylibCZIrw import czi as pyczi  # type: ignore
        with pyczi.open_czi(str(path)) as doc:
            return doc.raw_metadata
    except ImportError as exc:
        errors.append(f"pylibCZIrw: {exc}")
    try:
        from aicspylibczi import CziFile  # type: ignore
        from lxml import etree  # type: ignore
        return etree.tostring(CziFile(str(path)).meta).decode()
    except ImportError as exc:
        errors.append(f"aicspylibczi: {exc}")
    try:
        import czifile  # type: ignore
        with czifile.CziFile(str(path)) as f:
            return f.metadata()
    except ImportError as exc:
        errors.append(f"czifile: {exc}")
    raise MissingDependency("pylibCZIrw", "zeiss")


def _parse(root, rec: Record) -> None:
    # An Element with no children is falsey, so test against None explicitly.
    md = find(root, "Metadata")
    if md is None:
        md = root
    info = find(md, "Information")
    image = find(info, "Image") if info is not None else None
    instrument = find(info, "Instrument") if info is not None else None

    # ---- application / software ----
    app = find(info, "Application") if info is not None else None
    if app is not None:
        rec.software.name = fv(text_of(app, "Name"), Source.FILE, "Information/Application/Name")
        rec.software.version = fv(text_of(app, "Version"), Source.FILE,
                                  "Information/Application/Version")
    rec.software.developer = fv("Carl Zeiss Microscopy", Source.DERIVED, "CZI file format")

    # ---- stand ----
    scope = find(instrument, "Microscope") if instrument is not None else None
    if scope is not None:
        rec.stand.model = fv(attr_of(scope, "Name") or text_of(scope, "System"),
                             Source.FILE, "Instrument/Microscopes/Microscope@Name")
        rec.stand.stand_type = fv(_stand_type(text_of(scope, "Type")), Source.FILE,
                                  "Microscope/Type")
    rec.stand.manufacturer = fv("Carl Zeiss Microscopy", Source.DERIVED, "CZI file format")

    # ---- objective ----
    obj = find(instrument, "Objective") if instrument is not None else None
    if obj is not None:
        o = rec.objective
        o.designation = fv(attr_of(obj, "Name") or text_of(obj, "Manufacturer/Model"),
                           Source.FILE, "Objectives/Objective@Name")
        o.magnification = fv(as_float(text_of(obj, "NominalMagnification", "Magnification")),
                             Source.FILE, "Objective/NominalMagnification", "x")
        o.na = fv(as_float(text_of(obj, "LensNA")), Source.FILE, "Objective/LensNA")
        o.immersion = fv(_immersion(text_of(obj, "Immersion")), Source.FILE,
                         "Objective/Immersion")
        o.correction = fv(text_of(obj, "Correction"), Source.FILE, "Objective/Correction")
        o.working_distance_mm = fv(as_float(text_of(obj, "WorkingDistance")), Source.FILE,
                                   "Objective/WorkingDistance", "mm")
        man = find(obj, "Manufacturer")
        if man is not None:
            o.manufacturer = fv(text_of(man, "Manufacturer") or "Carl Zeiss Microscopy",
                                Source.FILE, "Objective/Manufacturer/Manufacturer")
            o.model = fv(text_of(man, "Model"), Source.FILE, "Objective/Manufacturer/Model")

    tubelens = find(instrument, "TubeLens") if instrument is not None else None
    if tubelens is not None:
        rec.stand.magnification_changer = fv(
            attr_of(tubelens, "Name") or text_of(tubelens, "Magnification"),
            Source.FILE, "Instrument/TubeLenses/TubeLens")

    # ---- light sources ----
    if instrument is not None:
        for src in findall(instrument, "LightSource"):
            ls = LightSource()
            laser = find(src, "Laser")
            led = find(src, "LightEmittingDiode")
            kind = "laser" if laser is not None else ("LED" if led is not None else
                                                      text_of(src, "LightSourceType"))
            ls.kind = fv(kind, Source.FILE, "LightSources/LightSource")
            ls.wavelength_nm = fv(
                _nm(as_float(text_of(src, "Wavelength", "NominalWavelength"))),
                Source.FILE, "LightSource/Wavelength", "nm")
            ls.name = fv(attr_of(src, "Id") or attr_of(src, "Name"), Source.FILE,
                         "LightSource@Id")
            ls.manufacturer = fv(text_of(src, "Manufacturer"), Source.FILE,
                                 "LightSource/Manufacturer")
            if raw(ls.kind) or raw(ls.wavelength_nm):
                rec.light_sources.append(ls)

        for det in findall(instrument, "Detector"):
            d = Detector()
            raw_kind = (text_of(det, "Type") or attr_of(det, "Name") or "").lower()
            for needle, label in _DETECTOR_KIND.items():
                if needle in raw_kind.replace(" ", "").replace("-", ""):
                    d.kind = fv(label, Source.FILE, "Detectors/Detector/Type")
                    break
            else:
                d.kind = fv(text_of(det, "Type"), Source.FILE, "Detectors/Detector/Type")
            d.manufacturer = fv(text_of(det, "Manufacturer"), Source.FILE,
                                "Detector/Manufacturer/Manufacturer")
            d.model = fv(text_of(det, "Model") or attr_of(det, "Name"), Source.FILE,
                         "Detector/Manufacturer/Model")
            d.name = fv(attr_of(det, "Id") or attr_of(det, "Name"), Source.FILE, "Detector@Id")
            rec.detectors.append(d)

    # ---- image geometry ----
    a = rec.acquisition
    if image is not None:
        a.size_x = fv(as_int(text_of(image, "SizeX")), Source.FILE, "Image/SizeX")
        a.size_y = fv(as_int(text_of(image, "SizeY")), Source.FILE, "Image/SizeY")
        a.size_z = fv(as_int(text_of(image, "SizeZ")), Source.FILE, "Image/SizeZ")
        a.size_c = fv(as_int(text_of(image, "SizeC")), Source.FILE, "Image/SizeC")
        a.size_t = fv(as_int(text_of(image, "SizeT")), Source.FILE, "Image/SizeT")
        a.bit_depth = fv(_bits(text_of(image, "ComponentBitCount", "PixelType")),
                         Source.FILE, "Image/ComponentBitCount", "bit")
        a.acquisition_date = fv(text_of(image, "AcquisitionDateAndTime"), Source.FILE,
                                "Image/AcquisitionDateAndTime")
        tiles = as_int(text_of(image, "SizeM"))
        if tiles and tiles > 1:
            a.tiles = fv(tiles, Source.FILE, "Image/SizeM")

    scaling = find(md, "Scaling")
    for item in findall(scaling, "Distance"):
        axis = attr_of(item, "Id")
        metres = as_float(text_of(item, "Value"))
        if metres is None or axis is None:
            continue
        um = metres * 1e6
        if axis.upper() == "X":
            a.pixel_size_x_um = fv(round(um, 6), Source.FILE, "Scaling/Distance[X]", "µm")
        elif axis.upper() == "Y":
            a.pixel_size_y_um = fv(round(um, 6), Source.FILE, "Scaling/Distance[Y]", "µm")
        elif axis.upper() == "Z":
            a.z_step_um = fv(round(um, 6), Source.FILE, "Scaling/Distance[Z]", "µm")

    # ---- time series ----
    for interval in findall(image, "Interval") if image is not None else []:
        inc = as_float(text_of(interval, "Increment"))
        if inc:
            a.time_increment_s = fv(inc, Source.FILE, "Dimensions/T/Positions/Interval/"
                                                      "Increment", "s")
            break

    # ---- scanner ----
    scan = find(md, "LaserScanInfo")
    if scan is not None:
        dwell = as_float(text_of(scan, "PixelTime"))
        if dwell:
            a.pixel_dwell_us = fv(round(dwell * 1e6, 4), Source.FILE,
                                  "LaserScanInfo/PixelTime", "µs")
        a.line_averaging = fv(as_int(text_of(scan, "Averaging")), Source.FILE,
                              "LaserScanInfo/Averaging")
        a.zoom = fv(as_float(text_of(scan, "ZoomX")), Source.FILE, "LaserScanInfo/ZoomX")
        a.scan_speed = fv(as_float(text_of(scan, "ScanSpeed", "FrameTime")), Source.FILE,
                          "LaserScanInfo/ScanSpeed")

    mode = text_of(md, "MultiChannelMode") or text_of(md, "SequentialMode")
    if mode:
        a.channel_mode = fv("sequential" if "seq" in mode.lower() else "simultaneous",
                            Source.FILE, "ConfocalScannerSettings/MultiChannelMode")

    overlap = text_of(md, "Overlap")
    if overlap is not None:
        val = as_float(overlap)
        if val is not None:
            a.tile_overlap_percent = fv(round(val * 100 if val <= 1 else val, 2),
                                        Source.FILE, "Experiment//Overlap", "%")

    # ---- channels ----
    channels = findall(image, "Channel") if image is not None else []
    for idx, chan in enumerate(channels):
        c = rec.channel(idx)
        c.name = fv(attr_of(chan, "Name") or attr_of(chan, "Id"), Source.FILE, "Channel@Name")
        c.fluorophore = fv(text_of(chan, "Fluor", "DyeName"), Source.FILE, "Channel/Fluor")
        c.excitation_nm = fv(_nm(as_float(text_of(chan, "ExcitationWavelength"))),
                             Source.FILE, "Channel/ExcitationWavelength", "nm")
        c.emission_nm = fv(_nm(as_float(text_of(chan, "EmissionWavelength"))),
                           Source.FILE, "Channel/EmissionWavelength", "nm")
        c.illumination_type = fv(text_of(chan, "IlluminationType"), Source.FILE,
                                 "Channel/IlluminationType")
        c.acquisition_mode = fv(text_of(chan, "AcquisitionMode"), Source.FILE,
                                "Channel/AcquisitionMode")
        exp = as_float(text_of(chan, "ExposureTime"))
        if exp:  # nanoseconds in CZI
            c.exposure_time_ms = fv(round(exp / 1e6, 4), Source.FILE,
                                    "Channel/ExposureTime", "ms")
        au = as_float(text_of(chan, "PinholeSizeAiry"))
        if au:
            c.pinhole_au = fv(round(au, 3), Source.FILE, "Channel/PinholeSizeAiry", "AU")
        pin = as_float(text_of(chan, "PinholeSize"))
        if pin:
            c.pinhole_um = fv(round(pin * 1e6, 3), Source.FILE, "Channel/PinholeSize", "µm")

        # spectral detection window
        ranges = []
        for rng in findall(chan, "DetectionWavelength") + findall(chan, "Ranges"):
            txt = (rng.text or "").strip()
            if "-" in txt:
                lo, _, hi = txt.partition("-")
                lo_f, hi_f = as_float(lo), as_float(hi)
                if lo_f and hi_f:
                    ranges.append((round(lo_f), round(hi_f)))
        if ranges:
            c.detection_range_nm = fv(ranges[0], Source.FILE,
                                      "Channel/DetectionWavelength/Ranges", "nm")

        lss = find(chan, "LightSourceSettings")
        if lss is not None:
            wl = _nm(as_float(text_of(lss, "Wavelength")))
            if wl and not raw(c.excitation_nm):
                c.excitation_nm = fv(wl, Source.FILE, "LightSourceSettings/Wavelength", "nm")
            inten = text_of(lss, "Intensity")
            c.laser_power = fv(inten, Source.FILE, "LightSourceSettings/Intensity")
        ds = find(chan, "DetectorSettings")
        if ds is not None:
            c.gain = fv(as_float(text_of(ds, "Gain", "Voltage")), Source.FILE,
                        "DetectorSettings/Gain")
            binning = text_of(ds, "Binning")
            ref = find(ds, "Detector")
            ref_id = attr_of(ref, "Id") if ref is not None else None
            for det in rec.detectors:
                if ref_id and raw(det.name) == ref_id:
                    c.detector = det
            if binning:
                c.detector.binning = fv(binning, Source.FILE, "DetectorSettings/Binning")
        if c.detector.kind is None and rec.detectors:
            c.detector = rec.detectors[min(idx, len(rec.detectors) - 1)]
        fs = text_of(chan, "FilterSetRef", "FilterSet")
        c.filter_set = fv(fs, Source.FILE, "Channel/FilterSetRef")

    _derive(rec)


def _derive(rec: Record) -> None:
    a = rec.acquisition
    nz, step = raw(a.size_z), raw(a.z_step_um)
    if nz and step and nz > 1:
        a.z_range_um = fv(round((nz - 1) * step, 4), Source.DERIVED,
                          "(SizeZ - 1) x z-step", "µm")
    nt, inc = raw(a.size_t), raw(a.time_increment_s)
    if nt and inc and nt > 1:
        a.total_time_s = fv(round((nt - 1) * inc, 3), Source.DERIVED,
                            "(SizeT - 1) x time increment", "s")
    na = raw(rec.objective.na)
    for c in rec.channels:
        if c.pinhole_au is None and raw(c.pinhole_um) and na:
            au, note = airy_units_auto(raw(c.pinhole_um), raw(c.emission_nm), na,
                                       raw(rec.objective.magnification))
            if au:
                c.pinhole_au = fv(au, Source.DERIVED,
                                  f"pinhole / (1.22 x lambda_em / NA), {note}", "AU")

    modality = None
    modes = {str(raw(c.acquisition_mode, "")).lower() for c in rec.channels}
    if any("airyscan" in m for m in modes):
        modality = "confocal (Airyscan)"
    elif any("spinningdisk" in m.replace(" ", "") for m in modes):
        modality = "spinning-disk confocal"
    elif any("laserscanningconfocal" in m.replace(" ", "") for m in modes):
        modality = "point-scanning confocal"
    elif any("multiphoton" in m for m in modes):
        modality = "two-photon laser-scanning microscopy"
    elif any("widefield" in m.replace("-", "") for m in modes):
        modality = "wide-field fluorescence"
    elif any("sheet" in m for m in modes):
        modality = "light-sheet fluorescence microscopy"
    if modality:
        rec.stand.modality = fv(modality, Source.FILE, "Channel/AcquisitionMode")


def _instrument_key(rec: Record) -> str:
    model = str(raw(rec.stand.model, "zeiss")).lower().replace(" ", "_")
    return f"zeiss_{model}"


def _nm(value):
    """CZI stores wavelengths in metres in some schema versions."""
    if value is None:
        return None
    return round(value * 1e9, 1) if value < 1e-3 else round(value, 1)


def _stand_type(value):
    if not value:
        return None
    low = value.lower()
    return "inverted" if "invert" in low else ("upright" if "upright" in low else value)


def _immersion(value):
    if not value:
        return None
    mapping = {"oil": "oil", "water": "water", "glyc": "glycerol", "air": "air",
               "sil": "silicone", "mult": "multi-immersion"}
    low = value.lower()
    for key, out in mapping.items():
        if low.startswith(key):
            return out
    return value


def _bits(value):
    if not value:
        return None
    return as_int(value)
