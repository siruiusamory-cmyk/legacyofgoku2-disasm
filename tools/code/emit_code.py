from __future__ import annotations

import argparse
import hashlib
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "tools", "split"))
sys.path.insert(0, os.path.join(ROOT, "tools", "recomp"))

import code_split
import export_inputs
import name_table

ROM = os.path.join(ROOT, "baserom.gba")
SHA1 = os.path.join(ROOT, "baserom.sha1")
OUT = os.path.join(ROOT, "build", "code")
ROM_BASE = code_split.ROM_BASE
START = 0x100
END = 0x800000
CLASS_TAGS = {"proven code": "proven", "filtered pointer-entry code": "filtered",
              "table-held code": "table", "gap-fill code": "gap"}
REGISTERS = ("r0", "r1", "r2", "r3", "r4", "r5", "r6", "r7",
             "r8", "r9", "r10", "r11", "r12", "sp", "lr", "pc")
CONDITIONS = ("eq", "ne", "cs", "cc", "mi", "pl", "vs", "vc", "hi", "ls", "ge", "lt", "gt", "le")
THUMB_ALU = ("AND", "EOR", "LSL", "LSR", "ASR", "ADC", "SBC", "ROR",
             "TST", "NEG", "CMP", "CMN", "ORR", "MUL", "BIC", "MVN")
THUMB_HI = ("ADD", "CMP", "MOV")
THUMB_MEMORY = ("STR", "STRH", "STRB", "LDRSB", "LDR", "LDRH", "LDRB", "LDRSH")
DATA_PROCESSING = ("AND", "EOR", "SUB", "RSB", "ADD", "ADC", "SBC", "RSC",
                   "TST", "TEQ", "CMP", "CMN", "ORR", "MOV", "BIC", "MVN")
NO_DESTINATION = (8, 9, 10, 11)
NO_SOURCE = (13, 15)


def register(number):
    return REGISTERS[number]


def label(address):
    return "|loc_%08X|" % address


def function_label(address, index=None):
    if index and address in index:
        return "|%s|" % index[address]
    return "|sub_%08X|" % address


def halfwords(rom, address):
    return int.from_bytes(rom[address - ROM_BASE:address - ROM_BASE + 2], "little")


def word(rom, address):
    return int.from_bytes(rom[address - ROM_BASE:address - ROM_BASE + 4], "little")


def rotate_right(value, amount):
    amount %= 32
    return ((value >> amount) | (value << (32 - amount))) & 0xFFFFFFFF if amount else value


def thumb_branch(address, half):
    offset = half & 0x7FF
    if offset & 0x400:
        offset -= 0x800
    return (address + 4 + (offset << 1)) & 0xFFFFFFFF


def thumb_conditional(address, half):
    offset = half & 0xFF
    if offset & 0x80:
        offset -= 0x100
    return (address + 4 + (offset << 1)) & 0xFFFFFFFF


def thumb_call(high, low):
    offset = ((high & 0x7FF) << 11) | (low & 0x7FF)
    if high & 0x400:
        offset -= 1 << 22
    return offset << 1


def arm_branch(address, instruction):
    offset = instruction & 0xFFFFFF
    if offset & 0x800000:
        offset -= 0x1000000
    return (address + 8 + (offset << 2)) & 0xFFFFFFFF


def arm_operand2(instruction):
    if instruction & (1 << 25):
        imm8 = instruction & 0xFF
        rotate = ((instruction >> 8) & 0xF) * 2
        return "#0x%X" % rotate_right(imm8, rotate)
    register_number = instruction & 0xF
    if instruction & 0x10:
        return "%s, %s %s" % (register(register_number),
                              ("LSL", "LSR", "ASR", "ROR")[(instruction >> 5) & 3],
                              register((instruction >> 8) & 0xF))
    kind = (instruction >> 5) & 3
    amount = (instruction >> 7) & 0x1F
    if kind == 0 and amount == 0:
        return register(register_number)
    if kind == 3 and amount == 0:
        return register(register_number) + ", RRX"
    return "%s, %s #0x%X" % (register(register_number), ("LSL", "LSR", "ASR", "ROR")[kind],
                             amount or 32)


