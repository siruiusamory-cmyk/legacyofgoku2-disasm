from __future__ import annotations

import argparse
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "tools", "split"))
sys.path.insert(0, os.path.join(ROOT, "tools", "recomp"))
sys.path.insert(0, os.path.join(ROOT, "tools", "code"))

import code_split
import emit_code
import export_inputs
import function_bounds
import name_table

ROM = os.path.join(ROOT, "baserom.gba")
MODE_NAMES = {code_split.MODE_THUMB: "thumb", code_split.MODE_ARM: "arm"}
POOL_LOAD = re.compile(r"\[pc, #(0x[0-9A-F]+)\]")
CALL_LABEL = re.compile(r"^\|loc_([0-9A-F]{8})\|$")
ADDRESS_TOKEN = re.compile(r"0x[0-9A-Fa-f]{8}")
INDIRECT = re.compile(r"^r(\d+), \[r(\d+)(?:, #(0x[0-9A-F]+))?\]$")
IMMEDIATE = re.compile(r"^r(\d+), #(0x[0-9A-F]+)$")
SHIFT = re.compile(r"^r(\d+), r(\d+), #(0x[0-9A-F]+)$")
SUM = re.compile(r"^r(\d+), r(\d+), #(0x[0-9A-F]+)$")
STEP = re.compile(r"^r(\d+), #(0x[0-9A-F]+)$")
MOVE = re.compile(r"^r(\d+), r(\d+)$")
LOADS = ("LDR", "LDRB", "LDRH", "LDRSB", "LDRSH")
STORES = ("STR", "STRB", "STRH")
REGISTER = re.compile(r"^(r\d+|sp|lr|pc|sl|fp|ip)$")
REGISTERS = emit_code.REGISTERS
WRITING = ("LDR", "MOV", "MVN", "ADR", "LSL", "LSR", "ASR", "NEG", "MUL", "AND", "ORR", "EOR",
           "BIC", "ADD", "SUB", "RSB", "ADC", "SBC", "LDM")
ADDRESS_LOW = 0x01000000
ADDRESS_HIGH = 0x09000000


def pool_at(position, mode, offset):
    return ((position + 4) & ~3) + offset if mode == "thumb" else position + 8 + offset


def touches(mode, lines, word, pairs=False):
    registers = [None] * 16
    found = []
    for position, operation, operands in lines:
        if operation == "BL":
            for number in range(0, 4):
                registers[number] = None
            registers[14] = None
            continue
        if operation in ("PUSH", "CMP", "CMN", "TST", "TEQ"):
            continue
        if operation == "POP":
            for field in operands.replace("{", "").replace("}", "").split(","):
                name = field.strip().strip("![]")
                if name in REGISTERS:
                    registers[REGISTERS.index(name)] = None
            continue
        pool = POOL_LOAD.search(operands)
        if pool and operation in LOADS:
            offset = int(pool.group(1), 16)
            registers[int(operands.split(",")[0].strip()[1:])] = word(
                pool_at(position, mode, offset))
            continue
        indirect = INDIRECT.match(operands)
        if indirect and operation in LOADS + STORES:
            destination, base = int(indirect.group(1)), int(indirect.group(2))
            offset = int(indirect.group(3), 16) if indirect.group(3) else 0
            address = registers[base]
            if isinstance(address, int) and address >= 0x03000000:
                if pairs:
                    found.append((address, offset, operation))
                else:
                    found.append((address + offset, operation,
                                  registers[destination] if operation in STORES else None))
            if operation in LOADS:
                registers[destination] = None
            continue
        step = STEP.match(operands)
        if step and operation in ("ADD", "SUB"):
            left, right = registers[int(step.group(1))], int(step.group(2), 16)
            registers[int(step.group(1))] = (left + right if operation == "ADD"
                                             else left - right) if isinstance(left, int) else None
            continue
        immediate = IMMEDIATE.match(operands)
        if immediate:
            registers[int(immediate.group(1))] = int(immediate.group(2), 16)
            continue
        shift = SHIFT.match(operands)
        if shift and operation in ("LSL", "LSR", "ASR"):
            source = registers[int(shift.group(2))]
            amount = int(shift.group(3), 16)
            if not isinstance(source, int):
                registers[int(shift.group(1))] = None
            elif operation == "LSL":
                registers[int(shift.group(1))] = (source << amount) & 0xFFFFFFFF
            elif operation == "LSR":
                registers[int(shift.group(1))] = source >> amount
            else:
                registers[int(shift.group(1))] = (source >> amount) if source < 0x80000000 \
                    else ~((~source) >> amount)
            continue
        total = SUM.match(operands)
        if total and operation in ("ADD", "SUB"):
            left, right = registers[int(total.group(2))], int(total.group(3), 16)
            registers[int(total.group(1))] = (left + right if operation == "ADD"
                                              else left - right) if isinstance(left, int) else None
            continue
        move = MOVE.match(operands)
        if move:
            registers[int(move.group(1))] = registers[int(move.group(2))]
    return found


