# tools

Everything here is run by the build, by the gate, or by a check. Nothing else lives in this folder.
`extract.cmd` checks the image, `rebuild.cmd` generates, assembles and re-encodes it, and
`python tools\gate\gate.py` proves the result against the retail sha256. CI runs
`tools/check_links.py`, `tools/lint/lints.py` and `python -m pytest -q tools`; `check.cmd` runs the
first two and the link check's test. A table a check reads sits beside the reader that derives it.

## Top level

| file | what it does | what runs it |
| --- | --- | --- |
| `README.md` | this page | - |
| `check_links.py` | fails on a markdown link that does not resolve, or on a commit id cited in a page | `check.cmd`, CI |
| `test_check_links.py` | the tests for `check_links.py` | CI |
| `test_conftest.py` | the tests for the repository's `conftest.py`, which creates the pytest temporary root | CI |
| `testkit.py` | the ROM-gated test helpers: skip when the image is absent, assert that a call was refused | the ROM-gated tests |
| `incbin.bat` | cut one image range into a `baserom.gba_0x…_0x….extracted` slice | `rebuild.cmd` |

## extract/

| file | what it does | what runs it |
| --- | --- | --- |
| `extract/slice_rom.py` | writes one `baserom.gba_0x…_0x….extracted` slice from the image | `incbin.bat` |

## code/

| file | what it does | what runs it |
| --- | --- | --- |
| `code/emit_code.py` | decodes the split's code rows and literal pools into assembler source, one file per function start, and re-derives each from the builder's image | `rebuild.cmd`; the gate runs two of its tests |
| `code/code_index.py` | writes `docs/CODE_INDEX.md`, one row per function start and the file that carries it | `lints.py` (`READABILITY-index`), `test_code_index.py` |
| `code/function_bounds.py` | classifies every emitted entry from the bytes and derives the bounds, ends and allow tables | `rebuild.cmd --check`, `lints.py`, `test_function_bounds.py` |
| `code/name_table.py` | reads the name table, the naming ledger, the RAM ledger and the address-named baseline | `emit_code.py`, `function_bounds.py`, `lints.py` |
| `code/thumb_vm.py` | runs one function from a private image copy on crafted registers and memory, and records its stores, calls and call arguments | `test_behaviour.py`, `test_thumb_vm.py`, the behaviour rows of the naming ledger |
| `code/names.csv`, `code/ram.csv` | the function name table and the data name table, `address,name` | `name_table.py`, `emit_code.py` |
| `code/CENSUS_EVIDENCE.csv` | the addresses whose entry or data status is not derivable from the image alone, with the evidence for each | `code_split.py`, `emit_code.py`, `function_bounds.py` |
| `code/NAMING_LEDGER.csv`, `code/NAMING_BASELINE.txt` | one row per promoted name with its evidence class and evidence; the count of functions that still carry the address form | `lints.py` (`NAMING-symbol`, `NAMING-behaviour-test`, `NAMING-address-ratchet`) |
| `code/FUNCTION_BOUNDS.csv`, `code/FUNCTION_ENDS.csv`, `code/FUNCTION_ENTRY_ALLOW.csv`, `code/RUNTIME_LABELS.csv` | the entry census, every start's end and mode, the flagged starts with a recorded reason, and the entries a bounded runtime run reached | `function_bounds.py --check`, `lints.py`, `export_inputs.py`, `unproven_remainder.py` |
| `code/test_behaviour.py`, `code/test_code_index.py`, `code/test_emit_code.py`, `code/test_function_bounds.py`, `code/test_thumb_vm.py` | the tests for the five modules above | CI; the gate runs two of `test_emit_code.py` |

## split/

| file | what it does | what runs it |
| --- | --- | --- |
| `split/code_split.py` | measures the code and data split of the image and writes its page and extents CSV | `--check`, `lints.py`, `emit_code.py`, `function_bounds.py`, `export_inputs.py`, `runtime_watch_targets.py`, `unproven_remainder.py` |
| `split/CODE_SPLIT.md`, `split/CODE_SPLIT.csv` | the split page and its per-extent ledger | `code_split.py --check`; the page is read by `lints.py` for the README figure |
| `split/test_code_split.py` | the tests for the split | CI |

## compress/

| file | what it does | what runs it |
| --- | --- | --- |
| `compress/main.cpp` | the compressor driver: reads a payload, writes the kind-1 container the assembly expects | `compress.exe`, built by `build.cmd` |
| `compress/CMakeLists.txt` | builds `compress.exe` from the driver and the jcalg1 MASM source | `build.cmd` |
| `compress/build.cmd` | finds the Visual Studio cmake through vswhere, builds the compressor and copies it beside the driver | `rebuild.cmd` |
| `compress/jcalg1/` | the jcalg1 r5.32 compressor as MASM source (`jcalg1_c.asm`, `jcalg1_gusocb.asm`, `string.asm`, `checksum32.asm`, `jcalg1_static.asm`) with its header, includes, notes and MIT licence (`jcalg1.h`, `jcalg1_proto.inc`, `jccomp.inc`, `revision.txt`, `README.md`, `LICENSE`) | `CMakeLists.txt` |
| `compress/container.py` | the container header and the kind-0, kind-1 and kind-2 payload | `generate_containers.py`, `container_census.py`, the tests |
| `compress/jcalg1.py` | the JCALG1 body decoder and the encoder driver the build re-encodes through | `generate_containers.py`, the tests |
| `compress/generate_containers.py` | re-encodes every packed container in the image and writes the token list `asm/remainder.s` | `rebuild.cmd` |
| `compress/container_census.py` | scans the image for containers, with its permuted-image null, and writes the census page and ledger | `--check`, `generate_containers.py` |
| `compress/CONTAINER_CENSUS.md`, `compress/CONTAINER_CENSUS.csv` | the container population, its method and its per-container ledger | `container_census.py --check`; the CSV is read by `unproven_remainder.py` |
| `compress/test_jcalg1.py`, `compress/test_generate_containers.py`, `compress/test_container_census.py` | the tests for the container layer | CI |

