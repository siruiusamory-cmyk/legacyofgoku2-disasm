# The sprite record family

Three record kinds hold the sprite data. `sprites.py` reads them into the CSV beside this page, one
record per row, and encodes those rows back into the bytes the build assembles. `--check` compares
every row's bytes with your own image, and the gate compares the rebuilt image with the retail
sha256. A row whose `address` column or whose bytes disagree with the image fails both.

A `refs` column holds record labels (`def_017`, `piece_204`) or, where the word names something this
family does not carry, eight hex digits. A label resolves through that record's own `address`
column, so the table holds the references itself. A `bytes` column holds the bytes no reader in this
tree reads yet; its name is its offset span.

The third column of each table below names the evidence that fixes the field, and it is one of
three kinds: an address is an instruction the image holds; a `tools/...` path is the tracked decoder
that reads the field; a page under `tools/research/` is a tracked comparison. Only the addresses are
load sites, and the fields that have one are listed first in each table.

## directory

The id table at file `0x3B4E74`: three null words, then one word per sprite id, `0x0C + 4 * 154 =
628` bytes. The resolver at `0x08009324` reaches it for every id of seven or more.

| field | offset | width | load site | evidence |
|---|---|---|---|---|
| entries | `0x0C` | 4 B each | 0x0800936C | `ldr r0,[r0,#0x24]` after `lsls r0,r0,#2` (0x08009366), `adds r0,r0,r1` (0x08009368) and `subs r0,#0x40` (0x0800936A); the literal it adds is at file `0x959C` and holds `0x083B4E90`, so the word read is `0x083B4E74 + 4 * id` |
| reserved_00_0b | `0x00` | 12 B | - | the three null words, one per sprite id 0 to 2, zero in the image; no instruction reads them here because the resolver answers those three ids from its RAM copy |

Ids 0 to 3 are the words the resolver answers from its RAM copy rather than from this table, and
measured, ids 0 to 3 name a 12-byte record at `0x083A98DC` whose `+8` word is a container header.
Those four records are not definitions, so they stay hex in the `entries` column and their bytes
stay in the raw class.

## definition

One record per sprite id of four or more: a `0x4C`-byte header and one word per slot. 150 records,
holding 1,304 slot words of which 1,220 name a piece, 72 are zero and 12 are neither.

| field | offset | width | load site | evidence |
|---|---|---|---|---|
| slots | `0x4C` | 4 B each | 0x08018FDE | the frame selector loads the slot array address at 0x08018FD8, scales the frame byte by four at 0x08018FDC and reads the piece pointer at 0x08018FDE, then stores it at 0x08018FE2 and reads the piece's box |
| count | `0x04` | 4 B | tools/research/asset_directory.py | the decoder reads it as the slot count; 150 records hold 8, 16 or 24, and the slots of that many words resolve |
| reserved_00_03 | `0x00` | 4 B | - | no reader found |
| reserved_08_4b | `0x08` | 68 B | - | no reader found; three records hold a pointer at `+0x08` |

## piece

A 12-byte record named by a slot word. 776 records.

| field | offset | width | load site | evidence |
|---|---|---|---|---|
| x | `0x00` | 1 B | 0x08013BFE | `ldrsb r4,[r1,r3]` with `r3` set to zero, and again at 0x08018FE6 |
| y | `0x01` | 1 B | 0x08013C0A | `ldrsb r5,[r1,r3]` with `r3` set to one, and again at 0x08018FFC |
| w | `0x02` | 1 B | 0x08013C10 | `ldrb r3,[r1,#2]`, and again at 0x08018FE4 |
| h | `0x03` | 1 B | 0x08013C12 | `ldrb r1,[r1,#3]`, and again at 0x08018FF4 |
| attribute | `0x04` | 4 B | tools/research/FORMAT_REUSE.md | no instruction that reads it was located; the page records the object attribute word of the piece id 30 names |
| graphics | `0x08` | 4 B | tools/research/asset_directory.py | the decoder reads it and every one of the 776 words names a container header |

The two read sites agree on signedness: `x` and `y` are sign-extended at 0x08013BFE, 0x08013C0A,
0x08018FE6 and 0x08018FFC, and `w` and `h` are loaded unsigned. The piece's byte order is
`{s8 x, s8 y, u8 w, u8 h}`, which is why the CSV holds two negatives per row where the box starts
left of and above the frame's origin.
