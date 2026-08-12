"""Synthetic vendor metadata used by the test suite.

Every block here is a well-formed reconstruction of metadata seen in a real
file: an Imspector Pro 7.7.2 Blaze acquisition, a ZEN CZI metadata block and a
LAS X STELLARIS LIF header. Property names, values and nesting are verbatim;
only the pixel data is fake.

Kept separate from the test modules so the same fixtures can be reused, and so
pytest never imports a module whose name starts with `test_` just to read a
string constant.
"""

from __future__ import annotations

from pathlib import Path

def _escape_props(props) -> str:
    """Property values contain quotes and angle brackets (embedded JSON and
    XML), so real files escape them as attribute entities."""
    from xml.sax.saxutils import escape

    def attr(text: str) -> str:
        return escape(str(text), {'"': "&quot;", "'": "&apos;"})

    rows = "\n".join(
        f'<prop Value="{attr(v)}" fname="{attr(k)}" label="{attr(k)}" '
        f'nId="524294" nTy="3"/>'
        for k, v in props)
    return f'<Properties encoding="UTF-8">\n{rows}\n</Properties>'


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
    return _escape_props(PROPS)



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


LEGACY_BLAZE_OME = """<?xml version="1.0" encoding="UTF-8"?>
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



def write_tiff(path: Path, xml: str, shape=(4, 64, 64)) -> Path:
    """Write a TIFF whose ImageDescription is the given OME-XML.

    This is how the metadata reaches the reader in production too: inside the
    file, in TIFF tag 270. No sidecar is involved.
    """
    import numpy as np
    import tifffile

    path.parent.mkdir(parents=True, exist_ok=True)
    data = (np.random.default_rng(0).random(shape) * 1000).astype("uint16")
    tifffile.imwrite(str(path), data, description=xml, photometric="minisblack")
    return path


# --- OME 2008-02, as written by Imspector Pro on the UltraMicroscope Blaze ----
# Structure taken from a real 61 GB BigTIFF: the CA namespace instead of
# StructuredAnnotations, <LogicalChannel> as a sibling of <Pixels>, ExWave /
# EmWave instead of ExcitationWavelength / EmissionWavelength, and plane timing
# in a child element.
BLAZE_2008_OME = f"""<?xml version="1.0" encoding="UTF-8"?>
<OME xmlns="http://www.openmicroscopy.org/Schemas/OME/2008-02"
     xmlns:ca="http://www.openmicroscopy.org/Schemas/CA/2008-02"
     xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
<Image ID="Image:0" Name="10-13-53_spaomtest1_Blaze_C00.ome.tif"
       DefaultPixels="Pixels:0">
  <CreationDate>2024-10-29T10:13:53</CreationDate>
  <Description>not_specified</Description>
  <Pixels ID="Pixels:0" DimensionOrder="XYZCT" PixelType="Uint16"
          BigEndian="false" SizeX="3886" SizeY="5701" SizeZ="1045"
          SizeC="1" SizeT="1" PhysicalSizeX="2.708333" PhysicalSizeY="2.708333"
          PhysicalSizeZ="5.0" TimeIncrement="0.0">
    <TiffData/>
    <Plane TheZ="0" TheC="0" TheT="0">
      <PlaneTiming DeltaT="0.0" ExposureTime="0.0201"/>
      <StagePosition PositionX="-17504.58" PositionY="23596.05"
                     PositionZ="-1325.0"/>
    </Plane>
  </Pixels>
  <LogicalChannel ID="LogicalChannel:0"
                  Name="Ex: 640.000000nm Em: 680.000000nm"
                  ExWave="640" EmWave="680" SamplesPerPixel="1">
    <ChannelComponent Pixels="Pixels:0" Index="0" ColorDomain="none"/>
  </LogicalChannel>
</Image>
<ca:CustomAttributes>
  <SerialNumber SerialNumber="UM-3095"/>
  <InstrumentMode InstrumentMode="Ultramicroscope Expert"/>
  <MeasurementMode MeasurementMode="Mosaic Acquisition"/>
  <ImspectorVersion ImspectorVersion="Imspector Pro 7.7.2"/>
  <ObjectiveID ObjectiveID="not_specified"/>
  <ObjectiveNA ObjectiveNA="not_specified"/>
  {_escape_props(PROPS)}
  <AlgorithmParameterSequence AlgorithmName="ImStitcher"
    AlgorithmParameters="RefChannel=0 WritePyramids=true"
    AlgorithmSource="Miltenyi Biotec B.V. &amp; Co. KG"
    AlgorithmVersion="4.5.0.240920-g0d05408e4a"
    SoftwareVersions="ImStitcher 4.5.0.240920-g0d05408e4a"/>
