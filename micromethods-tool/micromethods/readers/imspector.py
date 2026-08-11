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

from ..schema import Detector, LightSource, Record, Source, fv, raw

# Clearing / immersion liquids the Blaze knows about, with their nominal RI.
_LIQUIDS = {
    "ECI": ("ethyl cinnamate", 1.558),
    "DBE": ("dibenzyl ether", 1.562),
    "BABB": ("benzyl alcohol/benzyl benzoate", 1.559),
    "DILWATER": ("dilute water", 1.333),
    "WATER": ("water", 1.333),
    "CUBIC": ("CUBIC reagent", 1.48),
}


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


def _detection_wheel(props: dict) -> str | None:
    """Find which UltraMotor device is the detection filter wheel."""
    for key, value in props.items():
        if re.fullmatch(r"Blaze dev\d+name", key) and "detection" in str(value).lower():
            return re.search(r"dev(\d+)name", key).group(1)
    return None


def _channel_index(props: dict, excitation, emission) -> int | None:
    """Match an OME channel to one of the configured Blaze filter combinations."""
    if excitation is not None or emission is not None:
        for i in range(16):
            ex = _num(props, f"Blaze ExWavelength{i}")
            em = _num(props, f"Blaze EmWavelength{i}")
            if ex is None and em is None:
                continue
            if (excitation is None or (ex and abs(ex - excitation) <= 2)) and \
               (emission is None or (em and abs(em - emission) <= 2)):
                return i
    selected = _num(props, "Blaze SelectedFilterIndex")
    return int(selected) if selected is not None else None


def applies(custom: dict, props: dict, fingerprint: str) -> bool:
    blob = " ".join([str(custom.get("ImspectorVersion", "")),
                     str(custom.get("InstrumentMode", "")), fingerprint]).lower()
    return (any(k in blob for k in ("imspector", "ultramicroscope", "blaze", "miltenyi"))
            or any(k.startswith("Blaze ") for k in props))


def apply(rec: Record, custom: dict, props: dict) -> None:
    """Merge Imspector annotation metadata into ``rec``."""
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
        name, nominal_ri = _LIQUIDS.get(liquid.upper(), (liquid, None))
        o.immersion = o.immersion or fv("dipping (immersion in clearing medium)",
                                        Source.DERIVED, f"prop 'Blaze Liquid' = {liquid}")
        o.immersion_medium = o.immersion_medium or fv(f"{name} ({liquid})", src,
                                                      "prop 'Blaze Liquid'")
        ri = _num(props, "Blaze LRI") or nominal_ri
        o.refractive_index = o.refractive_index or fv(ri, src, "prop 'Blaze LRI'")
        rec.specimen.clearing_method = rec.specimen.clearing_method or fv(
            f"{name} ({liquid}) as the imaging medium, refractive index {ri}",
            Source.DERIVED, "prop 'Blaze Liquid' / 'Blaze LRI'")

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
    overlap = (_num(props, "xyz-Table UserRequestedOverlapInPercent")
               or _num(props, "xyz-Table XYOvl"))
    if overlap is not None:
        a.tile_overlap_percent = a.tile_overlap_percent or fv(
            overlap, src, "prop 'xyz-Table UserRequestedOverlapInPercent'", "%")

    # ---- detector -------------------------------------------------------
    binning = _num(props, "Blaze Camera XBin") or _num(props, "Camera XBin")
    camera = Detector(
        kind=fv("sCMOS camera", Source.DERIVED, "Blaze detection arm uses an sCMOS camera"),
        manufacturer=None, model=None,
        name=fv(_txt(props, "Camera SerialNumber"), src, "prop 'Camera SerialNumber'"),
    )
    if binning:
        camera.binning = fv(f"{int(binning)}x{int(_num(props, 'Camera YBin') or binning)}",
                            src, "prop 'Camera XBin/YBin'")
    if not rec.detectors:
        rec.detectors.append(camera)

    # ---- per-channel settings ------------------------------------------
    wheel = _detection_wheel(props)
    individual = _num(props, "Blaze IndividualExpTimes")
    global_exposure = _num(props, "Blaze GlobalExpTime")
    laser_backend = _txt(props, "Blaze ExtLaserImpl")
    external_laser = _num(props, "Blaze ExtLaser")

    if not rec.channels:
        rec.channel(0)
    for c in rec.channels:
        idx = _channel_index(props, raw(c.excitation_nm), raw(c.emission_nm))
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

        exposure = (_num(props, f"Blaze ExpTime{idx}") if individual
                    else global_exposure) or _num(props, "Camera exp")
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
            f"dynamic horizontal focus, {int(steps)} steps", src,
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
