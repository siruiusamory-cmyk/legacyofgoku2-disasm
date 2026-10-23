from __future__ import annotations

import argparse
import csv
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
ENDS = os.path.join(ROOT, "docs", "research", "FUNCTION_ENDS.csv")
ALLOW = os.path.join(ROOT, "docs", "research", "FUNCTION_ENTRY_ALLOW.csv")
RUNTIME = os.path.join(ROOT, "docs", "research", "RUNTIME_LABELS.csv")
HEADER = "address,role,evidence"
ENDS_HEADER = "address,mode,origin,end,reason"
FLAG_HEADER = "address,kind,limb,flags,entry,reason"
THUMB = 1
ARM = 2
LIMBS = ("call", "vector", "table", "prologue", "block")
REFERRING = ("call", "vector", "table", "prologue")
TERMINATORS = ("B", "BX", "SWI", "UDF")
PC_WRITERS = ("MOV", "ADD", "SUB", "LDR", "LDM", "LDMFD", "LDMIA", "POP")
FLAGS = ("data", "undecodable", "clobber")
REASONS = ("prefix", "row-start")
WRITES = ("ADD", "SUB", "RSB", "ADC", "SBC", "MOV", "MVN", "AND", "EOR", "ORR", "BIC",
          "MUL", "LSL", "LSR", "ASR", "ROR", "NEG", "LDR", "LDRB", "LDRH", "LDRSB", "LDRSH")
ARGUMENTS = ("r0", "r1", "r2", "r3")
HOMES = ("r4", "r5", "r6", "r7")


def unreferenced(limbs):
    return not any(limb in REFERRING for limb in limbs)


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


def walk_body(rom, address, mode, limit):
    name = "thumb" if mode == THUMB else "arm"
    seen = set()
    closed = False
    extent = 0
    todo = [address]
    while todo:
        position = todo.pop()
        while position not in seen and address <= position < limit:
            decoded = emit_code.decode(rom, position, name)
            if decoded is None:
                break
            operation, operands, size = decoded
            seen.add(position)
            extent = max(extent, position + size)
            fall = position + size
            if operation.startswith("B") and operation not in ("BL", "BX") \
                    and operands.startswith("|loc_"):
                todo.append(int(operands[5:13], 16))
                if operation != "B":
                    position = fall
                    continue
                break
            if ends_body(operation, operands):
                closed = True
                break
            position = fall
    return seen, min(extent, limit), closed


def body(rom, address, mode, limit):
    return walk_body(rom, address, mode, limit)[0]


def limit_of(rows, address):
    for begin, end in rows:
        if begin <= address < end:
            return end
    return address + 0x400


def edge_of(address, next_start, pool):
    edges = [edge for edge in (next_start, pool) if edge is not None and edge > address]
    return min(edges) if edges else None


def ending_of(extent, closed, edge, next_start):
    if not extent:
        return 0, "no-body"
    if edge is not None and edge < extent:
        return edge, "next-start" if edge == next_start else "pool"
    if not closed:
        return extent, "no-return"
    return extent, "-"


def saving(operation, operands):
    return (operation == "PUSH" or operation in ("STMDB", "STMFD")) and "lr" in operands


def closest(rom, address, mode):
    name = "thumb" if mode == THUMB else "arm"
    at = address
    for _step in range(6):
        decoded = emit_code.decode(rom, at, name)
        if decoded is None:
            return None
        operation, operands, size = decoded
        if saving(operation, operands):
            return at if at > address else None
        if ends_body(operation, operands):
            return None
        at += size
    return None


def leading(rom, address, mode, count=8):
    name = "thumb" if mode == THUMB else "arm"
    found = []
    at = address
    while len(found) < count:
        decoded = emit_code.decode(rom, at, name)
        if decoded is None:
            return found, at, True
        operation, operands, size = decoded
        found.append((at, operation, operands, size))
        at += size
        if saving(operation, operands) or ends_body(operation, operands):
            break
    return found, at, False


