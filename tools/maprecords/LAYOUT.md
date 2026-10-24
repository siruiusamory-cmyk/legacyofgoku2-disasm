# The map record family

Five record kinds hold the map data. `maprecords.py` reads them into the CSV beside this page, one
record per row, and encodes those rows back into the bytes the build assembles. `--check` compares
every row's bytes with your own image, and the gate compares the rebuilt image with the retail
sha256. A row whose `address` column or whose bytes disagree with the image fails both.

A `ref` column holds a record label (`root_017`) or, where the word names something this family
does not carry, eight hex digits. The label resolves through that record's own `address` column, so
the table holds the references itself. A `bytes` column holds the bytes no reader in this tree reads
yet; its name is its offset span.

## entry

One row of the table at file `0x409368`, stride `0x38`, 327 rows. `tools/mapcontainer/mapcontainer.py`
walks the table and `tools/research/data_census.py` names its load site `0x08005778`.

| field | offset | width | load site | evidence |
|---|---|---|---|---|
| field_00 | `0x00` | 1 B | 0x080057B2 | the renderer reads it and formats it |
| field_01 | `0x01` | 1 B | 0x080057D0 | the renderer reads it and formats it |
| field_02 | `0x02` | 1 B | 0x080057EE | the renderer reads it and formats it |
| reserved_03_2b | `0x03` | 41 B | - | no reader found |
| root_array | `0x2C` | 4 B | 0x0800EB4C | `Map_ReadRoot` loads it, scales the index by four and follows the word |
| reserved_30_37 | `0x30` | 8 B | - | no reader found |

## root

One 80-byte record named by a word of an entry's `root_array`. 336 records.

| field | offset | width | load site | evidence |
|---|---|---|---|---|
| reserved_00_13 | `0x00` | 20 B | - | no reader found |
| layer_0 | `0x14` | 4 B | 0x0800525E | the loader reads the four words at `+0x14 + 4*i` |
| layer_1 | `0x18` | 4 B | 0x0800525E | the same loop |
| layer_2 | `0x1C` | 4 B | 0x0800525E | the same loop |
| layer_3 | `0x20` | 4 B | 0x0800525E | the same loop |
| row_count | `0x24` | 4 B | 0x08005FE4 | the loop bound over the 24-byte rows |
| row_table | `0x28` | 4 B | 0x08005FF0 | the loop's base, indexed by `24 * i` at 0x08005FF2 |
| reserved_2c_47 | `0x2C` | 28 B | - | no reader found |
| container_48 | `0x48` | 4 B | 0x080050DA | the loader decodes the container this word names at 0x0800514E's sibling path |
| tile_banks | `0x4C` | 4 B | 0x08005148 | the loader reads the table here and decodes the container its selected entry names |

## array

The word array an entry's `root_array` names: one or more root addresses, one record per entry.

| field | offset | width | load site | evidence |
|---|---|---|---|---|
| roots | `0x00` | 4 B each | 0x0800EB4C | `Map_ReadRoot` scales the index by four and loads the word |

## layer

A record of `0x18` bytes plus a word per chunk. 1,294 records carry the handler word `0x080056A1`;
the other 50 layer records of the image carry another word and no reader, so they stay in the raw
class and out of this table.

| field | offset | width | load site | evidence |
|---|---|---|---|---|
| handler | `0x00` | 4 B | 0x080056A0 | every record here names this Thumb code address, and its body reads the record's counts and chunk array |
| declared | `0x04` | 4 B | tools/research/FORMAT_REUSE.md | the declared size, recorded with this family's other-title comparison |
| reserved_08_13 | `0x08` | 12 B | - | no reader found |
| rows | `0x14` | 1 B | 0x080052FA | the handler loads it as the row count |
| columns | `0x15` | 1 B | 0x080052FC | the handler loads it as the column count |
| reserved_16_17 | `0x16` | 2 B | - | no reader found |
| chunks | `0x18` | 4 B each | 0x08005310 | the handler indexes the array by the product of the two counts |

## row

One of the 24-byte rows at a root's `row_table`, `row_count` of them. 710 rows.

| field | offset | width | load site | evidence |
|---|---|---|---|---|
| word_00 | `0x00` | 4 B | 0x08012CB0 | the row's consumer copies three words into its object |
| word_04 | `0x04` | 4 B | 0x08012CB0 | the same copy |
| word_08 | `0x08` | 4 B | 0x08012CB0 | the same copy |
| word_0c | `0x0C` | 4 B | 0x08012CB6 | the same copy's fourth word, and read again at 0x08012CC2 |
| reserved_10_15 | `0x10` | 6 B | - | no reader found |
| byte_16 | `0x16` | 1 B | 0x08012CBE | the consumer copies it into its object |
| byte_17 | `0x17` | 1 B | 0x08012CC6 | the consumer tests it for zero |

## The write register

`Map_ReadRoot` reads its index as one-based: the word it returns is `array + 4 * index - 4`, so
index 1 is the array's first word.
