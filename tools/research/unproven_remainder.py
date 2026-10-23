from __future__ import annotations

import argparse
import csv
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "tools", "split"))
sys.path.insert(0, os.path.join(ROOT, "tools", "code"))

import code_split
import function_bounds

ROM = os.path.join(ROOT, "baserom.gba")
CONTAINERS = os.path.join(ROOT, "docs", "research", "CONTAINER_CENSUS.csv")
OUT = os.path.join(ROOT, "docs", "research", "UNPROVEN_REMAINDER.csv")
HEADER = "class,bytes,share"
BASE = code_split.ROM_BASE
NAME = "unproven remainder"
PAD = 8
RUN = 8


def union(intervals):
    out = []
    for begin, end in sorted(intervals):
        if out and begin <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], end))
        else:
            out.append((begin, end))
    return out


def subtract(intervals, holes):
    out = []
    for begin, end in intervals:
        position = begin
        for hole_begin, hole_end in holes:
            if hole_end <= position or hole_begin >= end:
                continue
            if hole_begin > position:
                out.append((position, hole_begin))
            position = max(position, hole_end)
        if position < end:
            out.append((position, end))
    return out


def bound(rom):
    classes = bytearray(len(rom))
    modes = bytearray(len(rom))
    spans = []
    roots = [(code_split.VECTOR, code_split.MODE_ARM), (code_split.CRT0, code_split.MODE_ARM)]
    taken, _words = code_split.thumb_entries(rom)
    for start, mode in roots + [(address, code_split.MODE_THUMB) for address in sorted(taken)]:
        found, _pools, _entries, _calls = code_split.walk(rom, [(start, mode)], classes, modes,
                                                         code_split.PROVEN)
        spans += [(begin - BASE, stop - BASE) for begin, stop, _mode in found]
    return union(spans)


def proven(rom):
    found = function_bounds.census(rom)
    edges = [(address - BASE, end - BASE)
             for address, _mode, origin, end, _reason in function_bounds.ends_rows(found)
             if origin == "census" and end]
    return union(edges)


def formats(rom, measured):
    out = []
    for row in csv.DictReader(open(CONTAINERS, encoding="ascii")):
        offset = int(row["offset"], 16)
        out.append((offset, offset + int(row["packed"])))
    out += [(begin, stop) for begin, stop in measured["pool"]]
    return union(out)


def padding(rom):
    out = []
    offset = 0
    while offset < len(rom):
        value = rom[offset]
        run = offset
        while run < len(rom) and rom[run] == value:
            run += 1
        if value in (0x00, 0xFF) and run - offset >= PAD:
            out.append((offset, run))
        offset = run
    return union(out)


def shaped(rom):
    data = bytes(rom)
    out = []
    offset = 0
    while offset < len(data):
        start = offset
        while offset < len(data) and code_split.thumb_length(data, BASE + offset) is not None:
            offset += 2
        length = offset - start
        if length >= 2 * RUN:
            out.append((start, offset))
        while offset < len(data) and code_split.thumb_length(data, BASE + offset) is None:
            offset += 2
    return union(out)


def classes(rom, remaining, measured):
    total = sum(end - begin for begin, end in remaining)
    world = bytearray(len(rom))
    for begin, end in formats(rom, measured):
        for index in range(begin, end):
            if world[index] == 0:
                world[index] = 1
    marks = ((2, padding(rom)), (3, shaped(rom)))
    for value, intervals in marks:
        for begin, end in intervals:
            for index in range(begin, end):
                if world[index] == 0:
                    world[index] = value
    names = {1: "data by format", 2: "padding", 3: "unreached-but-code-shaped", 4: "unknown"}
    counts = dict((name, 0) for name in names.values())
    for begin, end in remaining:
        for index in range(begin, end):
            counts[names[world[index] or 4]] += 1
    rows = [(names[key], counts[names[key]]) for key in (1, 2, 3, 4)]
    if sum(counts.values()) != total:
        raise SystemExit("the classes do not partition the remainder")
    return rows, total


def text(rows, total):
    lines = [HEADER]
    for name, size in rows:
        lines.append("%s,%d,%.4f" % (name, size, 100.0 * size / total))
    return "\n".join(lines) + "\n"


def report(rom):
    measured = code_split.measure(rom)
    bound_bytes = bound(rom)
    coverage = proven(rom)
    remaining = subtract(bound_bytes, coverage)
    rows, total = classes(rom, remaining, measured)
    outside = subtract(coverage, bound_bytes)
    shaped_null = sum(end - begin for begin, end
                      in overlap(remaining, shaped(code_split.permute(rom))))
    return rows, total, bound_bytes, coverage, outside, shaped_null


def overlap(left, right):
    return [(max(begin, other_begin), min(end, other_end))
            for begin, end in left for other_begin, other_end in right
            if max(begin, other_begin) < min(end, other_end)]


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--check", action="store_true")
    arguments = parser.parse_args(argv)
    if not os.path.exists(ROM):
        print("the remainder needs the retail image at %s" % ROM)
        return 1
    rom = open(ROM, "rb").read()
    rows, total, bound_bytes, coverage, outside, shaped_null = report(rom)
    print("bound=%d B in %d extents" % (sum(end - begin for begin, end in bound_bytes),
                                        len(bound_bytes)))
    print("proven=%d B in %d extents" % (sum(end - begin for begin, end in coverage),
                                         len(coverage)))
    print("proven outside the bound=%d B in %d extents"
          % (sum(end - begin for begin, end in outside), len(outside)))
    print("remaining=%d B" % total)
    for name, size in rows:
        print("%-28s %9d B %8.4f %%" % (name, size, 100.0 * size / total))
    print("shaped null=%d B, %s %% of the shaped class"
          % (shaped_null, "%.4f" % (100.0 * shaped_null / max(dict(rows)["unreached-but-code-shaped"], 1))))
    body = text(rows, total)
    if arguments.write:
        with open(OUT, "w", encoding="ascii", newline="\n") as handle:
            handle.write(body)
        print("wrote %s" % os.path.relpath(OUT, ROOT).replace("\\", "/"))
        return 0
    if arguments.check:
        current = open(OUT, encoding="ascii").read() if os.path.exists(OUT) else None
        if current != body:
            raise SystemExit("REMAINDER FAIL: %s is not what the image gives"
                             % os.path.relpath(OUT, ROOT).replace("\\", "/"))
        print("REMAINDER PASS")
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
