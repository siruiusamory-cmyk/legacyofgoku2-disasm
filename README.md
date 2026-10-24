<!-- TODO demo GIF: a short capture of extract.cmd, rebuild.cmd and the gate printing GATE PASS, saved as docs/demo.gif and placed under the tagline. -->
<!-- TODO social preview: set the repository social image in Settings once the banner exists. -->
<p align="center"><img src="docs/banner.png" alt="Dragon Ball Z: The Legacy of Goku II" width="900"></p>

# Dragon Ball Z: The Legacy of Goku II disassembly

**A byte-exact disassembly of Dragon Ball Z: The Legacy of Goku II (GBA, USA) that rebuilds the original ROM from tracked source.**

![License](https://img.shields.io/badge/license-MPL--2.0-blue.svg)
![Platform](https://img.shields.io/badge/platform-Game%20Boy%20Advance-lightgrey.svg)
![Functions](https://img.shields.io/badge/functions-1249-blueviolet.svg)

## Contents

- [What this is](#what-this-is)
- [What this is not](#what-this-is-not)
- [Progress](#progress)
- [Building](#building)
- [Reading and changing a function](#reading-and-changing-a-function)
- [Repository layout](#repository-layout)
- [Credits and license](#credits-and-license)

## What this is

The program code is ARM and Thumb assembly. ARM Developer Suite 1.2 assembles and links it back
into the retail ROM, and the gate compares the result with the retail sha256. The code is
generated from the addresses the split proves: `tools/code/emit_code.py` decodes each code extent
and literal pool into assembler source at build time, and `tools/compress/generate_containers.py`
re-encodes every packed container out of your own copy of the game. What remains is still carried
as slices of the retail image, and the gate's count names every byte of it.

It builds one ROM:

* Dragon Ball Z: The Legacy of Goku II (USA), sha1 `18e0715dec419f3501c301511530d2edcd590f8b`

## What this is not

This is not a decompilation. All of the game's code is still assembly, and the build compiles no C.
Nearly every symbol is still named by its address: 1,045 of the 1,249 functions the split classifies carry
the `sub_` form, and the blocks inside a function carry the `loc_` form (`loc_0801F0BC`). Naming one
takes evidence, never a guess; [docs/NAMING.md](docs/NAMING.md) says which evidence promotes a name
and which bytes make a function start, and [docs/CODE_INDEX.md](docs/CODE_INDEX.md) says which file
carries it. No part of the code is claimed to match the original
compiler's C output.

The progress figure below measures how much of the ROM the build produces from tracked source. It
does not measure how much of the code has been turned into C.

## Progress

45.6827 % of the ROM (3,832,141 of 8,388,608 bytes) builds from tracked source: transcribed
instructions, emitted code and literal pools, container bodies re-encoded from your own ROM, the
map record family re-encoded from the five tracked tables in `tools/maprecords/`, the sprite
record family re-encoded from the three tracked tables in `tools/sprites/`, and the text storage
records re-encoded from the four tracked tables in `tools/text/`. The rest is still
copied into the build as slices of the original image. `python tools\gate\gate.py` prints the split,
and [docs/DEFINITION_OF_DONE.md](docs/DEFINITION_OF_DONE.md) says what counts as source.

The code and data split, measured by `python tools\split\code_split.py --check` and recorded in
[tools/split/CODE_SPLIT.md](tools/split/CODE_SPLIT.md), is proven code 38,084 B, filtered
pointer-entry code 24,652 B, literal pool 3,744 B, overlay 3,708 B, unclassified 8,299,528 B, plus
the two classes the reaching channels name: table-held 2,396 B and gap-fill 16,496 B.

## Building

You need ARM Developer Suite 1.2, Python 3.12, Visual Studio 2022 or Build Tools with the C++
workload, and your own copy of the game saved as `baserom.gba`. [INSTALL.md](INSTALL.md) has the
details. The build compiles the jcalg1 compressor from the vendored source when it is absent, so no
compiled copy of it is distributed here.

```
extract.cmd
rebuild.cmd
python tools\gate\gate.py
```

The gate rebuilds from scratch and prints `DIGEST MATCH` and `GATE PASS` when the output equals the
retail ROM.

`check.cmd` runs the source checks, the link check and the link check's test, the same commands CI
runs; its test step needs the runner CI installs, `python -m pip install pytest`.

## Reading and changing a function

1. Find the function in [docs/CODE_INDEX.md](docs/CODE_INDEX.md). Every function start has a row
   there, and each one the emitter writes has a file of its own: a named function is
   `build\code\<name>.s`, an address-named one is `build\code\code_<address>.s`, and the blocks
   inside a function are `loc_<address>` labels in that same file. A start the emitter does not
   write, carried by the boot transcription or by a container, shows `none`.
2. Read the file. It is generated at build time, so read it after `rebuild.cmd` has run.
3. The instructions come from the retail image through `tools/code/emit_code.py`, so changing what a
   function does means changing the generator or the transcription it emits; `docs/NAMING.md` says
   what the tree does and does not claim about the code.
4. To give a function a name, add a ledger row and the test or evidence that row cites, as
   `docs/NAMING.md` says. The build then emits the name and the index carries it.
5. Any change to the emitted text, the layout or the names has one proof: `rebuild.cmd` followed by
   `python tools\gate\gate.py`, which must still print `DIGEST MATCH` and `GATE PASS`.
6. `check.cmd` runs the source checks and the link check, which is what a commit has to pass
   locally; [docs/READABILITY.md](docs/READABILITY.md) lists what the tree still has to improve.

## Repository layout

| Path | Contents |
| --- | --- |
| `asm/` | the assembly the image is built from: the startup block, the symbol tables and the token list |
| `tools/` | every generator, the gate, the source checks and the tables they read; `tools/README.md` says what runs each one |
| `docs/` | the reader guide: the function index, the naming and readability rules, and the RAM ledger; `docs/README.md` says where to start |
| `build/` | the objects, the generated source and the image; never tracked |

## Credits and license

The gate, the source checks, the link check, the slice writer and the build scripts start from the
[2genkidev/buusfury](https://github.com/2genkidev/buusfury) disassembly. Third-party code and
credits are listed in [NOTICE](NOTICE). Changes are listed in [CHANGELOG.md](CHANGELOG.md).

No ROM, BIOS or extracted game data is included. You need your own legally obtained copy of the
game. Not affiliated with the rights holders of the game.

MPL-2.0, see [LICENSE](LICENSE).

