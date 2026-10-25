from __future__ import annotations

import argparse
import hashlib
import os
import sys
import tomllib

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
INPUTS = os.path.join(ROOT, "tools", "recomp", "RECOMP_INPUTS.toml")
ROM = os.path.join(ROOT, "baserom.gba")


def labels_text(inputs, rom):
    with open(inputs, "rb") as handle:
        source = tomllib.load(handle)
    with open(rom, "rb") as handle:
        sha256 = hashlib.sha256(handle.read()).hexdigest()
    funcs = {}
    for row in source.get("code", []):
        funcs[row["addr"]] = (row["mode"], row["addr"] + row["size"])
    for row in source.get("entry", []):
        funcs.setdefault(row["addr"], (row["mode"], None))
    lines = ['format = "gba-labels"', "version = 2", "", "[image]",
             'sha256 = "%s"' % sha256, ""]
    for address in sorted(funcs):
        mode, end = funcs[address]
        lines += ["[[functions]]", "address = 0x%08x" % address]
        if end is not None:
            lines.append("end = 0x%08x" % end)
        lines += ['mode = "%s"' % mode, ""]
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--inputs", default=INPUTS)
    parser.add_argument("--rom", default=ROM)
    parser.add_argument("--out", required=True)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    text = labels_text(args.inputs, args.rom)
    if args.check:
        with open(args.out, encoding="ascii", newline="") as handle:
            if handle.read() != text:
                raise SystemExit("%s is not the map this export derives" % args.out)
        print("CHECK: the label map matches the export")
        return 0
    with open(args.out, "w", encoding="ascii", newline="\n") as handle:
        handle.write(text)
    print("wrote %s (%d B)" % (args.out, len(text)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
