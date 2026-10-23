# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Changed

- The recompilation input `docs/research/RECOMP_INPUTS.toml` carries one `[[code]]` row per
  closed row of `docs/research/FUNCTION_ENDS.csv`, with its start, end, mode and origin. Its
  `--check` reports a census row with no code row and a code row with no mode, and the
  `RECOMP-census` check holds the tracked export to the same record.

- The project is named a disassembly, not a decompilation: `README.md` states what the tree is,
  what it is not, and that its progress figure measures source-built bytes, not C.

### Added

- `tools/split/code_split.py` reads four data channels the entry census never looked at for an
  entry: a run of two or more consecutive odd words that holds no proven entry, a table the walked
  code names with a literal load, an odd word in a literal pool a walked load reaches, and an odd
  word the startup copy carries into IWRAM. Each carries its own permuted-image null, and the
  table-held class grows by the bytes they reach.

- `tools/split/code_split.py` accepts a word no table names when its own linear run closes: the run
  meets no halfword outside the ARMv4T encoding, ends on a return or on a branch into bytes a class
  already holds, and reaches every branch target it makes either as one of its own instruction
  boundaries or as bytes a class already holds. Its bytes join the table-held class only when the
  permuted image accepts fewer than 5 % as many words as the image does; on this image the counts
  are 96 against 90, so the channel contributes no entry and no byte, and
  `docs/research/CODE_SPLIT.md` prints both counts and the share.

- `tools/research/unproven_remainder.py` splits the bytes of the address-taken walk bound that no
  proven function bounds, into the data formats, the padding, the code a closing run proves, the
  words a pointer table holds and a residual per reason, and prints the closing run's rate on the
  census starts, the runtime entries, the named words inside a format and inside padding, and its
  permuted null. It writes `docs/research/UNPROVEN_REMAINDER.csv`.

- `tools/research/unproven_remainder.py` claims the closing run's bytes only when their measured
  null share is under 5 % of the class; at or over the bar the bytes take the residual reason for a
  run below it. It prints the measured null, the class size and the bar on every run. On this image
  the null is 44 B of 116 B, 37.9310 %, so those bytes sit in that residual and the code row is
  empty.

- `docs/research/FUNCTION_ENDS.csv` gives every census start an end, from a walk to its return or
  to the next start, and folds the runtime-only entries into the same bounds.
  `docs/research/FUNCTION_ENTRY_ALLOW.csv` records the starts that open no function, corrected to
  the prologue they lead into, and the `BOUNDS-entry-allow` check holds every flagged start to that
  record.

- `tools/check_links.py` follows an HTML `src` or `href` in markdown as well as a markdown link,
  and `check.cmd` runs the link check, the source checks and the link check's test.

- `.recomp.json`, the project entry the recompilation directory reads, with the retail game's sha1.

- The build: `asm/buu.s` and `asm/crt0.s` assembled with ARM Developer Suite 1.2, linked against
  `scatter.ld`, and converted to `build\ROM_START`.

- `tools/gate/gate.py`, which purges every object, rebuilds, compares the sha256 with the retail
  image, counts the source and raw-data classes, and requires them to sum to the image size.

- `tools/lint/lints.py`, `tools/check_links.py`, `tools/testkit.py` and their tests, with the README
  figure checked against the gate's own count.

- `tools/split/code_split.py`, which walks the image from the reset vector and the startup block,
  follows the branch, return and literal-pool targets that walk proves, accepts an address-taken
  odd word only when its paths return and branch, reads the overlay length from the startup DMA
  kick, names the one jump table, and writes `docs/research/CODE_SPLIT.md` with its extents CSV;
  `--check` refuses a stale pair, and the README split figures are checked against the document.

- `extract.cmd`, which checks the retail image's size, sha1 and game code before any build.

- `tools/recomp/export_inputs.py` and `docs/research/RECOMP_INPUTS.toml`, the mode of every code
  extent with its origin, the entries, the overlay copy, the one jump table and the identity;
  `--check` refuses a stale file.

- The split's walk rule refuses the ARMv5 `blx` halfword (0x4780..0x47FF), an instruction this
  CPU cannot execute.

- The split's call closure: every `bl` target of walked code is proven to a fixed point, a
  branchless entry is accepted only when a call or a function-pointer table names it, the jump
  table's `bhs` bound is 14 entries rather than 15, and the interrupt vector store at
  `[0x03007FC0 + 0x3C]` and the IWRAM handler and dispatch table it installs are measured.

- The register `bx` census over the walked bytes, and the split's dispatch scan reading each
  extent whole instead of stopping four bytes early.

- `.github/workflows/check.yml`, which runs the source checks, the link check and the ROM-free tests.

- `tools/mapcontainer/mapcontainer.py`, which ports Buu's Fury's map container finders to this
  image: the entry table at file 0x409368, its root pointer arrays, the root record's tile-bank
  table, the dominant layer record's counts and container array, and the root table; `--check`
  pins the census and both permuted nulls.

- `tools/research/opcode_stream.py`, which pins the interpreter at 0x080092E4 and its 30-entry
  table at 0x083B5C00, prints the operand length every opcode reads with the halfwords that fix
  it, decodes the 86 streams of the objective table at file 0x6D68DC and re-emits their bytes;
  `--check` refuses a difference.

- `tools/research/format_reuse.py` and `docs/research/FORMAT_REUSE.md`, the per-format verdicts
  against Buu's Fury's grammar with the bytes and the reader each one rests on; `--check`
  re-derives the page from the image.

- The split's four reaching channels and its eight classes: a register-loaded code address
  resolved to its reaching definition, a function-pointer table, repeated record word or
  literal-named slot table, a Thumb prologue swept linearly to its return, and the halfword after
  a return; each with its own null over a halfword-permuted image, and the bound a decode puts on
  the code still unnamed.