def thumb_text(rom, address):
    half = halfwords(rom, address)
    if half >= 0xF000:
        low = halfwords(rom, address + 2)
        if half >= 0xF800 or low < 0xF800:
            return None
        target = (address + 4 + thumb_call(half, low)) & 0xFFFFFFFF
        return "BL", label(target), 4
    if (half & 0xF800) == 0xE000:
        return "B", label(thumb_branch(address, half)), 2
    if (half & 0xF000) == 0xD000:
        condition = (half >> 8) & 0xF
        if condition == 0xE:
            return "UDF", "#0x%X" % (half & 0xFF), 2
        if condition == 0xF:
            return "SWI", "0x%X" % (half & 0xFF), 2
        return "B" + CONDITIONS[condition].upper(), label(thumb_conditional(address, half)), 2
    if (half & 0xF800) == 0x0000:
        return "LSL", "%s, %s, #0x%X" % (register(half & 7), register((half >> 3) & 7),
                                         (half >> 6) & 0x1F), 2
    if (half & 0xF800) == 0x0800:
        amount = (half >> 6) & 0x1F
        return "LSR", "%s, %s, #0x%X" % (register(half & 7), register((half >> 3) & 7),
                                         amount or 32), 2
    if (half & 0xF800) == 0x1000:
        amount = (half >> 6) & 0x1F
        return "ASR", "%s, %s, #0x%X" % (register(half & 7), register((half >> 3) & 7),
                                         amount or 32), 2
    if (half & 0xF800) == 0x1800:
        operation = "SUB" if half & 0x0200 else "ADD"
        if half & 0x0400:
            return operation, "%s, %s, #0x%X" % (register(half & 7),
                                                 register((half >> 3) & 7),
                                                 (half >> 6) & 7), 2
        return operation, "%s, %s, %s" % (register(half & 7), register((half >> 3) & 7),
                                          register((half >> 6) & 7)), 2
    if (half & 0xE000) == 0x2000:
        operation = ("MOV", "CMP", "ADD", "SUB")[(half >> 11) & 3]
        return operation, "%s, #0x%X" % (register((half >> 8) & 7), half & 0xFF), 2
    if (half & 0xFC00) == 0x4000:
        operation = THUMB_ALU[(half >> 6) & 0xF]
        return operation, "%s, %s" % (register(half & 7), register((half >> 3) & 7)), 2
    if (half & 0xFC00) == 0x4400:
        kind = (half >> 8) & 3
        if kind == 3:
            return "BX", register((half >> 3) & 0xF), 2
        if (half & 0xC0) == 0:
            return None
        destination = (half & 7) | ((half >> 4) & 8)
        source = (half >> 3) & 0xF
        return THUMB_HI[kind], "%s, %s" % (register(destination), register(source)), 2
    if (half & 0xF800) == 0x4800:
        return "LDR", "%s, [pc, #0x%X]" % (register((half >> 8) & 7), (half & 0xFF) * 4), 2
    if (half & 0xF000) == 0x5000:
        operation = THUMB_MEMORY[(half >> 9) & 7]
        return operation, "%s, [%s, %s]" % (register(half & 7), register((half >> 3) & 7),
                                            register((half >> 6) & 7)), 2
    if (half & 0xF000) in (0x6000, 0x7000, 0x8000):
        top = half & 0xF000
        if top == 0x6000:
            operation, step = ("LDR", 4) if half & 0x0800 else ("STR", 4)
        elif top == 0x7000:
            operation, step = ("LDRB", 1) if half & 0x0800 else ("STRB", 1)
        else:
            operation, step = ("LDRH", 2) if half & 0x0800 else ("STRH", 2)
        return operation, "%s, [%s, #0x%X]" % (register(half & 7), register((half >> 3) & 7),
                                               ((half >> 6) & 0x1F) * step), 2
    if (half & 0xF000) == 0x9000:
        operation = "LDR" if half & 0x0800 else "STR"
        return operation, "%s, [sp, #0x%X]" % (register((half >> 8) & 7), (half & 0xFF) * 4), 2
    if (half & 0xF000) == 0xA000:
        base = "sp" if half & 0x0800 else "pc"
        return "ADD", "%s, %s, #0x%X" % (register((half >> 8) & 7), base,
                                         (half & 0xFF) * 4), 2
    if (half & 0xFF00) in (0xB000, 0xB080):
        operation = "SUB" if half & 0x80 else "ADD"
        return operation, "sp, #0x%X" % ((half & 0x7F) * 4), 2
    if (half & 0xFE00) == 0xB400:
        return "PUSH", thumb_list(half, "lr"), 2
    if (half & 0xFE00) == 0xBC00:
        return "POP", thumb_list(half, "pc"), 2
    if (half & 0xF000) == 0xC000:
        operation = "LDMIA" if half & 0x0800 else "STMIA"
        return operation, "%s!, %s" % (register((half >> 8) & 7),
                                       thumb_list(half, None)), 2
    return None


