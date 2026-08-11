"""Instrument profiles.

Most of what the checklist demands never changes between experiments: the
stand model, the objective barrel text, the camera, the laser lines, the
software.  A facility writes that down once per microscope, and the tool
fills it in automatically instead of asking every user every time.

Profiles are plain YAML so a facility manager can edit them without touching
Python, and they are versioned per instrument so a hardware upgrade is a
visible change in the repository.

Search order (later wins on ties, earlier wins on equal specificity):
    1. profiles shipped with the package
    2. ~/.micromethods/profiles/*.yaml   (or $MICROMETHODS_PROFILES)
    3. paths passed explicitly on the command line
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .schema import Record, Source, Value, path_get, path_set, raw

PACKAGE_PROFILES = Path(__file__).resolve().parent / "instrument_profiles"
USER_PROFILES = Path(os.environ.get("MICROMETHODS_PROFILES",
                                    Path.home() / ".micromethods" / "profiles"))


@dataclass
class Profile:
    key: str
    label: str = ""
    match: dict[str, Any] = field(default_factory=dict)
    values: dict[str, Any] = field(default_factory=dict)
    channel_values: dict[str, Any] = field(default_factory=dict)
    overrides: dict[str, Any] = field(default_factory=dict)
    source_path: Path | None = None
    # Tie-breaker when several profiles match equally well:
    # 0 = shipped with the package, 1 = the user's own, 2 = named on the
    # command line. More specific wins, so a facility can correct a shipped
    # profile without editing the package.
    rank: int = 0

    def score(self, record: Record) -> int:
        """How well this profile matches a record. 0 means no match."""
        score = 0
        keys = _as_list(self.match.get("instrument_key"))
        if keys:
            if record.instrument_key in keys:
                score += 10
            else:
                return 0
        fingerprint = " ".join([
            str(record.vendor_raw.get("fingerprint", "")),
            str(raw(record.stand.model, "")), str(raw(record.stand.manufacturer, "")),
            str(raw(record.software.name, "")), record.file_path,
        ]).lower()
        needles = [n.lower() for n in _as_list(self.match.get("fingerprint_contains"))]
        if needles:
            hits = sum(1 for n in needles if n in fingerprint)
            if not hits:
                return 0
            score += hits
        formats = [f.lower() for f in _as_list(self.match.get("format"))]
        if formats:
            if record.file_format.lower() not in formats:
                return 0
            score += 1
        objective = self.match.get("objective_contains")
        if objective:
            barrel = str(raw(record.objective.designation, "")).lower()
            if objective.lower() not in barrel:
                return 0
            score += 3
        return score or 1

    def apply(self, record: Record) -> list[str]:
        """Fill empty fields. Never overwrites values read from the file,
        except for paths listed under ``overrides:`` — the escape hatch for
        vendor fields the facility knows to be wrong."""
        applied = []
        for path, value in self.overrides.items():
            previous = path_get(record, path)
            if path_set(record, path, Value(value, Source.PROFILE,
                                            f"instrument profile '{self.key}' (override)"),
                        force=True):
                applied.append(path)
                if previous is not None and previous.value != value:
                    record.notes.append(
                        f"Profile '{self.key}' overrode {path}: file said "
                        f"{previous.value!r}, profile says {value!r}.")
        for path, value in self.values.items():
            detail = f"instrument profile '{self.key}'"
            if path_set(record, path, Value(value, Source.PROFILE, detail)):
                applied.append(path)
        n_channels = max(1, len(record.channels))
        for suffix, value in self.channel_values.items():
            for i in range(n_channels):
                path = f"channels[{i}].{suffix}"
                record.channel(i)
                if path_set(record, path, Value(value, Source.PROFILE,
                                                f"instrument profile '{self.key}'")):
                    applied.append(path)
        return applied


def _as_list(value) -> list:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _load_yaml(path: Path) -> dict:
    try:
        import yaml
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("PyYAML is required for instrument profiles") from exc
    with path.open() as fh:
        return yaml.safe_load(fh) or {}


def load_profile(path: Path) -> Profile:
    data = _load_yaml(path)
    return Profile(
        key=data.get("key", path.stem),
        label=data.get("label", ""),
        match=data.get("match", {}) or {},
        values=data.get("values", {}) or {},
        channel_values=data.get("channel_values", {}) or {},
        overrides=data.get("overrides", {}) or {},
        source_path=path,
    )


def discover(extra: list[Path] | None = None) -> list[Profile]:
    out: list[Profile] = []
    for rank, folder in enumerate((PACKAGE_PROFILES, USER_PROFILES)):
        if folder.is_dir():
            for path in sorted(folder.glob("*.y*ml")):
                try:
                    profile = load_profile(path)
                    profile.rank = rank
                    out.append(profile)
                except Exception:
                    continue
    for path in extra or []:
        profile = load_profile(Path(path))
        profile.rank = 2
        out.append(profile)
    return out


def best_match(record: Record, extra: list[Path] | None = None) -> Profile | None:
    scored = [(p.score(record), p) for p in discover(extra)]
    scored = [(s, p) for s, p in scored if s > 0]
    if not scored:
        return None
    scored.sort(key=lambda sp: (sp[0], sp[1].rank), reverse=True)
    return scored[0][1]


def apply_best(record: Record, extra: list[Path] | None = None) -> Profile | None:
    profile = best_match(record, extra)
    if profile is not None:
        applied = profile.apply(record)
        record.notes.append(
            f"Applied instrument profile '{profile.key}' "
            f"({len(applied)} field(s) filled from {profile.source_path})"
        )
    return profile


def write_profile(key: str, values: dict[str, Any], label: str = "",
                  match: dict | None = None, folder: Path | None = None) -> Path:
    """Persist instrument-scope answers so nobody has to type them again."""
    import yaml

    folder = folder or USER_PROFILES
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{key}.yaml"
    data = _load_yaml(path) if path.exists() else {}
    data.setdefault("key", key)
    if label:
        data["label"] = label
    if match:
        data.setdefault("match", {}).update(match)
    merged = data.setdefault("values", {})
    channel_merged = data.setdefault("channel_values", {})
    for dotted, value in values.items():
        if dotted.startswith("channels["):
            channel_merged[dotted.split("].", 1)[1]] = value
        else:
            merged[dotted] = value
    with path.open("w") as fh:
        yaml.safe_dump(data, fh, sort_keys=False, allow_unicode=True)
    return path
