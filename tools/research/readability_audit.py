from __future__ import annotations

import argparse
import collections
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "tools", "code"))
sys.path.insert(0, os.path.join(ROOT, "tools", "gate"))
sys.path.insert(0, os.path.join(ROOT, "tools", "lint"))

import gate
import lints
import name_table

HEX = re.compile(r"0x([0-9A-Fa-f]{1,8})")
IMMEDIATE = re.compile(r"#-?0x([0-9A-Fa-f]{1,8})")
LABEL = re.compile(r"(?m)^\|\w+\|$")
DEFINITION = re.compile(r"(?m)^def ([A-Za-z_][A-Za-z0-9_]*)\(")
TEST_NAME = re.compile(r"(?m)^def (test_[A-Za-z0-9_]*)\(")
ADDRESS_IN_NAME = re.compile(r"[0-9a-f]{8}")
HARDWARE = (0x04000000, 0x05000000)
RAM = (0x02000000, 0x04000000)
EQUATES = "registers.s"
TABLES = os.path.join(ROOT, "docs", "TABLE_LEDGER.csv")
TABLE_HEADER = ("family", "reader", "evidence_class", "page")


def asm_files(root=ROOT):
    folder = os.path.join(root, "asm")
    found = [os.path.join(folder, name) for name in sorted(os.listdir(folder))
             if name.endswith(".s") and name != EQUATES]
    code = os.path.join(root, "build", "code")
    if os.path.isdir(code):
        found += [os.path.join(code, name) for name in sorted(os.listdir(code))
                  if name.endswith(".s")]
    return found


def python_files(root=ROOT):
    found = []
    for base, _folders, names in os.walk(os.path.join(root, "tools")):
        found += [os.path.join(base, name) for name in names if name.endswith(".py")]
    return sorted(found)


def values(files, pattern=HEX):
    found = collections.Counter()
    for path in files:
        with open(path, encoding="utf-8", errors="replace") as handle:
            for line in handle:
                for match in pattern.finditer(line):
                    found[int(match.group(1), 16)] += 1
    return found


def within(found, low, high):
    inside = [value for value in found if low <= value < high]
    return sum(found[value] for value in inside), len(inside)


def starts_per_file(paths):
    starts = set(name_table.starts() or [])
    named = set(name_table.names().values())
    counts = []
    for path in paths:
        with open(path, encoding="utf-8", errors="replace") as handle:
            labels = [label[1:-1] for label in LABEL.findall(handle.read())]
        counts.append(len([name for name in labels
                           if name in named
                           or (name.startswith("sub_") and int(name[4:], 16) in starts)]))
    return counts


def definitions():
    found = {}
    for path in python_files():
        with open(path, encoding="utf-8", errors="replace") as handle:
            found[path] = DEFINITION.findall(handle.read())
    return found


def referenced(name, texts):
    return sum(text.count(name) for text in texts)


def dead_definitions():
    found = definitions()
    texts = []
    for path in python_files():
        with open(path, encoding="utf-8", errors="replace") as handle:
            texts.append(handle.read())
    dead = []
    for path, names in found.items():
        for name in names:
            if name == "main" or os.path.basename(path).startswith("test_"):
                continue
            if referenced(name, texts) <= 1:
                dead.append((os.path.relpath(path, ROOT).replace("\\", "/"), name))
    return dead


def duplicate_blocks():
    names = lints.dup_scan_files() or []
    return lints.duplicate_blocks(names)


def tests():
    files = [path for path in python_files() if os.path.basename(path).startswith("test_")]
    names = []
    for path in files:
        with open(path, encoding="utf-8", errors="replace") as handle:
            names += TEST_NAME.findall(handle.read())
    return files, names


def unnamed_ram(found):
    named = name_table.ram_names()
    inside = [value for value in found if RAM[0] <= value < RAM[1] and value not in named]
    return sum(found[value] for value in inside), len(inside)


def table_families(text=None):
    if text is None:
        try:
            text = open(TABLES, encoding="utf-8").read()
        except OSError:
            return []
    return [cells for _number, cells in name_table.csv_rows(text, TABLE_HEADER)
            if len(cells) == len(TABLE_HEADER)]


def counts(root=ROOT):
    asm = asm_files(root)
    hardware = within(values(asm), *HARDWARE)
    ram = unnamed_ram(values(asm))
    immediates = values(asm, IMMEDIATE)
    labels = starts_per_file(asm)
    starts = name_table.starts()
    named = name_table.names()
    slices = gate.incbin_ranges(root)
    files, test_names = tests()
    named_ram = name_table.ram_names()
    found = {
        "asm_files": len(asm),
        "code_labels": sum(labels),
        "files_with_several_starts": len([count for count in labels if count > 1]),
        "functions": len(starts or []),
        "named_functions": len([address for address in named if address in set(starts or [])]),
        "hardware_literals": hardware[0],
        "distinct_hardware_literals": hardware[1],
        "ram_literals": ram[0],
        "distinct_ram_literals": ram[1],
        "named_ram_symbols": len(named_ram),
        "immediate_literals": sum(immediates.values()),
        "distinct_immediates": len(immediates),
        "raw_slices": len(slices),
        "raw_slice_bytes": sum(size for _start, size in slices),
        "table_families": len(table_families()),
        "tool_files": len(python_files(root)),
        "dead_definitions": len(dead_definitions()),
        "duplicate_blocks": len(duplicate_blocks()),
        "test_files": len(files),
        "tests": len(test_names),
        "address_named_tests": len([name for name in test_names
                                    if ADDRESS_IN_NAME.search(name)]),
    }
    return found


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--table", action="store_true")
    parser.add_argument("--count", default=None)
    arguments = parser.parse_args(argv)
    found = counts()
    if arguments.count:
        print(found[arguments.count])
        return 0
    for key in sorted(found):
        print("%s=%d" % (key, found[key]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
