"""Data model for the bare-minimal microscopy reporting checklist.

Every reportable quantity is stored as a :class:`Value`, which carries the
number/string *and* where it came from.  Provenance is the point: a methods
section must never contain a number that the tool invented, and a reviewer
must be able to ask "was that read from the file or typed by a human?".
"""

from __future__ import annotations

import dataclasses
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Source(str, Enum):
    """Where a value came from. Ordered from most to least authoritative."""

    FILE = "file"          # parsed from the image file's own metadata
    COMPANION = "companion"  # parsed from a sibling file (PrairieView XML, etc.)
    DERIVED = "derived"    # computed from other values (z range, AU, ...)
    PROFILE = "profile"    # instrument profile maintained by the facility
    USER = "user"          # answered interactively by the user
    DEFAULT = "default"    # fallback assumption; always flagged in the report


_PRECEDENCE = {
    Source.FILE: 100,
    Source.COMPANION: 90,
    Source.DERIVED: 60,
    Source.PROFILE: 50,
    Source.USER: 70,      # a human correcting the file beats a profile guess
    Source.DEFAULT: 10,
}


@dataclass
class Value:
    """A single reportable value plus its provenance."""

    value: Any
    source: Source = Source.FILE
    detail: str = ""       # XML path, derivation formula, or prompt id
    unit: str | None = None

    def __str__(self) -> str:  # pragma: no cover - convenience only
        return "" if self.value is None else str(self.value)

    @property
    def rank(self) -> int:
        return _PRECEDENCE[self.source]


def fv(value: Any, source: Source = Source.FILE, detail: str = "",
       unit: str | None = None) -> Value | None:
    """Wrap ``value`` in a :class:`Value`, or return None for empty input.

    Readers call this constantly, so it swallows Nones and empty strings to
    keep vendor parsing code free of ``if x is not None`` noise.
    """
    if value is None:
        return None
    if isinstance(value, str):
        value = value.strip()
        if not value or value.lower() in {"none", "n/a", "unknown", "nan"}:
            return None
    if isinstance(value, float) and value != value:  # NaN
        return None
    return Value(value, source, detail, unit)


def raw(v: Value | None, default: Any = None) -> Any:
    """Unwrap a Value (or None) to its plain payload."""
    return default if v is None or v.value is None else v.value


# --------------------------------------------------------------------------
# Structured entities, mirroring the checklist's own vocabulary
# --------------------------------------------------------------------------


@dataclass
class Objective:
    designation: Value | None = None      # full barrel text, if the file has it
    magnification: Value | None = None
    na: Value | None = None
    correction: Value | None = None       # Plan Apochromat, Plan Fluor, ...
    immersion: Value | None = None        # oil / water / glycerol / silicone / air
    immersion_medium: Value | None = None  # e.g. "Cargille Type 37", "ethyl cinnamate"
    refractive_index: Value | None = None
    working_distance_mm: Value | None = None
    manufacturer: Value | None = None
    model: Value | None = None


@dataclass
class MicroscopeStand:
    manufacturer: Value | None = None
    model: Value | None = None
    stand_type: Value | None = None       # inverted / upright / other
    modality: Value | None = None         # confocal, light-sheet, 2-photon, ...
    modules: Value | None = None          # scan head, TIRF arm, Apotome, ...
    magnification_changer: Value | None = None


@dataclass
class LightSource:
    kind: Value | None = None             # laser / LED / arc / metal halide / MultiLaserEngine
    wavelength_nm: Value | None = None
    manufacturer: Value | None = None
    model: Value | None = None
    power_setting: Value | None = None    # % AOTF, mW at objective, ...
    name: Value | None = None


@dataclass
class OpticalFilter:
    role: Value | None = None             # excitation / emission / dichroic
    center_nm: Value | None = None
    fwhm_nm: Value | None = None
    range_nm: Value | None = None         # (low, high) tuple for spectral detection
    manufacturer: Value | None = None
    model: Value | None = None


@dataclass
class Detector:
    kind: Value | None = None             # camera / PMT / GaAsP / HyD / photodiode
    manufacturer: Value | None = None
    model: Value | None = None
    name: Value | None = None
    gain: Value | None = None
    offset: Value | None = None
    binning: Value | None = None


@dataclass
class Channel:
    index: int = 0
    name: Value | None = None
    fluorophore: Value | None = None      # FP variant or dye
    illumination_type: Value | None = None
    acquisition_mode: Value | None = None
    excitation_nm: Value | None = None
    emission_nm: Value | None = None
    detection_range_nm: Value | None = None
    exposure_time_ms: Value | None = None
    pinhole_um: Value | None = None
    pinhole_au: Value | None = None
    laser_power: Value | None = None
    gain: Value | None = None
    averaging: Value | None = None
    detector: Detector = field(default_factory=Detector)
    light_source: LightSource = field(default_factory=LightSource)
    filters: list[OpticalFilter] = field(default_factory=list)
    filter_set: Value | None = None       # named filter cube


