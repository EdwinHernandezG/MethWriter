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

Two steps, on purpose. The environment file installs the *dependencies*;
micromethods itself is installed separately so that any packaging error shows
you the real message instead of a generic `CondaEnvException: Pip failed`.

```bash
cd <folder that contains pyproject.toml>

conda env create -f environment.yml
conda activate micromethods

python -m pip install -e .

# confirm the code, not just the metadata, was installed
python -c "import micromethods; print(micromethods.__file__)"
```

That last check matters: `pip install -e .` run from the wrong directory can
report success while installing nothing importable. The path it prints must
point into your project folder.

The environment file pins Python 3.11, pulls napari and its Qt binding from
conda-forge, installs the TIFF codecs, and adds the two vendor readers.

For a server or batch pipeline that never needs a GUI, use the Qt-free
variant instead:

```bash
conda env create -f environment-headless.yml
conda activate micromethods-headless
python -m pip install -e .
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

**napari logs `'micromethods' could not be imported: No module named 'micromethods'`.**
The distribution metadata is installed (napari found the entry point) but the
package itself is not — `pip install -e .` was run from a directory that does
not contain the `micromethods/` package folder. Check where the install points:

```bash
conda activate micromethods
pip show micromethods            # look at "Editable project location"
python -c "import micromethods; print(micromethods.__file__)"
```

Reinstall from the folder that holds `pyproject.toml` **and** `micromethods/`
side by side:

```bash
pip uninstall -y micromethods
cd <that folder>
python -m pip install -e .
python -c "import micromethods; print(micromethods.__file__)"
```

Then restart napari; manifests are only read at startup.

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

**`napari support for the PyQt5 backend is deprecated` / `System theme detection requires a Qt6 backend`.**
Both are warnings, not errors — napari runs fine on PyQt5 today, but support
ends in autumn 2026. Move the environment to Qt6:

```bash
conda activate micromethods
conda install -c conda-forge pyside6
conda remove pyqt qt-main --force      # avoid two bindings in one environment
```

conda-forge ships PySide6 but not PyQt6, so PySide6 is the Qt6 route here.
Never leave two Qt bindings installed at once; napari picks one at random and
the symptoms are baffling.

On headless Linux (SSH, containers), a GUI cannot open at all — use the CLI, or
forward X11. `QT_QPA_PLATFORM=offscreen` only helps for automated tests.

**`CondaEnvException: Pip failed` while creating the environment.**
Something in the pip section failed and conda swallowed the detail. Rerun the
failing install on its own to see the real error:

```bash
conda activate micromethods
python -m pip install -e . -v
```

If the message is *"neither 'setup.py' nor 'pyproject.toml' found"*, you are
not in the project root — `dir` (Windows) or `ls` should show `pyproject.toml`
and the `micromethods/` folder side by side. If the repository has the code one
level down, `cd` into that level first.

Other frequent causes, in order:

```bash
python -m pip install -U pip setuptools wheel   # editable installs need setuptools>=64
```

- a stale `build/` or `*.egg-info/` folder from an earlier attempt: delete it;
- a project folder inside OneDrive-synced `Documents` with files still marked
  online-only: make the folder "Always keep on this device", or clone
  somewhere outside OneDrive;
- a `pyproject.toml` edited to list packages that do not exist in the checkout.

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
