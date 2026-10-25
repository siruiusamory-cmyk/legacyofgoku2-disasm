# The IWRAM copy family's callers

The runtime census found a family of ROM reads whose pcs lie in IWRAM, `0x03000540` to
`0x030006EC`, reading 197,124 B of the gate's raw class over the five routes. Those bytes are a copy
of ROM code: IWRAM `0x03000000` is the image's `0x087FD6BC` overlay of `0xE7C` bytes, so the family's
pcs are ROM file offsets `0x87FDBFC` and after. This page records the caller census and why the
population is not authorable as source.

## The routine

`0x087FDBDC` is the entry (IWRAM `0x03000520`): `push {r4, r5, r6, r7, r8, sb, sl}`, then
`ldm r0, {r3, r4, r5, r6}`. `r0` is a transform slot; `r1` the destination buffer; `r2` the word
count; `r3` the value the call site put in it, which the routine overwrites. The loop reads the
coefficient byte stream with `ldrsb r0, [r3]` at `0x087FDAF0`-style step pairs and rewrites each
destination word with `ldr r5, [r1]` / `mla r5, r6, r0, r5` / `str r5, [r1], #4` at
`0x087FDC08`-`0x087FDC10`. The source pointer is therefore `[r0 + 8 ...]` as the routine reads it,
not a register the caller passes.

## The instrument

The private probe is the runtime census probe plus two hooks: one records
`lr`, `r0`-`r3` and a call id when a block transfer executes at `0x03000520`, and one records the
value of three instructions of the slot initialiser (`0x0801FA1A`, `0x0801FA1E`, `0x0801FA2A`)
together with the ROM read pages of each call. It is a private copy; no repository file came from it.

Non-perturbation: every route reproduced the census framebuffer hash with the hooks loaded -

```
r1-boot    12000 frames f8bc7144385737f6
r2-field   17020 frames 62c1a42751da431c
r3-menu    16500 frames 56f7bfb2aa1e20f7
r4-hunt    22870 frames b473ae33c77eb6be
r5-credits 17220 frames 13140958b74f3837
```

## The callers

Eight `bl` sites, all in the slot driver at `0x0801FA72`-`0x0801FBFF`, all calling the `bx r3`
veneer at `0x08021D2E` with `r3 = slot + 0x18`:

```
lr        call site   routes
0801FAAB  0801FAA6   all five
0801FAD9  0801FAD4   all five
0801FB03  0801FAFE   all five
0801FB33  0801FB2E   all five
0801FB6F  0801FB6A   all five
0801FB9D  0801FB98   all five
0801FBC7  0801FBC2   all five
0801FBE1  0801FBDC   all five
```

Call count and the distinct source words per route:

```
route      calls     slots  descriptors  sources  bytes read
r1-boot    165322    16     30           30       20450402
r2-field   233279    16     30           30       28700579
r3-menu    225568    16     31           31       27805841
r4-hunt    313027    16     32           32       38287724
r5-credits 236051    16     32           32       28992811
all        1173247   16     34           34       144237357
```

The byte total is the census's own family access total, 144,237,357, which is the cross-check that the
hook measured the same reads.

## The descriptor layout

Each descriptor is a 12-byte record and the initialiser reads every field it carries:

```
+0x00  source pointer           ldr r3,[r2]      0x0801FA1C
+0x04  flags                    ldrb r2,[r2,#4]  0x0801FA30
+0x06  clip start                ldrh r3,[r2,#6]  0x0801FA20
+0x08  clip end                  ldrh r3,[r2,#8]  0x0801FA26
+0x0a  step                      ldrh r3,[r2,#0xa] 0x0801FA2C
```

The record width is 12 B: the smallest gap between two of the 34 addresses is 12 B, no record overlaps
a decoded container, and the two records that sit 12 B apart both carry a source pointer of their own.
Those 34 records are tracked source in `tools/records/transform_slots.py`, 408 B.

The clip range is scaled by `0x4000` and the driver compares the running position against it before it
calls the copy; the copy routine (`0x087FDBDC`, ARM) reads one `ldrsb` per output word and advances the
source by `step >> 14` plus the carry of a `0x4000` fixed-point accumulator. The step runs from
`0x0F4B` to `0x4DB0` across the 34 records, so a record advances up to 1.21 source bytes per word: the
clip end bounds the pixels, not the bytes, and a record's source can be read past its own end value.
That is why the source population stays raw and only the record table is source.

## Why the population is not authorable

Walking back from the loop: the slot's source pointer is `descriptor[0]`, written at `0x0801FA1E`
from `ldr r3, [r2]` where `r2 = slot + 0x28` (`0x0801FA1A`) names a ROM descriptor; `descriptor+6`
and `descriptor+8` scaled by `0x4000` bound the slot's line range (`0x0801FA20`-`0x0801FA2A`), and
`descriptor+4` is a flag byte. The slot's descriptor pointer is written outside the initialiser, and
the whole slot array is 16 slots of `0x40` bytes filled by `0x0801FD22` and driven by
`0x0801FD38` per frame.

Measured at the five routes' descriptors and sources:

- 34 distinct descriptors, `0x080E15F8` to `0x0814AD24`; 34 distinct sources, `0x080410E7` to
  `0x08144E38`; every one of them lies inside the gate's raw class.
- 31 of the 34 descriptors appear nowhere in the image as a four-byte word, so no ROM pointer array
  lists them and the set is built in RAM. Every source does appear, but only inside its own
  descriptor's first word, which is where the initialiser reads it.
- The read length per call is the slot's pixel count (`r2`), not a stored extent, so no bound in the
  image states how many bytes a source carries.

The family therefore has no ROM structure with a code-derived bound over its source list. Its 197,124
B stay in the raw class and are claimed as 0 B.
