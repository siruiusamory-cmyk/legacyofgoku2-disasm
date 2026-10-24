# Runtime watch

An execute watch is the evidence source for the bytes the static split cannot settle: the swept
candidate runs, the register branches no literal resolves, and the interrupt slots.

## What a run needs

* A private copy of the retail image, outside the tracked tree, whose sha256 is the one the image
  gate records. The driver computes the digest itself and refuses any other file.
* `tools/research/RUNTIME_WATCH_TARGETS.csv`, the watch target table.
  `tools/research/runtime_watch_targets.py --check` re-derives it from the split and the
  recompiler export.
* A GBA runtime that opens a remote debug stub on port 2345. The driver starts it, arms one
  breakpoint per target start and one on the liveness pc, and reads the program counter at each
  stop. It writes no emulated memory, presses no key and drives no window.
* An output directory.

## Duration

The driver's bound is a wall-clock duration, given before the run with `--seconds`. It stops the
run when the bound expires, and every run so far has kept it.

## Outputs

* `ranges.txt`: the merged target ranges as bus addresses, one `start end` pair per line.
* `watch-log.csv`: `pc,elapsed,kind` per stop, where `kind` is `target`, `liveness` or `other`.
* `run.json`: the run's inputs, counts and the digests of the copy and the runtime.
* The tracked record, beside the reader that writes it: `tools/research/RUNTIME_WATCH_RUNS.csv` and
  `tools/research/RUNTIME_WATCH_HITS.csv` come from `tools/research/runtime_watch_results.py
  --import`, which also writes the generated page `RUNTIME_WATCH_RESULTS.md` and its CSV with
  `--write` and byte-compares them with `--check`.

The proposed `runtime` class is a proposal: the split is not edited, so no byte moves without a
separate promotion.

## Checks

* `tools/runtime/watch_sweep.py` starts nothing unless `--run`, a private copy, the recorded
  digest, a runtime and an output directory are all given. Its tests cover each refusal and prove
  that no process is started.
* The liveness breakpoint sits on the handler the startup block installs at the interrupt vector,
  so a hit is a frame that handler ran. A run with no liveness hit is void.
* A target's breakpoint is removed at its first hit, so each start is scored once and the run is
  not throttled by a hot loop.
* The driver kills only the process it started.

## The record

The run's figures are the tracked tables, not a copy of them: the seconds kept and the liveness
count in `tools/research/RUNTIME_WATCH_RUNS.csv`, the stops in `RUNTIME_WATCH_HITS.csv`, and the
per-target verdict in `RUNTIME_WATCH_RESULTS.md`. `tools/code/RUNTIME_LABELS.csv` carries the entry
points a second bounded run recorded from the translation runtime's own fallback recorder, as
region, address and mode; the results reader re-derives each one's span from the image and demands
that it start an instruction the walk decodes.

## What a run does not settle

A start that did not execute in this run is not dead: the run is one boot-to-attract window with
no input, and a later scene can reach it. A silent target therefore stays unclassified. Gameplay,
menus and map loads were not reached, so neither the target table nor the recorded entries bound
what the whole game executes.
