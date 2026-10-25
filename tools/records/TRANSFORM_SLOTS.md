# The transform slot descriptors

One generator reads the descriptor records of the transform-slot family the runtime census found
inside the gate's raw class, and encodes those rows back into the bytes the build assembles.
`--check` compares every row's bytes with your own image, and the gate compares the rebuilt image
with the retail sha256.

Each record is 12 B and describes one segment of a source stream: where the segment starts, the
flags the slot driver reads, the pixel range the copy clips to, and the step the copy advances the
source by. The record addresses are the descriptors the runtime census saw a live slot name, so the
rows are pinned by that census; the slots' own array address is built in RAM, and 31 of the 34
descriptors appear nowhere in the image as a four-byte word. The bytes between two records of one
array are contiguous: the gap between the 34 addresses is 12 B at its smallest, and no record
overlaps a decoded container.

The initialiser at `0x0801FA1A` reads every field the table below names: `r2` is the descriptor,
`ldr r3,[r2]` takes the source pointer, `ldrh r3,[r2,#6]` and `ldrh r3,[r2,#8]` the clip range the
driver scales by `0x4000`, `ldrh r3,[r2,#0xa]` the step, and `ldrb r2,[r2,#4]` the flags. The copy
routine the driver calls consumes at most one source byte per output word per `0x4000` of step, so
the clip end bounds the pixels, not the bytes: the source spans are not part of this family.

The fourth column of the table below names the evidence that fixes the field: an address is an
instruction the image holds, and `-` is a field with no reader located. Sites are quoted from the
image's bytes.

## slot

The 34 records, 12 B each.

| field | offset | width | load site | evidence |
|---|---|---|---|---|
| source_00 | 0x00 | 4 | 0x0801FA1C | `ldr r3,[r2]`; stored to the slot at `0x0801FA1E` |
| flags_04 | 0x04 | 1 | 0x0801FA30 | `ldrb r2,[r2,#4]`; stored at `0x0801FA32` |
| pad_05 | 0x05 | 1 | - | not read by the initialiser |
| clip_start_06 | 0x06 | 2 | 0x0801FA20 | `ldrh r3,[r2,#6]`, then `lsls r3,r3,#0xe` at `0x0801FA22` |
| clip_end_08 | 0x08 | 2 | 0x0801FA26 | `ldrh r3,[r2,#8]`, then `lsls r3,r3,#0xe` at `0x0801FA28` |
| step_0a | 0x0A | 2 | 0x0801FA2C | `ldrh r3,[r2,#0xa]`; stored at `0x0801FA2E` |
