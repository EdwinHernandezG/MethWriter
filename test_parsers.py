"""Vendor XML parsing tests that do not need the proprietary reader libraries.

The CZI and LIF readers are split so that the XML walk can be tested with
representative metadata blocks; only the *retrieval* of that XML depends on
pylibCZIrw / readlif.
"""

import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from micromethods.readers import czi, lif           # noqa: E402
from micromethods.schema import Record, raw          # noqa: E402
from micromethods.gaps import find_gaps              # noqa: E402
from micromethods import render                      # noqa: E402

CZI_XML = """<ImageDocument><Metadata>
 <Information>
  <Application><Name>ZEN (blue edition)</Name><Version>3.9.023</Version></Application>
  <Image>
    <SizeX>1024</SizeX><SizeY>1024</SizeY><SizeZ>21</SizeZ><SizeC>2</SizeC><SizeT>1</SizeT>
    <ComponentBitCount>16</ComponentBitCount>
    <AcquisitionDateAndTime>2026-03-11T14:02:11</AcquisitionDateAndTime>
    <Dimensions><Channels>
      <Channel Id="Channel:0" Name="EGFP">
        <ExcitationWavelength>488</ExcitationWavelength>
        <EmissionWavelength>509</EmissionWavelength>
        <AcquisitionMode>LaserScanningConfocalMicroscopy</AcquisitionMode>
        <PinholeSizeAiry>1.02</PinholeSizeAiry>
        <PinholeSize>4.4e-05</PinholeSize>
        <DetectionWavelength><Ranges>493-556</Ranges></DetectionWavelength>
        <DetectorSettings><Detector Id="Detector:1"/><Gain>750</Gain></DetectorSettings>
        <LightSourcesSettings><LightSourceSettings>
          <Wavelength>488</Wavelength><Intensity>2.0 %</Intensity>
        </LightSourceSettings></LightSourcesSettings>
      </Channel>
      <Channel Id="Channel:1" Name="mCherry">
        <ExcitationWavelength>561</ExcitationWavelength>
        <EmissionWavelength>610</EmissionWavelength>
        <AcquisitionMode>LaserScanningConfocalMicroscopy</AcquisitionMode>
        <PinholeSizeAiry>1.02</PinholeSizeAiry>
        <DetectionWavelength><Ranges>570-650</Ranges></DetectionWavelength>
        <DetectorSettings><Detector Id="Detector:2"/><Gain>800</Gain></DetectorSettings>
      </Channel>
    </Channels></Dimensions>
  </Image>
  <Instrument>
    <Microscopes><Microscope Id="Microscope:1" Name="LSM 980">
      <Type>Inverted</Type></Microscope></Microscopes>
    <Objectives><Objective Id="Objective:1" Name="Plan-Apochromat 63x/1.40 Oil DIC M27">
      <LensNA>1.4</LensNA><NominalMagnification>63</NominalMagnification>
      <Immersion>Oil</Immersion><Correction>PlanApo</Correction>
      <Manufacturer><Manufacturer>Carl Zeiss</Manufacturer>
      <Model>420782-9900-799</Model></Manufacturer>
    </Objective></Objectives>
    <Detectors>
      <Detector Id="Detector:1" Name="GaAsP-PMT1"><Type>Pmt</Type></Detector>
      <Detector Id="Detector:2" Name="GaAsP-PMT2"><Type>Pmt</Type></Detector>
    </Detectors>
    <LightSources>
      <LightSource Id="LightSource:1"><LightSourceType><Laser>
        <Wavelength>488</Wavelength></Laser></LightSourceType></LightSource>
      <LightSource Id="LightSource:2"><LightSourceType><Laser>
        <Wavelength>561</Wavelength></Laser></LightSourceType></LightSource>
    </LightSources>
  </Instrument>
 </Information>
 <Scaling><Items>
   <Distance Id="X"><Value>6.5e-08</Value></Distance>
   <Distance Id="Y"><Value>6.5e-08</Value></Distance>
   <Distance Id="Z"><Value>2.8e-07</Value></Distance>
 </Items></Scaling>
 <Experiment><AcquisitionBlock>
   <LaserScanInfo><PixelTime>2.06e-06</PixelTime><Averaging>2</Averaging>
     <ZoomX>1.8</ZoomX></LaserScanInfo>
   <MultiChannelMode>Sequential</MultiChannelMode>
 </AcquisitionBlock></Experiment>
</Metadata></ImageDocument>"""