## gate/

| file | what it does | what runs it |
| --- | --- | --- |
| `gate/gate.py` | checks the image, runs the lints and the two cited emission tests, purges the objects, rebuilds, and proves the digest and the byte accounting | `extract.cmd` (`--verify-rom`), you, the README's build path |
| `gate/test_gate.py` | the tests for the gate | CI |

## lint/

| file | what it does | what runs it |
| --- | --- | --- |
| `lint/lints.py` | the naming, layout, hardware-literal, ROM, README-number, bounds and recompiler checks | `check.cmd`, CI, `gate/gate.py` |
| `lint/READABILITY_BASELINE.txt` | the admitted counts of unnamed RAM literals and literal hardware registers | `lints.py` (`READABILITY-ratchet`) |
| `lint/test_lint.py` | the tests for the lints | CI |

## recomp/

| file | what it does | what runs it |
| --- | --- | --- |
| `recomp/export_inputs.py` | derives the recompiler's entry list from the census and the image's own targets | `lints.py` (`RECOMP-census`), `function_bounds.py`, `runtime_watch_targets.py`, `runtime_watch_results.py` |
| `recomp/RECOMP_INPUTS.toml` | that entry list, with a mode, size and origin per code row | `export_inputs.py --check` |
| `recomp/test_export_inputs.py` | the tests for the export | CI |

## mapcontainer/, text/, tilebank/

| file | what it does | what runs it |
| --- | --- | --- |
| `mapcontainer/mapcontainer.py` | the map block's container, entry, root, root-table and layer records, with a `--check` that re-derives them | `format_reuse.py`, `test_mapcontainer.py` |
| `text/text_storage.py` | the string-table storage, decoded and re-encoded | `format_reuse.py`, `test_text_storage.py` |
| `tilebank/tilebank.py` | the tile bank's decode and encode | `format_reuse.py`, `test_tilebank.py` |
| `mapcontainer/test_mapcontainer.py`, `text/test_text_storage.py`, `tilebank/test_tilebank.py` | the tests for the three format readers | CI |

## research/

| file | what it does | what runs it |
| --- | --- | --- |
| `research/readability_audit.py` | counts the unnamed RAM and hardware literals and the generation rules behind them | `lints.py` (`READABILITY-ratchet`) |
| `research/TABLE_LEDGER.csv` | one row per named record family, its reader and the page that measures it | `readability_audit.py` |
| `research/callers.py` | ranks every unnamed census start by the distinct starts whose bounds reach it | `test_callers.py` |
| `research/device_access.py` | re-reads every naming-ledger row against the body its evidence quotes | `test_device_access.py` |
| `research/library_match.py` | matches a function's bytes against the members of the ADS 1.2 libraries | `test_library_match.py` |
| `research/opcode_stream.py` | decodes the opcode streams the map entries name and re-encodes them | `format_reuse.py`, `test_opcode_stream.py` |
| `research/asset_directory.py` | the asset directory's descriptor and PCM stream, decoded and re-encoded | `format_reuse.py`, `test_asset_directory.py` |
| `research/format_reuse.py` | compares each format with Buu's Fury's grammar and writes the verdict page | `--check`, `test_format_reuse.py` |
| `research/FORMAT_REUSE.md` | the per-format verdicts | `format_reuse.py --check` |
| `research/runtime_watch_targets.py` | derives the watch target table from the split and the export | `--check`, `runtime_watch_results.py`, `runtime/watch_sweep.py` |
| `research/RUNTIME_WATCH_TARGETS.csv` | one row per watch target | `runtime_watch_targets.py --check`, `runtime_watch_results.py`, `watch_sweep.py` |
| `research/runtime_watch_results.py` | imports a bounded run's record and writes the results page and CSV | `--import`, `--check`, `test_runtime_watch_results.py` |
| `research/RUNTIME_WATCH_RUNS.csv`, `research/RUNTIME_WATCH_HITS.csv` | the run's inputs and its stops, imported by the results reader | `runtime_watch_results.py` |
| `research/RUNTIME_WATCH_RESULTS.csv`, `research/RUNTIME_WATCH_RESULTS.md` | the per-target verdict of the recorded runs | `runtime_watch_results.py --check` |
| `research/unproven_remainder.py` | splits the bytes no proven function bounds into their reasons | `--check`, `test_unproven_remainder.py` |
| `research/UNPROVEN_REMAINDER.csv` | that split, one row per reason | `unproven_remainder.py --check` |
| `research/test_asset_directory.py`, `research/test_callers.py`, `research/test_device_access.py`, `research/test_format_reuse.py`, `research/test_library_match.py`, `research/test_opcode_stream.py`, `research/test_readability_audit.py`, `research/test_runtime_watch_results.py`, `research/test_runtime_watch_targets.py`, `research/test_unproven_remainder.py` | the tests for the readers above | CI |

## runtime/

| file | what it does | what runs it |
| --- | --- | --- |
| `runtime/watch_sweep.py` | arms one execute breakpoint per target on a runtime's remote debug stub and records which targets ran | `test_watch_sweep.py` |
| `runtime/RUNTIME_WATCH.md` | what a watch run needs, its duration bound, its outputs and its checks | the reader of this folder |
| `runtime/test_watch_sweep.py` | the tests for the sweep: every refusal, and that no process starts | CI |
