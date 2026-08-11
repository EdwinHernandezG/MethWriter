"""The bare minimal microscopy reporting requirements, as a data structure.

Transcribed from the QUAREP-LiMi WG11 checklist (Montero Llopis et al.,
J Cell Biol 2026, doi:10.1083/jcb.202601032; checklist v2025-03-06).  Each
entry keeps the checklist's own category, example text and machine-readable
LiMi-model (formerly NBO-Q) alignment, so the generated report can be diffed
against the published table field by field.

`path` addresses the Record (see schema.path_get / path_set) and doubles as
the key used by instrument profiles and saved answers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Callable

from .schema import Record, raw


class Level(str, Enum):
    REQUIRED = "required"        # bare minimum: must appear in the methods
    CONDITIONAL = "conditional"  # required when `applies` is true
    RECOMMENDED = "recommended"  # beyond the bare minimum; modality-specific


class Scope(str, Enum):
    INSTRUMENT = "instrument"    # stable per microscope -> cache in a profile
    EXPERIMENT = "experiment"    # per dataset
    SPECIMEN = "specimen"        # per sample; essentially never in the file


@dataclass
class Requirement:
    path: str
    category: str
    item: str
    prompt: str
    example: str = ""
    limi: str = ""
    level: Level = Level.REQUIRED
    scope: Scope = Scope.EXPERIMENT
    kind: str = "str"            # str | float | int | choice | list
    choices: tuple[str, ...] = ()
    unit: str | None = None
    per_channel: bool = False
    applies: Callable[[Record], bool] = lambda r: True
    note: str = ""

    def paths(self, record: Record) -> list[str]:
        if not self.per_channel:
            return [self.path]
        n = max(1, len(record.channels))
        return [self.path.format(c=i) for i in range(n)]


# --- predicates ------------------------------------------------------------

def _has_camera(r: Record) -> bool:
    kinds = [str(raw(d.kind, "")).lower() for d in r.detectors]
    kinds += [str(raw(c.detector.kind, "")).lower() for c in r.channels]
    return any("camera" in k or "cmos" in k or "ccd" in k for k in kinds)


def _has_point_detector(r: Record) -> bool:
    kinds = [str(raw(d.kind, "")).lower() for d in r.detectors]
    kinds += [str(raw(c.detector.kind, "")).lower() for c in r.channels]
    point = ("pmt", "gaasp", "hyd", "photomultiplier", "photodiode", "hybrid", "spectral")
    if any(any(p in k for p in point) for k in kinds):
        return True
    modality = str(raw(r.stand.modality, "")).lower()
    return any(m in modality for m in ("confocal", "photon", "sted")) and not _has_camera(r)


def _is_scanned(r: Record) -> bool:
    modality = str(raw(r.stand.modality, "")).lower()
    return _has_point_detector(r) or any(
        m in modality for m in ("confocal", "photon", "sted", "raster")
    )


def _is_zstack(r: Record) -> bool:
    return (raw(r.acquisition.size_z) or 1) > 1


def _is_timelapse(r: Record) -> bool:
    return (raw(r.acquisition.size_t) or 1) > 1


def _is_tiled(r: Record) -> bool:
    return (raw(r.acquisition.tiles) or 1) > 1


def _is_lightsheet(r: Record) -> bool:
    return "sheet" in str(raw(r.stand.modality, "")).lower()


def _is_multiphoton(r: Record) -> bool:
    m = str(raw(r.stand.modality, "")).lower()
    return "photon" in m or "2p" in m or "mp" in m


def _laser_based(r: Record) -> bool:
    kinds = [str(raw(ls.kind, "")).lower() for ls in r.light_sources]
    return any("laser" in k for k in kinds) or _is_scanned(r) or _is_lightsheet(r)


# --- the checklist ---------------------------------------------------------

REQUIREMENTS: list[Requirement] = [
    # ---------------- Specimen set-up ----------------
    Requirement(
        "specimen.coverglass_no", "Specimen set-up", "Sample mounting",
        "Cover glass number/thickness and any coating",
        "#1.5H cover glass (Marienfeld), coated with 1 mg/ml collagen type I",
        "CoverGlass/CoverGlassNo, CoverGlass/Thickness, CoverGlass/Coating",
        Level.REQUIRED, Scope.SPECIMEN,
    ),
    Requirement(
        "specimen.mounting_medium", "Specimen set-up", "Sample mounting",
        "Mounting or imaging medium (name and manufacturer)",
        "SlowFade Glass mounting medium (Thermo Fisher Scientific)",
        "MountingMedium/Model, MountingMedium/Manufacturer",
        Level.REQUIRED, Scope.SPECIMEN,
    ),
    Requirement(
        "specimen.labels", "Specimen set-up", "Sample labelling",
        "Fluorescent proteins (specific variant), dyes (name, manufacturer, "
        "concentration) or conjugated antibodies used",
        "mGFPmut3; MitoTracker Green at 1 µg/ml; secondary antibody conjugated "
        "to Alexa Fluor 647",
        "", Level.REQUIRED, Scope.SPECIMEN,
    ),
    Requirement(
        "specimen.clearing_method", "Specimen set-up", "Sample mounting",
        "Clearing protocol and refractive-index matching medium",
        "Samples were cleared with iDISCO+ and imaged in ethyl cinnamate (RI 1.56)",
        "", Level.RECOMMENDED, Scope.SPECIMEN, applies=_is_lightsheet,
        note="Not part of the bare minimum, but the RI of the imaging medium "
             "determines the effective NA and axial resolution for cleared tissue.",
    ),

    # ---------------- Hardware set-up ----------------
    Requirement(
        "stand.manufacturer", "Hardware set-up", "Microscope stand",
        "Microscope stand manufacturer", "Nikon", "MicroscopeStand/Manufacturer",
        Level.REQUIRED, Scope.INSTRUMENT,
    ),
    Requirement(
        "stand.model", "Hardware set-up", "Microscope stand",
        "Microscope stand model", "Ti2", "MicroscopeStand/Model",
        Level.REQUIRED, Scope.INSTRUMENT,
    ),
    Requirement(
        "stand.stand_type", "Hardware set-up", "Microscope stand",
        "Inverted or upright", "inverted",
        "MicroscopeStand subtype (Inverted, Upright)",
        Level.REQUIRED, Scope.INSTRUMENT, kind="choice",
        choices=("inverted", "upright", "other"),
    ),
    Requirement(
        "stand.modality", "Hardware set-up", "Modalities and modules/add-on",
        "Imaging modality",
        "confocal (point-scanning); light-sheet; two-photon; wide-field",
        "Pixels/Channel/IlluminationType", Level.REQUIRED, Scope.INSTRUMENT,
    ),
    Requirement(
        "stand.modules", "Hardware set-up", "Modalities and modules/add-on",
        "Modules / add-ons in the light path",
        "Yokogawa CSU-W1 spinning disk with SORA module; Apotome; TIRF arm",
        "", Level.REQUIRED, Scope.INSTRUMENT,
    ),
    Requirement(
        "objective.magnification", "Hardware set-up", "Objective",
        "Objective magnification", "63", "Objective/Magnification",
        Level.REQUIRED, Scope.INSTRUMENT, kind="float", unit="x",
    ),
    Requirement(
        "objective.na", "Hardware set-up", "Objective",
        "Objective numerical aperture", "1.4", "Objective/LensNA",
        Level.REQUIRED, Scope.INSTRUMENT, kind="float",
    ),
    Requirement(
        "objective.correction", "Hardware set-up", "Objective",
        "Correction type as printed on the barrel",
        "Plan Apochromat", "Objective/Correction",
        Level.REQUIRED, Scope.INSTRUMENT,
    ),
    Requirement(
        "objective.immersion", "Hardware set-up", "Objective",
        "Immersion type", "oil", "Objective/ImmersionType",
        Level.REQUIRED, Scope.INSTRUMENT, kind="choice",
        choices=("air", "oil", "water", "glycerol", "silicone", "multi-immersion", "other"),
    ),
    Requirement(
        "stand.magnification_changer", "Hardware set-up", "Additional magnification",
        "Additional magnification in the light path (optovar, zoom lens, "
        "camera adapter); enter 'none' if not applicable",
        "1.5x Optovar", "MagnificationChanger",
        Level.REQUIRED, Scope.INSTRUMENT,
    ),
    Requirement(
        "light_sources[0].kind", "Hardware set-up", "Light source",
        "Light source type", "LED light engine; diode laser; metal halide",
        "LightSource subtype (Arc, Filament, GenericLightSource, Laser, "
        "LightEmittingDiode, MultiLaserEngine)",
        Level.REQUIRED, Scope.INSTRUMENT,
    ),
    Requirement(
        "light_sources[0].manufacturer", "Hardware set-up", "Light source",
        "Light source manufacturer and model (non-laser sources)",
        "Spectra X (Lumencor)", "LightSource/Manufacturer, LightSource/Model",
        Level.CONDITIONAL, Scope.INSTRUMENT,
        applies=lambda r: not _laser_based(r),
    ),
    Requirement(
        "channels[{c}].excitation_nm", "Hardware set-up", "Light source",
        "Excitation wavelength (laser-based systems)", "405 nm diode laser",
        "LightSource/PeakWavelength", Level.CONDITIONAL, Scope.EXPERIMENT,
        kind="float", unit="nm", per_channel=True, applies=_laser_based,
    ),
    Requirement(
        "channels[{c}].detection_range_nm", "Hardware set-up", "Wavelength selection",
        "Emission filter (centre/FWHM) or spectral detection window",
        "ET525/50m (Chroma); or spectral detection between 500 and 544 nm",
        "Filter/TransmittanceRange/Wavelength, Filter/TransmittanceRange/"
        "FWHMBandwidth, Filter/Manufacturer, Filter/Model",
        Level.REQUIRED, Scope.EXPERIMENT, per_channel=True,
    ),
    Requirement(
        "channels[{c}].filter_set", "Hardware set-up", "Wavelength selection",
        "Filter cube, filter wheel position or dichroic used",
        "Filter cube 38 HE (Zeiss, BP 470/40 Ex, DC495, BP 525/50 Em)",
        "FilterCube, Dichroic/TransmittanceRange/Wavelength",
        Level.CONDITIONAL, Scope.INSTRUMENT, per_channel=True,
        applies=lambda r: not _is_scanned(r),
    ),
    Requirement(
        "channels[{c}].detector.kind", "Hardware set-up", "Detection system",
        "Detector type", "sCMOS camera; GaAsP PMT; HyD hybrid detector",
        "Camera/Manufacturer, Camera/Model, PointDetector subtype",
        Level.REQUIRED, Scope.INSTRUMENT, per_channel=True,
    ),
    Requirement(
        "channels[{c}].detector.model", "Hardware set-up", "Detection system",
        "Detector manufacturer and model",
        "Orca Flash 4.0 (Hamamatsu)", "Camera/Manufacturer, Camera/Model",
        Level.REQUIRED, Scope.INSTRUMENT, per_channel=True,
    ),

    # ---------------- Acquisition set-up ----------------
    Requirement(
        "channels[{c}].exposure_time_ms", "Acquisition set-up", "Acquisition settings",
        "Exposure time (camera-based acquisition)", "30 ms",
        "Pixels/Plane/ExposureTime", Level.CONDITIONAL, Scope.EXPERIMENT,
        kind="float", unit="ms", per_channel=True, applies=_has_camera,
    ),
    Requirement(
        "channels[{c}].pinhole_au", "Acquisition set-up", "Acquisition settings",
        "Pinhole size in Airy units", "1 AU", "PinholeSettings/Aperture",
        Level.CONDITIONAL, Scope.EXPERIMENT, kind="float", unit="AU",
        per_channel=True,
        applies=lambda r: _has_point_detector(r) and not _is_multiphoton(r),
    ),
    Requirement(
        "acquisition.pixel_dwell_us", "Acquisition set-up", "Acquisition settings",
        "Pixel dwell time or scan speed", "2 µs",
        "Pixels/Plane/PixelDwellTime, ConfocalScannerSettings/ScanningFrequency",
        Level.CONDITIONAL, Scope.EXPERIMENT, kind="float", unit="µs",
        applies=_is_scanned,
    ),
    Requirement(
        "acquisition.channel_mode", "Acquisition set-up", "Acquisition settings",
        "Channels acquired sequentially or simultaneously", "sequentially",
        "ConfocalScannerSettings/MultiChannelMode (Parallel or Sequential)",
        Level.CONDITIONAL, Scope.EXPERIMENT, kind="choice",
        choices=("sequential", "simultaneous"),
        applies=lambda r: len(r.channels) > 1,
    ),
    Requirement(
        "acquisition.line_averaging", "Acquisition set-up", "Acquisition settings",
        "Line/frame averaging or accumulation (enter 1 for none)", "no averaging",
        "", Level.CONDITIONAL, Scope.EXPERIMENT, kind="float", applies=_is_scanned,
    ),
    Requirement(
        "acquisition.pixel_size_x_um", "Acquisition set-up", "Acquisition settings",
        "Final effective image pixel size (x)", "0.065 µm/pixel",
        "Pixels/PhysicalSizeX", Level.REQUIRED, Scope.EXPERIMENT,
        kind="float", unit="µm",
    ),
    Requirement(
        "acquisition.pixel_size_y_um", "Acquisition set-up", "Acquisition settings",
        "Final effective image pixel size (y)", "0.065 µm/pixel",
        "Pixels/PhysicalSizeY", Level.REQUIRED, Scope.EXPERIMENT,
        kind="float", unit="µm",
    ),
    Requirement(
        "acquisition.z_step_um", "Acquisition set-up", "Acquisition settings",
        "Z-step increment", "0.1 µm", "Pixels/PhysicalSizeZ",
        Level.CONDITIONAL, Scope.EXPERIMENT, kind="float", unit="µm",
        applies=_is_zstack,
    ),
    Requirement(
        "acquisition.time_increment_s", "Acquisition set-up", "Acquisition settings",
        "Time increment between frames", "10 min interval",
        "Pixels/Plane/TimeIncrement", Level.CONDITIONAL, Scope.EXPERIMENT,
        kind="float", unit="s", applies=_is_timelapse,
    ),
    Requirement(
        "acquisition.tile_overlap_percent", "Acquisition set-up", "Acquisition settings",
        "Tile overlap", "10% overlap", "", Level.CONDITIONAL, Scope.EXPERIMENT,
        kind="float", unit="%", applies=_is_tiled,
    ),
    Requirement(
        "software.name", "Acquisition set-up", "Acquisition software",
        "Acquisition software name", "NIS-Elements AR", "AcquisitionSoftware/Name",
        Level.REQUIRED, Scope.INSTRUMENT,
    ),
    Requirement(
        "software.developer", "Acquisition set-up", "Acquisition software",
        "Acquisition software developer", "Nikon", "AcquisitionSoftware/Developer",
        Level.REQUIRED, Scope.INSTRUMENT,
    ),
    Requirement(
        "software.version", "Acquisition set-up", "Acquisition software",
        "Acquisition software version", "5.21", "AcquisitionSoftware/Version",
        Level.REQUIRED, Scope.INSTRUMENT,
    ),

    # ------- Modality-specific, beyond the bare minimum -------
    Requirement(
        "extras.lightsheet.sheet_na", "Acquisition set-up", "Light-sheet settings",
        "Light-sheet NA / thickness and sheet width",
        "Light sheet NA 0.156 (~4 µm waist), sheet width 60%",
        "", Level.RECOMMENDED, Scope.EXPERIMENT, applies=_is_lightsheet,
    ),
    Requirement(
        "extras.lightsheet.illumination_sides", "Acquisition set-up", "Light-sheet settings",
        "Illumination configuration (one-sided, two-sided, blending, dynamic focus)",
        "Two-sided illumination with dynamic horizontal focus (5 steps)",
        "", Level.RECOMMENDED, Scope.EXPERIMENT, applies=_is_lightsheet,
    ),
    Requirement(
        "extras.multiphoton.laser", "Hardware set-up", "Two-photon settings",
        "Excitation laser model, tuned wavelength and power at the objective",
        "Insight X3 (Spectra-Physics) tuned to 920 nm, 25 mW at the back aperture",
        "", Level.RECOMMENDED, Scope.EXPERIMENT, applies=_is_multiphoton,
    ),
    Requirement(
        "extras.multiphoton.detection", "Hardware set-up", "Two-photon settings",
        "Detection path (non-descanned/descanned, dichroics, emission filters, PMT type)",
        "Non-descanned GaAsP PMTs behind a 565 nm dichroic with ET525/70 and "
        "ET595/50 filters", "", Level.RECOMMENDED, Scope.EXPERIMENT,
        applies=_is_multiphoton,
    ),
]

BY_PATH = {r.path: r for r in REQUIREMENTS}

CATEGORY_ORDER = ["Specimen set-up", "Hardware set-up", "Acquisition set-up"]
