#!/usr/bin/env python3
"""Report exactly what metadata is inside an OME-TIFF, and what the reader sees.

Standalone apart from tifffile, so it works even if micromethods is not
installed. Run it on the file that produced a disappointing report:

    python tools/inspect_ome.py "C:\\path\\to\\file.ome.tif"

It answers, in order:
  * how many TIFF pages there are, and which of them carry a description;
  * how big the OME-XML in tag 270 is, and whether it is well-formed;
  * how many <Image>, <Channel>, <StructuredAnnotations> and <prop> elements
    it contains, with sample property names;
  * whether any *other* page carries the annotation block;
  * what a sibling file or a BinaryOnly reference points to;
  * finally, what micromethods extracts, if it is importable.

Add --dump-xml to write the raw XML next to the file for inspection.
"""

from __future__ import annotations

import argparse
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

LINE = "-" * 72


def section(title: str) -> None:
    print(f"\n{title}\n{LINE}")


def local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def describe_xml(text: str, label: str) -> dict:
    """Parse and summarise one XML blob."""
    print(f"{label}: {len(text):,} characters")
    head = text[:160].replace("\n", " ")
    print(f"  starts: {head}")
    print(f"  ends:   ...{text[-120:].replace(chr(10), ' ')}")
    for marker in ("<StructuredAnnotations", "<XMLAnnotation", "<prop ",
                   "<Channel", "<BinaryOnly", "CustomAttributes", "Imspector"):
        print(f"  contains {marker:<24} {marker in text}")

    try:
        root = ET.fromstring(text.encode("utf-8", "ignore"))
    except ET.ParseError as exc:
        print(f"  XML IS NOT WELL FORMED: {exc}")
        return {}
    counts = Counter(local(e.tag) for e in root.iter())
    print(f"  root element: {local(root.tag)}")
    interesting = ["Image", "Pixels", "Channel", "Plane", "TiffData",
                   "StructuredAnnotations", "XMLAnnotation", "Value", "prop",
                   "AnnotationRef", "Instrument", "Objective", "Detector",
                   "AlgorithmParameterSequence", "BinaryOnly"]
    for name in interesting:
        if counts.get(name):
            print(f"  {name:<28} {counts[name]}")
    missing = [n for n in ("Channel", "StructuredAnnotations", "prop")
               if not counts.get(n)]
    if missing:
        print(f"  ABSENT: {', '.join(missing)}")

    props = [e for e in root.iter() if local(e.tag) == "prop"]
    if props:
        names = [p.get("fname") or p.get("label") or "?" for p in props]
        print(f"  sample property names: {', '.join(names[:8])}")
        for wanted in ("Blaze Objective", "Blaze ObjectiveNA", "Blaze NA",
                       "Blaze SelectedFilterIndex", "Blaze ExpTime1"):
            hit = next((p for p in props
                        if (p.get("fname") or "") == wanted), None)
            print(f"    {wanted:<28} {hit.get('Value') if hit is not None else 'absent'}")
    return counts


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("path")
    parser.add_argument("--dump-xml", action="store_true",
                        help="write the OME-XML next to the file")
    parser.add_argument("--pages", type=int, default=8,
                        help="how many pages to scan for descriptions")
    args = parser.parse_args()

    path = Path(args.path).expanduser()
    if not path.exists():
        print(f"error: no such file: {path}", file=sys.stderr)
        return 1

    try:
        import tifffile
    except ImportError:
        print("error: tifffile is required (pip install tifffile)", file=sys.stderr)
        return 1

    section("1. File")
    print(f"path        {path}")
    print(f"size        {path.stat().st_size:,} bytes")
    print(f"tifffile    {tifffile.__version__}")

    section("2. TIFF structure")
    descriptions: dict[int, str] = {}
    with tifffile.TiffFile(str(path)) as tif:
        print(f"pages       {len(tif.pages)}")
        print(f"series      {len(tif.series)}")
        print(f"is_ome      {tif.is_ome}")
        print(f"is_bigtiff  {tif.is_bigtiff}")
        for index, page in enumerate(tif.pages[:args.pages]):
            tag = page.tags.get("ImageDescription") if hasattr(page, "tags") else None
            if tag is not None and isinstance(tag.value, str):
                descriptions[index] = tag.value
                flag = " <- has annotations" if "<prop " in tag.value else ""
                print(f"  page {index}: description {len(tag.value):,} chars{flag}")
            else:
                print(f"  page {index}: no description")
        ome = tif.ome_metadata

    section("3. OME-XML as the reader receives it")
    if not ome:
        print("tifffile.ome_metadata is None — the reader would fall back to a "
              "companion file.")
    else:
        describe_xml(ome, "tag 270 / ome_metadata")
        if args.dump_xml:
            out = path.with_suffix(".extracted.ome.xml")
            out.write_text(ome, encoding="utf-8")
            print(f"  written to {out}")

    others = {i: d for i, d in descriptions.items() if d != ome and "<prop " in d}
    if others:
        section("4. Annotations found on another page")
        for index, text in others.items():
            describe_xml(text, f"page {index}")
    else:
        section("4. Annotations on other pages")
        print("none")

    section("5. Neighbouring files")
    siblings = [p for p in sorted(path.parent.iterdir())
                if p != path and p.is_file()][:12]
    if siblings:
        for sibling in siblings:
            print(f"  {sibling.name}")
    else:
        print("  none — the file is alone in its folder")

    section("6. What micromethods extracts")
    try:
        from micromethods import readers
        from micromethods.gaps import find_gaps
        from micromethods.schema import raw

        rec = readers.read(path)
        print(f"instrument_key      {rec.instrument_key}")
        print(f"vendor_raw keys     {sorted(rec.vendor_raw)}")
        print(f"custom attributes   "
              f"{len(rec.vendor_raw.get('custom_attributes', {}))}")
        print(f"vendor properties   "
              f"{len(rec.vendor_raw.get('vendor_properties', {}))}")
        print(f"channels            {len(rec.channels)}")
        if rec.channels:
            channel = rec.channels[0]
            print(f"  excitation        {raw(channel.excitation_nm)}")
            print(f"  emission          {raw(channel.emission_nm)}")
        print(f"objective           {raw(rec.objective.designation)} "
              f"{raw(rec.objective.magnification)}x NA {raw(rec.objective.na)}")
        print(f"software            {raw(rec.software.name)} "
              f"{raw(rec.software.version)}")
        print(f"coverage            {find_gaps(rec).completeness * 100:.0f}%")
        for note in rec.notes:
            print(f"  note: {note}")
    except ImportError:
        print("micromethods is not importable here; skipping.")
    except Exception as exc:
        print(f"reader raised {type(exc).__name__}: {exc}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