def before_return(rom, address, mode, window=0x20):
    if mode != THUMB:
        return False
    at = address - 2
    while at >= address - window:
        decoded = emit_code.decode(rom, at, "thumb")
        if decoded is not None:
            operation, operands, _size = decoded
            if saving(operation, operands):
                return False
            if ends_body(operation, operands):
                return True
        at -= 2
    return False


def undecodable(rom, items, mode, broken):
    if broken:
        return True
    for position, operation, _operands, size in items:
        if mode != THUMB:
            continue
        half = code_split.hw(rom, position)
        if any(low <= half <= high for low, high in code_split.THUMB_UNDEFINED):
            return True
        if size == 4 and operation != "BL":
            return True
    return False


def written(operation, operands):
    if operation not in WRITES:
        return set()
    first = operands.split(",")[0].strip()
    return {first} if first in ARGUMENTS else set()


def homed(operation, operands, register):
    if operation not in ("ADD", "MOV"):
        return False
    fields = [field.strip() for field in operands.split(",")]
    return len(fields) > 1 and fields[0] in HOMES and fields[1] == register


def clobbered(rom, items, after, mode, broken):
    if broken:
        return False
    hit = set()
    for _position, operation, operands, _size in items:
        if saving(operation, operands) or ends_body(operation, operands):
            break
        hit |= written(operation, operands)
    if not hit or not items or not saving(items[-1][1], items[-1][2]):
        return False
    follow, _at, _broken = leading(rom, after, mode, 2)
    return any(homed(operation, operands, register)
               for _position, operation, operands, _size in follow
               for register in hit)


def flag_rows(rom, found):
    rows = []
    for address in sorted(found["starts"]):
        mode = found["modes"].get(address, THUMB)
        items, after, broken = leading(rom, address, mode)
        entry = closest(rom, address, mode)
        flags = []
        if entry is not None:
            flags.append("data")
        if undecodable(rom, items, mode, broken):
            flags.append("undecodable")
        if clobbered(rom, items, after, mode, broken):
            flags.append("clobber")
        if not flags:
            continue
        rows.append((address, role_of(found, address),
                     "+".join(found["starts"][address]), "+".join(flags), entry))
    return rows


def return_before_rate(rom, found):
    starts = [address for address in found["starts"]
              if closest(rom, address, found["modes"].get(address, THUMB)) is None]
    inside = sorted(found["fragments"])
    return ([address for address in starts
             if before_return(rom, address, found["modes"].get(address, THUMB))],
            starts,
            [address for address in inside if before_return(rom, address, THUMB)],
            inside)


def flags_text(rows):
    lines = [FLAG_HEADER]
    for address, kind, limb, flags, entry in rows:
        lines.append("0x%08x,%s,%s,%s,%s,%s"
                     % (address, kind, limb, flags,
                        "0x%08x" % entry if entry is not None else "-",
                        "prefix" if entry is not None else "row-start"))
    return "\n".join(lines) + "\n"


def ends_rows(found):
    rows = []
    seen = set()
    for address in sorted(found["starts"]):
        target = found["corrected"].get(address, address)
        if target in seen:
            continue
        seen.add(target)
        end, reason = found["ends"][target]
        rows.append((target, found["modes"].get(address, THUMB), "census", end, reason))
    for address, mode, origin, end, reason in found["runtime"]:
        rows.append((address, mode, origin, end, reason))
    return sorted(rows)


def ends_text(found):
    lines = [ENDS_HEADER]
    for address, mode, origin, end, reason in ends_rows(found):
        lines.append("0x%08x,%s,%s,%s,%s"
                     % (address, "arm" if mode == 2 else "thumb", origin,
                        "0x%08x" % end if end else "-", reason))
    return "\n".join(lines) + "\n"


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


