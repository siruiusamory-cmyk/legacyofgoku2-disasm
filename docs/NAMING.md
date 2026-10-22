# Naming conventions

Every symbol the build emits carries one of two forms, and which form it carries is a statement
about the evidence for it.

## Functions

- Known purpose: `Module_Verb` in PascalCase, module first, one verb after it (`Input_ReadKeys`).
  The module names the subsystem the function works in, never the file it happens to sit in.
- Unknown purpose: `sub_` and the address as eight uppercase hex digits (`sub_0801EEFC`). No name
  is better than a name that claims more than the bytes show.
- A branch destination inside a function keeps the generator form (`loc_0801F0BC`); a `loc_` symbol
  is not a claim that a function starts there.
- One name per address and one address per name, because the symbol text is emitted verbatim into
  the link.

The name table is `tools/code/names.csv`, two columns, `address,name`. `tools/code/emit_code.py`
reads it and emits the named form for a keyed address, the address form for everything else. A key
must be an address the split proves is a code entry: a name on a byte the split does not call code
names nothing the linker can place.

## Evidence for a name

Only evidence promotes `sub_` to `Module_Verb`, never repetition, never a name borrowed from another
title, never the shape of the surrounding code. One of these classes has to hold, and the ledger row
names the class it is:

- **bios-call**: the body issues one BIOS call and does nothing else that acts, so the SWI number is
  the function's whole effect.
- **device-register**: the body writes or reads a hardware register, and the register, its offset and
  the constant written are all fixed in the body.
- **callee-role**: the function is a trampoline, an accessor or a wrapper whose only action is a known
  callee or one field move, and its callers and callee are both proven addresses.
- **structural-role**: the split itself proves the role at this address, for example the site its
  trace installs at the interrupt vector, or a target of the jump table that trace measures.
- **decoded-format**: the body decodes or writes a structure that a generator under `tools/` already
  decodes, and the two agree on layout.

A name says what the function does, never who called it, never why the change was made, and never a
number that the evidence cell does not also carry.

## The ledger

`docs/NAMING_LEDGER.csv` has one row per promotion: `address,old,new,evidence_class,evidence`. The
evidence cell is short and checkable on its own: the register and the constant, the SWI number, the
callee address, or the split figure. A promotion without a ledger row is a name without evidence.

## The address-named count

`docs/NAMING_BASELINE.txt` holds the number of emitted functions that still carry the address form.
`README.md` carries the same figure as a sentence. The `NAMING-address-ratchet` check in
`tools/lint/lints.py` refuses a tree whose live count is above the baseline, and refuses one whose
count is below it while the baseline still says the old number: the figure only falls, and it is
exact at every commit.
