from __future__ import annotations

import argparse
import csv
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "tools", "split"))
sys.path.insert(0, os.path.join(ROOT, "tools", "code"))

import code_split
import function_bounds

ROM = os.path.join(ROOT, "baserom.gba")
CONTAINERS = os.path.join(ROOT, "docs", "research", "CONTAINER_CENSUS.csv")
RUNTIME = os.path.join(ROOT, "docs", "research", "RUNTIME_LABELS.csv")
OUT = os.path.join(ROOT, "docs", "research", "UNPROVEN_REMAINDER.csv")
HEADER = "class,bytes,share"
BASE = code_split.ROM_BASE
PAD = 8
RUN = 8
FACTORY = 4
REASONS = (("invalid", "residual: run meets a non-ARMv4T halfword"),
           ("no-return", "residual: run ends without a return"),
           ("inconsistent", "residual: branch target leaves the run"),
           ("step-limit", "residual: run passes the step limit"))
CLOSING_CODE = 3
BELOW_BAR_CODE = 10
CLOSING_REASON = "residual: closing run below its null bar"
CLASSES = ("data by format", "padding", "code by a closing entry", "data by table word") \
    + tuple(name for _why, name in REASONS) \
    + (CLOSING_REASON, "residual: no naming entry reaches the byte", "unknown")


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


def coverage(measured, rom):
    found = function_bounds.describe(measured, rom)
    edges = [(address - BASE, end - BASE)
             for address, _mode, origin, end, _reason in function_bounds.ends_rows(found)
             if origin == "census" and end]
    return found, union(edges)


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
    out = []
    offset = 0
    while offset < len(rom):
        start = offset
        while offset < len(rom) and code_split.thumb_length(rom, BASE + offset) is not None:
            offset += 2
        if offset - start >= 2 * RUN:
            out.append((start, offset))
        while offset < len(rom) and code_split.thumb_length(rom, BASE + offset) is None:
            offset += 2
    return union(out)


def named(rom):
    return sorted({value & ~1 for (value,) in struct.iter_unpack("<I", rom)
                   if value & 1 and code_split.in_image(rom, value & ~1)})


def table_words(rom):
    values = [value for (value,) in struct.iter_unpack("<I", rom)]
    counts = {}
    for value in values:
        if value & 1 and code_split.in_image(rom, value & ~1):
            counts[value] = counts.get(value, 0) + 1
    repeated = set(value for value, count in counts.items() if count >= FACTORY)
    sites = []
    start = None
    for index, value in enumerate(values):
        if value & 1 and code_split.in_image(rom, value & ~1):
            if start is None:
                start = index
        else:
            if start is not None and index - start > 1:
                sites.append((start * 4, index * 4))
            start = None
        if value in repeated:
            sites.append((index * 4, index * 4 + 4))
    if start is not None and len(values) - start > 1:
        sites.append((start * 4, len(values) * 4))
    return union(sites)


def closures(rom, measured):
    accepted = []
    reasons = []
    for address in named(rom):
        why = code_split.closure(rom, address, measured["pre"], measured["modes"])[0]
        spans = spans_of(rom, measured, address)
        if why in ("return", "tail"):
            accepted += spans
        else:
            reasons += [(why, begin, end) for begin, end in spans]
    return union(accepted), reasons


def spans_of(rom, measured, address):
    found = code_split.walk(rom, [(address, code_split.MODE_THUMB)], measured["classes"],
                            measured["modes"], code_split.UNCLASSIFIED)[0]
    return [(begin - BASE, stop - BASE) for begin, stop, _mode in found if stop > begin]


def closing_class(counted, claimed):
    if code_split.under_closing_bar(counted, claimed):
        return "code by a closing entry"
    return CLOSING_REASON


def apply_closing_bar(spare, counted, claimed):
    if closing_class(counted, claimed) != CLOSING_REASON:
        return
    for index, value in enumerate(spare):
        if value == CLOSING_CODE:
            spare[index] = BELOW_BAR_CODE


