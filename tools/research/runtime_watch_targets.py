from __future__ import annotations

import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "tools", "split"))

import code_split

ROM = os.path.join(ROOT, "baserom.gba")
EXPORT = os.path.join(ROOT, "docs", "research", "RECOMP_INPUTS.toml")
CSV_OUT = os.path.join(ROOT, "docs", "research", "RUNTIME_WATCH_TARGETS.csv")
FIELDS = ("kind", "start", "end", "bytes", "mode", "runtime")
KINDS = ("candidate-code", "bx-unresolved", "irq-slot")
EXPECT = {"candidate-code": (825, 26658), "bx-unresolved": (39, 78), "irq-slot": (14, 56)}


def export_blocks(path, name):
    marker = "[[%s]]" % name
    out, current = [], None
    for line in open(path, encoding="ascii").read().splitlines():
        if line.startswith("["):
            current = {} if line.strip() == marker else None
            if current is not None:
                out.append(current)
        elif current is not None and " = " in line:
            key, value = line.split(" = ", 1)
            current[key] = value.strip('"')
    return out


def export_fields(path, name):
    out, inside = {}, False
    for line in open(path, encoding="ascii").read().splitlines():
        line = line.strip()
        if line == "[%s]" % name:
            inside = True
            continue
        if inside:
            if not line or line.startswith("["):
                break
            key, value = line.split(" = ")
            out[key] = value
    return out


def code_extents(path=EXPORT):
    return [(int(block["addr"], 16), int(block["size"]), block["mode"])
            for block in export_blocks(path, "code")]


def candidate_rows(rom, held):
    rows = []
    for address, _mode in held:
        stop = code_split.linear_end(rom, address)
        if stop is not None:
            rows.append((address, stop))
    return rows


def register_sites(rom, code):
    sites = []
    for start, size, mode in code:
        for at in range(start, start + size, 2):
            if mode == "thumb":
                half = code_split.hw(rom, at)
                if (half & 0xFF87) == 0x4700:
                    if (half & 0x78) == 0x70:
                        continue
                elif (half & 0xFF87) != 0x4687:
                    continue
            else:
                if at % 4:
                    continue
                instruction = code_split.word(rom, at)
                if (instruction & 0x0FFFFFF0) not in (0x012FFF10, 0x01A0F000):
                    continue
                if (instruction & 0x0F) == 14:
                    continue
            sites.append((at, mode))
    return sites


def resolves(rom, at, mode):
    if mode == "thumb":
        register = (code_split.hw(rom, at) >> 3) & 0x07
        source, _probe = code_split.thumb_source(rom, at, register)
    else:
        register = code_split.word(rom, at) & 0x0F
        source, _probe = code_split.arm_source(rom, at, register)
    return source is not None and source & 1 and code_split.in_image(rom, source & ~1)


def irq_rows(path=EXPORT):
    irq = export_fields(path, "irq")
    copy = export_blocks(path, "code_copy")[0]
    runtime_start = int(copy["runtime_start"], 16)
    source_start = int(copy["source_start"], 16)
    table = int(irq["table"], 16)
    image = source_start + (table - runtime_start)
    return [(image + 4 * index, "0x%08x" % (table + 4 * index))
            for index in range(int(irq["table_entries"]))]


def targets(rom_path=ROM, export=EXPORT):
    if not os.path.exists(rom_path):
        raise SystemExit("no image at %s, so the watch targets cannot be derived" % rom_path)
    rom = open(rom_path, "rb").read()
    measured = code_split.measure(rom)
    rows = []
    candidates = candidate_rows(rom, measured["held"]["prologue"])
    if code_split.merged_length(candidates) != measured["prologue_bytes"]:
        raise SystemExit("the swept runs measure %d B, not the split's %d"
                         % (code_split.merged_length(candidates), measured["prologue_bytes"]))
    for start, stop in candidates:
        rows.append({"kind": "candidate-code", "start": start, "end": stop, "mode": "thumb",
                     "runtime": ""})
    for at, mode in register_sites(rom, code_extents(export)):
        if resolves(rom, at, mode):
            continue
        size = 2 if mode == "thumb" else 4
        rows.append({"kind": "bx-unresolved", "start": at, "end": at + size, "mode": mode,
                     "runtime": ""})
    for at, runtime in irq_rows(export):
        rows.append({"kind": "irq-slot", "start": at, "end": at + 4, "mode": "word",
                     "runtime": runtime})
    order = {kind: index for index, kind in enumerate(KINDS)}
    rows.sort(key=lambda row: (order[row["kind"]], row["start"]))
    for row in rows:
        row["bytes"] = row["end"] - row["start"]
    check(rows)
    return rows


def check(rows):
    for kind in KINDS:
        mine = [row for row in rows if row["kind"] == kind]
        found = (len(mine), sum(row["bytes"] for row in mine))
        if found != EXPECT[kind]:
            raise SystemExit("%s measures %s, not %s: the split or the export moved"
                             % (kind, found, EXPECT[kind]))


def csv_text(rows):
    lines = [",".join(FIELDS)]
    for row in rows:
        lines.append(",".join(("0x%08x" % row[field]) if field in ("start", "end")
                              else str(row[field]) for field in FIELDS))
    return "\n".join(lines) + "\n"


def merged_bytes(rows):
    total, end = 0, 0
    for start, stop in sorted((row["start"], row["end"]) for row in rows):
        if stop <= end:
            continue
        total += stop - max(start, end)
        end = stop
    return total


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    rows = targets()
    text = csv_text(rows)
    rom = open(ROM, "rb").read()
    sites = register_sites(rom, code_extents())
    resolved = sum(1 for at, mode in sites if resolves(rom, at, mode))
    print("bx sites: %d, resolved %d, unresolved %d"
          % (len(sites), resolved, len(sites) - resolved))
    for kind in KINDS:
        mine = [row for row in rows if row["kind"] == kind]
        print("%s: %d row(s), %d B, %d B merged"
              % (kind, len(mine), sum(row["bytes"] for row in mine), merged_bytes(mine)))
    if args.check:
        if not os.path.exists(CSV_OUT):
            raise SystemExit("%s is absent, so there is nothing to check"
                             % os.path.relpath(CSV_OUT, ROOT))
        with open(CSV_OUT, encoding="ascii") as handle:
            if handle.read() != text:
                raise SystemExit("%s is not the target file this tree derives"
                                 % os.path.relpath(CSV_OUT, ROOT))
        print("CHECK: the watch targets match the split and the export")
    if args.write:
        with open(CSV_OUT, "w", encoding="ascii", newline="\n") as handle:
            handle.write(text)
        print("wrote %s (%d row(s))" % (os.path.relpath(CSV_OUT, ROOT), len(rows)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
