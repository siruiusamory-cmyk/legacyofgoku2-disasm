from __future__ import annotations

import argparse
import hashlib
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "tools", "split"))

import code_split

ROM = os.path.join(ROOT, "baserom.gba")
SHA1 = os.path.join(ROOT, "baserom.sha1")
OUT = os.path.join(ROOT, "docs", "research", "RECOMP_INPUTS.toml")
MODE_NAMES = {code_split.MODE_THUMB: "thumb", code_split.MODE_ARM: "arm"}
CLASS_TAGS = {"proven code": "proven", "filtered pointer-entry code": "filtered",
              "table-held code": "table", "gap-fill code": "gap"}


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


def render(root=ROOT, rom=ROM):
    if not os.path.exists(rom):
        raise SystemExit("no image at %s, so the export cannot be derived" % rom)
    data = open(rom, "rb").read()
    sha1, md5 = identity(rom, os.path.join(root, "baserom.sha1"))
    measured = code_split.measure(data)
    rows = measured["function_rows"]
    entries = entries_of(measured)
    source, dest, size, _declared = measured["overlay"]
    lines = [
        "[counts]",
        "functions = %d" % len(rows),
        "code_bytes = %d" % sum(stop - start for start, stop, _name, _mode in rows),
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
    for start, stop, name, mode in rows:
        lines += [
            "[[code]]",
            "addr = 0x%08x" % (code_split.ROM_BASE + start),
            'mode = "%s"' % MODE_NAMES[mode],
            "size = %d" % (stop - start),
            'origin = "%s"' % CLASS_TAGS[name],
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
    if args.check:
        if not os.path.exists(OUT):
            raise SystemExit("%s is absent, so there is no export to check"
                             % os.path.relpath(OUT, ROOT))
        with open(OUT, encoding="ascii", newline="") as handle:
            if handle.read() != text:
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
