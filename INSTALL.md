# Build

Prerequisites: ARM Developer Suite 1.2 (`armasm`, `armlink`, `fromelf`), Python 3.12 on `PATH`, and
the retail ROM as `baserom.gba` in this directory. `rebuild.cmd` defaults `ADS` to an ADS 1.2 Build
805 install beside this checkout's parent directory; set `ADS` to use another installation. The
ROM's sha1 must equal `baserom.sha1` and its game code must read `ALFE`; `extract.cmd` refuses
anything else.

```
extract.cmd
rebuild.cmd
python tools\gate\gate.py
```

`gate.py` rebuilds from scratch, purges every object first, and prints `DIGEST MATCH` and
`GATE PASS` when the image equals the retail sha256. It also accounts for every byte of the image
from the source tree:

```
source=<bytes> of 8388608 (<percent>)      code and container bodies generated from the retail image
raw-data=<bytes> (<percent>)               bytes the assembler embeds from extracted slices
identity copies=<bytes> (<percent>)        bytes copied through a build step
accounted=<bytes> of 8388608 (<percent>)   source plus raw-data; all of it when every byte is in one
```

[README.md](README.md) states the figure the gate prints today; this file does not repeat it.

`source` is the image size minus the bytes `asm/*.s` INCBINs, so it cannot drift from what the
assembler reads. `rebuild.cmd` runs `tools/code/emit_code.py` first and writes the header slice
through `tools\incbin.bat`; `tools/compress/generate_containers.py` writes the gap slices and the
generated container runs `asm/remainder.s` names, and `tools\extract\slice_rom.py` is the slice
writer; neither the slices nor the image is tracked.

`python tools\gate\gate.py --cold` purges every object, every INCBIN slice and the built image, runs
`extract.cmd`, rebuilds, and requires the digest match from that empty start.

`python tools\gate\gate.py --verify-rom` checks the retail file only: its size, its sha1 against
`baserom.sha1`, and the game code at `0x0AC`. `extract.cmd` runs it first.

The source checks are in `tools\lint\lints.py` and the link check in `tools\check_links.py`;
`check.cmd` runs both, with the link check's test, and the CI workflow runs the same three
commands. The tests are `python -m pytest tools`, one file per process, with the retail image
present; the ROM-gated tests skip while it is absent, which is what CI runs.

The build is byte sensitive: `asm/` carries the transcribed halfwords, so a change there moves the
digest. The gate is the only proof that a change kept the image equal.

Which file carries a function, and how a change to one is proven, is the path in
[README.md](README.md#reading-and-changing-a-function). [docs/READABILITY.md](docs/READABILITY.md)
measures what a reader still meets in this tree and which counts a commit may not raise.
