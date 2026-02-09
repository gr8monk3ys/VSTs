# Free VST Plugins

[![CI](https://github.com/gr8monk3ys/free-vst-plugins/actions/workflows/ci.yml/badge.svg)](https://github.com/gr8monk3ys/free-vst-plugins/actions/workflows/ci.yml)
[![Docker](https://github.com/gr8monk3ys/free-vst-plugins/actions/workflows/docker-publish.yml/badge.svg)](https://github.com/gr8monk3ys/free-vst-plugins/pkgs/container/free-vst-plugins)

A curated collection of **high-quality, legally free** VST plugins for music production. Works on **macOS**, **Windows**, and **Linux**.

## Quick Start

### Python (Recommended - All Platforms)

```bash
# Clone the repo
git clone https://github.com/gr8monk3ys/free-vst-plugins.git
cd free-vst-plugins

# Download all plugins (~1.5GB)
python3 scripts/download-plugins.py

# Or download specific categories
python3 scripts/download-plugins.py --synths
python3 scripts/download-plugins.py --effects
```

### macOS (Bash)

```bash
./scripts/download-plugins.sh
```

### Windows (PowerShell)

```powershell
.\scripts\download-plugins.ps1
```

### Docker

```bash
# Download all plugins to current directory
docker run -v $(pwd)/downloads:/downloads ghcr.io/gr8monk3ys/free-vst-plugins --all

# Download synths only
docker run -v $(pwd)/downloads:/downloads ghcr.io/gr8monk3ys/free-vst-plugins --synths

# List available plugins
docker run ghcr.io/gr8monk3ys/free-vst-plugins --list
```

Or with docker-compose:

```bash
# Download all plugins
docker-compose run download-all

# Download specific category
docker-compose run download-synths
docker-compose run download-effects
```

## What's Included

### Synths (7 plugins)

| Plugin | Description | macOS | Windows | Linux | Open Source |
|--------|-------------|:-----:|:-------:|:-----:|:-----------:|
| **[Surge XT](https://surge-synthesizer.github.io/)** | Hybrid synth - wavetable, FM, subtractive. 2800+ presets | ✅ | ✅ | ✅ | ✅ |
| **[Dexed](https://asb2m10.github.io/dexed/)** | Yamaha DX7 FM synth clone | ✅ | ✅ | ✅ | ✅ |
| **[OB-Xd](https://www.discodsp.com/obxd/)** | Oberheim OB-X emulation | ✅ | ✅ | ✅ | ✅ |
| **[Helm](https://tytel.org/helm/)** | Polyphonic synth with deep modulation | ✅ | ✅ | ✅ | ✅ |
| **[TAL-NoiseMaker](https://tal-software.com/products/tal-noisemaker)** | Classic VA synth, 256 presets | ✅ | ✅ | ✅ | |
| **[Tyrell N6](https://u-he.com/products/tyrelln6/)** | u-he analog synth | ✅ | ✅ | ✅ | |
| **[Zebralette](https://u-he.com/products/zebralette/)** | u-he wavetable oscillator | ✅ | ✅ | ✅ | |

### Effects (10+ plugins)

| Plugin | Type | macOS | Windows | Linux | Open Source |
|--------|------|:-----:|:-------:|:-----:|:-----------:|
| **[Valhalla Supermassive](https://valhalladsp.com/shop/reverb/valhalla-supermassive/)** | Reverb/Delay | ✅ | | | |
| **[Valhalla FreqEcho](https://valhalladsp.com/shop/delay/valhalla-freq-echo/)** | Freq Shifter + Echo | ✅ | | | |
| **[OTT](https://xferrecords.com/freeware)** | Multiband Compressor | ✅ | | | |
| **[Dragonfly Reverb](https://michaelwillis.github.io/dragonfly-reverb/)** | 4 Reverbs | ✅ | ✅ | ✅ | ✅ |
| **[BYOD](https://chowdsp.com/products.html)** | Modular Distortion | ✅ | ✅ | ✅ | ✅ |
| **[TDR Nova](https://www.tokyodawn.net/tdr-nova/)** | Dynamic EQ | ✅ | ✅ | | |
| **[Airwindows Consolidated](https://www.airwindows.com/consolidated/)** | **350+ effects** | ✅ | ✅ | ✅ | ✅ |
| **[TAL-Vocoder](https://tal-software.com/products/tal-vocoder)** | Classic 80s Vocoder | ✅ | ✅ | ✅ | |

### Instruments & Bundles

| Plugin | Description | macOS | Windows | Linux |
|--------|-------------|:-----:|:-------:|:-----:|
| **[Sitala](https://decomposer.de/sitala/)** | Drum sampler - 16 pads | ✅ | ✅ | ✅ |
| **[MeldaProduction MFreeFXBundle](https://www.meldaproduction.com/MFreeFXBundle)** | 37 free effects | ✅ | ✅ | |

## Manual Download Required

These require account registration but are worth it:

| Plugin | Platforms | Why It's Great |
|--------|-----------|----------------|
| **[DC1A](https://klanghelm.com/contents/products/DC1A)** | macOS/Win | Character compressor — direct URL serves a download-gate page |
| **[Vital](https://vital.audio)** | All | Best free wavetable synth (rivals $189 Serum) |
| **[Spitfire LABS](https://labs.spitfireaudio.com)** | macOS/Win | Pro-quality sampled instruments |
| **[Analog Obsession](https://analogobsession.com)** | macOS/Win | 50+ analog hardware emulations |
| **[Kilohearts Essentials](https://kilohearts.com/products/kilohearts_essentials)** | macOS/Win | 30+ modular effects |
| **[Komplete Start](https://www.native-instruments.com/en/products/komplete/bundles/komplete-start/)** | macOS/Win | NI's free starter bundle |
| **[LSP Plugins](https://lsp-plug.in/)** | Linux/Win | 70+ professional Linux-native plugins |

## Usage

```bash
# Show help
python3 scripts/download-plugins.py --help

# List all available plugins
python3 scripts/download-plugins.py --list

# Download everything
python3 scripts/download-plugins.py --all

# Download specific categories
python3 scripts/download-plugins.py --synths
python3 scripts/download-plugins.py --effects
python3 scripts/download-plugins.py --instruments
python3 scripts/download-plugins.py --bundles

# Custom download directory
python3 scripts/download-plugins.py --dir ~/Music/Plugins

# Force a specific platform (useful for testing)
python3 scripts/download-plugins.py --platform windows
```

## Installation

### macOS

1. Open `~/Downloads/VST-Plugins/`
2. Double-click each `.dmg` or `.pkg` file
3. Run the installer
4. Rescan plugins in your DAW:
   - **FL Studio**: Options → Manage Plugins → Start Scan
   - **Ableton**: Preferences → Plug-Ins → Rescan
   - **Logic Pro**: Automatic on restart

**Plugin Locations:**
```
/Library/Audio/Plug-Ins/VST3/         # System VST3
/Library/Audio/Plug-Ins/Components/   # System AU
~/Library/Audio/Plug-Ins/VST3/        # User VST3
```

### Windows

1. Open `%USERPROFILE%\Downloads\VST-Plugins\`
2. Run each `.exe` or `.msi` installer as Administrator
3. Follow installer prompts
4. Rescan plugins in your DAW

**Plugin Locations:**
```
C:\Program Files\Common Files\VST3\           # System VST3
C:\Program Files\VSTPlugins\                  # System VST
%APPDATA%\VST3\                               # User VST3
```

### Linux

1. Extract archives to plugin directories
2. Rescan plugins in your DAW

**Plugin Locations:**
```
~/.vst3/                  # User VST3
~/.vst/                   # User VST
~/.lv2/                   # User LV2
/usr/lib/vst3/            # System VST3
/usr/lib/lv2/             # System LV2
```

**Ubuntu/Debian package install:**
```bash
# For .deb packages
sudo dpkg -i plugin-name.deb
```

## File Structure

```
free-vst-plugins/
├── README.md
├── plugins.json              # Plugin database with URLs for all platforms
├── Dockerfile                # Docker image for containerized downloads
├── docker-compose.yml        # Docker Compose for easy usage
├── .github/
│   └── workflows/
│       ├── ci.yml            # CI/CD pipeline (lint, test, URL check)
│       └── docker-publish.yml # Docker image publishing to GHCR
└── scripts/
    ├── download-plugins.py   # Cross-platform downloader (single source of truth)
    ├── download-plugins.sh   # Bash wrapper — delegates to download-plugins.py
    └── download-plugins.ps1  # PowerShell wrapper — delegates to download-plugins.py
```

## CI/CD

This project uses GitHub Actions for continuous integration:

| Workflow | Description |
|----------|-------------|
| **CI** | Lints code, validates JSON, tests script on all platforms |
| **Docker Publish** | Builds and pushes Docker image to GHCR |
| **URL Check** | Weekly validation of plugin download URLs |

### Running Tests Locally

```bash
# Validate JSON
python -m json.tool plugins.json > /dev/null

# Lint Python script
pip install ruff && ruff check scripts/download-plugins.py

# Test script
python scripts/download-plugins.py --list
```

### Building Docker Locally

```bash
# Build image
docker build -t free-vst-plugins .

# Run container
docker run -v $(pwd)/downloads:/downloads free-vst-plugins --all
```

## Related Projects

- **[OpenAudio](https://github.com/webprofusion/OpenAudio)** - Comprehensive list of open-source audio software
- **[awesome-vst](https://github.com/dreikanter/awesome-vst)** - Curated VST plugins reference
- **[FreeAudioPluginList](https://github.com/twinysam/FreeAudioPluginList)** - Ultimate list of free audio plugins
- **[OwlPlug](https://github.com/DropSnorz/OwlPlug)** - Cross-platform plugin manager

## Contributing

Found a great free plugin? PRs welcome!

1. Fork the repo
2. Add plugin to `plugins.json` with URLs for all available platforms
3. Test the download script
4. Submit PR

### Plugin Criteria

- ✅ Legally free (not cracked/pirated)
- ✅ 64-bit
- ✅ VST3, AU, CLAP, or LV2 format
- ✅ High quality / useful for production
- ✅ Bonus: Available on multiple platforms

## License

MIT License - Plugin downloads are subject to their respective licenses.

## Disclaimer

All plugins are downloaded from their official sources. This project does not host any plugin binaries. Always verify downloads and check plugin licenses before commercial use.
