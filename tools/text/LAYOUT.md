# The text storage record family

`text_rows.py` reads four families out of the text storage into the CSV beside this page, one record
per row, and encodes those rows back into the bytes the build assembles. `--check` compares every
row's bytes with your own image, and the gate compares the rebuilt image with the retail sha256. A
row whose `address` column or whose bytes disagree with the image fails both.

A reference column holds a record label (`string_017`) or, where the word names something this
family does not carry, eight hex digits. A label resolves through that record's own `address`
column, so the table holds the references itself. A `bytes` column holds bytes no reader in this tree
reads yet; its name is its offset span. A `text` column holds the record's characters, and the
encoder adds the terminating zero.

The fourth column of each table below names the evidence that fixes the field: an address is an
instruction the image holds, and `-` is a field with no reader located. Sites are quoted from the
image's own bytes, disassembled for this ticket.

## roster

The 128-record roster table at file `0x6F8E40`, stride `0x14`, five words per record. Two addresses
in the walked code compute a record: the table's base reaches the pool word at file `0x19130` (loaded
at `0x08019104`), `lsls r0,r4,#2` / `adds r0,r0,r4` / `lsls r0,r0,#2` / `adds r0,r0,r6` at
`0x0801910A`-`0x08019110` scales the index by 20, and `cmp r4,#0x80` at `0x08019122` bounds it at
128.

| field | offset | width | load site | evidence |
|---|---|---|---|---|
| text_00 | `0x00` | 4 B | 0x0801945E | `ldr r1,[r0,#0x0]` after the record address is computed at `0x08019456`-`0x0801945C`, passed as the second argument to `0x0801F636`, which walks its bytes to the zero or the line feed at `0x0801F644`-`0x0801F64C` and looks every byte up in the font the object carries at `+0x0C` |
| text_04 | `0x04` | 4 B | 0x080196A2 | `ldr r0,[r6,#0x4]` on the record whose base `0x08019680` loaded, then passed at `0x080196AC`-`0x080196B0` to `0x0801F7FC`, which skips the string's leading spaces and line feeds |
| sprite_08 | `0x08` | 4 B | 0x08019112 | `ldr r0,[r0,#0x8]` on the scaled record, passed to the sprite directory resolver at `0x08009324`; the same word is read at `0x08018F22` |
| reserved_0c_0f | `0x0C` | 4 B | - | no reader found; every record holds a value below `0x73` in its low byte and zero in the three above it |
| record_10 | `0x10` | 4 B | 0x080190E6 | `ldr r5,[r3,#0x10]` on the scaled record, then `0x080190E8`-`0x080190EE` scale it by 24 and add the base the pool word at file `0x1912C` holds, and the record at that address is compared with the argument |

The two text fields are the strings this family names: 256 pointer words hold 124 distinct addresses,
and every one of them lies inside the stored text container.

## roster_string

One row per distinct string the roster names, in the order the table first names it: 124 strings,
15,512 B with their terminators. The strings are contiguous from file `0x6F9840`, and the 47,472 B
of the container's payload that no string covers stay in the raw class.

| field | offset | width | load site | evidence |
|---|---|---|---|---|
| text | `0x00` | to the zero | 0x0801F718 | the draw routine fetches one byte at `0x0801F718`, tests it for the terminator at `0x0801F71A` and for the space it breaks a line on at `0x0801F71E`; the measure path reads the same bytes at `0x0801F65E` |

## objective

The 43 records at file `0x6D68DC`, stride `0x10`, whose `+0x0C` word names the objective's text. One
row per record, in record order: the n-th row is the n-th record's text. The record's own 16 bytes
carry a byte at `+0x00` (read at `0x08004AD6` as an index into the word table the pool word at file
`0x4C88` holds), the two opcode streams at `+0x04` and `+0x08` (read at `0x08004A90` and `0x08004AB8`
and passed to the interpreter at `0x080092E4`) and the text at `+0x0C`; those 688 B are the opcode
record family's and stay in the raw class, so this table promotes the text alone.

| field | offset | width | load site | evidence |
|---|---|---|---|---|
| text | `0x00` | to the zero | 0x08004AA6 | `ldr r1,[r5,#0xC]` on the record `0x08004A86`-`0x08004A8A` computes from the base at file `0x4C80` and the index scaled by 16, then stored at `0x08004AAC` beside the text object; read again at `0x08004ACE` for the second stream's result, and `cmp r6,#0x2B` at `0x08004AE2` bounds the table at 43 records |

The 43 strings are contiguous from file `0x6D6B8C`, immediately after the record table, and 1,897 B
with their terminators.

## font

The font's offset table at file `0x28724`: 256 `u16` words, one per byte code, and 221 of them name a
glyph record. The record's first word past this table is the glyph's width and its advance is one
more. The table's last 4 B lie inside the stored container the census holds at `0x28920`, so the
rows assemble 508 B of the 512 B the table spans.

| field | offset | width | load site | evidence |
|---|---|---|---|---|
| offset | `0x00` | 2 B | 0x0801F744 | `ldrh r3,[r1,r3]` with `r3` set to the code doubled at `0x0801F742`, from the font base the object carries at `+0x0C` (`0x0801F740`); the word it names is read at `0x0801F746`-`0x0801F748` and the advance is its value plus one at `0x0801F74A` |

The base itself is loaded at `0x08004A70` from the pool word at file `0x4C78` and stored into a text
object at `+0x0C`. The defined codes ascend with the code index, and the widths the tracked sample
names are the image's: `' '` is 2 wide with an advance of 3, `'A'` and `'a'` are 5 wide with an
advance of 6, and `'.'` is 1 wide with an advance of 2.
