"""Build synthetic OME-TIFF fixtures and run the pipeline end to end.

Two fixtures:
  * a confocal-style OME-TIFF with a full instrument block (the good case)
  * a Blaze-style light-sheet OME-TIFF with a nearly empty instrument block
    and an Imspector-ish sidecar (the realistic case)

Run:  python tests/make_fixtures.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import tifffile

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

OUT = Path(__file__).resolve().parent / "fixtures"

RICH_OME = """<?xml version="1.0" encoding="UTF-8"?>
<OME xmlns="http://www.openmicroscopy.org/Schemas/OME/2016-06"
     Creator="ZEN 3.7">
  <Instrument ID="Instrument:0">
    <Microscope Manufacturer="Carl Zeiss Microscopy" Model="Axio Observer 7"
                Type="Inverted"/>
    <LightSource ID="LightSource:0" Manufacturer="Carl Zeiss Microscopy">
      <Laser Type="SolidState" Wavelength="488" WavelengthUnit="nm"/>
    </LightSource>
    <LightSource ID="LightSource:1" Manufacturer="Carl Zeiss Microscopy">
      <Laser Type="SolidState" Wavelength="561" WavelengthUnit="nm"/>
    </LightSource>
    <Detector ID="Detector:0" Manufacturer="Carl Zeiss Microscopy"
              Model="GaAsP-PMT1" Type="PMT"/>
    <Objective ID="Objective:0" Manufacturer="Carl Zeiss Microscopy"
               Model="Plan-Apochromat 63x/1.40 Oil DIC M27"
               NominalMagnification="63" LensNA="1.4" Immersion="Oil"
               Correction="PlanApo" WorkingDistance="190"
               WorkingDistanceUnit="um"/>
  </Instrument>
  <Image ID="Image:0" Name="cells_stack">
    <AcquisitionDate>2026-05-04T11:22:31</AcquisitionDate>
    <InstrumentRef ID="Instrument:0"/>
    <ObjectiveSettings ID="Objective:0" Medium="Oil" RefractiveIndex="1.518"/>
    <Pixels ID="Pixels:0" DimensionOrder="XYCZT" Type="uint16"
            SizeX="256" SizeY="256" SizeZ="12" SizeC="2" SizeT="1"
            PhysicalSizeX="0.065" PhysicalSizeXUnit="um"
            PhysicalSizeY="0.065" PhysicalSizeYUnit="um"
            PhysicalSizeZ="0.28" PhysicalSizeZUnit="um">
      <Channel ID="Channel:0" Name="EGFP" Fluor="mEGFP"
               IlluminationType="Epifluorescence"
               AcquisitionMode="LaserScanningConfocalMicroscopy"
               ExcitationWavelength="488" EmissionWavelength="509"
               PinholeSize="44.2" PinholeSizeUnit="um">
        <LightSourceSettings ID="LightSource:0" Attenuation="0.98"/>
        <DetectorSettings ID="Detector:0" Gain="750"/>
      </Channel>
      <Channel ID="Channel:1" Name="mScarlet" Fluor="mScarlet-I"
               IlluminationType="Epifluorescence"
               AcquisitionMode="LaserScanningConfocalMicroscopy"
               ExcitationWavelength="561" EmissionWavelength="592"
               PinholeSize="48.9" PinholeSizeUnit="um">
        <LightSourceSettings ID="LightSource:1" Attenuation="0.965"/>
        <DetectorSettings ID="Detector:0" Gain="800"/>
      </Channel>
      <TiffData/>
    </Pixels>
  </Image>
</OME>
"""

BLAZE_OME = """<?xml version="1.0" encoding="UTF-8"?>
<OME xmlns="http://www.openmicroscopy.org/Schemas/OME/2016-06"
     Creator="ImSpector 7.1.4">
  <Image ID="Image:0" Name="brain_UltraII[00 x 01]">
    <AcquisitionDate>2026-04-18T09:05:00</AcquisitionDate>
    <Pixels ID="Pixels:0" DimensionOrder="XYZCT" Type="uint16"
            SizeX="256" SizeY="256" SizeZ="8" SizeC="1" SizeT="1"
            PhysicalSizeX="1.21" PhysicalSizeXUnit="um"
            PhysicalSizeY="1.21" PhysicalSizeYUnit="um"
            PhysicalSizeZ="5.0" PhysicalSizeZUnit="um">
      <Channel ID="Channel:0" Name="561 nm" ExcitationWavelength="561"
               EmissionWavelength="620" SamplesPerPixel="1">
        <DetectorSettings ID="Detector:0" Binning="1x1"/>
      </Channel>
      <Plane TheZ="0" TheC="0" TheT="0" ExposureTime="120"
             ExposureTimeUnit="ms" PositionX="0" PositionY="0"/>
      <Plane TheZ="1" TheC="0" TheT="0" ExposureTime="120"
             ExposureTimeUnit="ms" PositionX="0" PositionY="0"/>
      <TiffData/>
    </Pixels>
  </Image>
</OME>
"""

SIDECAR = """[Image]
Sheet width = 60 %
Light sheet NA = 0.156
Left/Right sheet = both, blended
Dynamic horizontal focus = 5 steps
Zoom body = 4.0x
Laser power 561 = 30 %
Objective = LVMI-Fluar 12x/0.53
"""


def _write(path: Path, xml: str, shape=(8, 256, 256)) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = (np.random.default_rng(0).random(shape) * 1000).astype("uint16")
    tifffile.imwrite(str(path), data, description=xml, photometric="minisblack")
    return path


def build() -> tuple[Path, Path]:
    confocal = _write(OUT / "confocal_demo.ome.tif", RICH_OME, (24, 256, 256))
    blaze = _write(OUT / "blaze_demo.ome.tif", BLAZE_OME, (8, 256, 256))
    (OUT / "blaze_demo_MetaData.txt").write_text(SIDECAR)
    return confocal, blaze


if __name__ == "__main__":
    from micromethods import readers, render
    from micromethods import profiles as profile_store
    from micromethods.gaps import find_gaps

    confocal, blaze = build()
    for path in (confocal, blaze):
        print("=" * 78)
        print(path.name)
        print("=" * 78)
        record = readers.read(path)
        profile = profile_store.apply_best(record)
        report = find_gaps(record)
        print(f"instrument_key={record.instrument_key} profile="
              f"{profile.key if profile else None} "
              f"coverage={report.completeness * 100:.0f}%")
        print("\n--- methods text ---\n")
        print(render.methods_text(record))
        print("\n--- missing ---")
        for q in report.blocking:
            print(f"  {q.path}: {q.label}")
        for w in report.warnings:
            print(f"  ! {w}")
        print()
