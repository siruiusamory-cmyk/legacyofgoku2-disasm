# Readability

What a reader meets in this tree, how much of it there is, and the rule that keeps each count
falling. `python tools\research\readability_audit.py` prints every figure below from the tree and
from the generated code in `build\code`; run `rebuild.cmd` first, because the code files are
generated at build time.

The audience is a reader who has just cloned the repository and wants to find, read, change and
verify one function. Readability in this tree comes from names, layout and documents: the build
itself carries no comments, so a slice file has to say what it is by how it is named and where it
sits.

The after column repeats the before figure for a class no item has reached yet, so the table is a
ledger of what still has to fall, not a claim that it already fell.

## The measured classes

| class | before | after | rule |
| --- | --- | --- | --- |
| asm file organisation | 1,026 files, 125 code files carrying more than one function start, every generated file named `code_<address>.s` | 1,337 files, no file carrying more than one function start, 1,094 code files each named after the one start it opens (54 by name, 1,040 by address), and an index that maps every start to its file | a generated code file is named after the function or module group it carries, and `docs/CODE_INDEX.md` maps every name to its file and address |
| literal hardware-register addresses | 76 occurrences, 18 distinct values | 0 occurrences, 18 symbols | every literal that is a standard register becomes its GBATEK name from the single include `asm/registers.s` |
| literal RAM and flag addresses | 99 occurrences, 54 distinct values | 82 occurrences, 51 distinct values, 3 named | a RAM address becomes a symbol only where a ledger evidence class proves its role; everything else stays a literal and is counted here |
| carried data with no name | 3,360 slices, 5,624,200 B | 3,360 slices, 5,624,200 B, 9 record families named in `docs\TABLE_LEDGER.csv` with the reader that decodes each | a table a generator decodes gets a named record family and a tracked page; an undecoded slice stays a slice and is counted |
| magic constants | 26,887 immediate operands, 373 distinct values | 26,887, 373 | a constant that names a device field, a stride or a sentinel becomes an equate; a plain arithmetic literal stays |
| newcomer path gaps | 4 of 6 steps documented | 6 of 6 | the six steps below are each run on a fresh clone and each is a documented command |
| tool code | 53 files, 3 definitions nothing refers to, 0 duplicated blocks of 8 lines or more | 53, 3, 0 | a definition nothing calls is deleted, a helper that repeats another is merged, and a name says what the function returns |
| test naming | 25 files, 260 tests, 0 named by address | 25, 260, 0 | a test name states the behaviour its assertions prove; a test that names only an address names nothing |

The six steps of the newcomer path:

1. clone the repository and read `README.md`;
2. save your own copy of the game as `baserom.gba`;
3. `extract.cmd`;
4. `rebuild.cmd`;
5. find a function by name in `docs/CODE_INDEX.md`, read its file, change it;
6. `python tools\gate\gate.py` prints `DIGEST MATCH` and `GATE PASS`.

Steps 2 to 4 and 6 are in `README.md`. Steps 1 and 5 are not: nothing maps a function name to the
file that carries it, and nothing says what a change to one function has to keep true. That is the
gap this document and the index close.

## Examples, three per class

Asm file organisation: `build\code\Blend_ShowBg0.s` carries the function it is named after and no
other start; `build\code\Display_SetControlBit.s` holds its own start and the two block labels inside
it; `asm\remainder.s` carries 1,333 `INCLUDE` lines and 6,271 `INCBIN` lines, so a reader looking for
a function starts from `docs\CODE_INDEX.md` instead.

Literal hardware-register addresses: `DCD REG_DMA3SAD` in the pool at `pool_080004e4.s` is the DMA3
source register, written 43 times across the emitted pools; `mov r0, #REG_DISPCNT` in `asm\crt0.s`
loads the display control register before anything else runs; `DCD REG_IE` in `pool_08012378.s` is
the interrupt enable register.

Literal RAM and flag addresses: `DCD Heap_Head` names the free-list head the allocator's behaviour
test sets; `DCD Dma3_HalfwordSource` and `DCD Dma3_WordSource` are the two words the DMA3 fill
request builders store their value in and then name as the transfer source; each of the 51 remaining
distinct values is a global whose role no evidence class has named yet. The value `0x02020202` sits in
the writable range but is a fill pattern, not an address, and the count keeps it as one of the
unnamed literals rather than pretending the range decides the role.

Carried data with no name: `docs\TABLE_LEDGER.csv` names the nine record families a tracked reader
decodes, the map entry, root, layer and root-table records, the two tile-bank families, the sprite
directory, the text strings and the opcode stream, each with its reader and the page that measures
it; `baserom.gba_0x1fe_0x200.extracted` is a two-byte slice between two code runs and stays a slice;
and the 84 printable 16-bit runs `docs\research\FORMAT_REUSE.md` measures have no reader, so they
stay unnamed and counted.

Magic constants: `MOV r0, #0x38` is the header size the buffer constructor asks the allocator for;
`ADD r1, #0x8` is the field offset a record reader steps over; `CMP r1, #0x80` is the sentinel a
list walk stops on.

Newcomer path gaps: `README.md` lists the three build commands; `INSTALL.md` names the toolchain;
no document answers which file carries `Rect_Overlaps`, how to rebuild only one function, or which
checks a commit has to pass.

Tool code: `tools/split/code_split.py` defines `per_entry`, which nothing calls;
`tools/testkit.py` defines `refusal_message` and `perturbed_record`, which nothing calls;
`tools/code/thumb_vm.py` names its readers `half`, `word` and `run`, which say the type but not the
role.

Test naming: `test_rect_overlaps_reports_whether_two_rectangles_intersect` states what it proves;
`test_thumb_vm.py` and `test_behaviour.py` are named after the instrument and the evidence class
rather than one behaviour, which is right for a file and wrong for a test; no test is named by an
address.

## What is enforced

Three checks in `tools\lint\lints.py` hold the counts where they are:

- `READABILITY-ratchet` compares the live count of unnamed RAM literals and of literal hardware
  registers with `docs\READABILITY_BASELINE.txt`. A count above the baseline fails, and so does a
  count below it, because the figure only falls and the baseline is lowered in the same commit that
  lowers it.
- `READABILITY-index` fails when `docs\CODE_INDEX.md` is not what `tools\code\code_index.py`
  derives, and that derivation names every code file by its first function, so a file that breaks
  the layout rule breaks the index with it.
- `READABILITY-path` fails when neither `README.md` nor `INSTALL.md` names one of the path's
  commands or the index.

The first two read the retail image, so they are skipped in CI, which runs without it, exactly as
every ROM-gated test is. The cold gate runs them with the image present.

## What the counts mean

A count here is measured, not estimated. `readability_audit.py` reads the tracked `asm\*.s` files
and every generated file in `build\code`, counts the hex tokens by address range, counts the
immediate operands, walks `docs\research\FUNCTION_BOUNDS.csv` and `tools\code\names.csv` for the
function figures, counts the rows of `docs\TABLE_LEDGER.csv` for the table figures, takes the slice
count from the gate's own `incbin_ranges`, and scans the tracked Python for definitions nothing
refers to and for blocks of eight lines or more that repeat. A table-ledger row must quote a token
its own page carries, so a family cannot be named past the page that measures it.

`asm\registers.s` is left out of the address counts on purpose: its right-hand sides are the one
place in the tree where a register address belongs as a literal, and every other file names the
register instead.
