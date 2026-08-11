# micromethods

Extract acquisition metadata from microscopy files, check it against the
QUAREP-LiMi WG11 **bare minimal microscopy reporting requirements checklist**,
ask the user for whatever the file does not contain, and write a methods
paragraph you can paste into a manuscript — plus a machine-readable sidecar.

Built so the same core can be driven by a CLI today and a napari plugin
tomorrow: extraction, checklist logic and rendering are shared, and the user
interface is only a `Prompter` implementation.

## Formats

| Format | Reader | Dependency |
|---|---|---|
| Zeiss `.czi` | `readers.czi` | `pylibCZIrw` (or `aicspylibczi`, or `czifile`) |
| Leica `.lif`, `.lof`, `.xlef` | `readers.lif` | `readlif>=0.6.5` |
| OME-TIFF (generic) | `readers.ometiff` | `tifffile` |
| Miltenyi Blaze (Imspector) | `readers.imspector` | `tifffile` |
| Bruker Ultima 2P (PrairieView) | `readers.prairieview` | none — companion XML |

Both vendor enrichments run automatically. The Blaze writes a nearly empty OME
`<Image>` block and puts the real metadata in `<StructuredAnnotations>` — a
`CustomAttributes` block plus several hundred `<prop fname=".."/>` entries.
That is where the objective, zoom body, laser line, emission filter, exposure,
laser power, clearing liquid, mosaic layout and light-sheet geometry live, and
it is parsed into the same Record as everything else. Sub-resolution pyramid
levels are recognised as such rather than treated as separate datasets.

The PrairieView reader runs automatically as an *enrichment* pass: PrairieView
keeps dwell time, zoom, objective, laser and PMT settings in a sibling
`.xml`/`.env` that does not survive conversion to OME-TIFF, so it is merged in
with `source = companion`.

## Install

Full instructions, including the napari plugin and troubleshooting, are in
[INSTALL.md](INSTALL.md).

```bash
# conda (recommended - brings napari and the Qt binding with it)
conda env create -f environment.yml
conda activate micromethods

# or headless, for servers and batch pipelines
conda env create -f environment-headless.yml

# or into an environment you already have
pip install -e ".[all]"          # everything
pip install -e ".[zeiss,leica]"  # only what your unit needs
```

napari only discovers plugins installed in its own environment, so install
micromethods and napari into the same one.

## Use

```bash
# read a file, fill the gaps interactively, write report + JSON next to it
micromethods report /data/experiment1.lif

# batch: no prompting, gaps stay marked [MISSING: ...]
micromethods report /data/stack.ome.tif --non-interactive -o ./reports

# supply answers from a file (CI, or one specimen imaged across many files)
micromethods report /data/stack.czi --answers specimen.yaml

# first time on a microscope: answer once, save it for everyone
micromethods report /data/stack.czi --save-profile lsm980_roomB12

# what does this vendor actually store?
micromethods inspect /data/stack.czi --grep pinhole
```

Exit code is `0` when every applicable required field is reported and `2`
when something is still missing — useful as a pre-submission check in a
data-deposition pipeline.

## Output

`<name>_methods.md` contains:

1. the methods paragraph, with anything unknown as an explicit
   `[MISSING: ...]` marker;
2. an acknowledgement template (the checklist asks you to credit the facility
   and instrument grants);
3. the filled checklist as a table, with the LiMi-model path for each field;
4. a provenance summary — how many fields came from the file, a profile, a
   derivation, or a human.

`<name>_metadata.json` is the same content in machine-readable form, with
per-field provenance, ready to attach to a BioImage Archive / OMERO deposit.

## Instrument profiles

Most checklist fields never change between experiments (stand model, camera,
software, objective barrel text). Write them down once per microscope:

```yaml
key: lsm980_roomB12
match:
  fingerprint_contains: [lsm 980]
values:
  stand.manufacturer: Carl Zeiss Microscopy
  stand.model: Axio Observer 7 with LSM 980
  stand.stand_type: inverted
  stand.modality: point-scanning confocal
  software.name: ZEN blue
channel_values:
  detector.manufacturer: Carl Zeiss Microscopy
```

An `overrides:` block replaces values the file itself supplies — the escape
hatch for vendor fields known to be wrong. Every override is recorded in the
report ("file said 0.1, profile says 0.35"), so a corrected value is never
silently substituted.

Profiles live in `micromethods/instrument_profiles/` (shipped) and
`~/.micromethods/profiles/` (yours, or `$MICROMETHODS_PROFILES`). A profile
**never** overwrites a value read from the file — precedence is
file > companion > user answer > derived > profile > default.

The two shipped profiles deliberately contain only what is true of *every*
Blaze / Ultima 2P; configuration-specific lines are commented out. Fill them
in from your instrument documentation rather than trusting a default: a
missing field is flagged in the report, a wrong one is not.

## Architecture

```
readers/*      file -> Record            (vendor-specific, the only messy part)
profiles.py    Record -> Record          (fills stable per-instrument fields)
checklist.py   the standard, as data     (paths, prompts, examples, LiMi alignment)
gaps.py        Record -> [Question]      (what is missing, what is inconsistent)
prompt.py      [Question] -> answers     (CLI / napari / answer file / nothing)
render.py      Record -> methods text, checklist table, JSON
```

Every value is a `Value(value, source, detail, unit)`. Nothing enters the
methods text without a recorded origin, and derived quantities (z range, total
acquisition time, pinhole in Airy units) say so.

### napari

`micromethods/_napari/` provides a dock widget that reads the file, builds a
form from exactly the same `Question` list the CLI would ask, and renders the
same report. Register it by installing with `[napari]`; the manifest is at
`micromethods/_napari/napari.yaml`.

## Validating against your own data

The OME-TIFF path is exercised by `tests/make_fixtures.py`; the CZI and LIF
XML walks by `tests/test_parsers.py` (both run without the proprietary
libraries). Vendor XML layouts drift between software versions, so before
trusting this on production data, run `micromethods inspect` on one real file
per instrument and compare the extracted values against the acquisition
software. Expect to adjust attribute names for:

- Leica: `ATLConfocalSettingDefinition` attributes differ between SP8,
  STELLARIS and THUNDER; widefield systems use `ATLCameraSettingDefinition`.
- Zeiss: `PinholeSizeAiry` is present on newer ZEN versions only; the fallback
  conversion from a physical diameter is flagged in the report.
- Blaze: property names are stable within an Imspector generation but not
  across them; the mapping lives in one table in `readers/imspector.py`.
  Note that `Blaze ObjectiveNA` frequently disagrees with the PSF calibration
  block in the same file — the tool reports the discrepancy rather than
  picking one, and a profile `overrides:` entry settles it permanently.

## Reference

Montero Llopis P. et al. *Better reporting is better science:
community-defined minimal reporting requirements for light microscopy*,
J Cell Biol (2026), doi:10.1083/jcb.202601032, and the accompanying checklist
(v2025-03-06). Image-publication guidance follows Schmied C. et al.,
Nat Methods 21:170–181 (2024), doi:10.1038/s41592-023-01987-9.