def callees(lines):
    found = []
    for _position, operation, operands in lines:
        match = CALL_LABEL.match(operands)
        if operation == "BL" and match:
            found.append(int(match.group(1), 16))
    return found


def bios(lines):
    return sorted(set(int(operands, 16) for _position, operation, operands in lines
                      if operation == "SWI"))


def literals(mode, lines, word):
    found = []
    for position, operation, operands in lines:
        pool = POOL_LOAD.search(operands)
        if pool and operation in LOADS:
            found.append(word(pool_at(position, mode, int(pool.group(1), 16))))
    return found


def live_in(lines):
    saved = set("r%d" % number for number in range(4, 12))
    written = set()
    found = set()
    for _position, operation, operands in lines:
        fields = [field.strip().strip("[]!") for field in
                  operands.replace("{", "").replace("}", "").split(",")]
        registers = [field for field in fields if REGISTER.match(field)]
        if operation in ("BL", "PUSH", "SWI"):
            reads, target = [], None
        elif operation in ("STR", "STRB", "STRH", "CMP", "CMN", "TST", "TEQ", "BX"):
            reads, target = registers, None
        elif operation.startswith(WRITING):
            reads, target = registers[1:] if len(registers) > 1 else [], fields[0]
        else:
            reads, target = registers, None
        for register in reads:
            if register in saved and register not in written:
                found.add(register)
        if target:
            written.add(target)
        if operation == "BL":
            written.update(("r0", "r1", "r2", "r3", "lr"))
        if operation == "POP":
            written.update(registers)
    return sorted(found)


def body(rom, address, mode, end):
    positions = function_bounds.body(rom, address,
                                     function_bounds.THUMB if mode == "thumb" else 2, end)
    lines = []
    for position in sorted(positions):
        decoded = emit_code.decode(rom, position, mode)
        if decoded is None:
            continue
        lines.append((position, decoded[0], decoded[1]))
    return lines


def limit(starts, run_end, address):
    later = [start for start in starts if address < start < run_end]
    return min(later) if later else run_end


def census(rom):
    measured = code_split.measure(rom)
    mode_of = dict((address, MODE_NAMES[mode])
                   for address, mode in export_inputs.entries_of(measured))
    addresses = name_table.emitted(sorted(mode_of), name_table.runs())
    starts = name_table.starts() or []
    base = code_split.ROM_BASE
    runs = [(base + begin, base + stop) for begin, stop, _name, _mode
            in measured["function_rows"]]

    def word(address):
        at = address - base
        return int.from_bytes(rom[at:at + 4], "little") if 0 <= at < len(rom) - 4 else None

    def run_end(address):
        found = [stop for begin, stop in runs if begin <= address < stop]
        return found[0] if found else address + 0x400

    rows = []
    for address in addresses:
        if address not in starts:
            continue
        mode = mode_of[address]
        lines = body(rom, address, mode, limit(starts, run_end(address), address))
        rows.append({"address": address, "mode": mode, "body": lines,
                     "device": touches(mode, lines, word), "callees": callees(lines),
                     "live_in": live_in(lines), "bios": bios(lines),
                     "literals": literals(mode, lines, word)})
    return rows


