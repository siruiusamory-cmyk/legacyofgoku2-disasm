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
import name_table

ROM = os.path.join(ROOT, "baserom.gba")
MODE_NAMES = {code_split.MODE_THUMB: "thumb", code_split.MODE_ARM: "arm"}
POOL_LOAD = re.compile(r"\[pc, #(0x[0-9A-F]+)\]")
CALL_LABEL = re.compile(r"^\|loc_([0-9A-F]{8})\|$")
INDIRECT = re.compile(r"^r(\d+), \[r(\d+)(?:, #(0x[0-9A-F]+))?\]$")
IMMEDIATE = re.compile(r"^r(\d+), #(0x[0-9A-F]+)$")
SHIFT = re.compile(r"^r(\d+), r(\d+), #(0x[0-9A-F]+)$")
SUM = re.compile(r"^r(\d+), r(\d+), #(0x[0-9A-F]+)$")
STEP = re.compile(r"^r(\d+), #(0x[0-9A-F]+)$")
MOVE = re.compile(r"^r(\d+), r(\d+)$")
LOADS = ("LDR", "LDRB", "LDRH", "LDRSB", "LDRSH")
STORES = ("STR", "STRB", "STRH")
TERMINATORS = ("BX", "SWI")
REGISTER = re.compile(r"^(r\d+|sp|lr|pc|sl|fp|ip)$")
WRITING = ("LDR", "MOV", "MVN", "ADR", "LSL", "LSR", "ASR", "NEG", "MUL", "AND", "ORR", "EOR",
           "BIC", "ADD", "SUB", "RSB", "ADC", "SBC", "LDM")


def touches(mode, lines, word):
    registers = [None] * 16
    found = []
    for position, operation, operands in lines:
        if operation in ("PUSH", "POP", "BL"):
            for number in range(0, 8):
                registers[number] = None
            continue
        pool = POOL_LOAD.search(operands)
        if pool and operation in LOADS:
            offset = int(pool.group(1), 16)
            pool_at = ((position + 4) & ~3) + offset if mode == "thumb" else position + 8 + offset
            registers[int(operands.split(",")[0].strip()[1:])] = word(pool_at)
            continue
        indirect = INDIRECT.match(operands)
        if indirect and operation in LOADS + STORES:
            destination, base = int(indirect.group(1)), int(indirect.group(2))
            offset = int(indirect.group(3), 16) if indirect.group(3) else 0
            address = registers[base]
            if isinstance(address, int) and address >= 0x04000000:
                found.append((address + offset, operation,
                              registers[destination] if operation in STORES else None))
            if operation in LOADS:
                registers[destination] = None
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
        step = STEP.match(operands)
        if step and operation in ("ADD", "SUB"):
            left, right = registers[int(step.group(1))], int(step.group(2), 16)
            registers[int(step.group(1))] = (left + right if operation == "ADD"
                                             else left - right) if isinstance(left, int) else None
            continue
        move = MOVE.match(operands)
        if move:
            registers[int(move.group(1))] = registers[int(move.group(2))]
    return found


def callees(body):
    found = []
    for _position, operation, operands in body:
        match = CALL_LABEL.match(operands)
        if operation == "BL" and match:
            found.append(int(match.group(1), 16))
    return found


def live_in(body):
    saved = set("r%d" % number for number in range(4, 12))
    written = set()
    found = set()
    for _position, operation, operands in body:
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


def unit(lines, entries):
    body = []
    first = lines[0][0]
    for position, operation, operands in lines:
        if position != first and position in entries:
            return None
        body.append((position, operation, operands))
        if operation in TERMINATORS or operation == "B" or (operation == "POP" and "pc" in operands):
            return body
    return None


def census(rom):
    measured = code_split.measure(rom)
    mode_of = dict((address, MODE_NAMES[mode]) for address, mode in export_inputs.entries_of(measured))
    addresses = name_table.emitted(sorted(mode_of), name_table.runs())

    def word(address):
        at = address - code_split.ROM_BASE
        return int.from_bytes(rom[at:at + 4], "little") if 0 <= at < len(rom) - 4 else None

    rows = []
    for address in addresses:
        mode = mode_of[address]
        lines = []
        position = address
        for _step in range(600):
            decoded = emit_code.decode(rom, position, mode)
            if decoded is None:
                break
            lines.append((position, decoded[0], decoded[1]))
            position += decoded[2]
        body = unit(lines, set(addresses)) if lines else None
        rows.append((address, mode, body, touches(mode, body, word) if body else [],
                     callees(body) if body else [], live_in(body) if body else []))
    return rows


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--rom", default=ROM)
    parser.add_argument("--device", action="store_true")
    parser.add_argument("--named", action="store_true")
    parser.add_argument("--calls", action="store_true")
    parser.add_argument("--leaf", action="store_true")
    parser.add_argument("--call-to", type=lambda text: int(text, 0))
    arguments = parser.parse_args(argv)
    if not os.path.exists(arguments.rom):
        print("the census needs the retail image at %s" % arguments.rom)
        return 1
    rom = open(arguments.rom, "rb").read()
    rows = census(rom)
    names = name_table.load_names()
    shown = 0
    for address, mode, body, found, targets, live in rows:
        if arguments.device and not [row for row in found if 0x04000000 <= row[0] < 0x04000400]:
            continue
        if arguments.named and address not in names:
            continue
        if arguments.call_to is not None and arguments.call_to not in targets:
            continue
        if arguments.leaf and live:
            continue
        cells = " ".join("%08X %s%s" % (at, operation, "" if value is None else "=0x%X" % value)
                         for at, operation, value in found)
        calls = " ".join(names.get(target, "sub_%08X" % target) for target in targets)
        print("0x%08x %-5s %-4s %s%s%s" % (address, mode, "named" if address in names else "-",
                                          cells or "no device access",
                                          "" if not arguments.calls or not calls else " calls " + calls,
                                          ""))
        shown += 1
    print("entries=%d shown=%d named=%d" % (len(rows), shown, len(names)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