def thumb_list(half, ninth):
    names = [register(number) for number in range(8) if half & (1 << number)]
    if ninth and half & 0x100:
        names.append(ninth)
    if not names:
        return None
    return "{" + ", ".join(names) + "}"


def arm_text(rom, address):
    instruction = word(rom, address)
    if instruction >> 28 == 0xF:
        return None
    suffix = "" if instruction >> 28 == 0xE else CONDITIONS[instruction >> 28].upper()
    if (instruction & 0x0FBF0FFF) == 0x010F0000:
        special = "SPSR" if instruction & 0x00400000 else "CPSR"
        return "MRS" + suffix, "%s, %s" % (register((instruction >> 12) & 0xF), special), 4
    if (instruction & 0x0FB0FFF0) == 0x0120F000:
        fields = arm_fields(instruction)
        if fields is None:
            return None
        return "MSR" + suffix, "%s, %s" % (fields, register(instruction & 0xF)), 4
    if (instruction & 0x0FB0F000) == 0x0320F000:
        fields = arm_fields(instruction)
        if fields is None:
            return None
        return "MSR" + suffix, "%s, %s" % (fields, arm_operand2(instruction)), 4
    if (instruction & 0x0FFFFFF0) == 0x012FFF10:
        return "BX" + suffix, register(instruction & 0xF), 4
    if (instruction & 0x0E000090) == 0x00000090:
        if instruction & 0x60:
            return arm_halfword(instruction, suffix)
        return arm_multiply(instruction, suffix)
    operation = (instruction >> 25) & 7
    if operation in (0, 1):
        return arm_data_processing(instruction, suffix)
    if operation in (2, 3):
        return arm_transfer(instruction, suffix)
    if operation == 4:
        return arm_block(instruction, suffix)
    if operation == 5:
        return ("BL" if instruction & (1 << 24) else "B") + suffix, label(
            arm_branch(address, instruction)), 4
    if operation == 15:
        return "SWI" + suffix, "0x%X" % (instruction & 0xFFFFFF), 4
    return None


def arm_fields(instruction):
    names = []
    if instruction & 0x00010000:
        names.append("c")
    if instruction & 0x00020000:
        names.append("x")
    if instruction & 0x00040000:
        names.append("s")
    if instruction & 0x00080000:
        names.append("f")
    if not names:
        return None
    return ("SPSR_" if instruction & 0x00400000 else "CPSR_") + "".join(names)


