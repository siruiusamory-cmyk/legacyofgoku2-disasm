from __future__ import annotations

import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tools", "split"))

import emit_code
import name_table
import testkit

INDEX = os.path.join(ROOT, "docs", "CODE_INDEX.md")
HEADER = """# Code index

Every function the split classifies sits in its own generated file under `build\\code`, written at
build time from your own copy of the image. This page says which one.

- a named function: its file carries the function's name, and it has a row below;
- an address-named function: `build\\code\\code_<address>.s`, with the address in lowercase hex, no
  leading zeroes, eight digits, as in `code_0801f08c.s`, and the label `sub_<address>` in the file;
- a block inside a function: its `loc_<address>` label sits in the file of the start above it;
- a literal pool: `build\\code\\pool_<address>.s`, named by the first word it holds.

Every row below is one function start in `docs\\research\\FUNCTION_BOUNDS.csv`.
`python tools\\code\\code_index.py --check` fails when this page and the tree disagree.
"""


def spans(rom=None):
    if rom is None:
        rom = testkit.rom_bytes(emit_code.ROM, size=emit_code.END)
    return emit_code.span_files(emit_code.fragments(rom))


def file_of(found, address):
    for begin, end, name in found:
        if begin <= address < end:
            return name
    return None


def text(rom=None):
    found = spans(rom)
    names = name_table.names()
    starts = sorted(name_table.starts() or [])
    lines = [HEADER, "| function | address | file |", "| --- | --- | --- |"]
    rows = [(names.get(address, "sub_%08x" % address), address, file_of(found, address),
             address in names) for address in starts]
    for name, address, file, _named in rows:
        lines.append("| `%s` | `0x%08x` | `%s` |" % (name, address, file or "none"))
    lines.append("")
    lines.append("%d function starts: %d carry a name and %d carry their address; the address-named"
                 " ones are read through the rule above, and `docs\\NAMING.md` says what promotes a"
                 " name." % (len(rows), len([1 for _n, _a, _f, named in rows if named]),
                             len([1 for _n, _a, _f, named in rows if not named])))
    return "\n".join(lines) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--check", action="store_true")
    arguments = parser.parse_args(argv)
    if not os.path.exists(emit_code.ROM):
        print("the code index needs the retail image at %s" % emit_code.ROM)
        return 0
    rendered = text()
    if arguments.write:
        with open(INDEX, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(rendered)
        print("wrote %s" % os.path.relpath(INDEX, ROOT).replace("\\", "/"))
        return 0
    if arguments.check:
        try:
            present = open(INDEX, encoding="utf-8", newline="").read()
        except OSError:
            print("INDEX FAIL: %s is absent" % os.path.relpath(INDEX, ROOT).replace("\\", "/"))
            return 1
        if present != rendered:
            print("INDEX FAIL: %s differs from the tree" % os.path.relpath(INDEX, ROOT))
            return 1
        print("INDEX PASS")
        return 0
    print(rendered)
    return 0


if __name__ == "__main__":
    sys.exit(main())
