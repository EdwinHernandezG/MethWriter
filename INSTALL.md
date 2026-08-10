# Installing micromethods with conda

Two things get installed: the `micromethods` command line tool, and — in the
same environment — **napari**, which is what makes the plugin usable. napari
only sees plugins installed into *its own* environment, so the order matters:
one environment, napari and micromethods both inside it.

---

## 0. Prerequisites

Any conda distribution works. [Miniforge](https://github.com/conda-forge/miniforge)
is the recommended one: it defaults to conda-forge (where napari lives) and
ships the fast `mamba` solver, which matters because the napari dependency
graph is large.

```bash
conda --version          # any recent conda
```

If you already use Anaconda/Miniconda, everything below works — just expect a
slower solve, and always pass `-c conda-forge`.

Anywhere you see `conda`, you can substitute `mamba` for speed.

---

## 1. Quick install (recommended)

From the repository root:

```bash
conda env create -f environment.yml
conda activate micromethods
```

That single file pins Python 3.11, pulls napari and its Qt binding from
conda-forge, installs the TIFF codecs, and finishes with a pip section for the
two vendor readers plus `micromethods` itself in editable mode.

> The `-e .` line in `environment.yml` is a *relative* path, so the
> `conda env create` command has to be run from the directory containing
> `pyproject.toml`.

For a server or batch pipeline that never needs a GUI, use the Qt-free
variant instead:

```bash
conda env create -f environment-headless.yml
conda activate micromethods-headless
```

---

## 2. Step-by-step install

Useful when you want to understand or vary what goes in — for example
installing only the readers your unit actually needs.

```bash
# 1. environment + interpreter
conda create -n micromethods -c conda-forge python=3.11
conda activate micromethods

# 2. core dependencies (always needed)
conda install -c conda-forge numpy "tifffile>=2023.7.10" imagecodecs "pyyaml>=6" lxml

# 3. napari and a Qt binding (needed for the plugin, not for the CLI)
conda install -c conda-forge "napari>=0.5" pyqt npe2

# 4. vendor readers - install only what you use
pip install "readlif>=0.6.5"      # Leica  .lif / .lof / .xlef
pip install "pylibCZIrw>=4.0"     # Zeiss  .czi
conda install -c conda-forge "ome-types>=0.4"   # optional, OME-XML validation

# 5. micromethods itself, from the repository root
pip install -e .
```

Bruker Ultima 2P needs nothing extra: its PrairieView companion XML is parsed
with the standard library. Miltenyi Blaze OME-TIFFs need only `tifffile` and
`imagecodecs`.

Use `pip install .` instead of `pip install -e .` if you do not intend to edit
the code. Editable is the better default while you are still tuning the vendor
attribute paths against your own files.

---

## 3. Verify the installation

### Command line

```bash
micromethods --help
micromethods profiles            # should list miltenyi_blaze and bruker_ultima_2p
python tests/test_parsers.py     # Zeiss + Leica XML parsing, no vendor libs needed
python tests/make_fixtures.py    # builds synthetic OME-TIFFs and reports on them
```

### Which readers are actually available

```bash
python - <<'PY'
for mod, fmt in [("tifffile", "OME-TIFF"), ("readlif", "Leica .lif"),
                 ("pylibCZIrw", "Zeiss .czi"), ("aicspylibczi", "Zeiss .czi (alt)"),
                 ("czifile", "Zeiss .czi (fallback)"), ("ome_types", "OME validation")]:
    try:
        __import__(mod)
        print(f"  available    {fmt:<24} ({mod})")
    except ImportError:
        print(f"  MISSING      {fmt:<24} ({mod})")
PY
```

A missing reader is not fatal — the tool raises a clear
`MissingDependency` message naming the package and the extra to install.

### napari plugin

```bash
npe2 list                        # 'micromethods' should appear
npe2 validate micromethods       # manifest check
napari                           # then: Plugins > Methods reporter
```

If `napari --info` does not mention micromethods, the two are almost certainly
in different environments — see troubleshooting below.

---

## 4. Facility-wide install

For a shared workstation or analysis server, put the environment in a shared
prefix and keep the instrument profiles under central control:

```bash
# one environment for everyone
conda env create -p /opt/conda/envs/micromethods -f environment.yml
conda activate /opt/conda/envs/micromethods

# curated, read-only instrument profiles maintained by the facility
export MICROMETHODS_PROFILES=/srv/imaging/micromethods-profiles
```

Set `MICROMETHODS_PROFILES` in `/etc/profile.d/` or the users' shell profile so
every report picks up the same, validated hardware descriptions. Users can
still answer anything the profile does not cover; only a facility manager
should be editing the profiles themselves.

To update the tool afterwards:

```bash
conda activate micromethods
git pull
pip install -e .                 # only needed if dependencies changed
conda env update -f environment.yml --prune
```

---

## 5. Troubleshooting

**`pylibCZIrw` has no wheel for my platform.**
Zeiss publishes wheels for a limited set of Python versions and platforms
(this is the usual failure on Apple Silicon and on very new Python releases).
Two fallbacks, both understood by the CZI reader without any code change:

```bash
pip install aicspylibczi lxml    # preferred fallback
pip install czifile              # pure Python, slower, older schema support
```

The reader tries pylibCZIrw, then aicspylibczi, then czifile, and only raises
if none is importable. If none installs, convert to OME-TIFF with Bio-Formats'
`bfconvert` and use the generic reader.

**The plugin does not appear in napari.**
Check both are in the same environment:

```bash
conda activate micromethods
python -c "import napari, micromethods; print(napari.__file__); print(micromethods.__file__)"
```

Both paths must sit under the same `envs/micromethods/` prefix. A common cause
is a system-wide `pip install napari` shadowing the conda one. Then restart
napari completely — plugin manifests are read at startup.

**`ImportError: DLL load failed` / `qt.qpa.plugin: could not load the Qt platform plugin`.**
The Qt binding is broken or missing. Reinstall it from conda-forge rather than
pip, and do not mix bindings in one environment:

```bash
conda install -c conda-forge --force-reinstall pyqt
```

On headless Linux (SSH, containers), a GUI cannot open at all — use the CLI, or
forward X11. `QT_QPA_PLATFORM=offscreen` only helps for automated tests.

**`No reader for '<file>'`.**
The extension is not one of `.czi`, `.lif`, `.lof`, `.xlef`, `.tif`, `.tiff`,
`.ome.tif`, `.ome.tiff`, `.ome.btf`. Convert with `bfconvert -no-upgrade in.nd2
out.ome.tiff`; the OME-TIFF path will then handle it, though vendor-specific
extras are lost in conversion.

**Compressed TIFF fails to open.**
`imagecodecs` is missing. It is in both environment files; install with
`conda install -c conda-forge imagecodecs`.

**Solving the environment takes forever.**
Use Miniforge/mamba, or add `-c conda-forge --strict-channel-priority`. Mixing
`defaults` and `conda-forge` for napari is the usual cause.

---

## 6. Uninstall

```bash
conda deactivate
conda env remove -n micromethods
rm -rf ~/.micromethods          # your locally saved instrument profiles
```
