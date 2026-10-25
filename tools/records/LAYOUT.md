# The state table and the quest records

Two generators read the byte populations the runtime census found inside the gate's raw class, one
record family per CSV, and encode those rows back into the bytes the build assembles. `--check`
compares every row's bytes with your own image, and the gate compares the rebuilt image with the
retail sha256.

`table_086f6d8c.py` reads the table the code names with the literal at `0x080040F0` (`0x086F6D8C`)
into four families: the 8-byte header, the record-pointer array it names, the 68 records, and the 297
four-byte entries the records point at. `opcode_rows.py` reads the quest records the opcode
interpreter dispatches to into two families: the 43 records and the 323 instructions of their 86
streams.

A reference column holds a record label of the same file (`record_000`, `entry_000`) or, where the
word names something this family does not carry, eight hex digits. A `bytes` column holds bytes no
reader in this tree reads yet; its name is its offset span. The instruction `operands` column holds
the operands the decoder's own grammar gives: hex bytes, `v<hex>` for a 7-bit varint and `c<count>`
for the count byte of a counted opcode.

The fourth column of each table below names the evidence that fixes the field: an address is an
instruction the image holds, and `-` is a field with no reader located. Sites are quoted from the
image's own bytes, disassembled for this ticket.

## table

The header at `0x086F6D8C`, 8 B: a record count and the pointer array that follows it at
`0x086F6C7C`.

| field | offset | width | load site | evidence |
|---|---|---|---|---|
| count_00 | `0x00` | 4 B | 0x080040F4 | `ldr r3,[r0]` after the literal at `0x080040F0` loaded `0x086F6D8C`; the walk stops when `cmp r3,#0` at `0x080040F8` says the count is spent, and the loop index is `cmp`-bounded by it at `0x0800413E` |
| records_04 | `0x04` | 4 B | 0x08004102 | `ldr r0,[r0,#4]` at `0x080040FC` then `lsls r3,r4,#2` and `ldr r5,[r0,r3]` at `0x08004104`, so the word is a 4-byte-strided record array |

## array

The 68 record pointers at `0x086F6C7C`, 272 B, one row.

| field | offset | width | load site | evidence |
|---|---|---|---|---|
| records | `0x00` | 4 B | 0x08004104 | `ldr r5,[r0,r3]` reads slot `index` of this array; `0x0800413C`-`0x08004140` increment the index and compare it with the count at `0x080040F4` |

## record

One row per record the array names, 68 rows and 2,820 B with their inline pointer arrays. A record is
`0x18` bytes and one pointer per entry.

| field | offset | width | load site | evidence |
|---|---|---|---|---|
| reserved_00_13 | `0x00` | 20 B | - | no reader found; the five words before the count name image addresses and small integers, and no walked code loads them |
| count_14 | `0x14` | 4 B | 0x08004108 | `ldr r7,[r5,#0x14]`; `cmp r7,#0` at `0x0800410A` ends the entry walk and `cmp r7,r0` at `0x0800413E` bounds it |
| pointers_18 | `0x18` | 4 B | 0x08004112 | `lsls r3,r0,#2` / `adds r3,r3,r5` / `ldr r3,[r3,#0x18]`, so entry `index` is the word at `record + 0x18 + 4 * index` |

## entry

One row per distinct entry the records point at, 297 rows and 1,188 B. The reader compares the first
two bytes with its two arguments and sets one bit of a byte array keyed by the halfword.

| field | offset | width | load site | evidence |
|---|---|---|---|---|
| key_00 | `0x00` | 1 B | 0x08004114 | `ldrb r6,[r3]` then `cmp r6,r1` at `0x08004116` |
| key_01 | `0x01` | 1 B | 0x0800411A | `ldrb r6,[r3,#1]` then `cmp r6,r2` at `0x0800411C` |
| flag_02 | `0x02` | 2 B | 0x08004120 | `ldrh r0,[r3,#2]`; `lsrs r1,r0,#3` and `adds r1,#0xe0` give the byte, `lsls r3,r0,#0x1d` / `lsrs r3,r3,#0x1d` the bit, and `orrs r0,r2` / `strb r0,[r1,#7]` set it |

## quest_record

One row per record the opcode interpreter's dispatch reads, 43 rows and 688 B, stride 16. The base is
the literal the reader loads at `0x08004A86`; the index is `lsls r0,r6,#4` / `adds r5,r0,r1`.

| field | offset | width | load site | evidence |
|---|---|---|---|---|
| reserved_00_03 | `0x00` | 4 B | - | no reader found; the walk that names the records stops when this word reaches `0x10` (`cmp` in `opcode_stream.streams`), and no walked code loads it |
| stream_04 | `0x04` | 4 B | 0x08004A90 | `ldr r1,[r5,#4]` then `bl 0x080092E4`, the interpreter |
| stream_08 | `0x08` | 4 B | 0x08004AB8 | `ldr r1,[r5,#8]` then `bl 0x080092E4`, the same interpreter |
| text_0c | `0x0C` | 4 B | 0x08004AA6 | `ldr r1,[r5,#0xc]` stores the pointer into the caller's record; the bytes it names are not this family's |

## instruction

One row per instruction of the 86 streams the records name, 323 rows and 539 B. The stream grammar is
the interpreter's own, proven in `tools/research/opcode_stream.py`: the opcode fetch is
`ldrb r0,[r1]` at `0x08009300`, the dispatch is `lsls r0,r0,#2` / `ldr r2,[r6,r0]` at
`0x08009306`-`0x08009308`, and `0x11` ends a stream.

| field | offset | width | load site | evidence |
|---|---|---|---|---|
| opcode | `0x00` | 1 B | 0x08009300 | `ldrb r0,[r1]`, then the table at `0x083B5C00` dispatches it |
| operands | `0x01` | - | - | no single site: every handler of the table at `0x083B5C00` reads its own operands, quoted per opcode in the `HANDLERS` table of `tools/research/opcode_stream.py` and proven by its `pinned()` check |