def arm_data_processing(instruction, suffix):
    opcode = (instruction >> 21) & 0xF
    storing = instruction & (1 << 20)
    source = (instruction >> 16) & 0xF
    destination = (instruction >> 12) & 0xF
    operand = arm_operand2(instruction)
    name = DATA_PROCESSING[opcode]
    if opcode in NO_DESTINATION:
        if not storing:
            return None
        return name + suffix, "%s, %s" % (register(source), operand), 4
    if opcode in NO_SOURCE:
        return name + suffix + ("S" if storing else ""), "%s, %s" % (register(destination),
                                                                    operand), 4
    return (name + suffix + ("S" if storing else ""),
            "%s, %s, %s" % (register(destination), register(source), operand), 4)


def arm_shift(instruction):
    kind = (instruction >> 5) & 3
    if instruction & 0x10:
        return "%s %s" % (("LSL", "LSR", "ASR", "ROR")[kind], register((instruction >> 8) & 0xF))
    amount = (instruction >> 7) & 0x1F
    if kind == 0 and amount == 0:
        return None
    if kind == 3 and amount == 0:
        return "RRX"
    return "%s #0x%X" % (("LSL", "LSR", "ASR", "ROR")[kind], amount or 32)


def arm_transfer(instruction, suffix):
    register_offset = instruction & (1 << 25)
    pre = instruction & (1 << 24)
    up = "U" if instruction & (1 << 23) else ""
    byte = "B" if instruction & (1 << 22) else ""
    write = instruction & (1 << 21)
    load = instruction & (1 << 20)
    source = (instruction >> 16) & 0xF
    destination = (instruction >> 12) & 0xF
    if register_offset:
        if not up:
            return None
        shift = arm_shift(instruction)
        offset = register(instruction & 0xF) + (", " + shift if shift else "")
    else:
        value = instruction & 0xFFF
        offset = ("#0x%X" % value) if up else ("#-0x%X" % value if value else "#0")
    name = ("LDR" if load else "STR") + suffix + byte
    if pre and write:
        return name, "%s, [%s, %s]!" % (register(destination), register(source),
                                        offset), 4
    if pre:
        return name, "%s, [%s, %s]" % (register(destination), register(source),
                                       offset), 4
    if write:
        return name, "%s, [%s], %s" % (register(destination), register(source),
                                       offset), 4
    return None


def arm_halfword(instruction, suffix):
    pre = instruction & (1 << 24)
    up = instruction & (1 << 23)
    immediate = instruction & (1 << 22)
    write = instruction & (1 << 21)
    load = instruction & (1 << 20)
    source = (instruction >> 16) & 0xF
    destination = (instruction >> 12) & 0xF
    kind = (instruction >> 5) & 3
    if not kind:
        return None
    name = ("LDR" if load else "STR") + suffix + ("H", "SB", "SH")[kind - 1]
    if immediate:
        value = ((instruction >> 4) & 0xF0) | (instruction & 0xF)
        offset = ("#0x%X" % value) if up else "#-0x%X" % value
        offset = offset if value else "#0"
    else:
        if not up:
            return None
        offset = register(instruction & 0xF)
    if not pre:
        return None
    return name + suffix, "%s, [%s, %s]%s" % (register(destination), register(source),
                                              offset, "!" if write else ""), 4


def arm_multiply(instruction, suffix):
    accumulate = instruction & (1 << 21)
    storing = instruction & (1 << 20)
    destination = (instruction >> 16) & 0xF
    accumulator = (instruction >> 12) & 0xF
    source = instruction & 0xF
    second = (instruction >> 8) & 0xF
    if accumulate:
        return "MLA" + suffix + ("S" if storing else ""), "%s, %s, %s, %s" % (
            register(destination), register(source), register(second), register(accumulator)), 4
    return "MUL" + suffix + ("S" if storing else ""), "%s, %s, %s" % (
        register(destination), register(source), register(second)), 4