@dataclass
class Acquisition:
    size_x: Value | None = None
    size_y: Value | None = None
    size_z: Value | None = None
    size_c: Value | None = None
    size_t: Value | None = None
    pixel_size_x_um: Value | None = None
    pixel_size_y_um: Value | None = None
    z_step_um: Value | None = None
    z_range_um: Value | None = None
    time_increment_s: Value | None = None
    total_time_s: Value | None = None
    bit_depth: Value | None = None
    dimension_order: Value | None = None
    tiles: Value | None = None
    tile_overlap_percent: Value | None = None
    pixel_dwell_us: Value | None = None
    scan_speed: Value | None = None
    line_averaging: Value | None = None
    zoom: Value | None = None
    channel_mode: Value | None = None     # sequential / simultaneous
    acquisition_date: Value | None = None


@dataclass
class Specimen:
    coverglass_no: Value | None = None
    coverglass_thickness_um: Value | None = None
    coverglass_coating: Value | None = None
    mounting_medium: Value | None = None
    mounting_medium_manufacturer: Value | None = None
    clearing_method: Value | None = None   # relevant for light-sheet / cleared tissue
    labels: Value | None = None            # free text: FP variants, dyes, antibodies
    live_imaging_conditions: Value | None = None


@dataclass
class Software:
    name: Value | None = None
    developer: Value | None = None
    version: Value | None = None


@dataclass
class Record:
    """Everything the report generator needs for one image dataset."""

    file_path: str = ""
    file_format: str = ""
    reader: str = ""
    instrument_key: str | None = None
    image_name: Value | None = None

    specimen: Specimen = field(default_factory=Specimen)
    stand: MicroscopeStand = field(default_factory=MicroscopeStand)
    objective: Objective = field(default_factory=Objective)
    light_sources: list[LightSource] = field(default_factory=list)
    detectors: list[Detector] = field(default_factory=list)
    channels: list[Channel] = field(default_factory=list)
    acquisition: Acquisition = field(default_factory=Acquisition)
    software: Software = field(default_factory=Software)

    # Modality-specific fields beyond the bare minimum (light-sheet, 2-photon).
    extras: dict[str, Any] = field(default_factory=dict)
    # Untouched vendor key/value dump, kept for `micromethods inspect`.
    vendor_raw: dict[str, Any] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def channel(self, i: int) -> Channel:
        while len(self.channels) <= i:
            self.channels.append(Channel(index=len(self.channels)))
        return self.channels[i]


# --------------------------------------------------------------------------
# Dotted-path addressing: "channels[0].exposure_time_ms"
#
# Used by the checklist registry, the instrument profiles and the answer
# store, so all three speak the same language.
# --------------------------------------------------------------------------

_TOKEN = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)(?:\[(\d+)\])?")

# Lists that path_set is allowed to grow when an answer addresses an entry
# that the file never declared (e.g. a light source the vendor omitted).
_LIST_ELEMENT = {
    "light_sources": lambda: LightSource(),
    "detectors": lambda: Detector(),
    "channels": lambda: Channel(),
    "filters": lambda: OpticalFilter(),
}


def _walk(root: Any, path: str, create: bool = False):
    """Return ``(container, attribute_name)`` for the final path element."""
    parts = path.split(".")
    obj = root
    for part in parts[:-1]:
        m = _TOKEN.fullmatch(part)
        if not m:
            raise ValueError(f"bad path segment {part!r} in {path!r}")
        name, idx = m.group(1), m.group(2)
        if isinstance(obj, dict):
            nxt = obj.get(name)
            if nxt is None:
                if not create:
                    return None, None
                nxt = {}
                obj[name] = nxt
            obj = nxt
        else:
            obj = getattr(obj, name)
        if idx is not None:
            i = int(idx)
            if isinstance(obj, list):
                if len(obj) <= i:
                    if not create:
                        return None, None
                    factory = _LIST_ELEMENT.get(name)
                    if factory is None:
                        raise IndexError(f"{path}: index {i} out of range")
                    while len(obj) <= i:
                        obj.append(factory())
                obj = obj[i]
            else:
                return None, None
    return obj, parts[-1]


def path_get(root: Any, path: str) -> Value | None:
    container, name = _walk(root, path)
    if container is None:
        return None
    if isinstance(container, dict):
        return container.get(name)
    return getattr(container, name, None)


def path_set(root: Any, path: str, value: Value | None, force: bool = False) -> bool:
    """Set a path. Refuses to clobber a higher-precedence value unless forced."""
    if value is None:
        return False
    container, name = _walk(root, path, create=True)
    if container is None:
        return False
    current = container.get(name) if isinstance(container, dict) else getattr(container, name, None)
    if isinstance(current, Value) and not force and current.rank >= value.rank:
        return False
    if isinstance(container, dict):
        container[name] = value
    else:
        setattr(container, name, value)
    return True


def to_dict(obj: Any) -> Any:
    """JSON-friendly dump that keeps provenance."""
    if isinstance(obj, Value):
        d = {"value": to_dict(obj.value), "source": obj.source.value}
        if obj.detail:
            d["detail"] = obj.detail
        if obj.unit:
            d["unit"] = obj.unit
        return d
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return {k: to_dict(v) for k, v in dataclasses.asdict.__wrapped__(obj).items()} \
            if hasattr(dataclasses.asdict, "__wrapped__") else \
            {f.name: to_dict(getattr(obj, f.name)) for f in dataclasses.fields(obj)}
    if isinstance(obj, dict):
        return {str(k): to_dict(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [to_dict(v) for v in obj]
    if isinstance(obj, Enum):
        return obj.value
    return obj