def mark(rom, measured, remaining):
    size = len(rom)
    world = bytearray(size)
    for begin, end in formats(rom, measured):
        world[begin:end] = b"\x01" * (end - begin)
    for begin, end in padding(rom):
        for index in range(begin, end):
            if world[index] == 0:
                world[index] = 2
    accepted, reasons = closures(rom, measured)
    spare = bytearray(size)
    for begin, end in accepted:
        for index in range(begin, end):
            if spare[index] == 0:
                spare[index] = CLOSING_CODE
    claimed = sum(1 for begin, end in remaining for index in range(begin, end)
                  if world[index] == 0 and spare[index] == CLOSING_CODE)
    counted = null(rom, class_mask(rom, measured, remaining))
    apply_closing_bar(spare, counted, claimed)
    for begin, end in table_words(rom):
        for index in range(begin, end):
            if spare[index] == 0:
                spare[index] = 4
    for number, (why, name) in enumerate(REASONS):
        for reason, begin, end in reasons:
            if reason != why:
                continue
            for index in range(begin, end):
                if spare[index] == 0:
                    spare[index] = 5 + number
    for begin, end in shaped(rom):
        for index in range(begin, end):
            if world[index] == 0 and spare[index] == 0:
                spare[index] = 9
    names = {1: CLASSES[0], 2: CLASSES[1], 3: CLASSES[2], 4: CLASSES[3],
             5: CLASSES[4], 6: CLASSES[5], 7: CLASSES[6], 8: CLASSES[7],
             9: CLASSES[9], 10: CLASSES[8], 0: CLASSES[10]}
    counts = dict((name, 0) for name in CLASSES)
    total = sum(end - begin for begin, end in remaining)
    for begin, end in remaining:
        for index in range(begin, end):
            counts[names[world[index] or spare[index]]] += 1
    if sum(counts.values()) != total:
        raise SystemExit("the classes do not partition the remainder")
    return ([(name, counts[name]) for name in CLASSES], total,
            (counted, claimed, closing_class(counted, claimed)))


def rates(rom, measured, found):
    starts = [address for address, _mode, origin, end, _reason
              in function_bounds.ends_rows(found) if origin == "census" and end]
    source, dest, _size, _declared = measured["overlay"]
    runtime = []
    for row in csv.DictReader(open(RUNTIME, encoding="ascii")):
        address = int(row["address"], 16)
        image = source + address - dest if row["region"] == "iwram" else address
        if row["mode"] == "thumb" and code_split.in_image(rom, image):
            runtime.append(image)
    taken, _words = code_split.thumb_entries(rom)
    known = formats(rom, measured)
    padding_runs = padding(rom)
    pools = (("the census starts", starts),
             ("the runtime entries", runtime),
             ("the named words inside a format",
              [address for address in taken if inside(known, address - BASE)]),
             ("the named words inside padding",
              [address for address in taken if inside(padding_runs, address - BASE)]))
    out = []
    for name, pool in pools:
        hits = sum(1 for address in pool
                   if code_split.closure(rom, address, measured["pre"],
                                         measured["modes"])[0] in ("return", "tail"))
        out.append((name, hits, len(pool)))
    return out


def inside(intervals, offset):
    for begin, end in intervals:
        if begin <= offset < end:
            return True
    return False


def class_mask(rom, measured, remaining):
    mask = bytearray(len(rom))
    for begin, end in shaped(rom):
        mask[begin:end] = b"\x01" * (end - begin)
    for begin, end in formats(rom, measured) + padding(rom):
        mask[begin:end] = b"\x00" * (end - begin)
    for begin, end in subtract([(0, len(rom))], remaining):
        mask[begin:end] = b"\x00" * (end - begin)
    return mask


def null(rom, mask):
    permuted = code_split.permute(rom)
    census = code_split.measure_null(rom)
    covered = 0
    for address in sorted({value & ~1 for (value,) in struct.iter_unpack("<I", permuted)
                           if value & 1 and code_split.in_image(rom, value & ~1)}):
        why, extent = code_split.closure(permuted, address, census["pre"],
                                         census["modes"])
        if why in ("return", "tail"):
            for index in range(address - BASE, extent - BASE):
                if 0 <= index < len(mask) and mask[index]:
                    covered += 1
    return covered


def text(rows, total):
    lines = [HEADER]
    for name, size in rows:
        lines.append("%s,%d,%.4f" % (name, size, 100.0 * size / total))
    return "\n".join(lines) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--rates", action="store_true",
                        help="print the closing test's rate on the known populations")
    arguments = parser.parse_args(argv)
    if not os.path.exists(ROM):
        print("the remainder needs the retail image at %s" % ROM)
        return 1
    rom = open(ROM, "rb").read()
    measured = code_split.measure(rom)
    found, proof = coverage(measured, rom)
    bound_bytes = bound(rom)
    remaining = subtract(bound_bytes, proof)
    outside = subtract(proof, bound_bytes)
    rows, total, closing = mark(rom, measured, remaining)
    print("bound=%d B in %d extents" % (sum(end - begin for begin, end in bound_bytes),
                                        len(bound_bytes)))
    print("proven=%d B in %d extents" % (sum(end - begin for begin, end in proof),
                                         len(proof)))
    print("proven outside the bound=%d B in %d extents"
          % (sum(end - begin for begin, end in outside), len(outside)))
    print("remaining=%d B" % total)
    for name, size in rows:
        print("%-58s %9d B %8.4f %%" % (name, size, 100.0 * size / total))
    print("closing null=%d B, %.4f %% of the %d B class, bar %.1f %%: %s"
          % (closing[0], 100.0 * closing[0] / max(closing[1], 1), closing[1],
             code_split.CLOSING_BAR, closing[2]))
    if arguments.rates:
        for name, hits, size in rates(rom, measured, found):
            print("closing entry on %-32s %5d / %5d = %s %%"
                  % (name, hits, size, "%.4f" % (100.0 * hits / max(size, 1))))
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