def classify(rom, entries, modes, rows, calls, table, vectors, spans=(), pools=()):
    spans = set(spans)
    pools = sorted(set(pools))
    entries = sorted(set(entries) | spans)
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
    walked = {}
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
        if not limbs and address not in spans:
            continue
        inside, extent, closed = walk_body(rom, address, modes.get(address, THUMB),
                                          limits.get(address, address + 0x400))
        if not inside and address not in spans:
            continue
        limbs_of[address] = limbs
        bodies[address] = inside
        walked[address] = (extent, closed)
    starts = {}
    contained = 0
    for address in sorted(entries):
        if address not in limbs_of:
            continue
        if address not in spans and "prologue" not in limbs_of[address]:
            if any(address in starts[start] for start in starts
                   if not unreferenced(limbs_of[start])):
                contained += 1
                continue
        starts[address] = bodies[address]
    edges = sorted(starts)
    ends = {}
    for address in edges:
        next_start = [edge for edge in edges if edge > address]
        pool = [edge for edge in pools if edge > address]
        edge = edge_of(address, next_start[0] if next_start else None,
                       pool[0] if pool else None)
        extent, closed = walked[address]
        ends[address] = ending_of(extent, closed, edge,
                                  next_start[0] if next_start else None)
    corrected = {}
    for address in edges:
        entry = closest(rom, address, modes.get(address, THUMB))
        if entry is None:
            continue
        corrected[address] = entry
        if entry not in ends:
            extent, closed = walk_body(rom, entry, modes.get(address, THUMB),
                                       limit_of(rows, entry))[1:]
            ends[entry] = ending_of(extent, closed, None, None)
    fragments = {}
    for address in entries:
        if address in starts:
            continue
        row = row_of.get(address, address)
        earlier = [start for start in starts if row_of.get(start) == row and start < address]
        fragments[address] = max(earlier) if earlier else None
    return {"entries": entries,
            "starts": dict((address, limbs_of[address]) for address in starts),
            "fragments": fragments,
            "bodies": dict((address, max(starts[address])) for address in starts
                           if starts[address]),
            "ends": ends,
            "corrected": corrected,
            "modes": modes,
            "runtime": [],
            "contained": contained}


def runtime_rows(measured):
    source, dest, _size, _declared = measured["overlay"]
    found = []
    for row in csv.DictReader(open(RUNTIME, encoding="ascii")):
        address = int(row["address"], 16)
        iwram = row["region"] == "iwram"
        found.append((address, THUMB if row["mode"] == "thumb" else ARM,
                      "runtime-iwram" if iwram else "runtime",
                      source + address - dest if iwram else address))
    return found


def folded(rom, measured):
    source, dest, size, _declared = measured["overlay"]
    found = []
    rows = runtime_rows(measured)
    for region in ("runtime", "runtime-iwram"):
        inside = sorted(row for row in rows if row[2] == region)
        for number, (address, mode, origin, image) in enumerate(inside):
            limit = source + size if origin == "runtime-iwram" else len(rom) + code_split.ROM_BASE
            shift = image - address
            next_start = inside[number + 1][0] + shift if number + 1 < len(inside) else None
            extent, closed = walk_body(rom, image, mode, limit)[1:]
            image_end, reason = ending_of(extent, closed, next_start, next_start)
            found.append((address, mode, origin, image_end - shift if image_end else 0, reason))
    return found


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
    found = classify(rom, entries, modes, rows, calls, table, vectors,
                     spans=emit_code.spans(measured),
                     pools=[base + start for start, _stop in measured["pool"]])
    found["rows"] = rows
    found["runtime"] = folded(rom, measured)
    return found


