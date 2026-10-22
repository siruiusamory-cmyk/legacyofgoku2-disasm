# Naming conventions

Every symbol the build emits carries one of three forms, and which form it carries is a statement
about the evidence for it.

## Functions

- Known purpose: `Module_Verb` in PascalCase, module first, one verb after it (`Input_ReadKeys`).
  The module names the subsystem the function works in, never the file it happens to sit in.
- A toolchain library function: the exact exported symbol of the library member whose code the
  address reproduces, spelled as the librarian exports it (`strlen`, `__16_ll_udiv10`,
  `__vfprintf`). This form needs a `toolchain-library` ledger row and nothing else admits it.
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
- **toolchain-library**: the entry's bytes reproduce a member of the ARM Developer Suite 1.2 runtime
  and C libraries the game was linked with, so the member's exported symbol is the function's name.
  The match is byte-exact with only the fields the linker relocated masked: for a PC-relative
  relocation the three bytes that carry the branch offset are masked and the opcode byte is compared,
  for a Thumb call the four bytes of the call pair are masked, and for a word relocation the four
  bytes that hold the address are masked. Every other byte, including a literal-pool word no
  relocation patches, is compared. `tools/research/library_match.py` applies the rule and its test
  holds each case.

A name says what the function does, never who called it, never why the change was made, and never a
number that the evidence cell does not also carry.

## Where a quoted effect has to lie

Every quoted effect has to sit inside the named function's own body as
`docs/research/FUNCTION_BOUNDS.csv` defines it: the start, plus every block reachable from it
inside its own code run, up to the next function start. A register write in a later block of that
function is the function's effect. A write past another function's start belongs to that function
and not to this one.

`tools/research/device_access.py --ledger` re-reads every ledger row this way and fails a row whose
evidence quotes an address the body neither accesses, nor loads as a literal, nor calls, nor writes
as a stored value. A failing row is demoted, never repaired by narrowing the quote.

## The ledger

`docs/NAMING_LEDGER.csv` has one row per promotion: `address,old,new,evidence_class,evidence`. The
evidence cell is short and checkable on its own: the register and the constant, the SWI number, the
callee address, or the split figure. A promotion without a ledger row is a name without evidence.

## Function boundaries

The split proves code at 2,402 addresses, and only some of them start a function; the rest are blocks
inside one. `tools/code/function_bounds.py` classifies every emitted entry from the bytes, and
`docs/research/FUNCTION_BOUNDS.csv` carries one row per entry: `address,role,evidence`. An entry is a
function start when at least one limb holds:

- **call**: an instruction in the emitted code reaches it with `bl`;
- **vector**: it is the reset vector's target, the interrupt handler's target, or a word of a proved
  dispatch table;
- **prologue**: its first instruction saves `lr` (`push {..., lr}` in Thumb, `stmfd sp!, {..., lr}`
  in ARM);
- **block**: it opens a code run the split proves, at a byte the split does not call code.

Every other entry is an interior fragment, and its evidence cell names the start whose code contains
it (`0x0800b35c,fragment,0x0800b33e`). A limb is proof of a start and is never withdrawn; the census
counts the one case where it is qualified, an entry whose only proof is a call or a table word and
which lies inside another proved body, as `contained` and leaves it a fragment.

`tools/code/emit_code.py` labels a function start with its name or `sub_` form and every fragment
with `loc_`, so a function is one contiguous labelled block and the build fails on a boundary file
that disagrees with the image. A fragment is not a place a name may attach.

## The address-named count

`docs/NAMING_BASELINE.txt` holds the number of functions that still carry the address form, not the
number of emitted entries: the fragments carry `loc_` and are not counted. `README.md` carries the
same figure as a sentence. The `NAMING-address-ratchet` check in `tools/lint/lints.py` refuses a tree
whose live count is above the baseline, and refuses one whose count is below it while the baseline
still says the old number: the figure only falls, and it is exact at every commit. `NAMING-symbol`
refuses a name on an interior fragment and refuses a boundary file that does not cover the entries.