def arm_block(instruction, suffix):
    pre = instruction & (1 << 24)
    up = instruction & (1 << 23)
    write = instruction & (1 << 21)
    load = instruction & (1 << 20)
    source = (instruction >> 16) & 0xF
    names = [register(number) for number in range(16) if instruction & (1 << number)]
    if not names:
        return None
    if pre and up:
        mode = "IB"
    elif pre and not up:
        mode = "DA"
    elif up:
        mode = "IA"
    else:
        mode = "DB"
    return ("LDM" if load else "STM") + suffix + mode, "%s%s, {%s}" % (
        register(source), "!" if write else "", ", ".join(names)), 4


def decode(rom, address, mode):
    if mode == "thumb":
        half = halfwords(rom, address)
        size = 4 if half >= 0xF000 else 2
        text = thumb_text(rom, address)
        if text is None or text[0] is None:
            return None
        if text[0] == "POP" or text[0] == "PUSH" or text[0] in ("LDMIA", "STMIA"):
            if text[1] is None:
                return None
        return text[0], text[1], size
    text = arm_text(rom, address)
    if text is None or text[0] is None or text[1] is None:
        return None
    return text[0], text[1], text[2]


def data_text(rom, begin, end):
    lines = []
    position = begin
    if begin % 4:
        while position + 2 <= end:
            lines.append("\tDCW\t0x%04X" % halfwords(rom, position))
            position += 2
    while position + 4 <= end:
        lines.append("\tDCD\t0x%08X" % word(rom, position))
        position += 4
    while position + 2 <= end:
        lines.append("\tDCW\t0x%04X" % halfwords(rom, position))
        position += 2
    if position < end:
        lines.append("\tDCB\t0x%02X" % rom[position - ROM_BASE])
    return lines


def fragments(rom):
    index = name_table.load_names()
    measured = code_split.measure(rom)
    entries = set(address for address, _mode in export_inputs.entries_of(measured))
    runs = name_table.runs()
    kept_bytes = {}
    kept_rows = []
    raw = []
    for start, stop, name, mode in measured["function_rows"]:
        if stop <= START or start >= END:
            raw.append((ROM_BASE + start, stop - start, "outside the remainder"))
            continue
        begin, end = max(start, START), min(stop, END)
        if start < START:
            raw.append((ROM_BASE + start, START - start, "already carried before the remainder"))
        if stop > END:
            raw.append((ROM_BASE + END, stop - END, "past the end of the image"))
        if name_table.covered(runs, begin, end):
            raw.append((ROM_BASE + begin, end - begin, "inside a carried container"))
            continue
        text_mode = "thumb" if mode == code_split.MODE_THUMB else "arm"
        lines = []
        position = ROM_BASE + begin
        while position < ROM_BASE + end:
            step = decode(rom, position, text_mode)
            if step is None:
                lines = None
                break
            operation, operands, size = step
            lines.append((position, operation, operands))
            position += size
        if lines is None or position != ROM_BASE + end:
            raw.append((ROM_BASE + begin, end - begin, "no byte-exact source form"))
            continue
        tag = CLASS_TAGS[name]
        kept_bytes[tag] = kept_bytes.get(tag, 0) + (end - begin)
        kept_rows.append((ROM_BASE + begin, ROM_BASE + end, text_mode, tag, lines))
    pools = []
    for start, stop in measured["pool"]:
        if stop <= START or start >= END:
            raw.append((ROM_BASE + start, stop - start, "outside the remainder"))
            continue
        begin, end = max(start, START), min(stop, END)
        if name_table.covered(runs, begin, end):
            raw.append((ROM_BASE + begin, end - begin, "inside a carried container"))
            continue
        pools.append((ROM_BASE + begin, ROM_BASE + end))
    targets = set()
    for _begin, _end, _mode, _tag, lines in kept_rows:
        for _position, operation, operands in lines:
            if operation.startswith("B") and operands.startswith("|loc_"):
                targets.add(int(operands[5:13], 16))
    files = {}
    for begin, end, mode, _tag, lines in kept_rows:
        text = ["\tCODE16" if mode == "thumb" else "\tCODE32"]
        for position, operation, operands in lines:
            if position == begin or position in targets or position in entries:
                if position in entries:
                    text.append(function_label(position, index))
                text.append(label(position))
            text.append("\t%s\t%s" % (operation, operands))
        files["code_%08x.s" % begin] = "\n".join(text) + "\n"
    for begin, end in pools:
        files["pool_%08x.s" % begin] = "\n".join(data_text(rom, begin, end)) + "\n"
    return {"measured": measured, "files": files, "kept": kept_rows, "pools": pools,
            "raw": raw, "bytes": kept_bytes, "entries": entries, "targets": targets,
            "pool_bytes": sum(end - begin for begin, end in pools)}


