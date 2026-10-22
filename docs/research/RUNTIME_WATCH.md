# Runtime watch

An execute watch is the next evidence source for the bytes the static split cannot settle: the
swept candidate runs, the register branches no literal resolves, and the interrupt slots.

## What a run needs

* A private copy of the retail image, outside the tracked tree, whose sha256 is the one the image
  gate records. The driver computes the digest itself and refuses any other file.
* `docs/research/RUNTIME_WATCH_TARGETS.csv`, the watch target table.
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
* The tracked record: `RUNTIME_WATCH_RUNS.csv` and `RUNTIME_WATCH_HITS.csv`, written by
  `tools/research/runtime_watch_results.py --import`. The generated page
  `RUNTIME_WATCH_RESULTS.md` and its CSV are re-derived by `--write` and byte-compared by
  `--check`.

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

## Run record

One run, 900 s bound and 900.0 s kept, against the private copy whose digest matched. All 878
target starts and the liveness pc armed; 720 merged ranges. The liveness pc `0x03000824` fired
17,160 times, so the channel was live for the whole run. 23 target starts executed: 9 of the 825
candidate rows (194 B outside the code the export names), 14 of the 39 unresolved register sites
(28 B inside it, already named), and none of the 14 slots, which an execute watch cannot score
because they are data words the dispatcher reads.

## Recorded entries

A second bounded run used the translation runtime's own fallback recorder instead of a breakpoint
watch: 10,800 emulated frames (180 s of game time), no input, headless, one process. It reached the
publisher logo, the intro cards, the title screen and one attract panel, and its frame hash at the
bound equals an interpreter run of the same frame count. The recorder wrote 93 entry points the
translation was missing (75 in the image, 18 in the copied interrupt region).

`docs/research/RUNTIME_LABELS.csv` carries those entries as region, address and mode. The results
reader re-derives each one's span from the image and demands that it start an instruction the walk
decodes; all 93 pass, giving 63 extents / 226 B, none of them already named. A recompile seeded with
those entries ran the same 10,800 frames with no interpreter fallback and the same hash.

The two runs agree at the bound and at the logo, intro and title samples. Inside the attract window
they show the same card at a one-frame animation phase difference (frames 7,000, 7,200, 7,300 and
7,400 differ), so equality is claimed at the sampled frames, not per frame.

## What a run does not settle

A start that did not execute in this run is not dead: the run is one boot-to-attract window with
no input, and a later scene can reach it. A silent target therefore stays unclassified. Gameplay,
menus and map loads were not reached, so neither the target table nor the recorded entries bound
what the whole game executes.