</ca:CustomAttributes>
</OME>
"""


# --- A real two-colour Blaze mosaic (Imspector Pro 8.0.3, OME 2016-06) -------
# Properties copied verbatim from an acquisition on UM-3140. Two points of
# interest: the <Channel> elements are bare (no wavelengths at all, despite
# SizeC=2), and 'UserRequestedOverlapInPercent' holds uninitialised memory
# while the per-axis properties carry the real 10%.
BLAZE_TWOCOLOUR_PROPS = [
    ('Blaze AttenuatorPower0', '21'),
    ('Blaze AttenuatorPower1', '55'),
    ('Blaze AttenuatorPower2', '10'),
    ('Blaze AttenuatorPower3', '20'),
    ('Blaze AttenuatorPower4', '13'),
    ('Blaze AttenuatorPower5', '1'),
    ('Blaze AttenuatorPower6', '9'),
    ('Blaze AttenuatorPower7', '43'),
    ('Blaze AttenuatorPower8', '43'),
    ('Blaze AttenuatorPower9', '43'),
    ('Blaze ChanEmFilter0', '4'),
    ('Blaze ChanEmFilter1', '3'),
    ('Blaze ChanEmFilter2', '2'),
    ('Blaze ChanEmFilter3', '1'),
    ('Blaze ChanEmFilter4', '0'),
    ('Blaze ChanEmFilter5', '5'),
    ('Blaze ChanEmFilter6', '6'),
    ('Blaze ChanEmFilter7', '2'),
    ('Blaze ChanEmFilter8', '2'),
    ('Blaze ChanEmFilter9', '2'),
    ('Blaze ChromCorrWithTurret', '1'),
    ('Blaze ContinuousStackMode', '0'),
    ('Blaze CurPower', '20'),
    ('Blaze CurWLEmission', '595'),
    ('Blaze CurWLExcitation', '561'),
    ('Blaze CurrentZoom', '1.000000'),
    ('Blaze DynFocusNumImages', '4'),
    ('Blaze EmWavelength0', '805'),
    ('Blaze EmWavelength1', '680'),
    ('Blaze EmWavelength2', '595'),
    ('Blaze EmWavelength3', '525'),
    ('Blaze EmWavelength4', '460'),
    ('Blaze EmWavelength5', '561'),
    ('Blaze EmWavelength6', '785'),
    ('Blaze EmWavelength7', '620'),
    ('Blaze EmWavelength8', '620'),
    ('Blaze EmWavelength9', '620'),
    ('Blaze ExBeamWaist', '3.600000'),
    ('Blaze ExWavelength0', '785'),
    ('Blaze ExWavelength1', '640'),
    ('Blaze ExWavelength2', '561'),
    ('Blaze ExWavelength3', '488'),
    ('Blaze ExWavelength4', '405'),
    ('Blaze ExWavelength5', '561'),
    ('Blaze ExWavelength6', '785'),
    ('Blaze ExWavelength7', '561'),
    ('Blaze ExWavelength8', '561'),
    ('Blaze ExWavelength9', '561'),
    ('Blaze ExpTime0', '100.000000'),
    ('Blaze ExpTime1', '149.999176'),
    ('Blaze ExpTime2', '100.000000'),
    ('Blaze ExpTime3', '149.999176'),
    ('Blaze ExpTime4', '100.000000'),
    ('Blaze ExpTime5', '100.000000'),
    ('Blaze ExpTime6', '100.000000'),
    ('Blaze ExpTime7', '100.000000'),
    ('Blaze ExpTime8', '100.000000'),
    ('Blaze ExpTime9', '100.000000'),
    ('Blaze ExtLaser', '1'),
    ('Blaze ExtLaserImpl', 'Laser combiner'),
    ('Blaze FilterInMeasurement0', '0'),
    ('Blaze FilterInMeasurement1', '0'),
    ('Blaze FilterInMeasurement2', '1'),
    ('Blaze FilterInMeasurement3', '1'),
    ('Blaze FilterInMeasurement4', '0'),
    ('Blaze FilterInMeasurement5', '0'),
    ('Blaze FilterInMeasurement6', '0'),
    ('Blaze FilterInMeasurement7', '0'),
    ('Blaze FilterInMeasurement8', '0'),
    ('Blaze FilterInMeasurement9', '0'),
    ('Blaze GlobalExpTime', '150.014008'),
    ('Blaze HorzMode', '2'),
    ('Blaze IndividualExpTimes', '0'),
    ('Blaze LRI', '1.558000'),
    ('Blaze LaserName0', '785'),
    ('Blaze LaserName1', '640'),
    ('Blaze LaserName2', '561'),
    ('Blaze LaserName3', '488'),
    ('Blaze LaserName4', '405'),
    ('Blaze LaserName5', '561'),
    ('Blaze LaserName6', '785'),
    ('Blaze LaserName7', '561'),
    ('Blaze LaserName8', '561'),
    ('Blaze LaserName9', '561'),
    ('Blaze Liquid', 'MACS IS'),
    ('Blaze Liquids', 'CUBIC R2;DBE;ECi;H2O;MACS IS;Milk'),
    ('Blaze NA', '0.162765'),
    ('Blaze Objective', 'LVBT 4x'),
    ('Blaze ObjectiveMagnification', '4.000000'),
    ('Blaze ObjectiveNA', '0.350000'),
    ('Blaze PowerInfo0', '21'),
    ('Blaze PowerInfo1', '55'),
    ('Blaze PowerInfo2', '10'),
    ('Blaze PowerInfo3', '20'),
    ('Blaze PowerInfo4', '13'),
    ('Blaze PowerInfo5', '1'),
    ('Blaze PowerInfo6', '9'),
    ('Blaze PowerInfo7', '43'),
    ('Blaze PowerInfo8', '43'),
    ('Blaze PowerInfo9', '43'),
    ('Blaze SelSheets', 'Right light sheet'),
    ('Blaze SelectedFilterIndex', '3'),
    ('Blaze SheetMergeAlg', 'Adaptive Blending'),
    ('Blaze SheetThickness', '3.912724'),
    ('Blaze SheetWidthPercent', '100.000000'),
    ('Blaze XRes', '2048'),
    ('Blaze YRes', '2048'),
    ('Blaze dev12name', 'MagnificationChanger'),
    ('Blaze dev8name', 'Detection-FW'),
    ('Blaze dev8step0name', '460/40'),
    ('Blaze dev8step1name', '525/50'),
    ('Blaze dev8step2name', '620/60'),
    ('Blaze dev8step3name', '680/30'),
    ('Blaze dev8step4name', '805LP'),
    ('Blaze dev8step5name', 'empty'),
    ('Blaze dev8step6name', 'empty'),
    ('Blaze dev8step7name', 'Position_7'),
    ('Blaze dev8step8name', 'Position_8'),
    ('Blaze dev8step9name', 'Position_9'),
    ('Camera FullXLen', '13312.000000'),
    ('Camera Info', 'Camera: pco.edge 4.2 M CLHS rolling shutter (s/n: 61010487)  Hardware 00: (MAIN 0015001730) 0.19 [variant: 20] Hardware 01: (HEAD 0013208441) 1.01 [variant: 6] Hardware 02: (IF   0010301716) 2.03 [variant: 1]  Firmware 00: (LADRA) 2.42 [variant: 20] Firmware 01: (MIDIR) 1.30 [variant: 20] Firmware 02: (CAMAL) 0.22 [variant: 20] Firmware 03: (LODAN) 0.11 [variant: 20] Firmware 04: (DAGDA) 1.02 [variant: 20] Firmware 05: (BRESS) 1.00 [variant: 20] Firmware 06: (NUADA) 1.00 [variant: 20] Firmware 07: (KRIOS) 1.00 [variant: 20] '),
    ('Camera ROIRight', '2048'),
    ('Camera SerialNumber', '61010487'),
    ('Camera XBin', '1'),
    ('Camera YBin', '1'),
    ('Camera exp', '150.017990'),
    ('xyz-Table UserRequestedOverlapInPercent', '1092616192'),
    ('xyz-Table UserRequestedOverlapInPercentX', '10.000000'),
    ('xyz-Table UserRequestedOverlapInPercentY', '10.000000'),
    ('xyz-Table XRes', '2'),
    ('xyz-Table XYOvl', '10.000000'),
    ('xyz-Table YRes', '2'),
]

BLAZE_TWOCOLOUR_OME = f"""<?xml version="1.0" encoding="UTF-8"?>
<OME xmlns="http://www.openmicroscopy.org/Schemas/OME/2016-06">
<Image ID="Image:0" Name="11-14-17_Alg_tl_4X_1Z_2Colormosaic_Blaze[00 x 00]_C00.ome.tif">
  <AcquisitionDate>2026-08-12T11:13:16</AcquisitionDate>
  <Description>not_specified</Description>
  <Pixels BigEndian="false" DimensionOrder="XYZCT" ID="Pixels:0" Interleaved="false"
          PhysicalSizeX="1.625" PhysicalSizeXUnit="&#181;m"
          PhysicalSizeY="1.625" PhysicalSizeYUnit="&#181;m"
          PhysicalSizeZ="2.0" PhysicalSizeZUnit="&#181;m"
          SignificantBits="16" SizeC="2" SizeT="1" SizeX="2048" SizeY="2048"
          SizeZ="12" Type="uint16">
    <Channel ID="Channel:0:0" SamplesPerPixel="1"><LightPath/></Channel>
    <Channel ID="Channel:0:1" SamplesPerPixel="1"><LightPath/></Channel>
    <TiffData FirstC="0" FirstZ="0"/>
  </Pixels>
  <AnnotationRef ID="Annotation:CustomAttributes1"/>
</Image>
<StructuredAnnotations>
  <XMLAnnotation ID="Annotation:CustomAttributes1"><Value>
    <SerialNumber SerialNumber="UM-3140"/>
    <InstrumentMode InstrumentMode="Ultramicroscope Expert"/>
    <MeasurementMode MeasurementMode="Multi Color Mosaic Acquisition"/>
    <ImspectorVersion ImspectorVersion="Imspector Pro 8.0.3"/>
  </Value></XMLAnnotation>
  <XMLAnnotation ID="Annotation:CustomAttributes2"><Value>
    {_escape_props(BLAZE_TWOCOLOUR_PROPS)}
  </Value></XMLAnnotation>
</StructuredAnnotations>
</OME>
"""
