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
INDIRECT = re.compile(r"^r(\d+), \[r(\d+)(?:, #(0x[0-9A-F]+))?\]$")
IMMEDIATE = re.compile(r"^r(\d+), #(0x[0-9A-F]+)$")
SHIFT = re.compile(r"^r(\d+), r(\d+), #(0x[0-9A-F]+)$")
SUM = re.compile(r"^r(\d+), r(\d+), #(0x[0-9A-F]+)$")
STEP = re.compile(r"^r(\d+), #(0x[0-9A-F]+)$")
MOVE = re.compile(r"^r(\d+), r(\d+)$")
LOADS = ("LDR", "LDRB", "LDRH", "LDRSB", "LDRSH")
STORES = ("STR", "STRB", "STRH")
TERMINATORS = ("BX", "SWI")


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
            value = left + right if operation == "ADD" else left - right
            registers[int(total.group(1))] = value if isinstance(left, int) else None
            continue
        step = STEP.match(operands)
        if step and operation in ("ADD", "SUB"):
            left, right = registers[int(step.group(1))], int(step.group(2), 16)
            value = left + right if operation == "ADD" else left - right
            registers[int(step.group(1))] = value if isinstance(left, int) else None
            continue
        move = MOVE.match(operands)
        if move:
            registers[int(move.group(1))] = registers[int(move.group(2))]
    return found


def unit(lines, entries):
    body = []
    first = lines[0][0]
    for position, operation, operands in lines:
        if position != first and position in entries:
            return None
        body.append((position, operation, operands))
        if operation in TERMINATORS or (operation == "POP" and "pc" in operands):
            return body
        if operation.startswith("B") and not operation.startswith(("BL", "BX")):
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
        rows.append((address, mode, body, touches(mode, body, word) if body else []))
    return rows


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--rom", default=ROM)
    parser.add_argument("--device", action="store_true")
    parser.add_argument("--named", action="store_true")
    arguments = parser.parse_args(argv)
    if not os.path.exists(arguments.rom):
        print("the census needs the retail image at %s" % arguments.rom)
        return 1
    rom = open(arguments.rom, "rb").read()
    rows = census(rom)
    names = name_table.load_names()
    shown = 0
    for address, mode, body, found in rows:
        if arguments.device and not [row for row in found if 0x04000000 <= row[0] < 0x04000400]:
            continue
        if arguments.named and address not in names:
            continue
        cells = " ".join("%08X %s%s" % (at, operation, "" if value is None else "=0x%X" % value)
                         for at, operation, value in found)
        print("0x%08x %-5s %-4s %s%s" % (address, mode, "named" if address in names else "-",
                                         cells or "no device access", ""))
        shown += 1
    print("entries=%d shown=%d named=%d" % (len(rows), shown, len(names)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
