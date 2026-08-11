"""Unit conversion and formatting helpers.

Vendors disagree about units (Zeiss stores metres, Leica stores metres and
seconds, OME stores whatever the writer felt like plus an explicit unit).
Everything is normalised to µm / ms / s / nm on the way into the Record.
"""

from __future__ import annotations

_LENGTH_TO_UM = {
    "m": 1e6, "meter": 1e6, "metre": 1e6,
    "cm": 1e4, "mm": 1e3, "µm": 1.0, "um": 1.0, "micron": 1.0, "micrometer": 1.0,
    "nm": 1e-3, "angstrom": 1e-4, "Å": 1e-4,
}

_TIME_TO_S = {
    "h": 3600.0, "hour": 3600.0, "min": 60.0, "minute": 60.0,
    "s": 1.0, "sec": 1.0, "second": 1.0,
    "ms": 1e-3, "millisecond": 1e-3,
    "µs": 1e-6, "us": 1e-6, "microsecond": 1e-6,
    "ns": 1e-9, "nanosecond": 1e-9,
}


def to_um(value, unit: str | None = "m"):
    if value is None:
        return None
    factor = _LENGTH_TO_UM.get((unit or "m").strip())
    return None if factor is None else float(value) * factor


def to_seconds(value, unit: str | None = "s"):
    if value is None:
        return None
    factor = _TIME_TO_S.get((unit or "s").strip())
    return None if factor is None else float(value) * factor


def airy_units(pinhole_um: float, emission_nm: float, na: float,
               magnification: float | None = None, space: str = "object"):
    """Convert a physical pinhole diameter to Airy units.

    1 AU is the diameter of the Airy disc in object space, 1.22 * lambda / NA.
    Zeiss reports the back-projected (object-space) diameter; Leica reports it
    in metres, also back-projected.  If a vendor reports the diameter in the
    intermediate image plane, pass ``space="image"`` and the total
    magnification so it can be divided out first.
    """
    if not pinhole_um or not emission_nm or not na:
        return None
    d = float(pinhole_um)
    if space == "image":
        if not magnification:
            return None
        d /= float(magnification)
    airy_diameter_um = 1.22 * (float(emission_nm) / 1000.0) / float(na)
    if airy_diameter_um <= 0:
        return None
    return d / airy_diameter_um


def airy_units_auto(pinhole_um, emission_nm, na, magnification=None):
    """Convert a pinhole diameter to AU without knowing the vendor's convention.

    Vendors are inconsistent about whether the pinhole diameter is given in
    the intermediate image plane (ZEN, LAS X) or back-projected into object
    space.  Both are tried and the physically plausible one wins; if neither
    lands in a sane range the conversion is refused rather than guessed.

    Returns ``(value, note)`` or ``(None, reason)``.
    """
    candidates = []
    if magnification:
        image = airy_units(pinhole_um, emission_nm, na, magnification, space="image")
        if image is not None:
            candidates.append((image, "assuming the diameter is given in the "
                                      "intermediate image plane"))
    obj = airy_units(pinhole_um, emission_nm, na)
    if obj is not None:
        candidates.append((obj, "assuming a back-projected diameter"))
    for value, note in candidates:
        if 0.1 <= value <= 20:
            return round(value, 2), note
    if not candidates:
        return None, "emission wavelength or NA unknown"
    return None, (f"conversion gave an implausible value "
                  f"({candidates[0][0]:.1f} AU); pinhole not reported in AU")


def nyquist_xy_um(emission_nm: float, na: float) -> float | None:
    """Nyquist-limited lateral sampling, for the sanity-check warnings."""
    if not emission_nm or not na:
        return None
    return (float(emission_nm) / 1000.0) / (4.0 * float(na))


def fmt(value, digits: int = 3, unit: str = "") -> str:
    """Format a number for prose: no trailing zeros, no scientific notation."""
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        return "-".join(fmt(v, digits) for v in value) + (f" {unit}" if unit else "")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return f"{value}{' ' + unit if unit else ''}"
    if isinstance(value, int) or float(value).is_integer():
        s = str(int(value))
    else:
        s = f"{float(value):.{digits}g}"
        if "e" in s:
            s = f"{float(value):.{max(digits, 6)}f}".rstrip("0").rstrip(".")
    return f"{s} {unit}".strip()


def fmt_duration(seconds: float | None) -> str:
    """Human duration: 9000 -> '2.5 h', 600 -> '10 min', 0.5 -> '500 ms'."""
    if seconds is None:
        return ""
    s = float(seconds)
    if s >= 3600:
        return f"{fmt(s / 3600)} h"
    if s >= 60:
        return f"{fmt(s / 60)} min"
    if s >= 1:
        return f"{fmt(s)} s"
    return f"{fmt(s * 1000)} ms"