def describe(row, names):
    device = " ".join("%08X %s%s" % (at, operation, "" if value is None else "=0x%X" % value)
                      for at, operation, value in row["device"])
    loaded = " ".join("%08X" % value for value in row["literals"] if isinstance(value, int))
    called = " ".join(names.get(target, "sub_%08X" % target) for target in row["callees"])
    print("0x%08x %-5s device=%s" % (row["address"], row["mode"], device or "-"))
    print("  literals=%s" % (loaded or "-"))
    print("  calls=%s live_in=%s swi=%s"
          % (called or "-", ",".join(row["live_in"]) or "-",
             " ".join("0x%X" % number for number in row["bios"]) or "-"))


def quoted(evidence):
    return sorted(set(int(token, 16) for token in ADDRESS_TOKEN.findall(evidence)
                      if ADDRESS_LOW < int(token, 16) < ADDRESS_HIGH))


def audit(rows, names):
    starts = dict((row["address"], row) for row in rows)
    failures = 0
    for _number, cells in name_table.ledger_rows():
        if len(cells) != 5:
            continue
        address, _old, new, evidence_class, evidence = cells
        at = int(address, 16)
        row = starts.get(at)
        if row is None:
            print("FAIL 0x%08x %-28s %-17s not a function start" % (at, new, evidence_class))
            failures += 1
            continue
        known = set(item[0] for item in row["device"])
        known.update(item[2] for item in row["device"] if isinstance(item[2], int))
        known.update(value for value in row["literals"] if isinstance(value, int))
        known.update(row["callees"])
        known.add(at)
        missing = [token for token in quoted(evidence) if token not in known]
        print("%s 0x%08x %-28s %-17s quotes=%s missing=%s"
              % ("PASS" if not missing else "FAIL", at, new, evidence_class,
                 " ".join("%08X" % token for token in quoted(evidence)) or "-",
                 " ".join("%08X" % token for token in missing) or "-"))
        if missing:
            failures += 1
    print("ledger rows=%d failed=%d" % (len(list(name_table.ledger_rows())), failures))
    return 1 if failures else 0


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--rom", default=ROM)
    parser.add_argument("--device", action="store_true")
    parser.add_argument("--named", action="store_true")
    parser.add_argument("--calls", action="store_true")
    parser.add_argument("--leaf", action="store_true")
    parser.add_argument("--call-to", type=lambda text: int(text, 0))
    parser.add_argument("--at", type=lambda text: int(text, 0))
    parser.add_argument("--ledger", action="store_true")
    arguments = parser.parse_args(argv)
    if not os.path.exists(arguments.rom):
        print("the census needs the retail image at %s" % arguments.rom)
        return 1
    rom = open(arguments.rom, "rb").read()
    rows = census(rom)
    names = name_table.load_names()
    if arguments.at is not None:
        for row in rows:
            if row["address"] == arguments.at:
                describe(row, names)
        return 0
    if arguments.ledger:
        return audit(rows, names)
    shown = 0
    for row in rows:
        if arguments.device and not [item for item in row["device"]
                                     if 0x04000000 <= item[0] < 0x04000400]:
            continue
        if arguments.named and row["address"] not in names:
            continue
        if arguments.call_to is not None and arguments.call_to not in row["callees"]:
            continue
        if arguments.leaf and row["live_in"]:
            continue
        cells = " ".join("%08X %s%s" % (at, operation, "" if value is None else "=0x%X" % value)
                         for at, operation, value in row["device"])
        calls = " ".join(names.get(target, "sub_%08X" % target) for target in row["callees"])
        bios_calls = " ".join("0x%X" % number for number in row["bios"])
        print("0x%08x %-5s %-4s %s%s%s" % (row["address"], row["mode"],
                                          "named" if row["address"] in names else "-",
                                          cells or "no device access",
                                          "" if not calls else " calls " + calls,
                                          "" if not bios_calls else " swi " + bios_calls))
        shown += 1
    print("starts=%d shown=%d named=%d" % (len(rows), shown, len(names)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
