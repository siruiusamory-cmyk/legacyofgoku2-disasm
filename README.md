<!-- TODO banner: add docs/banner.png at 1280x320, then put it above the title as a centered 900 px image. -->
<!-- TODO demo GIF: a short capture of extract.cmd, rebuild.cmd and the gate printing GATE PASS, saved as docs/demo.gif. -->
<!-- TODO social preview: set a repository social image in Settings once the banner exists. -->
# Dragon Ball Z: The Legacy of Goku II disassembly

**A byte-exact disassembly of Dragon Ball Z: The Legacy of Goku II (GBA, USA) that rebuilds the original ROM from tracked source.**

![License](https://img.shields.io/badge/license-MPL--2.0-blue.svg)
![Platform](https://img.shields.io/badge/platform-Game%20Boy%20Advance-lightgrey.svg)
![Build](https://img.shields.io/badge/build-byte--exact-brightgreen.svg)

## Contents

- [What this is](#what-this-is)
- [What this is not](#what-this-is-not)
- [Progress](#progress)
- [Building](#building)
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
Nearly every symbol is still named by its address: 1,005 of the 1,048 functions the build emits carry
the `sub_` form, and the blocks inside a function carry the `loc_` form (`loc_0801F0BC`). Naming one
takes evidence, never a guess; [docs/NAMING.md](docs/NAMING.md) says which evidence promotes a name
and which bytes make a function start. No part of the code is claimed to match the original
compiler's C output.

The progress figure below measures how much of the ROM the build produces from tracked source. It
does not measure how much of the code has been turned into C.

## Progress

32.9543 % of the ROM (2,764,408 of 8,388,608 bytes) builds from tracked source: transcribed
instructions, emitted code and literal pools, and container bodies re-encoded from your own ROM.
The rest is still copied into the build as slices of the original image. `python tools\gate\gate.py`
prints the split, and [docs/DEFINITION_OF_DONE.md](docs/DEFINITION_OF_DONE.md) says what counts as
source.

The code and data split, measured by `python tools\split\code_split.py --check` and recorded in
[docs/research/CODE_SPLIT.md](docs/research/CODE_SPLIT.md), is proven code 38,032 B, filtered
pointer-entry code 24,652 B, literal pool 3,760 B, overlay 3,708 B, unclassified 8,300,378 B, plus
the two classes the reaching channels name: table-held 1,318 B and gap-fill 16,760 B.

## Building

You need ARM Developer Suite 1.2, Python 3.12 and your own copy of the game saved as `baserom.gba`.
[INSTALL.md](INSTALL.md) has the details.

```
extract.cmd
rebuild.cmd
python tools\gate\gate.py
```

The gate rebuilds from scratch and prints `DIGEST MATCH` and `GATE PASS` when the output equals the
retail ROM.

## Repository layout

| Path | Contents |
| --- | --- |
| `asm/` | the assembly the image is built from |
| `tools/` | extraction, the generators, the gate, the source checks and the research scripts |
| `docs/` | how source is counted, the format record and the research notes |
| `assets/` | inputs the build writes from your ROM; never tracked |
| `build/` | the objects, the generated source and the image; never tracked |
| `work/` | build logs and research output; never tracked |

## Credits and license

The gate, the source checks, the link check, the slice writer and the build scripts start from the
[2genkidev/buusfury](https://github.com/2genkidev/buusfury) disassembly. Third-party code and
credits are listed in [NOTICE](NOTICE). Changes are listed in [CHANGELOG.md](CHANGELOG.md).

No ROM, BIOS or extracted game data is included. You need your own legally obtained copy of the
game. Not affiliated with the rights holders of the game.

MPL-2.0, see [LICENSE](LICENSE).
