# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added

- `docs/banner.png`, shown centred at the top of the README.
- `tools/maprecords/` holds the map record family as five tracked tables, one record per row with
  named fields and each pointer written as a record label, and encodes those rows back into
  `build/maprecords/`. `LAYOUT.md` cites a load site for every named field, `--check` refuses a row
  whose bytes are not the image's and a field with no citation, and the null permutes the record
  extents and finds no record. `generate_containers.py` splits the retail slices at the runs the
  tables emit, so 46,397 B of the family are assembled from source and the gate's raw class falls by
  the same bytes.

- `tools/research/data_census.py` classes the 3,630,726 B the gate's raw class holds outside every
  accepted container: twelve reader classes that cite the load site in walked code which names the
  family's base, and three `no reader found` classes for a fill run, a run of image addresses and the
  residual, and the classes partition the region exactly. `tools/research/DATA_CENSUS.md` is the page
  it derives and `--check` refuses a difference; the null reverses the region's halfword order and
  leaves no reader-backed byte.

- `tools/sprites/` holds the sprite directory, definition and piece records as three tracked tables,
  one record per row with named fields and each pointer written as a record label, and encodes those
  rows back into `build/sprites/`. `LAYOUT.md` records the evidence that fixes every named field,
  `--check` refuses a row whose bytes are not the image's and a field with no citation, and the null
  permutes the record extents and finds no record. `generate_containers.py` splits the retail slices
  at the runs the tables emit, so 26,508 B of the family are assembled from source and the gate's raw
  class falls by the same bytes.

- `tools/text/` holds the text storage as four tracked tables: the 128-record roster table, the 124
  strings it names, the 43 objective texts and the 256-entry font offset table, one record per row
  with named fields and each string pointer written as a record label, and encodes those rows back
  into `build/text/`. `LAYOUT.md` records the evidence that fixes every named field, `--check`
  refuses a row whose bytes are not the image's and a field with no citation, and the null permutes
  the record and string extents and finds no record of any family. `generate_containers.py` splits
  the retail slices at the runs the tables emit, so 20,477 B of the family are assembled from source
  and the gate's raw class falls by the same bytes.

### Changed

- The container census rejects a stored (kind 0) hit that overlaps a container named by the map layer
  chunk directory and accepts the chunk instead, since the chunk decodes and re-encodes to the image's
  own bytes. 1,256 stored hits give way to 3,631 chunks, and the share of the ROM that builds from
  tracked source rises from 34.0739 % to 45.3781 %.
- `tools/compress/container_census.py` rejects a kind-0 hit whose extent overlaps a container the
  map layer chunk directory names that re-encodes byte-exact, and accepts that chunk in its place:
  1,256 stored hits over 798,968 B of extents leave the population and 3,631 chunks over 887,984 B
  join it, so the census holds 13,913 containers (3,994 stored, 9,919 packed) covering 4,775,808 B.
  The same re-carve releases 53,022 B of map record bytes the map emitter was withholding, and
  `tools/compress/generate_containers.py` stops emitting the two code fragments (8 B) that now fall
  inside a carried container. `tools/research/data_census.py` classes the 3,406,114 B region that
  remains outside the containers, and the gate's source class rises from 2,858,330 B to 3,806,588 B
  (34.0739 % to 45.3781 %).
- The technique page at `0x08003684` is one function: a `tools/code/CENSUS_EVIDENCE.csv` entry row keeps
  it from being corrected to the push that follows its two halfword adds, and two fragment rows retire
  the two starts the census had opened inside its body, so the emitter writes one file where it wrote
  three and the disposition of the status page's pool now cites the bytes at `0x08003B34` instead of a
  branch nothing reaches. `Menu_DrawTechniqueDetail` at `0x08003520` and the input state
  `Input_State` at `0x0300229C` are named, each with a behaviour case in the fourteenth batch.
- The emitter reads `tools/code/CENSUS_EVIDENCE.csv` and leaves a recorded data row out of the
  generated code files, so the two runs the census stopped counting as code are carried into the build
  as slices of the image like any other data. The two tests that expect one generated file per function
  start keep that rule without an exemption.
- The census stops counting two data runs as code (the status page's literal pool and the two words and
  translation-unit name that follow the level-curve readers) and keeps two handlers whole whose body
  starts a few bytes before its prologue, one of them named `Character_AwardXpToActive`. A new
  `tools/code/CENSUS_EVIDENCE.csv` carries those four addresses with their evidence, and the split, the
  census and the recompiler export read it.
- `tools/` holds only what the build, the gate or a check runs, one directory per subsystem, and
  `tools/README.md` names what runs every file in it. The tables a check reads sit beside the reader
  that derives them, and the page each generator writes sits beside the generator.
- `docs/` is the reader guide: `docs/README.md` says what the game's code is organised into, how to
  build, how names are chosen and where to look next; the naming, readability and definition-of-done
  pages and the RAM ledger stay beside it.
- `tools/compress/compress.exe` is no longer tracked. `rebuild.cmd` builds it from the vendored
  jcalg1 source under `tools/compress/jcalg1/` with `tools/compress/build.cmd` when it is absent,
  and the build then re-encodes every container with the binary it built.
- Nine transcribed starts in the character-stats slice carry the names their bytes prove: the five
  readers of the level curve, the XP award and the level-up it applies, the level setter and the
  status page, each with a behaviour test and a ledger row.
- `README.md` follows the house layout: the tagline, a license, platform and function-count badge
  row that states nothing by colour, a Contents entry for every section, and a comment in place of the
  banner, the demo GIF and the social preview until each exists. Its layout table lists only the
  directories a clone or a build produces, and the build section names the test runner `check.cmd`
  needs.

### Fixed

- `tools/research/test_data_census.py` takes the image from the shared `tools/testkit.py` helper, so
  the five tests that need the retail image skip with the missing path named where the image is
  absent and CI needs no game copy; the two tests over synthetic inputs still run.

- `tools/compress/generate_containers.py --write` builds `tools/compress/compress.exe` through
  `tools/compress/build.cmd` when it is absent, and fails with one message naming `build.cmd` when
  that build exits nonzero or produces no binary, so a fresh clone regenerates without a manual step.
- `tools/research/device_access.py --ledger` passes every row: eleven evidence cells quoted a value
  the body does not reach, such as a caller's table or a value a stub supplied, and each now quotes
  the address, literal or stored value the body itself carries.
- `docs/CODE_INDEX.md` says `none` for the four starts the emitter does not write, the two boot
  starts and the two inside container runs; its test asserts that rather than a file for every
  start, and `README.md` says the same.
- The status-page and level-up behaviour tests assert the argument registers of every call they
  record, so the record fields read, the stat pointers passed and the values written are pinned;
  `tools/code/thumb_vm.py` reports those arguments beside the calls.

The notes for the changes before this one stay in the repository history.
