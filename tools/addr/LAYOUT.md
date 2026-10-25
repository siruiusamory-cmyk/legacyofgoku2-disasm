# The address-run label table

`addr_runs.py` reads every run of the data census's address-run class whose words all name a code
label the build already emits, one row per run, and encodes those rows back into the bytes the build
assembles. `--check` compares every row's bytes with your own image, and the gate compares the
rebuilt image with the retail sha256.

The table is one family. A row is a maximal run of two or more consecutive four-byte-aligned words
inside one class extent, where each word's `value & ~1` is an address the emitter writes a label at:
an emitted segment start, a `loc_` label the branch operands force, or an export entry. Every word
the emitter writes resolves; a run with one unresolvable word stays raw.

## run

822 rows and 7,892 B. The `words` column holds the label of each word, `+1` when the word carries the
Thumb bit; the encoder writes the label's address with that bit.

| field | offset | width | load site | evidence |
|---|---|---|---|---|
| words | `0x00` | 4 B | - | no reader for most runs: five runs are named by a literal load in the split's walked code, and every run's words are labels the emitter writes |

The five consumer-named runs, each wholly inside this table, from the literal pool word that names
its start:

| run start | bytes | literal |
|---|---|---|
| `0x083B5D28` | 580 | `0x0800921C` (the opcode `0x02` sub-table) |
| `0x083B5F70` | 68 | `0x08009220` (the opcode `0x03` sub-table) |
| `0x087FCB1C` | 128 | a literal in the boot transcription |
| `0x083B5C00` | 68 | `0x08009320` (the opcode dispatch table) |
| `0x087FD0DC` | 24 | a literal in the boot transcription |

The rule is measured, not assumed: on the byte-permuted region the same walk resolves no word and
all 822 rows differ, and a table row whose Thumb bit is flipped no longer matches the image.