LIF_XML = """<Element Name="Series012">
 <Data><Image>
  <ImageDescription>
   <Dimensions>
    <DimensionDescription DimID="1" NumberOfElements="1024" Length="1.1638e-04" Unit="m"/>
    <DimensionDescription DimID="2" NumberOfElements="1024" Length="1.1638e-04" Unit="m"/>
    <DimensionDescription DimID="3" NumberOfElements="31" Length="9.0e-06" Unit="m"/>
   </Dimensions>
   <Channels>
    <ChannelDescription Resolution="8" ChannelName="Ch1" LUTName="Green"/>
    <ChannelDescription Resolution="8" ChannelName="Ch2" LUTName="Red"/>
   </Channels>
  </ImageDescription>
  <Attachment Name="HardwareSetting">
   <ATLConfocalSettingDefinition ObjectiveName="HC PL APO CS2 63x/1.40 OIL"
     NumericalAperture="1.4" Magnification="63" RefractionIndex="1.518"
     Pinhole="0.0000895" PinholeAiry="1.0" ScanSpeed="400" Zoom="2.0"
     SystemTypeName="STELLARIS 8" SoftwareVersion="4.5.0.25531" Line_Average="4">
    <LaserArray><Laser LaserName="Diode 405" Wavelength="405"/>
      <Laser LaserName="White light laser" Wavelength="488"/></LaserArray>
    <AotfList><Aotf>
      <LaserLineSetting LaserLine="488" IntensityDev="2.5"/>
      <LaserLineSetting LaserLine="552" IntensityDev="4.0"/>
    </Aotf></AotfList>
    <DetectorList>
      <Detector Name="HyD S 1" Type="HyD" Gain="100" IsActive="1"/>
      <Detector Name="HyD X 2" Type="HyD" Gain="150" IsActive="1"/>
    </DetectorList>
    <Spectro>
      <MultiBand LeftWorld="498" RightWorld="545" ChannelName="Ch1" DyeName="Alexa 488"/>
      <MultiBand LeftWorld="560" RightWorld="630" ChannelName="Ch2" DyeName="Alexa 555"/>
    </Spectro>
   </ATLConfocalSettingDefinition>
  </Attachment>
  <Attachment Name="TileScanInfo" OverlapPercentageX="0.1"/>
 </Image></Data>
</Element>"""


def check(label, got, expected):
    ok = got == expected
    print(f"  {'PASS' if ok else 'FAIL'}  {label}: {got!r}"
          f"{'' if ok else f' (expected {expected!r})'}")
    return ok


def test_czi():
    print("\nZeiss CZI metadata block")
    rec = Record(file_format="CZI (Zeiss)")
    czi._parse(ET.fromstring(CZI_XML), rec)
    ok = all([
        check("stand model", raw(rec.stand.model), "LSM 980"),
        check("stand type", raw(rec.stand.stand_type), "inverted"),
        check("modality", raw(rec.stand.modality), "point-scanning confocal"),
        check("objective NA", raw(rec.objective.na), 1.4),
        check("magnification", raw(rec.objective.magnification), 63.0),
        check("immersion", raw(rec.objective.immersion), "oil"),
        check("pixel size x", raw(rec.acquisition.pixel_size_x_um), 0.065),
        check("z step", raw(rec.acquisition.z_step_um), 0.28),
        check("z range", raw(rec.acquisition.z_range_um), 5.6),
        check("pixel dwell", raw(rec.acquisition.pixel_dwell_us), 2.06),
        check("averaging", raw(rec.acquisition.line_averaging), 2),
        check("channel mode", raw(rec.acquisition.channel_mode), "sequential"),
        check("channels", len(rec.channels), 2),
        check("ch0 pinhole AU", raw(rec.channels[0].pinhole_au), 1.02),
        check("ch0 window", raw(rec.channels[0].detection_range_nm), (493, 556)),
        check("ch1 detector", raw(rec.channels[1].detector.model), "GaAsP-PMT2"),
        check("software", raw(rec.software.version), "3.9.023"),
    ])
    print("\n  --- methods text ---")
    print("  " + render.methods_text(rec).replace("\n", "\n  "))
    print(f"  coverage: {find_gaps(rec).completeness * 100:.0f}%")
    return ok


def test_lif():
    print("\nLeica LIF metadata block")
    rec = Record(file_format="Leica LIF")
    lif._parse(ET.fromstring(LIF_XML), rec)
    ok = all([
        check("system", raw(rec.stand.model), "STELLARIS 8"),
        check("modality", raw(rec.stand.modality), "point-scanning confocal"),
        check("objective NA", raw(rec.objective.na), 1.4),
        check("immersion", raw(rec.objective.immersion), "oil"),
        check("refractive index", raw(rec.objective.refractive_index), 1.518),
        check("pixel size x", raw(rec.acquisition.pixel_size_x_um), 0.113763),
        check("z step", raw(rec.acquisition.z_step_um), 0.3),
        check("z range", raw(rec.acquisition.z_range_um), 9.0),
        check("channels", len(rec.channels), 2),
        check("ch0 window", raw(rec.channels[0].detection_range_nm), (498, 545)),
        check("ch0 dye", raw(rec.channels[0].fluorophore), "Alexa 488"),
        check("ch1 detector", raw(rec.channels[1].detector.kind),
              "HyD hybrid detector"),
        check("pinhole AU", raw(rec.channels[0].pinhole_au), 1.0),
        check("laser lines", sorted(raw(ls.wavelength_nm) for ls in rec.light_sources),
              [488, 552]),
        check("tile overlap", raw(rec.acquisition.tile_overlap_percent), 10.0),
        check("software version", raw(rec.software.version), "4.5.0.25531"),
    ])
    print("\n  --- methods text ---")
    print("  " + render.methods_text(rec).replace("\n", "\n  "))
    print(f"  coverage: {find_gaps(rec).completeness * 100:.0f}%")
    return ok


if __name__ == "__main__":
    results = [test_czi(), test_lif()]
    print("\nALL PASS" if all(results) else "\nFAILURES PRESENT")
    raise SystemExit(0 if all(results) else 1)
