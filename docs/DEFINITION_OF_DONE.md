# Definition of done

One target for every change: the full image, as `python tools\gate\gate.py` measures it.

## What counts as source

- Code assembled or compiled from tracked source.
- A tracked table of plain numbers whose rows have a named layout and a consumer or a structural
  proof. An unlabeled byte dump is not source.
- A byte-exact generator that re-encodes assets from the builder's own ROM at build time, with
  nothing from the ROM committed. An identity copy is not source.

## The finish line

- 100 % of the 8,388,608 B image. A byte that cannot be reached is named irreducible, with its
  reason.

## The gate output

`python tools\gate\gate.py` prints the figures for the tree it is run on. `README.md` carries the
progress figure, and the README-numbers check in `tools/lint/lints.py` holds it to the gate's own
count, so no second copy of the figures is kept here.
