from __future__ import annotations

import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "tools", "split"))
sys.path.insert(0, os.path.join(ROOT, "tools", "recomp"))
sys.path.insert(0, HERE)

import code_split
import emit_code
import export_inputs
import name_table

ROM = os.path.join(ROOT, "baserom.gba")
BOUNDS = os.path.join(ROOT, "docs", "research", "FUNCTION_BOUNDS.csv")
HEADER = "address,role,evidence"
THUMB = 1
LIMBS = ("call", "vector", "table", "prologue", "block")
TERMINATORS = ("B", "BX", "SWI", "UDF")
PC_WRITERS = ("MOV", "ADD", "SUB", "LDR", "LDM", "LDMFD", "LDMIA", "POP")


def writes_pc(operation, operands):
    if operation == "BX":
        return True
    if operation not in PC_WRITERS:
        return False
    fields = [field.strip() for field in operands.replace("{", "").replace("}", "").split(",")]
    return "pc" in fields


def ends_body(operation, operands):
    return operation in TERMINATORS or writes_pc(operation, operands)


def prologue(rom, address, mode):
    if mode == THUMB:
        half = code_split.hw(rom, address)
        return half is not None and (half & 0xF800) == 0xB000 and bool(half & 0x0100)
    instruction = code_split.word(rom, address)
    return (instruction & 0xFFFF0000) == 0xE92D0000 and bool(instruction & 0x4000)


def body(rom, address, mode, limit):
    name = "thumb" if mode == THUMB else "arm"
    seen = set()
    todo = [address]
    while todo:
        position = todo.pop()
        while position not in seen and address <= position < limit:
            decoded = emit_code.decode(rom, position, name)
            if decoded is None:
                break
            operation, operands, size = decoded
            seen.add(position)
            fall = position + size
            if operation.startswith("B") and operation not in ("BL", "BX") \
                    and operands.startswith("|loc_"):
                todo.append(int(operands[5:13], 16))
                if operation != "B":
                    position = fall
                    continue
                break
            if ends_body(operation, operands):
                break
            position = fall
    return seen


def call_targets(rom, rows, modes):
    found = set()
    for begin, end in rows:
        name = "thumb" if modes.get(begin, THUMB) == THUMB else "arm"
        position = begin
        while position < end:
            decoded = emit_code.decode(rom, position, name)
            if decoded is None:
                break
            operation, operands, size = decoded
            if operation == "BL" and operands.startswith("|loc_"):
                found.add(int(operands[5:13], 16))
            position += size
            if ends_body(operation, operands):
                break
    return found


def classify(rom, entries, modes, rows, calls, table, vectors):
    limits = {}
    for begin, end in rows:
        limits[begin] = end
    row_of = {}
    for begin, end in rows:
        for address in entries:
            if begin <= address < end:
                row_of[address] = begin
    bodies = {}
    limbs_of = {}
    for address in entries:
        limbs = []
        if address in calls:
            limbs.append("call")
        if address in vectors:
            limbs.append("vector")
        if address in table:
            limbs.append("table")
        if prologue(rom, address, modes.get(address, THUMB)):
            limbs.append("prologue")
        if address in limits:
            limbs.append("block")
        if not limbs:
            continue
        inside = body(rom, address, modes.get(address, THUMB),
                      limits.get(address, address + 0x400))
        if not inside:
            continue
        limbs_of[address] = limbs
        bodies[address] = inside
    starts = {}
    contained = 0
    for address in sorted(entries):
        if address not in limbs_of:
            continue
        if "block" not in limbs_of[address] and "prologue" not in limbs_of[address]:
            if any(address in starts[start] for start in starts):
                contained += 1
                continue
        starts[address] = bodies[address]
    fragments = {}
    for address in entries:
        if address in starts:
            continue
        row = row_of.get(address, address)
        earlier = [start for start in starts if row_of.get(start) == row and start < address]
        fragments[address] = max(earlier) if earlier else None
    return {"starts": dict((address, limbs_of[address]) for address in starts),
            "fragments": fragments,
            "bodies": dict((address, max(starts[address])) for address in starts),
            "contained": contained}