def span_files(result):
    spans = [(begin, end, "code_%08x.s" % begin)
             for begin, end, _mode, _tag, _lines in result["kept"]]
    spans += [(begin, end, "pool_%08x.s" % begin) for begin, end in result["pools"]]
    return sorted(spans)


def describe(result):
    lines = []
    for tag in ("proven", "filtered", "table", "gap"):
        lines.append("emitted %s=%d" % (tag, result["bytes"].get(tag, 0)))
    lines.append("emitted pool=%d" % result["pool_bytes"])
    lines.append("emitted bytes=%d" % (sum(result["bytes"].values()) + result["pool_bytes"]))
    causes = {}
    for _begin, size, cause in result["raw"]:
        causes[cause] = causes.get(cause, 0) + size
    for cause in sorted(causes):
        lines.append("left raw %s=%d" % (cause.replace(" ", "-"), causes[cause]))
    labelled = sum(1 for address in result["entries"]
                   if any(begin <= address < end for begin, end, _mode, _tag, _lines
                          in result["kept"]))
    lines.append("entries=%d labelled=%d" % (len(result["entries"]), labelled))
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--out", default=OUT)
    parser.add_argument("--rom", default=ROM)
    arguments = parser.parse_args(argv)
    if not os.path.exists(arguments.rom):
        print("the code generator needs the retail image at %s" % arguments.rom)
        return 1
    rom = open(arguments.rom, "rb").read()
    if os.path.exists(SHA1):
        expected = open(SHA1, encoding="ascii").read().strip().lower()
        measured = hashlib.sha1(rom).hexdigest()
        if measured != expected:
            print("%s sha1 %s is not %s's %s" % (arguments.rom, measured, os.path.basename(SHA1),
                                                 expected))
            return 1
    result = fragments(rom)
    print(describe(result))
    if arguments.write:
        os.makedirs(arguments.out, exist_ok=True)
        for name in os.listdir(arguments.out):
            if name.endswith(".s"):
                os.remove(os.path.join(arguments.out, name))
        for name in sorted(result["files"]):
            with open(os.path.join(arguments.out, name), "w", encoding="utf-8",
                      newline="\n") as handle:
                handle.write(result["files"][name])
        print("wrote %d file(s) to %s" % (len(result["files"]), arguments.out))
        return 0
    if arguments.check:
        missing = []
        if not os.path.isdir(arguments.out):
            print("CODE FAIL: %s is absent" % arguments.out)
            return 1
        present = sorted(name for name in os.listdir(arguments.out) if name.endswith(".s"))
        for name in sorted(result["files"]):
            path = os.path.join(arguments.out, name)
            if name not in present:
                missing.append(name)
                continue
            if open(path, encoding="utf-8", newline="").read() != result["files"][name]:
                missing.append(name + " (content)")
        for name in present:
            if name not in result["files"]:
                missing.append(name + " (extra)")
        if missing:
            print("CODE FAIL: %d file(s) differ: %s" % (len(missing), ", ".join(missing[:6])))
            return 1
        print("CODE PASS files=%d" % len(present))
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
