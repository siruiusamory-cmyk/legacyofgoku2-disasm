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
- **behaviour-test**: a tracked test runs the function from a private copy of the image on the
  registers and memory it crafts, and asserts the registers it returns, the memory it writes and the
  calls it makes, so the name claims only what that test asserts. `tools/code/thumb_vm.py` is the
  harness: it stops at the function's return, refuses a step past its budget and a run outside the
  function's body in `tools/code/FUNCTION_BOUNDS.csv` except through a recorded call, and stubs
  that call unless the test supplies its return values. The row's evidence cell cites the test as
  `tools/...py::test_name`; `NAMING-behaviour-test` in `tools/lint/lints.py` refuses a row whose
  citation is absent, repeats, names an untracked file, names a test its file does not define, or
  whose test does not pass. A test that needs the image skips when `baserom.gba` is absent, as every
  other ROM-gated test does.

A name says what the function does, never who called it, never why the change was made, and never a
number that the evidence cell does not also carry.

## Where a quoted effect has to lie

Every quoted effect has to sit inside the named function's own body as
`tools/code/FUNCTION_BOUNDS.csv` defines it: the start, plus every block reachable from it
inside its own code run, up to the next function start. A register write in a later block of that
function is the function's effect. A write past another function's start belongs to that function
and not to this one.

`tools/research/device_access.py --ledger` re-reads every ledger row this way and fails a row whose
evidence quotes an address the body neither accesses, nor loads as a literal, nor calls, nor writes
as a stored value. A failing row is demoted, never repaired by narrowing the quote.

## ## The ledger

`tools/code/NAMING_LEDGER.csv` has one row per promotion: `address,old,new,evidence_class,evidence`. The
evidence cell is short and checkable on its own: the register and the constant, the SWI number, the
callee address, or the split figure. A promotion without a ledger row is a name without evidence.

## Data symbols

A word of writable memory takes a name only when a behaviour test reads or writes it and asserts
what the function does with it, so the name claims exactly that use. The table is
`tools/code/ram.csv`, two columns, `address,name`, and `docs/RAM_LEDGER.csv` carries one row per
promotion in the same five columns as the function ledger. `tools/code/emit_code.py` emits the name
for a named literal pool word and the plain address for everything else, and `asm/memory.s` holds
the equates the emitted files assemble against. A data name is `Module_Field` in PascalCase, the
module naming the structure the word belongs to; every address with no such evidence stays a
literal and is counted in `docs/READABILITY.md`.

## Hardware symbols

`asm/registers.s` holds the GBATEK name of every hardware register the code touches, and
`asm/buu.s` includes it before any code. `tools/code/emit_code.py` emits the register name for a
literal pool word that holds a register address, so no emitted file carries the number.

## Function boundaries

The census carries every emitted entry and every transcribed code-span start, the beginning of a
`code_*.s` slice the build assembles, so a span the split proves but no export names still takes its
place in the population. `tools/code/function_bounds.py` classifies each of them from the bytes, and
`tools/code/FUNCTION_BOUNDS.csv` carries one row per address: `address,role,evidence`. The split
proves code at 2,447 addresses. A `start` carries at least one limb:

- **call**: an instruction in the emitted code reaches it with `bl`;
- **vector**: it is the reset vector's target, the interrupt handler's target, or a word of a proved
  dispatch table;
- **prologue**: its first instruction saves `lr` (`push {..., lr}` in Thumb, `stmfd sp!, {..., lr}`
  in ARM);
- **block**: it opens a code run the split proves, at a byte the split does not call code.

A start that no call, vector, table or prologue rule reaches, and that the split reaches only through
transcription, is carried with role `unreferenced` rather than dropped, so a name on it obeys the same
rules as a name on a start. Every other address is an interior fragment, and its evidence cell names
the start whose code contains it (`0x0800b35c,fragment,0x0800b33e`). A limb is proof of a start and is
never withdrawn; the census counts the one case where it is qualified, an entry whose only proof is a
call or a table word and which lies inside another proved body, as `contained` and leaves it a
fragment. Only a body a call, vector, table or prologue limb opens contains another entry: an
`unreferenced` start never takes an evidence start into itself, and a transcribed span start is never
an interior fragment.