def coverage(found):
    named = [(begin, stop) for begin, stop in found["rows"]]
    spans = 0
    inside = 0
    edges = []
    for address, _mode, origin, end, _reason in ends_rows(found):
        if not end or origin != "census":
            continue
        spans += end - address
        inside += sum(max(0, min(end, stop) - max(address, begin)) for begin, stop in named)
        edges.append((address, end))
    union = 0
    reach = 0
    for begin, end in sorted(edges):
        begin = max(begin, reach)
        if end > begin:
            union += end - begin
            reach = end
    return union, spans, inside


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
            "unreferenced": len([address for address in found["starts"]
                                 if unreferenced(found["starts"][address])]),
            "contained": found["contained"]}


def role_of(found, address):
    return "unreferenced" if unreferenced(found["starts"][address]) else "start"


def rows_text(found):
    lines = [HEADER]
    for address in found["entries"]:
        if address in found["starts"]:
            lines.append("0x%08x,%s,%s" % (address, role_of(found, address),
                                           "+".join(found["starts"][address])))
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
    rom = open(arguments.rom, "rb").read()
    found = census(rom)
    names = name_table.load_names()
    for address in found["entries"]:
        if arguments.starts and address not in found["starts"]:
            continue
        if arguments.fragments and address in found["starts"]:
            continue
        if address in found["starts"]:
            print("0x%08x %-12s %-24s %s" % (address, role_of(found, address),
                                             "+".join(found["starts"][address]) or "-",
                                             names.get(address, "-")))
        else:
            parent = found["fragments"][address]
            print("0x%08x fragment     %-24s %s"
                  % (address, "none" if parent is None else "in 0x%08x" % parent,
                     names.get(address, "-")))
    tally = counts(found)
    print("entries=%d starts=%d fragments=%d covered=%d orphans=%d contained=%d unreferenced=%d"
          % (tally["entries"], tally["starts"], tally["fragments"], tally["covered"],
             tally["orphans"], tally["contained"], tally["unreferenced"]))
    print("by_limb " + " ".join("%s=%d" % (limb, tally["by_limb"].get(limb, 0)) for limb in LIMBS))
    ends = ends_rows(found)
    closed = len([row for row in ends if row[3]])
    print("bounds=%d closed=%d open=%d runtime=%d corrected=%d"
          % (len(ends), closed, len(ends) - closed,
             len([row for row in ends if row[2] != "census"]), len(found["corrected"])))
    print("by_reason " + " ".join("%s=%d" % (reason, len([row for row in ends
                                                          if row[4] == reason]))
                                  for reason in ("-", "next-start", "pool", "no-return",
                                                 "no-body")))
    flags = flag_rows(rom, found)
    print("flagged=%d by_flag %s" % (len(flags),
                                     " ".join("%s=%d" % (flag, len([row for row in flags
                                                                    if flag in row[3].split("+")]))
                                              for flag in FLAGS)))
    before, starts, inside, fragments = return_before_rate(rom, found)
    print("return_before starts=%d/%d (%.4f %%) inside=%d/%d (%.4f %%)"
          % (len(before), len(starts), 100.0 * len(before) / max(len(starts), 1),
             len(inside), len(fragments),
             100.0 * len(inside) / max(len(fragments), 1)))
    union, spans, inside = coverage(found)
    print("coverage union=%d spans=%d over_named=%d outside_named=%d named=%d"
          % (union, spans, inside, union - inside,
             sum(stop - begin for begin, stop in found["rows"])))
    text = rows_text(found)
    if arguments.write:
        for path, body in ((BOUNDS, text), (ENDS, ends_text(found)),
                           (ALLOW, flags_text(flags))):
            with open(path, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(body)
            print("wrote %s" % os.path.relpath(path, ROOT).replace("\\", "/"))
        return 0
    if arguments.check:
        for path, body in ((BOUNDS, text), (ENDS, ends_text(found)),
                           (ALLOW, flags_text(flags))):
            current = open(path, encoding="utf-8").read() if os.path.exists(path) else None
            if current != body:
                print("BOUNDS FAIL: %s is not what the image gives"
                      % os.path.relpath(path, ROOT).replace("\\", "/"))
                return 1
        print("BOUNDS PASS")
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
