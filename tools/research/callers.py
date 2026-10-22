from __future__ import annotations

import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "tools", "code"))
sys.path.insert(0, os.path.join(ROOT, "tools", "split"))

import function_bounds
import name_table
import readability_audit

ROM = os.path.join(ROOT, "baserom.gba")
THUMB = function_bounds.THUMB
GAP = 0x400
SWITCH = "BX pc"


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
        lines.append((position, function_bounds.emit_code.decode(rom, position, "thumb")))
    return lines


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--top", type=int, default=0)
    parser.add_argument("--body", default=None)
    parser.add_argument("--ram", action="store_true")
    parser.add_argument("--rom", default=ROM)
    arguments = parser.parse_args(argv)
    if arguments.ram:
        for value, count in ram_ranking()[:arguments.top or None]:
            print("0x%08X refs=%d" % (value, count))
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
