"""Miltenyi Blaze OME-TIFF test.

The XML below is a well-formed reconstruction of a real Blaze file: the same
empty Image block, the same CustomAttributes annotation, and the subset of the
~700 <prop> entries that carry reportable metadata. Property names, values and
nesting are taken verbatim from an Imspector Pro 7.7.2 dataset.

Run:  python tests/test_blaze.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np                                    # noqa: E402
import tifffile                                       # noqa: E402

from micromethods import profiles as profile_store     # noqa: E402
from micromethods import readers, render               # noqa: E402
from micromethods.gaps import find_gaps                # noqa: E402
from micromethods.schema import raw                    # noqa: E402

OUT = Path(__file__).resolve().parent / "fixtures"

PROPS = [
    ("Blaze Objective", "LVBT 4x"),
    ("Blaze ObjectiveMagnification", "4.000000"),
    ("Blaze ObjectiveNA", "0.100000"),
    ("Blaze CurrentZoom", "0.600000"),
    ("Blaze SystemMagnification", "1.000000"),
    ("Blaze Liquid", "ECI"),
    ("Blaze LRI", "1.558000"),
    ("Blaze Liquids", "DBE;ECI;DilWater"),
    ("Blaze SelectedFilterIndex", "1"),
    ("Blaze CurWLExcitation", "640"),
    ("Blaze CurWLEmission", "680"),
    ("Blaze CurPower", "21"),
    ("Blaze ExtLaser", "1"),
    ("Blaze ExtLaserImpl", "Lasos Beamcombiner"),
    ("Blaze IndividualExpTimes", "1"),
    ("Blaze GlobalExpTime", "80.000000"),
    # configured channel table (only a few of the ten slots shown)
    ("Blaze LaserName0", "785"), ("Blaze ExWavelength0", "785"),
    ("Blaze EmWavelength0", "845"), ("Blaze ExpTime0", "100.000000"),
    ("Blaze AttenuatorPower0", "36"), ("Blaze ChanEmFilter0", "4"),
    ("Blaze LaserName1", "640"), ("Blaze ExWavelength1", "640"),
    ("Blaze EmWavelength1", "680"), ("Blaze ExpTime1", "20.099998"),
    ("Blaze AttenuatorPower1", "21"), ("Blaze ChanEmFilter1", "3"),
    ("Blaze LaserName2", "561"), ("Blaze ExWavelength2", "561"),
    ("Blaze EmWavelength2", "620"), ("Blaze ExpTime2", "50.000000"),
    ("Blaze AttenuatorPower2", "11"), ("Blaze ChanEmFilter2", "2"),
    # detection filter wheel
    ("Blaze dev8name", "Detection-FW"),
    ("Blaze dev8step0name", "460/40"), ("Blaze dev8step1name", "525/50"),
    ("Blaze dev8step2name", "620/60"), ("Blaze dev8step3name", "680/30"),
    ("Blaze dev8step4name", "845/55"), ("Blaze dev8step5name", "595/40"),
    ("Blaze dev8step6name", "empty2"),
    ("Blaze dev12name", "MagnificationChanger"),
    # light sheet
    ("Blaze NA", "0.059664"),
    ("Blaze SheetThickness", "6.110960"),
    ("Blaze SheetWidthPercent", "50.000000"),
    ("Blaze SelSheets", "Left and right light sheet"),
    ("Blaze SheetMergeAlg", "Fixed Blending"),
    ("Blaze ExBeamWaist", "3.600000"),
    ("Blaze HorzMode", "2"),
    ("Blaze DynFocusNumImages", "3"),
    ("Blaze ContinuousStackMode", "1"),
    ("Blaze SystemNA", "0.060000"),
    # camera
    ("Camera XBin", "1"), ("Camera YBin", "1"),
    ("Camera exp", "20.099998"),
    ("Camera SerialNumber", "61009704"),
    ("Camera FullXLen", "13312.000000"),
    ("Camera FullYLen", "13312.000000"),
    ("Camera ROIRight", "2048"),
    ("Blaze YRes", "2048"), ("Blaze XRes", "390"),
    # mosaic
    ("xyz-Table XRes", "11"), ("xyz-Table YRes", "3"),
    ("xyz-Table UserRequestedOverlapInPercent", "11"),
    ("xyz-Table XYOvl", "11.000000"),
    # PSF calibration block, trimmed but structurally identical
    ("Blaze LightSheetCalibration",
     '{"GENERAL": {"device_serialnumber": "UM-3095"}, '
     '"PSF": {"LVBT 4x": {"0.6": {"NA": 0.35, "isDefault": true}}}}'),
]


def _props_xml() -> str:
    # Property values can contain quotes and angle brackets (the calibration
    # block is embedded JSON, and the focus-offset block is embedded XML), so
    # real files escape them as attribute entities.
    from xml.sax.saxutils import escape

    def attr(text: str) -> str:
        return escape(str(text), {'"': "&quot;", "'": "&apos;"})

    rows = "\n".join(
        f'<prop Value="{attr(v)}" fname="{attr(k)}" label="{attr(k)}" '
        f'nId="524294" nTy="3"/>'
        for k, v in PROPS)
    return f'<Properties encoding="UTF-8">\n{rows}\n</Properties>'


BLAZE_OME = f"""<?xml version="1.0" encoding="UTF-8"?>
<OME xmlns="http://www.openmicroscopy.org/Schemas/OME/2016-06">
<Image ID="Image:0" Name="10-13-53_demo_Blaze_C00.ome.tif #1">
  <AcquisitionDate>2024-10-29T10:13:53</AcquisitionDate>
  <Description>not_specified</Description>
  <Pixels BigEndian="false" DimensionOrder="XYZCT" ID="Pixels:0" Interleaved="false"
          PhysicalSizeX="2.708333" PhysicalSizeXUnit="&#181;m"
          PhysicalSizeY="2.708333" PhysicalSizeYUnit="&#181;m"
          PhysicalSizeZ="5.0" PhysicalSizeZUnit="&#181;m"
          SignificantBits="16" SizeC="1" SizeT="1" SizeX="3886" SizeY="5701"
          SizeZ="1045" TimeIncrement="0.0" TimeIncrementUnit="s" Type="uint16">
    <Channel Color="-1" EmissionWavelength="680.0" EmissionWavelengthUnit="nm"
             ExcitationWavelength="640.0" ExcitationWavelengthUnit="nm"
             ID="Channel:0:0" Name="Ex: 640.000000nm Em: 680.000000nm"
             SamplesPerPixel="1"><LightPath/></Channel>
    <TiffData>
      <Plane PositionX="-17504.58" PositionXUnit="reference frame"
             PositionY="23596.05" PositionYUnit="reference frame"
             PositionZ="-1325.0" PositionZUnit="reference frame"
             TheC="0" TheT="0" TheZ="0"/>
    </TiffData>
  </Pixels>
  <AnnotationRef ID="Annotation:CustomAttributes1"/>
