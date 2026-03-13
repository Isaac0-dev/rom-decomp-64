# rom-decomp-64

A tool to extract assets from Super Mario 64 style ROMs, with a heavy focus on compatibility with romhacks, especially romhacks that are less deterministic like romhacks built with the SM64 decomp project.
More recently, it's output is also targetted towards being compatible with sm64coopdx.

## Prerequisites

- **Python 3**: Main language the program was written in.
- **Bun**: JavaScript runtime. Used to run n64js for headless emulation. https://bun.com/get

## Installation

1. Clone the repository with submodules:
   ```bash
   git clone --recurse-submodules https://github.com/Isaac0-dev/rom-decomp-64.git
   ```
3. Install Python dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Usage

### Standard GUI Extraction
Launch the GUI with:
```bash
python3 gui_extract.py
```

### CLI Extraction
Extract a single ROM:
```bash
python3 extract.py path/to/rom.z64
```

If no path is provided, defaults to `baserom.us.z64` in the current directory.

### Batch Extraction (for testing)
Extract all `.z64` files in the current directory:
```bash
python3 main.py
```

### Output Structure
Extracted assets are organized in `out/<rom_filename>/`:
- **`levels/`**: Identified level scripts (e.g. `bob/`, `ccm/`)
- **`misc/`**: Unidentified or global scripts
- **`sound/`**: Sequences (.m64) and samples
- **`textures/`**: Textures folder
  - **`segment2/`**: Textures from segment 2
  - **`skybox_tiles/`**: Skybox textures
- **`main.lua`**: sm64coopdx mod script
- **`raw.log`**: Complete extraction log with debug info

## Contributors
- Isaac0-dev
- Sunk

## Credits
- [n64js](https://github.com/hulkholden/n64js) by hulkholden - ROM emulation for deterministic data tracing
- djoslin0 - for his research and prototypes on rom2c, a private tool.
- [SM64 Decomp](https://github.com/n64decomp/sm64)
- [RNC ProPack decompressor](https://github.com/lab313ru/rnc_propack_source) - RNC decompression
- [Quad64](https://github.com/DavidSM64/Quad64) - Reference for display list parsing
