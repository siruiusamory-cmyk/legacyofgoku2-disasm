from __future__ import annotations

import csv
import io
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TABLE = os.path.join(ROOT, "tools", "code", "names.csv")
RAM = os.path.join(ROOT, "tools", "code", "ram.csv")
LEDGER = os.path.join(ROOT, "tools", "code", "NAMING_LEDGER.csv")
RAM_LEDGER = os.path.join(ROOT, "docs", "RAM_LEDGER.csv")
BASELINE = os.path.join(ROOT, "tools", "code", "NAMING_BASELINE.txt")
EXPORT = os.path.join(ROOT, "tools", "recomp", "RECOMP_INPUTS.toml")
BOUNDS = os.path.join(ROOT, "tools", "code", "FUNCTION_BOUNDS.csv")
REMAINDER = os.path.join(ROOT, "asm", "remainder.s")
CARRIED = re.compile(r"gen_([0-9a-f]+)_([0-9a-f]+)\.bin")
ROM_BASE = 0x08000000
START = 0x100
END = 0x800000
ADDRESS = re.compile(r"^0x[0-9a-f]{8}$")
TABLE_HEADER = ("address", "name")
LEDGER_HEADER = ("address", "old", "new", "evidence_class", "evidence")


def read(path):
    try:
        return open(path, encoding="utf-8", errors="replace").read()
    except OSError:
        return None


def csv_rows(text, header):
    if text is None:
        return []
    rows = []
    reader = csv.reader(io.StringIO(text))
    for number, cells in enumerate(reader, 1):
        if not cells or not "".join(cells).strip():
            continue
        rows.append((number, [cell.strip() for cell in cells]))
    return [(number, cells) for number, cells in rows if tuple(cells) != header]


def table_rows(text=None):
    if text is None:
        text = read(TABLE)
    return csv_rows(text, TABLE_HEADER)


def ledger_rows(text=None):
    if text is None:
        text = read(LEDGER)
    return csv_rows(text, LEDGER_HEADER)


def names(text=None):
    index = {}
    for _number, cells in table_rows(text):
        if len(cells) != 2 or not ADDRESS.match(cells[0]):
            continue
        index[int(cells[0], 16)] = cells[1]
    return index


def entries(text=None):
    if text is None:
        text = read(EXPORT)
    if text is None:
        return []
    found = []
    for block in text.split("[[entry]]")[1:]:
        match = re.search(r"^addr = (0x[0-9a-f]{8})$", block, re.M)
        if match:
            found.append(int(match.group(1), 16))
    return sorted(found)


def runs(text=None):
    if text is None:
        text = read(REMAINDER)
    if text is None:
        return []
    found = []
    for match in CARRIED.finditer(text):
        found.append((int(match.group(1), 16), int(match.group(2), 16)))
    return sorted(found)


def covered(ranges, start, stop):
    for begin, end in ranges:
        if begin < stop and start < end:
            return True
    return False


def emitted(addresses=None, ranges=None):
    if addresses is None:
        addresses = entries()
    if ranges is None:
        ranges = runs()
    return [address for address in addresses
            if START <= address - ROM_BASE < END
            and not covered(ranges, address - ROM_BASE, address - ROM_BASE + 1)]


def baseline(text=None):
    if text is None:
        text = read(BASELINE)
    if text is None:
        return None
    match = re.search(r"(\d+)", text)
    return int(match.group(1)) if match else None


def bounds(text=None):
    if text is None:
        text = read(BOUNDS)
    if text is None:
        return None
    found = []
    reader = csv.reader(io.StringIO(text))
    for number, cells in enumerate(reader, 1):
        if len(cells) != 3 or number == 1:
            continue
        found.append([cell.strip() for cell in cells])
    return found


def starts(text=None):
    rows = bounds(text)
    if rows is None:
        return None
    return [int(cells[0], 16) for cells in rows if cells[1] in ("start", "unreferenced")]


def load_names():
    return names()


def ram_names(text=None):
    if text is None:
        text = read(RAM)
    index = {}
    for _number, cells in csv_rows(text, TABLE_HEADER):
        if len(cells) != 2 or not ADDRESS.match(cells[0]):
            continue
        index[int(cells[0], 16)] = cells[1]
    return index