</Image>
<Image ID="Image:1" Name="10-13-53_demo_Blaze_C00.ome.tif #2">
  <Pixels BigEndian="false" DimensionOrder="XYZCT" ID="Pixels:1" Interleaved="false"
          SignificantBits="16" SizeC="1" SizeT="1" SizeX="1943" SizeY="2850"
          SizeZ="1045" Type="uint16">
    <Channel ID="Channel:1:0" SamplesPerPixel="1"><LightPath/></Channel>
    <MetadataOnly/>
  </Pixels>
</Image>
<Image ID="Image:2" Name="10-13-53_demo_Blaze_C00.ome.tif #3">
  <Pixels BigEndian="false" DimensionOrder="XYZCT" ID="Pixels:2" Interleaved="false"
          SignificantBits="16" SizeC="1" SizeT="1" SizeX="971" SizeY="1425"
          SizeZ="1045" Type="uint16">
    <Channel ID="Channel:2:0" SamplesPerPixel="1"><LightPath/></Channel>
    <MetadataOnly/>
  </Pixels>
</Image>
<StructuredAnnotations>
  <XMLAnnotation ID="Annotation:CustomAttributes1"><Value>
    <SerialNumber SerialNumber="UM-3095"/>
    <InstrumentMode InstrumentMode="Ultramicroscope Expert"/>
    <MeasurementMode MeasurementMode="Mosaic Acquisition"/>
    <ImspectorVersion ImspectorVersion="Imspector Pro 7.7.2"/>
    <ObjectiveID ObjectiveID="not_specified"/>
    <ObjectiveNA ObjectiveNA="not_specified"/>
    <ObjectiveMedium ObjectiveMedium="not_specified"/>
    <IsPartOfMosaic IsPartOfMosaic="1"/>
    <DataAxis2 AxisName="xyz-Table Z" Offset="1285" PhysicalUnit="5" Steps="1045"/>
  </Value></XMLAnnotation>
  <XMLAnnotation ID="Annotation:CustomAttributes2"><Value>
    {_props_xml()}
    <AlgorithmParameterSequence AlgorithmName="ImStitcher"
      AlgorithmParameters="RefChannel=0 WritePyramids=true"
      AlgorithmSource="Miltenyi Biotec B.V. &amp; Co. KG"
      AlgorithmVersion="4.5.0.240920-g0d05408e4a"
      SoftwareVersions="ImStitcher 4.5.0.240920-g0d05408e4a"/>
  </Value></XMLAnnotation>
