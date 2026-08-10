"""Turn a Record into a methods section, a filled checklist and a JSON sidecar.

Sentence structure follows the worked examples in the QUAREP-LiMi WG11
checklist so that the output reads like something a person would write, not
like a metadata dump.  Anything still unknown is emitted as an explicit
[MISSING: ...] marker: an incomplete methods section should be visibly
incomplete rather than quietly wrong.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from .checklist import CATEGORY_ORDER, REQUIREMENTS, Level
from .gaps import Report
from .schema import Record, Source, Value, path_get, raw, to_dict
from .units import fmt, fmt_duration

MISSING = "[MISSING: {}]"


# --------------------------------------------------------------------------
# small formatting helpers
# --------------------------------------------------------------------------

def _v(value: Value | None, unit: str = "", digits: int = 4) -> str:
    if value is None or value.value is None:
        return ""
    payload = value.value
    if isinstance(payload, (list, tuple)) and len(payload) == 2:
        return f"{fmt(payload[0], digits)}-{fmt(payload[1], digits)}{' ' + unit if unit else ''}"
    return fmt(payload, digits, unit)


def _vu(value: Value | None) -> str:
    """Render a value together with the unit it carries."""
    if value is None or value.value is None:
        return ""
    unit = value.unit or ""
    if unit in ("%", "% AOTF"):
        return f"{_v(value)}%"
    return _v(value, unit)


# Letters whose spoken name begins with a vowel sound, for acronyms such as
# "an LSM 980", "an sCMOS camera", "an HyD detector".
_VOWEL_SOUNDING = set("AEFHILMNORSX")


def _article(phrase: str) -> str:
    word = phrase.lstrip("[ ").split(" ")[0].strip("([") if phrase.strip() else ""
    if not word:
        return "a"
    acronymish = ((word.isupper() and len(word) <= 4)
                  or (word[:1].islower() and word[1:2].isupper()))
    if acronymish:
        return "an" if word[0].upper() in _VOWEL_SOUNDING else "a"
    return "an" if word[:1].lower() in "aeiou" else "a"


def _need(value: Value | None, label: str, unit: str = "") -> str:
    text = _v(value, unit)
    return text or MISSING.format(label)


def _join(parts, sep=" "):
    return sep.join(p for p in parts if p)


def _sentence(parts, sep=" ") -> str:
    text = _join(parts, sep).strip()
    if not text:
        return ""
    text = text[0].upper() + text[1:]
    return text if text.endswith((".", "!", "?")) else text + "."


def _channel_label(rec: Record, idx: int) -> str:
    c = rec.channels[idx]
    name = raw(c.fluorophore) or raw(c.name)
    if name:
        return f"the {name} channel"
    return f"channel {idx + 1}"


# --------------------------------------------------------------------------
# methods prose
# --------------------------------------------------------------------------

def specimen_paragraph(rec: Record) -> str:
    s = rec.specimen
    sentences = []
    coverglass = _v(s.coverglass_no) or _v(s.coverglass_thickness_um, "µm")
    coating = _v(s.coverglass_coating)
    if coverglass:
        sentences.append(_sentence([
            f"samples were mounted on {coverglass} cover glass",
            f"coated with {coating}" if coating and coating != "not applicable" else "",
        ], sep=", "))
    medium = _v(s.mounting_medium)
    if medium:
        man = _v(s.mounting_medium_manufacturer)
        sentences.append(_sentence(
            [f"prior to imaging, samples were mounted in {medium}",
             f"({man})" if man else ""]))
    if _v(s.clearing_method):
        sentences.append(_sentence([f"samples were cleared using {_v(s.clearing_method)}"]))
    if _v(s.labels):
        sentences.append(_sentence([f"labelling: {_v(s.labels)}"]))
    if _v(s.live_imaging_conditions):
        sentences.append(_sentence(
            [f"live imaging was performed {_v(s.live_imaging_conditions)}"]))
    return " ".join(sentences)


def hardware_sentences(rec: Record) -> list[str]:
    out = []
    stand = _join([
        _need(rec.stand.model, "microscope stand model"),
        _v(rec.stand.stand_type),
    ])
    manufacturer = _v(rec.stand.manufacturer)
    modality = _need(rec.stand.modality, "imaging modality")
    out.append(_sentence([
        f"images were acquired on {_article(stand)} {stand} microscope stand",
        f"({manufacturer})" if manufacturer else "",
        f"configured for {modality}" if modality else "",
    ]))
    modules = _v(rec.stand.modules)
    if modules and modules.lower() not in ("none", "not applicable"):
        out.append(_sentence([f"the stand was equipped with {modules}"]))

    o = rec.objective
    designation = _v(o.designation)
    immersion = _need(o.immersion, "immersion type")
    if not any(w in immersion.lower() for w in ("immersion", "dipping")):
        immersion = f"{immersion}-immersion"
    objective = _join([
        f"{_need(o.magnification, 'objective magnification')}x/"
        f"{_need(o.na, 'objective NA')}",
        _v(o.correction) or MISSING.format("objective correction type"),
        immersion,
    ])
    detail = _join([designation, _v(o.manufacturer)], ", ")
    out.append(_sentence([
        f"imaging used {_article(objective)} {objective} objective",
        f"({detail})" if detail else "",
    ]))
    changer = _v(rec.stand.magnification_changer)
    if changer and changer.lower() not in ("none", "not applicable", "1", "1x"):
        out.append(_sentence([f"an additional {changer} magnification was used in the "
                              "light path"]))
    return [s for s in out if s]


def illumination_sentences(rec: Record) -> list[str]:
    out = []
    lasers = [ls for ls in rec.light_sources
              if "laser" in str(raw(ls.kind, "")).lower() and raw(ls.wavelength_nm)]
    others = [ls for ls in rec.light_sources if ls not in lasers and raw(ls.kind)]
    if lasers:
        lines = sorted({int(raw(ls.wavelength_nm)) for ls in lasers})
        names = {str(raw(ls.kind)).strip() for ls in lasers if raw(ls.kind)}
        descriptor = names.pop() if len(names) == 1 else "laser"
        if len(lines) > 1:
            listed = ", ".join(str(w) for w in lines[:-1]) + f" and {lines[-1]} nm"
        else:
            listed = f"{lines[0]} nm"
        descriptor = descriptor.lower()
        out.append(_sentence([
            f"excitation was provided by {listed}",
            descriptor if descriptor.endswith("laser") else f"{descriptor} laser",
            "lines" if len(lines) > 1 else "line",
        ]))
    for ls in others:
        detail = _join([_v(ls.model), _v(ls.manufacturer)], ", ")
        out.append(_sentence([
            f"samples were illuminated using a {_v(ls.kind)}",
            f"({detail})" if detail else "",
        ]))
    if not rec.light_sources:
        out.append(_sentence([MISSING.format("light source type, manufacturer and model")]))
    return out


def channel_sentences(rec: Record) -> list[str]:
    out = []
    for idx, c in enumerate(rec.channels):
        label = _channel_label(rec, idx)
        excitation = _v(c.excitation_nm, "nm")
        detection = _v(c.detection_range_nm)
        filter_set = _v(c.filter_set)
        detector = _join([_v(c.detector.kind), _v(c.detector.model)], " ")
        detector_man = _v(c.detector.manufacturer)
        emission_bits = ""
        window = c.detection_range_nm.value if c.detection_range_nm else None
        if isinstance(window, (list, tuple)) and len(window) == 2:
            emission_bits = (f"detected between {fmt(window[0])} and "
                             f"{fmt(window[1])} nm")
        elif detection:
            emission_bits = f"detected through {detection}"
        elif filter_set:
            emission_bits = f"detected through {filter_set}"
        else:
            emission_bits = f"detected {MISSING.format('emission filter or detection window')}"
        parts = [
            f"{label} was excited at {excitation}" if excitation
            else f"{label} was excited using {MISSING.format('excitation wavelength')}",
            f"and {emission_bits}",
        ]
        if detector:
            parts.append(f"on {_article(detector)} {detector}"
                         + (f" ({detector_man})" if detector_man else ""))
        else:
            parts.append(f"on {MISSING.format('detector type and model')}")
        settings = []
        if raw(c.pinhole_au):
            settings.append(f"a {_v(c.pinhole_au)} AU pinhole")
        if raw(c.exposure_time_ms):
            settings.append(f"{_v(c.exposure_time_ms)} ms exposure")
        if raw(c.laser_power):
            settings.append(f"{_vu(c.laser_power)} laser power")
        if raw(c.gain):
            settings.append(f"detector gain {_v(c.gain)}")
        if settings:
            parts.append("with " + _join(settings, ", "))
        out.append(_sentence(parts))
    return out


def acquisition_sentences(rec: Record) -> list[str]:
    a = rec.acquisition
    out = []
    px, py = _v(a.pixel_size_x_um), _v(a.pixel_size_y_um)
    if px and py and px != py:
        out.append(_sentence([f"the final image pixel size was {px} x {py} µm"]))
    else:
        out.append(_sentence([
            f"the final image pixel size was {px or MISSING.format('pixel size')} µm/pixel"
        ]))

    if (raw(a.size_z) or 1) > 1:
        out.append(_sentence([
            "volumes were acquired over a",
            _need(a.z_range_um, "z-range", "µm"), "range with a",
            _need(a.z_step_um, "z-step", "µm"), "z-step",
            f"({fmt(raw(a.size_z))} planes)" if raw(a.size_z) else "",
        ]))
    if (raw(a.size_t) or 1) > 1:
        interval = fmt_duration(raw(a.time_increment_s)) or MISSING.format("time interval")
        total = fmt_duration(raw(a.total_time_s)) or MISSING.format("total acquisition time")
        out.append(_sentence([
            f"time-lapse imaging was performed for {total} with a {interval} interval",
            f"({fmt(raw(a.size_t))} time points)" if raw(a.size_t) else "",
        ]))
    if (raw(a.tiles) or 1) > 1:
        overlap = _v(a.tile_overlap_percent, "%") or MISSING.format("tile overlap")
        out.append(_sentence([
            f"{fmt(raw(a.tiles))} tiles were acquired with {overlap} overlap"]))

    scanner = []
    if raw(a.channel_mode):
        scanner.append(f"channels were acquired {_v(a.channel_mode)}ly"
                       if _v(a.channel_mode) == "sequential"
                       else f"channels were acquired {_v(a.channel_mode)}")
    if raw(a.pixel_dwell_us):
        scanner.append(f"pixel dwell time was {_v(a.pixel_dwell_us)} µs")
    elif raw(a.scan_speed):
        scanner.append(f"scan speed was {_vu(a.scan_speed)}")
    if raw(a.line_averaging):
        avg = raw(a.line_averaging)
        scanner.append("no averaging was applied" if avg in (1, 1.0, "1")
                       else f"{fmt(avg)}x line averaging was applied")
    if raw(a.zoom):
        scanner.append(f"the scanner zoom was {_v(a.zoom)}")
    if scanner:
        out.append(_sentence([_join(scanner, ", ")]))
    return out


_EXTRA_LABELS = {"lightsheet": "light-sheet settings",
                 "multiphoton": "two-photon settings",
                 "illumination": "illumination settings",
                 "optics": "detection optics"}


def extras_sentences(rec: Record) -> list[str]:
    out = []
    for group, values in (rec.extras or {}).items():
        if not isinstance(values, dict):
            continue
        bits = [f"{k.replace('_', ' ')} {_vu(v) if isinstance(v, Value) else v}"
                for k, v in values.items() if v is not None]
        if bits:
            label = _EXTRA_LABELS.get(group, group.replace("_", " ") + " settings")
            out.append(_sentence([f"{label}: {_join(bits, '; ')}"]))
    return out


def software_sentence(rec: Record) -> str:
    s = rec.software
    name = _need(s.name, "acquisition software name")
    version = _v(s.version) or MISSING.format("software version")
    developer = _v(s.developer)
    head = f"acquisition was controlled with {name} v{version}"
    if developer:
        head += f" ({developer})"
    if rec.file_format:
        head += f", and data were saved in {rec.file_format} format"
    return _sentence([head])


def methods_text(rec: Record) -> str:
    paragraphs = []
    specimen = specimen_paragraph(rec)
    if specimen:
        paragraphs.append(specimen)
    body = (hardware_sentences(rec) + illumination_sentences(rec)
            + channel_sentences(rec) + acquisition_sentences(rec)
            + extras_sentences(rec) + [software_sentence(rec)])
    paragraphs.append(" ".join(s for s in body if s))
    return "\n\n".join(paragraphs)


ACKNOWLEDGEMENT = (
    "Imaging was performed at [core facility name]. We thank the facility for "
    "access to [instrument] and for support, and acknowledge [grant number] "
    "for instrument funding."
)


# --------------------------------------------------------------------------
# checklist table and machine-readable output
# --------------------------------------------------------------------------

def checklist_rows(rec: Record) -> list[dict]:
    rows = []
    for req in REQUIREMENTS:
        if not req.applies(rec):
            continue
        for idx, path in enumerate(req.paths(rec)):
            value = path_get(rec, path)
            rows.append({
                "category": req.category,
                "item": req.item,
                "requirement": req.prompt + (f" (channel {idx})" if req.per_channel else ""),
                "value": _v(value, req.unit or ""),
                "source": value.source.value if isinstance(value, Value) else "-",
                "level": req.level.value,
                "limi": req.limi,
                "path": path,
            })
    return rows


def checklist_markdown(rec: Record) -> str:
    rows = checklist_rows(rec)
    lines = []
    for category in CATEGORY_ORDER:
        subset = [r for r in rows if r["category"] == category]
        if not subset:
            continue
        lines.append(f"\n### {category}\n")
        lines.append("| Requirement | Reported value | Source | LiMi-model alignment |")
        lines.append("|---|---|---|---|")
        for r in subset:
            value = r["value"] or ("_not reported_" if r["level"] != "recommended"
                                   else "_n/a_")
            limi = r["limi"].replace("\n", " ") or "-"
            lines.append(f"| {r['requirement']} | {value} | {r['source']} | `{limi}` |")
    return "\n".join(lines)


def report_markdown(rec: Record, report: Report) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    missing = report.blocking
    out = [
        f"# Microscopy methods report",
        "",
        f"- **File:** `{rec.file_path}`",
        f"- **Format:** {rec.file_format} (reader: {rec.reader})",
        f"- **Instrument profile:** {rec.instrument_key or 'not identified'}",
        f"- **Checklist coverage:** {report.completeness * 100:.0f}% of applicable "
        f"required fields ({len(report.satisfied)} reported, {len(missing)} missing)",
        f"- **Generated:** {now}",
        "",
        "## Methods text",
        "",
        methods_text(rec),
        "",
        "## Acknowledgements (template)",
        "",
        ACKNOWLEDGEMENT,
        "",
        "## Reporting checklist",
        "",
        "Aligned with the QUAREP-LiMi WG11 bare minimal microscopy reporting "
        "requirements checklist (Montero Llopis et al., *J Cell Biol* 2026, "
        "doi:10.1083/jcb.202601032).",
        checklist_markdown(rec),
        "",
    ]
    if missing:
        out += ["## Still missing", ""]
        out += [f"- **{q.requirement.item}** - {q.label}"
                f"{' (e.g. ' + q.requirement.example + ')' if q.requirement.example else ''}"
                for q in missing]
        out.append("")
    if report.warnings:
        out += ["## Consistency warnings", ""]
        out += [f"- {w}" for w in report.warnings]
        out.append("")

    counts: dict[str, int] = {}
    for row in checklist_rows(rec):
        counts[row["source"]] = counts.get(row["source"], 0) + 1
    out += [
        "## Provenance",
        "",
        "| Source | Fields |",
        "|---|---|",
    ]
    labels = {
        Source.FILE.value: "read from the image file",
        Source.COMPANION.value: "read from a companion vendor file",
        Source.DERIVED.value: "computed from other metadata",
        Source.PROFILE.value: "instrument profile",
        Source.USER.value: "supplied by the user",
        Source.DEFAULT.value: "assumed default",
        "-": "not reported",
    }
    for key, count in sorted(counts.items(), key=lambda kv: -kv[1]):
        out.append(f"| {labels.get(key, key)} | {count} |")
    if rec.notes:
        out += ["", "### Notes", ""] + [f"- {n}" for n in rec.notes]
    return "\n".join(out)


def metadata_json(rec: Record, report: Report | None = None) -> str:
    payload = {
        "file": rec.file_path,
        "format": rec.file_format,
        "reader": rec.reader,
        "instrument_key": rec.instrument_key,
        "record": {k: to_dict(v) for k, v in {
            "image_name": rec.image_name, "specimen": rec.specimen, "stand": rec.stand,
            "objective": rec.objective, "light_sources": rec.light_sources,
            "detectors": rec.detectors, "channels": rec.channels,
            "acquisition": rec.acquisition, "software": rec.software,
            "extras": rec.extras,
        }.items()},
        "notes": rec.notes,
    }
    if report is not None:
        payload["checklist"] = {
            "completeness": round(report.completeness, 3),
            "missing": [q.path for q in report.blocking],
            "warnings": report.warnings,
            "rows": checklist_rows(rec),
        }
    return json.dumps(payload, indent=2, ensure_ascii=False, default=str)