`tools/code/emit_code.py` labels a function start with its name or `sub_` form and every fragment
with `loc_`, so a function is one contiguous labelled block and the build fails on a boundary file
that disagrees with the image. A fragment is not a place a name may attach.

The addresses whose entry, fragment or data status the image alone does not settle are carried in
`tools/code/CENSUS_EVIDENCE.csv`, one row each with the evidence: a `data` row keeps the address out
of the census entry set, an `entry` row keeps a start from being corrected to a later prologue, and a
`fragment` row names the start whose body holds the address.

## The address-named count

`tools/code/NAMING_BASELINE.txt` holds the number of functions that still carry the address form, not the
number of emitted entries: the fragments carry `loc_` and are not counted. `README.md` carries the
same figure as a sentence. The `NAMING-address-ratchet` check in `tools/lint/lints.py` refuses a tree
whose live count is above the baseline, and refuses one whose count is below it while the baseline
still says the old number: the figure only falls, and it is exact at every commit. `NAMING-symbol`
refuses a name on an interior fragment and refuses a boundary file that does not cover the entries.

## The population with three or more callers

`tools/research/callers.py` ranks every census start that carries no name, and its `callers` column
counts the distinct starts whose own bounds hold a `bl` to the target. Ninety-six starts are reached
from three or more distinct callers. Eighty carry a name; the sixteen below carry a measured
refusal, and a refusal is a result, not a gap: no name may claim more than its evidence.

The measurement is a seeded run of `tools/code/thumb_vm.py` on a zeroed `0x40`-byte workspace at
`0x02000000`, with `r0` at that base and `r1`..`r7` at `0x40`-byte steps, or the harness's own
refusal text where a run cannot start.

| address | callers | class | measured refusal |
| --- | --- | --- | --- |
| `0x0801FE20` | 13 | seed-not-separating | the run takes the 16-step exit path and writes nothing the seeded state decides |
| `0x080236A8` | 9 | arm-switch | `0x080236A8 switches to ARM, which this run cannot follow`; the literal the body loads is `0x03000000`, inside the block the boot copy installs, and no census start or library member names that address |
| `0x08006664` | 8 | seed-not-separating | two seeded paths disagree on what the record's byte at +0 records, so the effects do not separate a merge from a link |
| `0x080236CC` | 7 | arm-switch | `0x080236CC switches to ARM, which this run cannot follow`; the literal is `0x03000480`, and the same unnamed block holds it |
| `0x08006C24` | 6 | effect-without-a-module | the run pins four DMA3 copies, a `0x159`-word fill and the 138-cell grid walk, and every name those writes support is a module claim |
| `0x080135E0` | 5 | effect-without-a-module | the run pins the vtable `0x080245C0`, the `0x1120` node halfword and the position and extent words the parameter record fills |
| `0x08020D40` | 5 | bios-call | `0x08020D6E is a BIOS call, which this run cannot make`; the swap is the body's last instruction, and the countdown it stores is scaled from VCOUNT at `0x04000006` |
| `0x080078E4` | 4 | image-pointer | `0x00000003+1 is outside the image and the writable space`: the pointer it copies bytes from is the callee's return word |
| `0x0800B1E2` | 4 | tail-branch | `the run left the body at 0x0800B282 from 0x0800B264` |
| `0x08002244` | 3 | effect-without-a-module | the run pins the vtable `0x08023A60`, three zeroed spans and eight vtable stores in two sub-objects |
| `0x08002FF8` | 3 | image-pointer | `0x00000000+1 is outside the image and the writable space`: the word read at `0x081D9094` is used as a pointer |
| `0x080086A2` | 3 | image-pointer | `0x00000000+1 is outside the image and the writable space`: the record at `0x083B5268+4` names the word it follows |
| `0x0800E4D2` | 3 | image-pointer | `0x00000000+1 is outside the image and the writable space`: the table at `0x0840DAF4` names the word it follows |
| `0x0800FC84` | 3 | image-pointer | `0x00000000+1 is outside the image and the writable space`: the object's word at +0x14 names the record it copies |
| `0x08010124` | 3 | tail-branch | `the run left the body at 0x08010170 from 0x0801016E` |
| `0x080143A8` | 3 | effect-without-a-module | the run pins the vtable `0x08024ACC`, the `0x300` code, the `0x086E29B4` table words and a `0x10`-word DMA3 upload to VRAM |