</StructuredAnnotations>
</OME>
"""


def check(label, got, expected):
    ok = got == expected
    print(f"  {'PASS' if ok else 'FAIL'}  {label}: {got!r}"
          f"{'' if ok else f' (expected {expected!r})'}")
    return ok


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / "blaze_real.ome.tif"
    data = (np.random.default_rng(0).random((4, 64, 64)) * 1000).astype("uint16")
    tifffile.imwrite(str(path), data, description=BLAZE_OME, photometric="minisblack")

    rec = readers.read(path)
    profile = profile_store.apply_best(rec)
    report = find_gaps(rec)
    ch = rec.channels[0]

    print("\nMiltenyi Blaze OME-TIFF (Imspector annotations)")
    ok = all([
        check("instrument key", rec.instrument_key, "miltenyi_blaze"),
        check("profile", profile.key if profile else None, "miltenyi_blaze"),
        check("software", raw(rec.software.name), "Imspector Pro"),
        check("software version", raw(rec.software.version), "7.7.2"),
        check("serial number", raw(rec.extras["instrument"]["serial_number"]), "UM-3095"),
        check("modality", raw(rec.stand.modality),
              "light-sheet fluorescence microscopy"),
        check("objective", raw(rec.objective.designation), "LVBT 4x"),
        check("magnification", raw(rec.objective.magnification), 4.0),
        check("zoom body", raw(rec.stand.magnification_changer), "zoom body set to 0.6x"),
        check("immersion medium", raw(rec.objective.immersion_medium),
              "ethyl cinnamate (ECI)"),
        check("refractive index", raw(rec.objective.refractive_index), 1.558),
        check("pixel size", raw(rec.acquisition.pixel_size_x_um), 2.708333),
        check("z step", raw(rec.acquisition.z_step_um), 5.0),
        check("z range", raw(rec.acquisition.z_range_um), 5220.0),
        check("tiles", raw(rec.acquisition.tiles), 33),
        check("tile overlap", raw(rec.acquisition.tile_overlap_percent), 11.0),
        check("excitation", raw(ch.excitation_nm), 640.0),
        check("emission filter window", raw(ch.detection_range_nm), (665, 695)),
        check("filter name", raw(ch.filter_set), "680/30 bandpass emission filter"),
        check("exposure", raw(ch.exposure_time_ms), 20.099998),
        check("laser power", raw(ch.laser_power), 21.0),
        check("laser manufacturer", raw(ch.light_source.manufacturer),
              "Lasos beam combiner"),
        check("detector kind", raw(ch.detector.kind), "sCMOS camera"),
        check("binning", raw(ch.detector.binning), "1x1"),
        check("sheet NA", raw(rec.extras["lightsheet"]["sheet_na"]), 0.0597),
        check("sheet thickness", raw(rec.extras["lightsheet"]["sheet_thickness"]),
              6.111),
        check("sheet width", raw(rec.extras["lightsheet"]["sheet_width"]), 50.0),
        check("pyramid levels", raw(rec.extras["image_data"]["pyramid_levels"]), 3),
        check("stitching recorded",
              "ImStitcher" in str(raw(rec.extras["processing"]["steps"], "")), True),
    ])

    print("\n  --- methods text ---")
    print("  " + render.methods_text(rec).replace("\n", "\n  "))
    print(f"\n  coverage: {report.completeness * 100:.0f}%  "
          f"({len(report.blocking)} required field(s) missing)")
    for q in report.blocking:
        print(f"    missing: {q.path}")
    for note in rec.notes:
        print(f"    note: {note}")
    return 0 if ok else 1


if __name__ == "__main__":
    code = main()
    print("\nALL PASS" if code == 0 else "\nFAILURES PRESENT")
    raise SystemExit(code)
