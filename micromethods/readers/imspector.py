"""Miltenyi Biotec UltraMicroscope Blaze / Imspector metadata.

The Blaze writes an OME-XML whose ``<Image>`` block is close to empty — no
Instrument, no Objective, no Detector — and puts everything of interest in
``<StructuredAnnotations>``:

  * a ``CustomAttributes`` annotation with the serial number, the Imspector
    version, the measurement mode and the physical axis descriptions;
  * a ``Properties`` annotation holding several hundred
    ``<prop Value=".." fname=".." label=".."/>`` entries, which is where the
    objective, zoom, laser lines, filter wheel, exposure times and light-sheet
    geometry actually live.

The property block describes up to ten *configured* channels (filter/laser
combinations) as parallel arrays, e.g. ``Blaze ExWavelength3`` /
``Blaze EmWavelength3`` / ``Blaze ExpTime3``. Only one of them is acquired per
file, identified by ``Blaze SelectedFilterIndex`` or matched on the
excitation/emission pair that the OME channel reports.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from ..schema import Detector, LightSource, Record, Source, fv, raw

# Clearing / immersion liquids the Blaze knows about, with their nominal RI.
# Imaging media the Blaze offers, mapped to (expansion, manufacturer, nominal RI).
# The vendor's own short name is what goes in the methods text — it is what the
# user selected and what appears in their protocol — with the expansion kept
# available for the checklist's "name and manufacturer" requirement.
_LIQUIDS = {
    "ECI": ("ethyl cinnamate", None, 1.558),
    "ECi": ("ethyl cinnamate", None, 1.558),
    "DBE": ("dibenzyl ether", None, 1.562),
    "BABB": ("benzyl alcohol / benzyl benzoate", None, 1.559),
    "CUBIC R2": ("CUBIC-R2 reagent", None, 1.48),
    "MACS IS": ("MACS Imaging Solution", "Miltenyi Biotec", 1.558),
    "MILK": ("MACS Clearing Solution", "Miltenyi Biotec", 1.46),
    "H2O": ("water", None, 1.333),
    "WATER": ("water", None, 1.333),
    "DILWATER": ("dilute water", None, 1.333),
}


# Imspector encodes the position of each file within the dataset in its name:
#   <time>_<name>_Blaze[00 x 01]_C02_xyz-Table Z0034.ome.tif
#            tile X --^     ^-- tile Y   ^-- channel     ^-- z plane
_FILENAME = re.compile(
    r"\[(?P<tile_x>\d+)\s*x\s*(?P<tile_y>\d+)\]"
    r"(?:_C(?P<channel>\d+))?"
    r"(?:_[^_]*?Z(?P<plane>\d+))?", re.IGNORECASE)


def parse_filename(name: str) -> dict[str, int]:
    """Extract tile position, channel index and z plane from a Blaze filename.

    Returns an empty dict when the name does not follow the pattern, which is
    normal for stitched or exported files.
    """
    match = _FILENAME.search(name)
    if not match:
        return {}
    return {key: int(value) for key, value in match.groupdict().items()
            if value is not None}


def _num(props: dict, key: str):
    value = props.get(key)
    if value is None:
        return None
    try:
        return float(str(value).strip())
    except ValueError:
        return None


def _txt(props: dict, key: str):
    value = props.get(key)
    if value is None:
        return None
    value = str(value).strip()
    return value or None


def _filter_window(name: str | None):
    """'680/30' -> (665, 695). Returns None for slot names like 'empty2'."""
    if not name:
        return None
    m = re.fullmatch(r"\s*(\d{3,4})\s*/\s*(\d{1,3})\s*", name)
    if not m:
        return None
    centre, width = float(m.group(1)), float(m.group(2))
    return (round(centre - width / 2), round(centre + width / 2))


# 'Camera Info' opens with a free-text identification line, e.g.
#   Camera: pco.edge 4.2 M CLHS rolling shutter (s/n: 61010487)  Hardware 00: ...
# Everything after the model is firmware and hardware revisions.
_CAMERA_INFO = re.compile(
    r"Camera:\s*(?P<model>.+?)\s*(?:\(s/n:\s*(?P<serial>[^)]*)\))?\s*(?:Hardware|Firmware|$)",
    re.IGNORECASE | re.DOTALL)

# Manufacturers recognisable from the model string. The Blaze detection arm has
# shipped with several cameras over the years, so this is read from the file
# rather than assumed.
_CAMERA_MAKERS = [
    ("pco.", "PCO"), ("pco ", "PCO"),
    ("zyla", "Andor"), ("neo", "Andor"), ("ixon", "Andor"), ("sona", "Andor"),
    ("orca", "Hamamatsu"), ("flash", "Hamamatsu"), ("fusion", "Hamamatsu"),
    ("prime", "Teledyne Photometrics"), ("kinetix", "Teledyne Photometrics"),
]


def parse_camera_info(text: str | None) -> dict[str, str]:
    """Pull model, manufacturer, serial and shutter mode out of 'Camera Info'."""
    if not text:
        return {}
    match = _CAMERA_INFO.search(str(text))
    if not match:
        return {}
    model = " ".join((match.group("model") or "").split())
    if not model:
        return {}
    out: dict[str, str] = {}
    low = model.lower()
    for needle, maker in _CAMERA_MAKERS:
        if needle in low:
            out["manufacturer"] = maker
            break
    # The shutter mode is a property of the acquisition, not part of the name.
    for mode in ("global shutter", "rolling shutter"):
        if mode in low:
            out["shutter"] = mode
            model = re.sub(mode, "", model, flags=re.IGNORECASE).strip()
            break
    out["model"] = " ".join(model.split())
    serial = (match.group("serial") or "").strip()
    if serial:
        out["serial"] = serial
    return out


def _detection_wheel(props: dict) -> str | None:
    """Find which UltraMotor device is the detection filter wheel."""
    for key, value in props.items():
        if re.fullmatch(r"Blaze dev\d+name", key) and "detection" in str(value).lower():
            return re.search(r"dev(\d+)name", key).group(1)
    return None


def acquired_slots(props: dict) -> list[int]:
    """Slot indices that were actually acquired, in acquisition order.

    The Blaze configures up to ten laser/filter combinations and flags the ones
    included in the measurement with ``Blaze FilterInMeasurement{i} = 1``. That
    flag is the only reliable way to know how many channels a multi-colour
    dataset really has, because the OME <Channel> elements Imspector writes
    carry no wavelengths at all.

    The slots themselves are stored longest-excitation-first, while acquisition
    runs shortest-excitation-first (channel C00 of a 488/561 experiment is the
    488 nm stack), so the slots are returned sorted by excitation wavelength.
    """
    slots = [i for i in range(16) if _num(props, f"Blaze FilterInMeasurement{i}") == 1]
    if not slots:
        selected = _num(props, "Blaze SelectedFilterIndex")
        return [int(selected)] if selected is not None else []
    return sorted(slots, key=lambda i: (_num(props, f"Blaze ExWavelength{i}") or 0, i))


def _channel_index(props: dict, excitation, emission, position: int = 0) -> int | None:
    """Resolve one OME channel to a configured Blaze slot.

    Matching on the wavelength pair is preferred and unambiguous. When the OME
    channel is bare (the usual case for Imspector), fall back to the acquired
    slots in order.
    """
    if excitation is not None or emission is not None:
        for i in range(16):
            ex = _num(props, f"Blaze ExWavelength{i}")
            em = _num(props, f"Blaze EmWavelength{i}")
            if ex is None and em is None:
                continue
            if (excitation is None or (ex and abs(ex - excitation) <= 2)) and \
               (emission is None or (em and abs(em - emission) <= 2)):
                return i
    slots = acquired_slots(props)
    if position < len(slots):
        return slots[position]
    return slots[0] if slots else None


def applies(custom: dict, props: dict, fingerprint: str) -> bool:
    blob = " ".join([str(custom.get("ImspectorVersion", "")),
                     str(custom.get("InstrumentMode", "")), fingerprint]).lower()
    return (any(k in blob for k in ("imspector", "ultramicroscope", "blaze", "miltenyi"))
            or any(k.startswith("Blaze ") for k in props))


def apply(rec: Record, custom: dict, props: dict) -> None:
    """Merge Imspector annotation metadata into ``rec``."""
    file_index = parse_filename(Path(rec.file_path).name)
    src = Source.FILE
    rec.instrument_key = "miltenyi_blaze"

    # ---- instrument identity ------------------------------------------
    version = custom.get("ImspectorVersion")          # "Imspector Pro 7.7.2"
    if version:
        m = re.match(r"(.*?)\s*([\d.]+)\s*$", str(version))
        rec.software.name = fv(m.group(1) if m else version, src,
                               "CustomAttributes/ImspectorVersion")
        rec.software.version = fv(m.group(2) if m else None, src,
                                  "CustomAttributes/ImspectorVersion")
    rec.software.developer = rec.software.developer or fv(
        "Miltenyi Biotec", Source.DERIVED, "Imspector is the Blaze acquisition software")
    serial = custom.get("SerialNumber")
    if serial:
        rec.extras.setdefault("instrument", {})["serial_number"] = fv(
            serial, src, "CustomAttributes/SerialNumber")
    mode = custom.get("InstrumentMode")
    if mode:
        rec.extras.setdefault("instrument", {})["instrument_mode"] = fv(
            mode, src, "CustomAttributes/InstrumentMode")
    if rec.stand.modality is None:
        rec.stand.modality = fv("light-sheet fluorescence microscopy", Source.DERIVED,
                                "Imspector / UltraMicroscope annotation")

    # ---- objective and magnification changer ---------------------------
    o = rec.objective
    o.designation = o.designation or fv(_txt(props, "Blaze Objective"), src,
                                        "prop 'Blaze Objective'")
    o.magnification = o.magnification or fv(_num(props, "Blaze ObjectiveMagnification"),
                                            src, "prop 'Blaze ObjectiveMagnification'", "x")
    o.na = o.na or fv(_num(props, "Blaze ObjectiveNA"), src, "prop 'Blaze ObjectiveNA'")

    liquid = _txt(props, "Blaze Liquid")
    if liquid:
        expansion, maker, nominal_ri = _LIQUIDS.get(
            liquid.upper(), _LIQUIDS.get(liquid, (None, None, None)))
        o.immersion = o.immersion or fv("dipping", Source.DERIVED,
                                        f"prop 'Blaze Liquid' = {liquid}")
        o.immersion_medium = o.immersion_medium or fv(liquid, src, "prop 'Blaze Liquid'")
        ri = _num(props, "Blaze LRI") or nominal_ri
        o.refractive_index = o.refractive_index or fv(ri, src, "prop 'Blaze LRI'")

        # On a dipping light-sheet system the sample sits in the imaging
        # chamber, so the imaging medium *is* the mounting medium; there is no
        # separate mountant and no cover glass. Satisfying the checklist item
        # this way is accurate rather than a workaround.
        rec.specimen.mounting_medium = rec.specimen.mounting_medium or fv(
            liquid, Source.DERIVED,
            "prop 'Blaze Liquid'; on a dipping system the imaging medium in the "
            "chamber is the mounting medium")
        if maker:
            rec.specimen.mounting_medium_manufacturer = (
                rec.specimen.mounting_medium_manufacturer
                or fv(maker, Source.DERIVED, f"'{liquid}' is {expansion} ({maker})"))
        rec.specimen.coverglass_no = rec.specimen.coverglass_no or fv(
            "not applicable — the sample is submerged in the imaging chamber",
            Source.DERIVED, "dipping objective, no cover glass in the light path")
        if expansion and expansion.lower() != liquid.lower():
            rec.extras.setdefault("specimen", {})["imaging_medium"] = fv(
                f"{liquid} ({expansion}" + (f", {maker}" if maker else "") + ")",
                Source.DERIVED, "prop 'Blaze Liquid'")

    zoom = _num(props, "Blaze CurrentZoom")
    if zoom:
        rec.acquisition.zoom = rec.acquisition.zoom or fv(zoom, src,
                                                          "prop 'Blaze CurrentZoom'", "x")
        rec.stand.magnification_changer = rec.stand.magnification_changer or fv(
            f"zoom body set to {zoom:g}x", src, "prop 'Blaze CurrentZoom'")

    # ---- tiling ---------------------------------------------------------
    a = rec.acquisition
    nx, ny = _num(props, "xyz-Table XRes"), _num(props, "xyz-Table YRes")
    mosaic = str(custom.get("MeasurementMode", "")).lower()
    if nx and ny and ("mosaic" in mosaic or nx * ny > 1):
        a.tiles = a.tiles or fv(int(nx * ny), Source.DERIVED,
                                "xyz-Table XRes x YRes (mosaic acquisition)")
    # 'UserRequestedOverlapInPercent' is frequently uninitialised (values such
    # as 1092616192 are a float/int reinterpretation of raw memory), while the
    # per-axis properties carry the real setting. Try the reliable ones first
    # and reject anything outside a plausible range whatever its source.
    for prop in ("xyz-Table UserRequestedOverlapInPercentX",
                 "xyz-Table UserRequestedOverlapInPercentY",
                 "xyz-Table XYOvl",
                 "xyz-Table UserRequestedOverlapInPercent"):
        overlap = _num(props, prop)
        if overlap is None or not 0 <= overlap <= 100:
            continue
        a.tile_overlap_percent = a.tile_overlap_percent or fv(
            round(overlap, 3), src, f"prop '{prop}'", "%")
        break
    else:
        bogus = _num(props, "xyz-Table UserRequestedOverlapInPercent")
        if bogus is not None:
            rec.notes.append(
                f"The tile overlap recorded in this file is not usable "
                f"({bogus:g}%); no per-axis overlap property was present either.")

    # ---- detector -------------------------------------------------------
    info = parse_camera_info(_txt(props, "Camera Info"))
    binning = _num(props, "Blaze Camera XBin") or _num(props, "Camera XBin")
    camera = Detector(
        kind=fv("sCMOS camera", Source.DERIVED,
                "Blaze detection arm uses an sCMOS camera"),
        manufacturer=fv(info.get("manufacturer"), src, "prop 'Camera Info'"),
        model=fv(info.get("model"), src, "prop 'Camera Info'"),
        name=fv(info.get("serial") or _txt(props, "Camera SerialNumber"), src,
                "prop 'Camera SerialNumber'"),
    )
    if binning:
        camera.binning = fv(f"{int(binning)}x{int(_num(props, 'Camera YBin') or binning)}",
                            src, "prop 'Camera XBin/YBin'")
    if not rec.detectors:
        rec.detectors.append(camera)

    detection = rec.extras.setdefault("detection", {})
    if info.get("shutter"):
        detection.setdefault("shutter_mode", fv(info["shutter"], src,
                                                "prop 'Camera Info'"))
    # Sensor pitch, which the pixel-size cross-check needs and which is worth
    # reporting: it is what makes the effective pixel size interpretable.
    full_x = _num(props, "Camera FullXLen")
    roi_right = _num(props, "Camera ROIRight")
    if full_x and roi_right:
        pitch = full_x / roi_right
        if 1 <= pitch <= 30:
            detection.setdefault("sensor_pixel_pitch", fv(
                round(pitch, 3), Source.DERIVED,
                "Camera FullXLen / Camera ROIRight", "µm"))
    if roi_right and _num(props, "Camera ROIBottom"):
        detection.setdefault("sensor_roi", fv(
            f"{int(roi_right)} x {int(_num(props, 'Camera ROIBottom'))} pixels",
            src, "prop 'Camera ROIRight/ROIBottom'"))

    # ---- per-channel settings ------------------------------------------
    wheel = _detection_wheel(props)
    individual = _num(props, "Blaze IndividualExpTimes")
    global_exposure = _num(props, "Blaze GlobalExpTime")
    laser_backend = _txt(props, "Blaze ExtLaserImpl")
    external_laser = _num(props, "Blaze ExtLaser")

    slots = acquired_slots(props)
    # Trust the acquisition flags over an under-populated OME header: a
    # multi-colour Blaze dataset routinely declares SizeC correctly but writes
    # empty <Channel> elements.
    for i in range(max(len(slots), 1)):
        rec.channel(i)
    if len(slots) > 1 and any(raw(c.excitation_nm) is None for c in rec.channels):
        rec.notes.append(
            f"{len(slots)} channels were acquired (Blaze filter slots "
            f"{', '.join(str(s) for s in slots)}). The OME header carries no "
            "wavelengths, so channels were matched to slots in acquisition "
            "order; confirm the assignment if the order matters.")

    for position, c in enumerate(rec.channels):
        idx = _channel_index(props, raw(c.excitation_nm), raw(c.emission_nm), position)
        if idx is None:
            continue
        detail = f"prop index {idx} (Blaze channel configuration)"
        c.excitation_nm = c.excitation_nm or fv(_num(props, f"Blaze ExWavelength{idx}"),
                                                src, detail, "nm")
        c.emission_nm = c.emission_nm or fv(_num(props, f"Blaze EmWavelength{idx}"),
                                            src, detail, "nm")

        slot = _num(props, f"Blaze ChanEmFilter{idx}")
        if wheel is not None and slot is not None:
            name = _txt(props, f"Blaze dev{wheel}step{int(slot)}name")
            window = _filter_window(name)
            if window:
                c.detection_range_nm = c.detection_range_nm or fv(
                    window, src, f"detection filter wheel position '{name}'", "nm")
                c.filter_set = c.filter_set or fv(
                    f"{name} bandpass emission filter", src,
                    f"prop 'Blaze dev{wheel}step{int(slot)}name'")

        # 'IndividualExpTimes = 0' means one global exposure for every channel.
        exposure = (_num(props, f"Blaze ExpTime{idx}") if individual
                    else (global_exposure or _num(props, f"Blaze ExpTime{idx}")))
        if exposure is None:
            exposure = _num(props, "Camera exp")
        c.exposure_time_ms = c.exposure_time_ms or fv(exposure, src,
                                                      f"prop 'Blaze ExpTime{idx}'", "ms")
        power = _num(props, f"Blaze AttenuatorPower{idx}")
        if power is None:
            power = _num(props, "Blaze CurPower")
        c.laser_power = c.laser_power or fv(power, src,
                                            f"prop 'Blaze AttenuatorPower{idx}'", "%")
        if c.detector.kind is None:
            c.detector = rec.detectors[0]

        line = raw(c.excitation_nm)
        if line and not raw(c.light_source.kind):
            source = LightSource(
                kind=fv("laser", src, "prop 'Blaze LaserName'"),
                wavelength_nm=fv(line, src, detail, "nm"),
                power_setting=fv(power, src, f"prop 'Blaze AttenuatorPower{idx}'", "%"),
            )
            if laser_backend:
                source.manufacturer = fv(
                    laser_backend.replace("Beamcombiner", "beam combiner"), src,
                    "prop 'Blaze ExtLaserImpl'")
            c.light_source = source
            rec.light_sources.append(source)

    # One illumination path means channels can only be acquired one after the
    # other. The file naming confirms it: each channel of each tile is written
    # as its own stack (..._C00_..., ..._C01_...).
    if len(rec.channels) > 1:
        detail = ("the Blaze has a single illumination and detection path, so "
                  "channels cannot be acquired simultaneously")
        if "channel" in file_index:
            detail += "; the file name indexes one channel per stack"
        a.channel_mode = a.channel_mode or fv("sequential", Source.DERIVED, detail)

    if file_index:
        info = rec.extras.setdefault("dataset", {})
        if "tile_x" in file_index and "tile_y" in file_index:
            info.setdefault("tile_position", fv(
                f"column {file_index['tile_x']}, row {file_index['tile_y']}",
                Source.FILE, "file name [XX x YY] index"))
        if "channel" in file_index:
            info.setdefault("file_channel_index", fv(
                file_index["channel"], Source.FILE, "file name _Cnn index"))
        if "plane" in file_index:
            info.setdefault("first_plane_index", fv(
                file_index["plane"], Source.FILE, "file name Znnnn index"))
        rec.notes.append(
            "This file is one stack of a multi-file acquisition (its name "
            "encodes tile position, channel and z plane); the metadata "
            "describes the whole acquisition.")

    if external_laser:
        rec.notes.append(
            "Excitation is delivered directly from the laser combiner; the "
            "excitation filter wheel positions in the file are not in the light path.")

    # ---- light-sheet geometry ------------------------------------------
    sheet = rec.extras.setdefault("lightsheet", {})
    mapping = [
        ("sheet_na", "Blaze NA", None, "prop 'Blaze NA' (sheet NA)"),
        ("sheet_thickness", "Blaze SheetThickness", "µm FWHM",
         "prop 'Blaze SheetThickness'"),
        ("sheet_width", "Blaze SheetWidthPercent", "%",
         "prop 'Blaze SheetWidthPercent'"),
        ("excitation_beam_waist", "Blaze ExBeamWaist", "µm",
         "prop 'Blaze ExBeamWaist'"),
    ]
    for key, prop, unit, detail in mapping:
        value = _num(props, prop)
        if value is not None:
            sheet.setdefault(key, fv(round(value, 4), src, detail, unit))
    sides = _txt(props, "Blaze SelSheets")
    if sides:
        blending = _txt(props, "Blaze SheetMergeAlg")
        sheet.setdefault("illumination_sides", fv(
            f"{sides}" + (f", merged by {blending.lower()}" if blending else ""),
            src, "prop 'Blaze SelSheets' / 'Blaze SheetMergeAlg'"))
    steps = _num(props, "Blaze DynFocusNumImages")
    if steps and _num(props, "Blaze HorzMode"):
        sheet.setdefault("dynamic_focus", fv(
            f"horizontal, {int(steps)} steps", src,
            "prop 'Blaze DynFocusNumImages'"))
    if _num(props, "Blaze ContinuousStackMode"):
        sheet.setdefault("stack_mode", fv("continuous z-stack acquisition", src,
                                          "prop 'Blaze ContinuousStackMode'"))

    _cross_check(rec, props)


def _cross_check(rec: Record, props: dict) -> None:
    """Flag the two places where the Blaze annotation contradicts itself."""
    # 1. pixel size against the magnification chain and the sensor pitch
    px = raw(rec.acquisition.pixel_size_x_um)
    mag = raw(rec.objective.magnification)
    zoom = raw(rec.acquisition.zoom) or 1.0
    full_x = _num(props, "Camera FullXLen")
    sensor_px = _num(props, "Blaze YRes") or _num(props, "Camera ROIRight")
    if px and mag and full_x and sensor_px:
        pitch = full_x / 2048.0 if sensor_px <= 2048 else full_x / sensor_px
        expected = pitch / (mag * zoom)
        if expected and abs(expected - px) / px > 0.05:
            rec.notes.append(
                f"Pixel size cross-check: {mag:g}x objective x {zoom:g} zoom with a "
                f"{pitch:.2f} µm sensor pitch predicts {expected:.4f} µm/pixel, but the "
                f"file reports {px:.4f} µm/pixel.")

    # 2. objective NA against the PSF calibration block
    reported = raw(rec.objective.na)
    calib = props.get("Blaze LightSheetCalibration")
    if not reported or not calib:
        return
    try:
        data = json.loads(str(calib))
        psf = data.get("PSF", {})
        objective = str(raw(rec.objective.designation, ""))
        entry = psf.get(objective) or {}
        zoom_key = f"{zoom:g}"
        candidate = (entry.get(zoom_key) or next(iter(entry.values()), {})).get("NA")
    except (ValueError, TypeError, AttributeError):
        return
    if candidate and abs(candidate - reported) > 0.02:
        rec.notes.append(
            f"Objective NA is ambiguous in this file: the 'Blaze ObjectiveNA' property "
            f"says {reported:g}, while the PSF calibration block gives {candidate:g} for "
            f"{objective}. Check the objective barrel and set the correct value with an "
            f"'overrides:' entry in the instrument profile.")