- `docs/research/RECOMP_INPUTS.toml` carries every accepted code class with its tag, and the
  entries of all five channels, so a recompiler reads the table-held, prologue-sweep and gap-fill
  extents it used to miss.

- A channel whose null is not below its accept rate emits no entry and no byte: the Thumb prologue
  sweep is measured and reported, its bytes stay unclassified, the export carries none of its
  entries, and the gap fill re-measures without it.

- `tools/compress/`, the Webfoot container codec, the JCALG1 body decoder and the encoder oracle,
  with the container round trip and the decoder's refusal tests.



- `tools/research/container_census.py` and `docs/research/CONTAINER_CENSUS.md` with its per-row
  CSV, the accepted population and the permuted null.
- `tools/research/asset_directory.py` and the sprite asset directory row in
  `docs/research/FORMAT_REUSE.md`, with the resolver quote and the id-30 chain to a container.
- `tools/compress/generate_containers.py`, `asm/remainder.s` and 1,938 generated container runs;
  the source class grows from 64 to 1,637,304 B.
- `tools/compress/test_generate_containers.py`, which pins the tracked token list against the runs
  the image derives.
- `tools/tilebank/tilebank.py` and its test, which read the map tile-bank table at 0x084DF574 as 32
  containers declaring 16,384 bytes, decode the three 4,096-byte character banks, quote the two
  loaders at 0x0800510C and 0x080072C4 with the dispatcher at 0x0801F394, and refuse a bank whose
  header disagrees; a shuffle of the whole image and of the block alone decode 0 banks.
- `tools/text/text_storage.py` and its test, which quote the string routine at 0x0801F702 and the
  256-entry u16 glyph table at 0x08028724, resolve 124 distinct biography strings of 15,512 bytes
  inside the stored container at 0x6F4394 and 43 objective strings of 1,897 bytes outside it, and
  refuse a string byte outside the printable set; both permutations resolve 0 strings.
- The tile-bank and text rows of `docs/research/FORMAT_REUSE.md`, generated by
  `tools/research/format_reuse.py` from the two tools above, with the reader instructions printed
  from the tools' own quote tables.

- `tools/research/runtime_watch_targets.py` and `docs/research/RUNTIME_WATCH_TARGETS.csv`, the 825
  swept candidate-code runs, the 39 register-branch sites no static source resolves and the 14
  interrupt slots; `--check` pins all three populations against the split and the export.

- `tools/research/runtime_watch_results.py`, which folds a watch log's program counters into the
  targets that hold them and merges the hit targets into a proposed `runtime` class without
  touching the split; its test reads a hand-written log fixture.

- `tools/runtime/watch_sweep.py`, which refuses to start without `--run`, a private image copy whose
  sha256 is the recorded one, a logging runtime and an output directory; its tests cover every
  refusal path and prove no process is started.

- `docs/research/RUNTIME_WATCH.md`, the inputs, duration bound, outputs and safety checks a runtime
  watch run needs before one is authorised.

- `tools/runtime/watch_sweep.py` now drives a runtime's remote debug stub: it arms one breakpoint
  per target start plus the liveness pc, removes a start's breakpoint at its first hit, and records
  `pc,elapsed,kind`; its tests cover the packet framing, the register block and every refusal.

- `tools/research/runtime_watch_results.py` imports a run into the tracked run and hit tables and
  generates `docs/research/RUNTIME_WATCH_RESULTS.md` with its CSV: the executed targets per kind,
  the proposed `runtime` class and its named and new bytes; `--import`, `--write` and `--check`.

- The first runtime watch run: 900 s bound, 878 targets armed, 17,160 liveness hits at `0x03000824`,
  23 starts executed; 9 candidate rows / 194 B outside the named code and 14 register sites / 28 B
  inside it.

- `docs/research/RUNTIME_WATCH.md` records the run's inputs, bound, outputs and the reading of its
  23 hits, and what a single no-input window does not settle.

- `tools/code/emit_code.py`, which decodes the split's code rows and literal pools into assembler
  source, names a function for every entry it can place and a local label for every branch target,
  and re-derives each fragment from the builder's image (`--write`/`--check`); a row whose bytes a
  carried container holds, or that the startup sources already carry, stays a retail slice with its
  cause counted. `tools/code/test_emit_code.py` reassembles all 1,024 emitted fragments with ADS 1.2
  and compares them with the image byte for byte, skipping when the toolchain or the image is absent.

- The build runs `tools/code/emit_code.py` first, splits each retail gap in `asm/remainder.s` at the
  emitted fragments to `INCLUDE` them, and re-emits the 38 kind-2 container streams with their kind
  word: 84,404 B of code and 53,872 B of container bodies join the source class.

### Fixed

- `tools/compress/generate_containers.py` emits a packed container to the decoder's extent when
  the encoder's end-marker word is the first word of the next container, and lets that next token
  supply the word: 2,023 containers and 988,828 bytes that `compress.exe` already reproduced byte
  for byte were left as retail slices because the word would have been owned twice.

- `tools/compress/generate_containers.py` leaves a container whose payload is shorter than the
  encoder's ten-byte block header as retail bytes, and names it in the generator's census line,
  instead of handing that payload to `compress.exe`: the encoder sizes its destination as the
  payload plus four bytes, so a payload below the header overruns the destination and the process
  exits with heap corruption on some runs, which made a cold build fail at random.

- `python tools\gate\gate.py --cold` purges `build/compress-cache`, so a cold gate re-encodes every
  container instead of reading an encode store a previous build filled.
