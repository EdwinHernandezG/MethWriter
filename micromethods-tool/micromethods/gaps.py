"""Compare a Record against the checklist and report what is missing.

The output is data, not text: `find_gaps` returns Question objects that a CLI,
a napari widget or a batch answer file can all consume.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .checklist import REQUIREMENTS, Level, Requirement, Scope
from .schema import Record, Source, Value, path_get, raw
from .units import nyquist_xy_um


@dataclass
class Question:
    path: str
    requirement: Requirement
    channel: int | None = None
    current: Value | None = None

    @property
    def label(self) -> str:
        if self.channel is None:
            return self.requirement.prompt
        name = ""
        return f"{self.requirement.prompt} [channel {self.channel}{name}]"

    @property
    def scope(self) -> Scope:
        return self.requirement.scope

    @property
    def level(self) -> Level:
        return self.requirement.level


@dataclass
class Report:
    questions: list[Question] = field(default_factory=list)
    satisfied: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def blocking(self) -> list[Question]:
        return [q for q in self.questions if q.level is not Level.RECOMMENDED]

    @property
    def completeness(self) -> float:
        total = len(self.satisfied) + len(self.blocking)
        return 1.0 if total == 0 else len(self.satisfied) / total


def _is_empty(value: Value | None) -> bool:
    if value is None or value.value is None:
        return True
    if isinstance(value.value, str) and not value.value.strip():
        return True
    return False


def find_gaps(record: Record, include_recommended: bool = True) -> Report:
    report = Report()
    for req in REQUIREMENTS:
        if not req.applies(record):
            continue
        if req.level is Level.RECOMMENDED and not include_recommended:
            continue
        for idx, path in enumerate(req.paths(record)):
            current = path_get(record, path)
            if _is_empty(current):
                report.questions.append(Question(
                    path=path, requirement=req,
                    channel=idx if req.per_channel else None,
                    current=current))
            else:
                report.satisfied.append(path)
    report.warnings = sanity_checks(record)
    return report


def sanity_checks(record: Record) -> list[str]:
    """Cheap plausibility checks. These catch the classic metadata failures:
    a pixel size that was never calibrated, a z-step that undersamples, an
    objective/immersion mismatch."""
    out: list[str] = []
    a = record.acquisition
    px, py = raw(a.pixel_size_x_um), raw(a.pixel_size_y_um)
    na = raw(record.objective.na)

    if px and py and abs(px - py) / max(px, py) > 0.02:
        out.append(f"Pixel size is anisotropic in xy ({px} x {py} µm). Confirm this is "
                   "intentional before reporting a single value.")
    if px in (1.0, 0.0) and na:
        out.append("Pixel size reads exactly 1.0 µm, which usually means the file "
                   "carries no calibration. Verify against the acquisition software.")
    emissions = [raw(c.emission_nm) for c in record.channels if raw(c.emission_nm)]
    if px and na and emissions:
        nyq = nyquist_xy_um(min(emissions), na)
        if nyq and px > nyq * 2.2:
            out.append(f"Lateral sampling ({px} µm/pixel) is coarser than ~2x the "
                       f"Nyquist criterion for NA {na} ({nyq:.3f} µm). Worth stating "
                       "explicitly if resolution claims are made.")
    ri = raw(record.objective.refractive_index)
    imm = str(raw(record.objective.immersion, "")).lower()
    if ri and imm:
        expected = {"oil": 1.518, "water": 1.333, "glycerol": 1.45, "air": 1.0,
                    "silicone": 1.406}.get(imm)
        if expected and abs(ri - expected) > 0.05:
            out.append(f"Objective immersion is reported as '{imm}' but the refractive "
                       f"index in the file is {ri}. One of the two is wrong.")
    if (raw(a.size_z) or 1) > 1 and not raw(a.z_step_um):
        out.append("The dataset has multiple z-planes but no z-step; the axial "
                   "calibration is missing from the file.")
    derived = [c.pinhole_au for c in record.channels
               if c.pinhole_au and c.pinhole_au.source is Source.DERIVED]
    if derived:
        out.append("Pinhole size in Airy units was computed from the physical pinhole "
                   "diameter and the emission wavelength; check it against the value "
                   "shown in the acquisition software.")
    return out
