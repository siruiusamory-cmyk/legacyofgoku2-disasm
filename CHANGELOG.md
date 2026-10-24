# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Changed

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

### Fixed

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
