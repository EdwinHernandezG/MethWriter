"""Leica reader (.lif, .lof, .xlef).

Leica stores a full LAS X hardware setting tree inside the container as XML.
``readlif`` is used to locate the image elements; the XML is then walked
directly, because readlif only surfaces a subset of the attributes and the
attribute names differ between SP8, STELLARIS and THUNDER systems.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from ..schema import Detector, LightSource, Record, Source, fv, raw
from ..units import airy_units_auto
from .base import (MissingDependency, Reader, as_float, as_int, attr_of, findall,
                   flatten_xml)

# DimID in Leica DimensionDescription
_DIM = {1: "X", 2: "Y", 3: "Z", 4: "T", 5: "Rotation", 6: "XT", 9: "Mosaic"}

_DETECTOR_KIND = {
    "pmt": "PMT", "hyd": "HyD hybrid detector", "gaasp": "GaAsP PMT",
    "apd": "avalanche photodiode", "camera": "camera", "hybrid": "HyD hybrid detector",
    "power hv": "PMT",
}


class LifReader(Reader):
    name = "lif"
    extensions = (".lif", ".lof", ".xlef")

    def read(self, path: Path, series: int = 0) -> Record:
        rec = Record(file_path=str(path), file_format=f"Leica {path.suffix.upper()[1:]}",
                     reader=self.name)
        root, image_names = _load_xml(path)
        elem = _image_element(root, series, image_names)
        rec.image_name = fv(attr_of(elem, "Name"), Source.FILE, "Element@Name")
        rec.vendor_raw["leica"] = flatten_xml(elem, limit=2000)
        _parse(elem, rec)
        rec.instrument_key = _instrument_key(rec)
        return rec


def _load_xml(path: Path):
    """Return (xml_root, [image element names])."""
    try:
        from readlif.reader import LifFile  # type: ignore
    except ImportError as exc:
        raise MissingDependency("readlif", "leica") from exc

    lif = LifFile(str(path))
    root = getattr(lif, "xml_root", None)
    if root is None:  # older readlif exposes the header string only
        header = getattr(lif, "xml_header", None)
        if header is None:
            raise MissingDependency("readlif>=0.6.5", "leica")
        root = ET.fromstring(header)
    names = [img.get("name", "") for img in getattr(lif, "image_list", [])]
    return root, names


def _image_element(root, series: int, names: list[str]):
    elements = [e for e in root.iter() if e.tag.endswith("Element")
                and any(c.tag.endswith("Data") for c in e)]
    if not elements:
        elements = [e for e in root.iter() if e.tag.endswith("Element")]
    if names and series < len(names):
        wanted = names[series].split("/")[-1]
        for elem in elements:
            if attr_of(elem, "Name") == wanted:
                return elem
    return elements[min(series, len(elements) - 1)] if elements else root


def _parse(elem, rec: Record) -> None:
    conf = next(iter(findall(elem, "ATLConfocalSettingDefinition")), None)
    cam = next(iter(findall(elem, "ATLCameraSettingDefinition")), None)
    setting = conf if conf is not None else cam
    a = rec.acquisition

    # ---- stand / system ----
    system = attr_of(setting, "SystemTypeName", "SystemType", "MicroscopeModel") \
        if setting is not None else None
    rec.stand.manufacturer = fv("Leica Microsystems", Source.DERIVED, "Leica file format")
    rec.stand.model = fv(system, Source.FILE, "ATLSettingDefinition@SystemTypeName")
    stand = attr_of(setting, "IsInverseMicroscopeModel") if setting is not None else None
    if stand is not None:
        rec.stand.stand_type = fv("inverted" if stand in ("1", "true", "True") else "upright",
                                  Source.FILE, "@IsInverseMicroscopeModel")
    if conf is not None:
        rec.stand.modality = fv("point-scanning confocal", Source.DERIVED,
                                "ATLConfocalSettingDefinition present")
    elif cam is not None:
        rec.stand.modality = fv("wide-field fluorescence", Source.DERIVED,
                                "ATLCameraSettingDefinition present")

    version = attr_of(setting, "SoftwareVersion") if setting is not None else None
    rec.software.name = fv("LAS X", Source.DERIVED, "Leica file format")
    rec.software.developer = fv("Leica Microsystems", Source.DERIVED, "Leica file format")
    rec.software.version = fv(version, Source.FILE, "@SoftwareVersion")

    # ---- objective ----
    if setting is not None:
        o = rec.objective
        o.designation = fv(attr_of(setting, "ObjectiveName", "Objective"), Source.FILE,
                           "@ObjectiveName")
        o.magnification = fv(as_float(attr_of(setting, "Magnification")), Source.FILE,
                             "@Magnification", "x")
        o.na = fv(as_float(attr_of(setting, "NumericalAperture")), Source.FILE,
                  "@NumericalAperture")
        o.refractive_index = fv(as_float(attr_of(setting, "RefractionIndex")), Source.FILE,
                                "@RefractionIndex")
        o.immersion = fv(_immersion(attr_of(setting, "Immersion"),
                                    as_float(attr_of(setting, "RefractionIndex"))),
                         Source.FILE, "@Immersion")
        o.manufacturer = fv("Leica Microsystems", Source.DERIVED, "Leica objective")
        if raw(o.designation):
            _split_designation(str(raw(o.designation)), rec)

        a.zoom = fv(as_float(attr_of(setting, "Zoom", "ZoomFactor")), Source.FILE, "@Zoom")
        speed = as_float(attr_of(setting, "ScanSpeed"))
        a.scan_speed = fv(speed, Source.FILE, "@ScanSpeed", "lines/s")
        dwell = as_float(attr_of(setting, "PixelDwellTime", "Pixel_Dwell_Time"))
        if dwell:
            a.pixel_dwell_us = fv(round(dwell * 1e6, 4) if dwell < 1e-3 else round(dwell, 4),
                                  Source.FILE, "@PixelDwellTime", "µs")
        avg = as_float(attr_of(setting, "Line_Average", "LineAverage", "Averaging"))
        a.line_averaging = fv(avg, Source.FILE, "@Line_Average")
        a.bit_depth = fv(as_int(attr_of(setting, "Resolution", "BitSize")), Source.FILE,
                         "@Resolution", "bit")
        exp = as_float(attr_of(setting, "ExposureTime", "WideFieldExposureTime"))
        if exp:
            rec.channel(0).exposure_time_ms = fv(round(exp * 1000, 3) if exp < 10
                                                 else round(exp, 3), Source.FILE,
                                                 "@ExposureTime", "ms")

    # ---- dimensions ----
    sizes = {}
    for dim in findall(elem, "DimensionDescription"):
        dim_id = as_int(attr_of(dim, "DimID"))
        n = as_int(attr_of(dim, "NumberOfElements"))
        length = as_float(attr_of(dim, "Length"))
        unit = attr_of(dim, "Unit") or ""
        axis = _DIM.get(dim_id or -1)
        if axis is None or n is None:
            continue
        sizes[axis] = n
        if length and n > 1:
            step = length / (n - 1)
            if axis in ("X", "Y", "Z") and unit.lower() in ("m", ""):
                um = round(step * 1e6, 6)
                target = {"X": "pixel_size_x_um", "Y": "pixel_size_y_um",
                          "Z": "z_step_um"}[axis]
                setattr(a, target, fv(um, Source.FILE,
                                      f"DimensionDescription[{axis}] Length/(N-1)", "µm"))
            if axis == "T":
                a.time_increment_s = fv(round(step, 4), Source.FILE,
                                        "DimensionDescription[T] Length/(N-1)", "s")
    a.size_x = fv(sizes.get("X"), Source.FILE, "DimensionDescription[X]")
    a.size_y = fv(sizes.get("Y"), Source.FILE, "DimensionDescription[Y]")
    a.size_z = fv(sizes.get("Z"), Source.FILE, "DimensionDescription[Z]")
    a.size_t = fv(sizes.get("T"), Source.FILE, "DimensionDescription[T]")
    if sizes.get("Mosaic", 1) > 1:
        a.tiles = fv(sizes["Mosaic"], Source.FILE, "DimensionDescription[Mosaic]")

    # ---- pinhole ----
    if setting is not None:
        pin_m = as_float(attr_of(setting, "Pinhole"))
        pin_au = as_float(attr_of(setting, "PinholeAiry"))
        pinhole_um = round(pin_m * 1e6, 3) if pin_m and pin_m < 1e-2 else pin_m

    # ---- channels ----
    descriptions = findall(elem, "ChannelDescription")
    multibands = findall(elem, "MultiBand")
    detectors = [d for d in findall(elem, "Detector")
                 if attr_of(d, "IsActive") in (None, "1", "true", "True")]
    for idx, chan in enumerate(descriptions or multibands):
        c = rec.channel(idx)
        c.name = fv(attr_of(chan, "ChannelName", "LUTName", "Name"), Source.FILE,
                    "ChannelDescription@LUTName")
        c.fluorophore = fv(attr_of(chan, "DyeName"), Source.FILE, "@DyeName")
        c.gain = fv(as_float(attr_of(chan, "Gain")), Source.FILE, "@Gain")
        if idx < len(multibands):
            band = multibands[idx]
            lo = as_float(attr_of(band, "LeftWorld"))
            hi = as_float(attr_of(band, "RightWorld"))
            if lo and hi:
                c.detection_range_nm = fv((round(lo), round(hi)), Source.FILE,
                                          "Spectro/MultiBand LeftWorld-RightWorld", "nm")
                c.emission_nm = fv(round((lo + hi) / 2), Source.DERIVED,
                                   "centre of the spectral detection window", "nm")
            c.fluorophore = c.fluorophore or fv(attr_of(band, "DyeName"), Source.FILE,
                                                "MultiBand@DyeName")
            c.name = c.name or fv(attr_of(band, "ChannelName"), Source.FILE,
                                  "MultiBand@ChannelName")
        if idx < len(detectors):
            det = detectors[idx]
            d = Detector()
            name = attr_of(det, "Name") or ""
            kind = next((v for k, v in _DETECTOR_KIND.items() if k in name.lower()), None)
            d.kind = fv(kind or attr_of(det, "Type"), Source.FILE, "Detector@Name/@Type")
            d.name = fv(name, Source.FILE, "Detector@Name")
            d.manufacturer = fv("Leica Microsystems", Source.DERIVED, "Leica detector")
            d.gain = fv(as_float(attr_of(det, "Gain")), Source.FILE, "Detector@Gain")
            d.offset = fv(as_float(attr_of(det, "Offset")), Source.FILE, "Detector@Offset")
            rec.detectors.append(d)
            c.detector = d
        if setting is not None:
            if pin_au:
                c.pinhole_au = fv(round(pin_au, 2), Source.FILE, "@PinholeAiry", "AU")
            if pinhole_um:
                c.pinhole_um = fv(pinhole_um, Source.FILE, "@Pinhole", "µm")

    # ---- laser lines ----
    laser_names = {}
    for laser in findall(elem, "Laser"):
        wl = as_float(attr_of(laser, "Wavelength"))
        if wl:
            laser_names[round(wl)] = attr_of(laser, "LaserName", "Name")
    for line in findall(elem, "LaserLineSetting"):
        wl = as_float(attr_of(line, "LaserLine"))
        intensity = as_float(attr_of(line, "IntensityDev", "IntensityLowSignal"))
        if not wl or not intensity:
            continue
        ls = LightSource()
        ls.kind = fv(f"{laser_names.get(round(wl)) or ''} laser".strip(), Source.FILE,
                     "LaserArray/Laser@LaserName")
        ls.wavelength_nm = fv(round(wl), Source.FILE, "LaserLineSetting@LaserLine", "nm")
        ls.power_setting = fv(round(intensity, 3), Source.FILE,
                              "LaserLineSetting@IntensityDev", "% AOTF")
        ls.manufacturer = fv("Leica Microsystems", Source.DERIVED, "Leica laser launch")
        rec.light_sources.append(ls)
    active = [ls for ls in rec.light_sources if (raw(ls.power_setting) or 0) > 0]
    for idx, c in enumerate(rec.channels):
        if idx < len(active):
            c.light_source = active[idx]
            c.excitation_nm = c.excitation_nm or active[idx].wavelength_nm
            c.laser_power = c.laser_power or active[idx].power_setting

    if len(rec.channels) > 1 and findall(elem, "LDM_Block_Sequential"):
        a.channel_mode = fv("sequential", Source.FILE, "LDM_Block_Sequential present")

    tile_nodes = findall(elem, "TileScanInfo") + [
        e for e in findall(elem, "Attachment")
        if (attr_of(e, "Name") or "").lower() == "tilescaninfo"]
    for tile in tile_nodes:
        ov = as_float(attr_of(tile, "OverlapPercentageX", "Overlap"))
        if ov is not None:
            a.tile_overlap_percent = fv(round(ov * 100 if ov <= 1 else ov, 2), Source.FILE,
                                        "TileScanInfo@OverlapPercentageX", "%")

    _derive(rec)


def _derive(rec: Record) -> None:
    a = rec.acquisition
    a.size_c = fv(len(rec.channels) or None, Source.DERIVED, "number of channel elements")
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


def _split_designation(text: str, rec: Record) -> None:
    """Pull correction/immersion words out of e.g.
    'HC PL APO CS2 63x/1.40 OIL'."""
    tokens = {t.strip("/,").upper() for t in text.replace("-", " ").split()}
    low = text.lower()
    parts = []
    if tokens & {"PL", "PLAN"} or "plan" in low:
        parts.append("Plan")
    for key, name in (("APO", "Apochromat"), ("FLUOTAR", "Fluotar"),
                      ("FLUAR", "Fluar"), ("ACH", "Achromat"),
                      ("NEOFLUAR", "Neofluar")):
        if any(t.startswith(key) for t in tokens):
            parts.append(name)
            break
    if parts and rec.objective.correction is None:
        rec.objective.correction = fv(" ".join(parts), Source.FILE,
                                      "parsed from @ObjectiveName")
    for key, val in (("oil", "oil"), ("water", "water"), ("wat", "water"),
                     ("glyc", "glycerol"), ("dry", "air"), ("air", "air"),
                     ("imm", "multi-immersion")):
        if key in low and rec.objective.immersion is None:
            rec.objective.immersion = fv(val, Source.FILE, "parsed from @ObjectiveName")
            break


def _immersion(value, ri=None):
    if value:
        low = str(value).lower()
        for key, out in (("oil", "oil"), ("wat", "water"), ("gly", "glycerol"),
                         ("air", "air"), ("dry", "air"), ("sil", "silicone")):
            if key in low:
                return out
        return value
    if ri:
        if abs(ri - 1.518) < 0.01:
            return "oil"
        if abs(ri - 1.333) < 0.01:
            return "water"
        if abs(ri - 1.0) < 0.02:
            return "air"
    return None


def _instrument_key(rec: Record) -> str:
    model = str(raw(rec.stand.model, "leica")).lower().replace(" ", "_")
    return f"leica_{model}"
