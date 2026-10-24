# A reader's guide to this tree

This repository is a disassembly of Dragon Ball Z: The Legacy of Goku II (GBA, USA): the tracked
source assembles and re-encodes back into the retail image byte for byte. Nothing here is a
decompilation of the original C. The code is assembly, decoded from the image at build time, and
most symbols are still named after their address.

## What the game's code is organised into

The image is built from four kinds of tracked source.

| kind | where | what it is |
| --- | --- | --- |
| transcribed code | `asm/crt0.s` | the startup block, written out instruction by instruction and assembled as `CODE32` |
| symbol tables | `asm/registers.s`, `asm/memory.s` | the GBATEK name of every hardware register and every named word of writable memory, as assembler equates |
| the token list | `asm/remainder.s` | one line per extent of the image, in address order: `INCLUDE` for a generated code file, `INCBIN` for a slice of the image, in the order the build lays them down |
| generated source | `build/` | assets and code files that a generator decodes from your own copy of the ROM at build time |

`asm/buu.s` is the one unit the assembler reads: it includes the two symbol tables, assembles the
header from a slice of the image, includes `asm/crt0.s`, and then includes `asm/remainder.s`, which
carries the rest of the image in address order.

`tools/code/emit_code.py` walks the split and writes one file per function start under
`build/code/`: `code_<address>.s` or the function's own name, plus `pool_<address>.s` for each
literal pool. A named function and an address-named one are the same source; only the symbol
differs. `tools/compress/generate_containers.py` decodes every packed container in the image and
re-encodes it with `tools/compress/compress.exe`, which the build compiles from the vendored jcalg1
source on first use. Both generators refuse an encoding that is not the retail extent's bytes, so a
generator cannot drift silently.

The bytes no generator rebuilds yet are carried as slices of your own image, written by
`tools/extract/slice_rom.py`. They are never tracked, and `python tools\gate\gate.py` counts every
one of them.

## How to build

You need ARM Developer Suite 1.2, Python 3.12, Visual Studio 2022 or Build Tools with the C++
workload (for the compressor), and your own copy of the game as `baserom.gba`. [INSTALL.md](../INSTALL.md)
has the details.

```
extract.cmd
rebuild.cmd
python tools\gate\gate.py
```

`extract.cmd` checks that `baserom.gba` is the image this tree expects; `rebuild.cmd` assembles,
generates and re-encodes everything into `build/ROM_START`; the gate rebuilds from scratch, purges
every object first, and prints `DIGEST MATCH` and `GATE PASS` when that image equals the retail
sha256. [DEFINITION_OF_DONE.md](DEFINITION_OF_DONE.md) says what counts as source and what the finish
line is.

## How names are chosen

A function whose purpose is known is `Module_Verb` (`Map_LoadLayer`); one whose purpose is not yet
known keeps its retail address (`sub_0801F702`, `loc_0801444C`). Only a quoted byte-level or runtime
measurement promotes a name, and every promotion adds a row to the ledger under `tools/code/`, which
is a check input. A toolchain library member takes its exported symbol. [NAMING.md](NAMING.md) lists
the evidence classes and the assembler rules.

## Where to look next

| page | says |
| --- | --- |
| [CODE_INDEX.md](CODE_INDEX.md) | one file per function start, and how to find the file for a name |
| [NAMING.md](NAMING.md) | function, data and unit names, and the evidence each one needs |
| [READABILITY.md](READABILITY.md) | the rules a change has to keep readable |
| [RAM_LEDGER.csv](RAM_LEDGER.csv) | the words of writable memory the tree has named, and the evidence for each |
| [DEFINITION_OF_DONE.md](DEFINITION_OF_DONE.md) | what counts as source and what the finish line is |
| [../README.md](../README.md) | what the tree is, its progress figure, and how a change is proven |