def describe(measured, rom):
    base = code_split.ROM_BASE
    pairs = export_inputs.entries_of(measured)
    modes = dict((address, mode) for address, mode in pairs)
    entries = name_table.emitted([address for address, _mode in pairs], name_table.runs())
    rows = [(base + start, base + stop) for start, stop, _name, _mode in measured["function_rows"]]
    calls = call_targets(rom, rows, modes)
    calls.update(address for address, _mode in measured["calls"])
    table = set()
    for key in ("run", "record", "slot"):
        for item in measured["held"][key]:
            table.add(item[0] if isinstance(item, tuple) else item)
    for item in measured["tables"]:
        if isinstance(item.get("target"), int):
            table.add(item["target"])
        table.update(value for value in item.get("entries", []) if isinstance(value, int))
    vectors = {code_split.VECTOR, code_split.CRT0}
    handler = measured["irq"]["handler"]
    if isinstance(handler, dict) and isinstance(handler.get("rom"), int):
        vectors.add(handler["rom"])
    found = classify(rom, entries, modes, rows, calls, table, vectors)
    found["entries"] = entries
    found["modes"] = modes
    return found


def census(rom):
    return describe(code_split.measure(rom), rom)


def counts(found):
    by_limb = {}
    for address in found["starts"]:
        for limb in found["starts"][address]:
            by_limb[limb] = by_limb.get(limb, 0) + 1
    covered = len([address for address in found["fragments"] if found["fragments"][address]])
    return {"entries": len(found["entries"]), "starts": len(found["starts"]),
            "fragments": len(found["fragments"]), "covered": covered,
            "orphans": len(found["fragments"]) - covered, "by_limb": by_limb,
            "contained": found["contained"]}


def rows_text(found):
    lines = [HEADER]
    for address in found["entries"]:
        if address in found["starts"]:
            lines.append("0x%08x,start,%s" % (address, "+".join(found["starts"][address])))
        else:
            parent = found["fragments"][address]
            lines.append("0x%08x,fragment,%s"
                         % (address, "" if parent is None else "0x%08x" % parent))
    return "\n".join(lines) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--rom", default=ROM)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--starts", action="store_true")
    parser.add_argument("--fragments", action="store_true")
    arguments = parser.parse_args(argv)
    if not os.path.exists(arguments.rom):
        print("the census needs the retail image at %s" % arguments.rom)
        return 1
    found = census(open(arguments.rom, "rb").read())
    names = name_table.load_names()
    for address in found["entries"]:
        if arguments.starts and address not in found["starts"]:
            continue
        if arguments.fragments and address in found["starts"]:
            continue
        if address in found["starts"]:
            print("0x%08x start    %-24s %s" % (address, "+".join(found["starts"][address]),
                                                names.get(address, "-")))
        else:
            parent = found["fragments"][address]
            print("0x%08x fragment %-24s %s"
                  % (address, "none" if parent is None else "in 0x%08x" % parent,
                     names.get(address, "-")))
    tally = counts(found)
    print("entries=%d starts=%d fragments=%d covered=%d orphans=%d contained=%d"
          % (tally["entries"], tally["starts"], tally["fragments"], tally["covered"],
             tally["orphans"], tally["contained"]))
    print("by_limb " + " ".join("%s=%d" % (limb, tally["by_limb"].get(limb, 0)) for limb in LIMBS))
    text = rows_text(found)
    if arguments.write:
        with open(BOUNDS, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
        print("wrote %s" % os.path.relpath(BOUNDS, ROOT).replace("\\", "/"))
        return 0
    if arguments.check:
        current = open(BOUNDS, encoding="utf-8").read() if os.path.exists(BOUNDS) else None
        if current != text:
            print("BOUNDS FAIL: %s is not what the image gives"
                  % os.path.relpath(BOUNDS, ROOT).replace("\\", "/"))
            return 1
        print("BOUNDS PASS")
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
