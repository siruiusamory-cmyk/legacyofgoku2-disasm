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

The notes for the changes before this one stay in the repository history.
