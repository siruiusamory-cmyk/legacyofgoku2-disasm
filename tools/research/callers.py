from __future__ import annotations

import argparse
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "tools", "code"))
sys.path.insert(0, os.path.join(ROOT, "tools", "split"))

import device_access
import function_bounds
import name_table
import readability_audit

ROM = os.path.join(ROOT, "baserom.gba")
THUMB = function_bounds.THUMB
GAP = 0x400
SWITCH = "BX pc"
POOL = re.compile(r"\[pc, #(0x[0-9A-F]+)\]")
LOADS = ("LDR", "LDRB", "LDRH", "LDRSB", "LDRSH")
RAM = (0x02000000, 0x04000000)
ROM_BASE = 0x08000000


def image(path=ROM):
    with open(path, "rb") as handle:
        return handle.read()


def starts(text=None):
    return sorted(name_table.starts(text) or [])


def walk(rom, addresses=None):
    ordered = addresses if addresses is not None else starts()
    limits = dict(zip(ordered, ordered[1:] + [ordered[-1] + GAP]))
    bodies = {}
    sites = []
    for address in ordered:
        inside = function_bounds.body(rom, address, THUMB, limits[address])
        bodies[address] = inside
        for position in sorted(inside):
            decoded = function_bounds.emit_code.decode(rom, position, "thumb")
            if decoded is None:
                continue
            operation, operands, _size = decoded
            if operation == "BL" and operands.startswith("|loc_"):
                sites.append((address, int(operands[5:13], 16)))
    return sites, bodies


def counted(pairs):
    sites = {}
    callers = {}
    for caller, target in pairs:
        sites[target] = sites.get(target, 0) + 1
        callers.setdefault(target, set()).add(caller)
    return dict((target, (sites[target], len(callers[target]))) for target in sites)


def switches_state(rom, address, inside):
    if len(inside) != 1:
        return False
    decoded = function_bounds.emit_code.decode(rom, address, "thumb")
    return decoded is not None and "%s %s" % (decoded[0], decoded[1]) == SWITCH


def kind(pairs, address, named, rom=None, inside=None):
    callees = set(target for caller, target in pairs if caller == address)
    if rom is not None and inside is not None and switches_state(rom, address, inside):
        return "arm-veneer"
    if not callees:
        return "leaf"
    if callees <= set(named):
        return "named-callees"
    return "stubbable-callees"


def ranked(rom=None, named=None):
    if rom is None:
        rom = image()
    if named is None:
        named = name_table.names()
    pairs, bodies = walk(rom)
    totals = counted(pairs)
    known = set(starts())
    rows = [(target, totals[target][0], totals[target][1],
             kind(pairs, target, named, rom, bodies.get(target, set())))
            for target in totals if target not in named and target in known]
    return sorted(rows, key=lambda row: (-row[1], -row[2], row[0]))


def ram_ranked(found, named):
    inside = [value for value in found
              if readability_audit.RAM[0] <= value < readability_audit.RAM[1]
              and value not in named]
    return sorted(((value, found[value]) for value in inside),
                  key=lambda row: (-row[1], row[0]))


def ram_ranking(root=ROOT):
    return ram_ranked(readability_audit.values(readability_audit.asm_files(root)),
                      name_table.ram_names())


def body(rom, address):
    order = [start for start in starts() if start > address]
    limit = order[0] if order else address + GAP
    lines = []
    for position in sorted(function_bounds.body(rom, address, THUMB, limit)):
        decoded = function_bounds.emit_code.decode(rom, position, "thumb")
        if decoded is not None and decoded[0] in LOADS:
            match = POOL.search(decoded[1])
            if match is not None:
                at = ((position + 4) & ~3) + int(match.group(1), 16)
                offset = at - ROM_BASE
                decoded = (decoded[0], "%s -> 0x%08X" % (
                    decoded[1], int.from_bytes(rom[offset:offset + 4], "little")), decoded[2])
        lines.append((position, decoded))
    return lines


def fields(rom):
    rows = device_access.census(rom)
    totals = {}
    for row in rows:
        lines = row["body"]
        for base, offset, operation in device_access.touches(
                row["mode"], lines, lambda at: word_of(rom, at), pairs=True):
            if RAM[0] <= base < RAM[1]:
                totals[(base, offset)] = totals.get((base, offset), 0) + 1
    return totals


def word_of(rom, address):
    at = address - ROM_BASE
    return int.from_bytes(rom[at:at + 4], "little") if 0 <= at < len(rom) - 4 else None


def base_ranked(totals):
    bases = {}
    for (base, offset), count in totals.items():
        sites, distinct = bases.get(base, (0, 0))
        bases[base] = (sites + count, distinct + 1)
    return sorted(((base, sites, distinct) for base, (sites, distinct) in bases.items()),
                  key=lambda row: (-row[1], -row[2], row[0]))


def field_ranked(totals):
    return sorted(((base, offset, count) for (base, offset), count in totals.items()),
                  key=lambda row: (-row[2], row[0], row[1]))


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--top", type=int, default=0)
    parser.add_argument("--body", default=None)
    parser.add_argument("--ram", action="store_true")
    parser.add_argument("--data", action="store_true")
    parser.add_argument("--fields", action="store_true")
    parser.add_argument("--rom", default=ROM)
    arguments = parser.parse_args(argv)
    if arguments.ram:
        for value, count in ram_ranking()[:arguments.top or None]:
            print("0x%08X refs=%d" % (value, count))
        return 0
    if arguments.data or arguments.fields:
        rom = image(arguments.rom)
        totals = fields(rom)
        if arguments.fields:
            for base, offset, count in field_ranked(totals)[:arguments.top or None]:
                print("0x%08X +0x%X sites=%d" % (base, offset, count))
            return 0
        for base, sites, distinct in base_ranked(totals)[:arguments.top or None]:
            print("0x%08X sites=%d fields=%d" % (base, sites, distinct))
        return 0
    rom = image(arguments.rom)
    named = name_table.names()
    if arguments.body:
        for position, decoded in body(rom, int(arguments.body, 16)):
            text = "%s %s" % (decoded[0], decoded[1]) if decoded else "data"
            print("0x%08X  %s" % (position, text))
        return 0
    rows = ranked(rom, named)
    for target, site_count, caller_count, callee_kind in rows[:arguments.top or len(rows)]:
        print("0x%08X sites=%d callers=%d %s" % (target, site_count, caller_count, callee_kind))
    return 0


if __name__ == "__main__":
    sys.exit(main())
