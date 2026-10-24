from __future__ import annotations

import argparse
import csv
import hashlib
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "tools", "split"))

import code_split

ROM = os.path.join(ROOT, "baserom.gba")
SHA1 = os.path.join(ROOT, "baserom.sha1")
OUT = os.path.join(ROOT, "tools", "recomp", "RECOMP_INPUTS.toml")
BOUNDS = os.path.join("tools", "code", "FUNCTION_ENDS.csv")
MODES = ("arm", "thumb")
CODE_ROW = re.compile(r'\[\[code\]\]\naddr = 0x([0-9a-fA-F]{8})\nmode = "([^"]*)"\n'
                      r'size = (\d+)\norigin = "([^"]*)"')
MODE_NAMES = {code_split.MODE_THUMB: "thumb", code_split.MODE_ARM: "arm"}


def identity(path=ROM, sha1_path=SHA1):
    if not os.path.exists(path):
        raise SystemExit("no image at %s, so the identity block cannot be derived" % path)
    data = open(path, "rb").read()
    digest = hashlib.sha1(data).hexdigest()
    expected = open(sha1_path, encoding="ascii").read().strip()
    if digest != expected:
        raise SystemExit("%s has sha1 %s, not the %s of %s"
                         % (path, digest, expected, sha1_path))
    return digest, hashlib.md5(data).hexdigest()


def entry_address(rom):
    instruction = code_split.word(rom, code_split.VECTOR)
    if (instruction & 0x0F000000) != 0x0A000000:
        raise SystemExit("the reset vector at 0x%08X is not an ARM branch: %08X"
                         % (code_split.VECTOR, instruction))
    return code_split.VECTOR


def entries_of(measured):
    found = set(measured["proven_entries"]) | set(measured["accepted_modes"])
    return sorted(found | set(measured["extra"]))


def bounds_rows(root=ROOT):
    path = os.path.join(root, *BOUNDS.split("/"))
    rows = []
    with open(path, newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row["end"] == "-":
                continue
            start, end = int(row["address"], 16), int(row["end"], 16)
            if row["mode"] not in MODES:
                raise SystemExit("%s: 0x%08X carries mode %s, not one of %s"
                                 % (BOUNDS, start, row["mode"] or "none", ", ".join(MODES)))
            if end <= start:
                raise SystemExit("%s: 0x%08X ends at 0x%08X, which is not after it"
                                 % (BOUNDS, start, end))
            if not (code_split.ROM_BASE <= start
                    and end <= code_split.ROM_BASE + code_split.ROM_SIZE
                    or 0x03000000 <= start and end <= 0x03008000):
                raise SystemExit("%s: 0x%08X..0x%08X is neither in the image nor in IWRAM"
                                 % (BOUNDS, start, end))
            rows.append((start, end - start, row["mode"], row["origin"]))
    return rows


def audit(text, rows):
    found = {int(match.group(1), 16): match.group(2) for match in CODE_ROW.finditer(text)}
    uncovered = [row for row in rows if row[0] not in found]
    modeless = [mode for mode in found.values() if mode not in MODES]
    return uncovered, modeless


def render(root=ROOT, rom=ROM):
    if not os.path.exists(rom):
        raise SystemExit("no image at %s, so the export cannot be derived" % rom)
    data = open(rom, "rb").read()
    sha1, md5 = identity(rom, os.path.join(root, "baserom.sha1"))
    measured = code_split.measure(data)
    functions = bounds_rows(root)
    entries = entries_of(measured)
    source, dest, size, _declared = measured["overlay"]
    lines = [
        "[counts]",
        "functions = %d" % len(functions),
        "code_bytes = %d" % sum(row[1] for row in functions),
        "entries = %d" % len(entries),
        "jump_tables = %d" % len(measured["tables"]),
        "code_copies = 1",
        "",
        "[identity]",
        'sha1 = "%s"' % sha1,
        'md5 = "%s"' % md5,
        "",
        "[program]",
        "entry_pc = 0x%08x" % entry_address(data),
        "",
        "[[code_copy]]",
        "runtime_start = 0x%08x" % dest,
        "source_start = 0x%08x" % source,
        "size = 0x%x" % size,
        "",
    ]
    irq = measured["irq"]
    if irq is not None:
        lines += [
            "[irq]",
            "vector = 0x%08x" % code_split.IRQ_VECTOR,
            "install = 0x%08x" % irq["install"]["site"],
            "handler = 0x%08x" % irq["install"]["handler"],
            "handler_bytes = %d" % irq["handler"]["bytes"],
        ]
        if irq["handler"]["table"] is not None:
            lines += ["table = 0x%08x" % irq["handler"]["table"]["at"],
                      "table_entries = %d" % len(irq["handler"]["table"]["entries"])]
        lines += [""]
    for start, size, mode, origin in functions:
        lines += [
            "[[code]]",
            "addr = 0x%08x" % start,
            'mode = "%s"' % mode,
            "size = %d" % size,
            'origin = "%s"' % origin,
            "",
        ]
    for address, mode in entries:
        lines += [
            "[[entry]]",
            "addr = 0x%08x" % address,
            'mode = "%s"' % MODE_NAMES[mode],
            "",
        ]
    for table in measured["tables"]:
        lines += [
            "[[jump_table]]",
            "dispatch = 0x%08x" % table["dispatch"],
            "base = 0x%08x" % table["base"],
            "stride = %d" % table["stride"],
            "entries = %d" % table["count"],
            "scale = %d" % table["scale"],
            "",
        ]
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    text = render()
    for line in text.splitlines()[1:6]:
        print(line)
    tracked = None
    if args.check:
        if not os.path.exists(OUT):
            raise SystemExit("%s is absent, so there is no export to check"
                             % os.path.relpath(OUT, ROOT))
        with open(OUT, encoding="ascii", newline="") as handle:
            tracked = handle.read()
    uncovered, modeless = audit(text if tracked is None else tracked, bounds_rows())
    print("uncovered = %d" % len(uncovered))
    print("modeless = %d" % len(modeless))
    if uncovered:
        raise SystemExit("%d census row(s) have no code row, the first 0x%08X"
                         % (len(uncovered), uncovered[0][0]))
    if modeless:
        raise SystemExit("%d code row(s) carry a mode outside %s"
                         % (len(modeless), ", ".join(MODES)))
    if args.check:
        if tracked != text:
            raise SystemExit("%s is not the export this tree derives"
                             % os.path.relpath(OUT, ROOT))
        print("CHECK: the export matches the tree")
        return 0
    if args.write:
        with open(OUT, "w", encoding="ascii", newline="\n") as handle:
            handle.write(text)
        print("wrote %s (%d B)" % (os.path.relpath(OUT, ROOT), len(text)))
        return 0
    print("dry run: pass --write or --check")
    return 0


if __name__ == "__main__":
    sys.exit(main())
