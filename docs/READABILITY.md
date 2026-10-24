# Readability

What a reader meets in this tree, and the rules a change has to keep. `python tools\code\code_index.py`
maps a function to its file; `python tools\gate\gate.py` prints the figures a change is measured by.

The audience is a reader who has just cloned the repository and wants to find, read, change and
verify one function. Readability in this tree comes from names, layout and documents: the build
itself carries no comments, so a file has to say what it is by how it is named and where it sits.

## The newcomer path

1. clone the repository and read `README.md`;
2. save your own copy of the game as `baserom.gba`;
3. `extract.cmd`;
4. `rebuild.cmd`;
5. find a function by name in `docs/CODE_INDEX.md`, read its file under `build\code`, change it;
6. `python tools\gate\gate.py` prints `DIGEST MATCH` and `GATE PASS`.

Steps 2 to 4 and 6 are in `README.md`, and [README.md](../README.md) walks the same path with the
evidence rules attached.

## The rules

- A generated code file carries one function start. It is named after the function when the name is
  proven and after the address when it is not, so a reader looking for a function starts from
  `docs/CODE_INDEX.md` rather than from `asm\remainder.s`, which carries the token list only.
- A literal hardware register becomes its GBATEK name from the single include `asm/registers.s`. A
  RAM word becomes a symbol only where a ledger evidence class proves its role; every other one
  stays a literal and is counted in `tools/lint/READABILITY_BASELINE.txt`, whose figure only falls.
- A table a generator decodes gets a named record family and a tracked page; an undecoded slice stays
  a slice and is counted by the gate. `tools/research/TABLE_LEDGER.csv` names the record families a
  tracked reader decodes, with the reader and the page that measures it.
- A constant that names a device field, a stride or a sentinel becomes an equate; a plain arithmetic
  literal stays.
- A test name states the behaviour its assertions prove, in
  `test_<what the code does>_<the condition it holds>`. A test that names only an address names
  nothing.

## What is enforced

Three checks in `tools\lint\lints.py` hold the rules where a commit can be refused:

- `READABILITY-ratchet` compares the live count of unnamed RAM literals and of literal hardware
  registers with `tools/lint/READABILITY_BASELINE.txt`. A count above the baseline fails, and so does
  a count below it, because the figure only falls and the baseline is lowered in the same commit that
  lowers it.
- `READABILITY-index` fails when `docs/CODE_INDEX.md` is not what `tools/code/code_index.py`
  derives, so a file that breaks the layout rule breaks the index with it.
- `READABILITY-path` fails when neither `README.md` nor `INSTALL.md` names one of the path's commands
  or the index.

The first two read the retail image, so they are skipped in CI, which runs without it, exactly as
every ROM-gated test is. The cold gate runs them with the image present.

## What a count means

A count here is measured, not estimated. `tools/research/readability_audit.py` reads the tracked
`asm\*.s` files and every generated file in `build\code`, counts the hex tokens by address range,
counts the immediate operands, walks `tools/code/FUNCTION_BOUNDS.csv` and `tools/code/names.csv` for
the function figures, counts the rows of `tools/research/TABLE_LEDGER.csv` for the table figures,
takes the slice count from the gate's own `incbin_ranges`, and scans the tracked Python for
definitions nothing refers to and for blocks of eight lines or more that repeat. A table-ledger row
must quote a token its own page carries, so a family cannot be named past the page that measures it.

`asm\registers.s` is left out of the address counts on purpose: its right-hand sides are the one
place in the tree where a register address belongs as a literal, and every other file names the
register instead.
