from __future__ import annotations

import hashlib
import os
import struct
import sys

ROM_BASE = 0x08000000
ROM_SHA256 = "6e6c370c339ec9171cb1956adf837a0d342a197f78964882ef46c3086656ff75"
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
ROM = os.path.join(ROOT, "baserom.gba")

INTERPRETER = 0x080092E4
TABLE = 0x083B5C00
TABLE_LITERAL = 0x08009320
END = 0x11
TABLE_ENTRIES = 30
CONTEXT_LITERAL = 0x0800931C
QUEST_TABLE = 0x6D68DC
QUEST_STRIDE = 16
QUEST_STREAMS = (4, 8)
QUEST_TEXT = 12
LOOP = (
    (0x080092FE, "0699", "ldr r1,[sp,#0x18]"),
    (0x08009300, "0878", "ldrb r0,[r1]"),
    (0x08009302, "0131", "adds r1,#1"),
    (0x08009304, "0691", "str r1,[sp,#0x18]"),
    (0x08009306, "8000", "lsls r0,r0,#2"),
    (0x08009308, "3258", "ldr r2,[r6,r0]"),
    (0x0800930a, "002a", "cmp r2,#0"),
    (0x0800930c, "04d0", "beq #0x8009318"),
    (0x08009312, "18f00bfd", "bl #0x8021d2c"),
)
HANDLERS = {
    0x00: (0x08008F45, "byte", ((0x08008F44, "0a68", "ldr r2,[r1]"),
                               (0x08008F4C, "1378", "ldrb r3,[r2]"),
                               (0x08008F48, "0b60", "str r3,[r1]"))),
    0x01: (0x08008F5B, "varint", ((0x08008F5E, "0c68", "ldr r4,[r1]"),
                                 (0x08008F62, "2378", "ldrb r3,[r4]"),
                                 (0x08008F70, "f5d4", "bmi #0x8008f5e"))),
    0x02: (0x08008F8F, "dispatch", ((0x08008F92, "1a78", "ldrb r2,[r3]"),
                                   (0x08008F9C, "5158", "ldr r1,[r2,r1]"),
                                   (0x08008F9E, "18f0c4fe", "bl #0x8021d2a"))),
    0x03: (0x08008FA5, "dispatch", ((0x08008FA8, "1a78", "ldrb r2,[r3]"),
                                   (0x08008FBC, "4068", "ldr r0,[r0,#4]"),
                                   (0x08008FC0, "18f0b3fe", "bl #0x8021d2a"))),
    0x04: (0x08008FC7, "none", ((0x08008FC6, "0168", "ldr r1,[r0]"),)),
    0x05: (0x08008FE7, "none", ((0x08008FE6, "0168", "ldr r1,[r0]"),)),
    0x06: (0x08009001, "none", ((0x08009000, "0168", "ldr r1,[r0]"),)),
    0x07: (0x0800900F, "none", ((0x0800900E, "0168", "ldr r1,[r0]"),)),
    0x08: (0x08009023, "none", ((0x08009022, "0168", "ldr r1,[r0]"),)),
    0x09: (0x08009037, "none", ((0x08009036, "0168", "ldr r1,[r0]"),)),
    0x0A: (0x0800904B, "none", ((0x0800904A, "10b5", "push {r4,lr}"),)),
    0x0B: (0x08009063, "none", ((0x08009062, "0168", "ldr r1,[r0]"),)),
    0x0C: (0x0800907D, "none", ((0x0800907C, "0168", "ldr r1,[r0]"),)),
    0x0D: (0x08009097, "none", ((0x08009096, "0168", "ldr r1,[r0]"),)),
    0x0E: (0x080090B1, "none", ((0x080090B0, "0168", "ldr r1,[r0]"),)),
    0x0F: (0x080090CB, "none", ((0x080090CA, "0168", "ldr r1,[r0]"),)),
    0x10: (0x080090E5, "none", ((0x080090E4, "0168", "ldr r1,[r0]"),)),
    0x12: (0x080090FF, "jump", ((0x080090FE, "0868", "ldr r0,[r1]"),
                               (0x08009100, "0278", "ldrb r2,[r0]"),
                               (0x08009104, "0130", "adds r0,#1"))),
    0x13: (0x0800910B, "skip", ((0x08009118, "0378", "ldrb r3,[r0]"),
                               (0x0800911A, "0130", "adds r0,#1"),
                               (0x08009122, "c018", "adds r0,r0,r3"))),
    0x14: (0x08009129, "none", ((0x08009128, "0168", "ldr r1,[r0]"),)),
    0x15: (0x08009131, "dispatch", ((0x08009136, "1078", "ldrb r0,[r2]"),
                                   (0x0800913E, "3748", "ldr r0,[pc,#0xdc]"),
                                   (0x08009144, "18f0f1fd", "bl #0x8021d2a"))),
    0x16: (0x08009161, "dispatch", ((0x08009166, "1078", "ldrb r0,[r2]"),
                                   (0x0800916E, "2b48", "ldr r0,[pc,#0xac]"),
                                   (0x08009174, "18f0d9fd", "bl #0x8021d2a"))),
    0x17: (0x08009191, "dispatch", ((0x08009196, "1078", "ldrb r0,[r2]"),
                                   (0x0800919E, "1f48", "ldr r0,[pc,#0x7c]"),
                                   (0x080091A4, "18f0c1fd", "bl #0x8021d2a"))),
    0x18: (0x080091BD, "dispatch", ((0x080091C2, "1078", "ldrb r0,[r2]"),
                                   (0x080091CA, "1448", "ldr r0,[pc,#0x50]"),
                                   (0x080091D0, "18f0abfd", "bl #0x8021d2a"))),
    0x19: (0x080091ED, "dispatch", ((0x080091F2, "1078", "ldrb r0,[r2]"),
                                   (0x080091FA, "0848", "ldr r0,[pc,#0x20]"),
                                   (0x08009200, "18f093fd", "bl #0x8021d2a"))),
    0x1A: (0x08009225, "dispatch", ((0x0800922A, "1078", "ldrb r0,[r2]"),
                                   (0x08009232, "2a48", "ldr r0,[pc,#0xa8]"),
                                   (0x08009238, "18f077fd", "bl #0x8021d2a"))),
    0x1B: (0x08009251, "none", ((0x08009250, "0168", "ldr r1,[r0]"),
                               (0x0800925C, "4430", "adds r0,#0x44"))),
    0x1C: (0x0800926D, "loop", ((0x08009274, "1478", "ldrb r4,[r2]"),
                               (0x08009294, "001b", "subs r0,r0,r4"))),
    0x1D: (0x0800929B, "counted", ((0x0800929E, "1578", "ldrb r5,[r2]"),
                                  (0x080092AA, "2378", "ldrb r3,[r4]"),
                                  (0x080092D4, "e6d1", "bne #0x80092a4"))),
}
KIND_TEXT = {
    "byte": "one byte",
    "varint": "one 7-bit varint, bit 7 continues",
    "dispatch": "one sub-opcode byte, then the sub-handler the sub-table names",
    "none": "none",
    "jump": "one byte, forward target = the operand's address + 1 + byte",
    "skip": "one byte, and the cursor skips it when the stack top is zero",
    "loop": "one byte, backward target = the cursor - byte while a repeat count runs",
    "counted": "one count byte, then that many 7-bit varints",
}
SUBTABLES = {0x02: (0x083B5D28, 0x0800921C), 0x03: (0x083B5F70, 0x08009220)}
PINNED = {"streams": 86, "bytes": 539, "instructions": 323, "ends": 86}
PINNED_OPS = {0x00: 107, 0x01: 1, 0x02: 107, 0x04: 16, 0x05: 6, 0x11: 86}
PINNED_SUBS = {(0x02, 0x13): 99, (0x02, 0x15): 8}


class OpcodeError(ValueError):
    pass


def halfword(image, address):
    return struct.unpack_from("<H", image, address - ROM_BASE)[0]


def word(image, address):
    return struct.unpack_from("<I", image, address - ROM_BASE)[0]


def pinned(image):
    for address, expected, text in LOOP:
        found = image[address - ROM_BASE:address - ROM_BASE + len(expected) // 2].hex()
        if found != expected:
            raise OpcodeError("0x%08X holds %s, not %s (%s)" % (address, found, expected, text))
    if word(image, TABLE_LITERAL) != TABLE:
        raise OpcodeError("the table literal is 0x%08X, not 0x%08X"
                          % (word(image, TABLE_LITERAL), TABLE))
    if word(image, CONTEXT_LITERAL) != 0x03001FAC:
        raise OpcodeError("the context literal is 0x%08X, not 0x03001FAC"
                          % word(image, CONTEXT_LITERAL))
    for opcode in range(TABLE_ENTRIES):
        entry = word(image, TABLE + 4 * opcode)
        if opcode == END:
            if entry:
                raise OpcodeError("table entry 0x%02X is 0x%08X, not the null the loop exits on"
                                  % (opcode, entry))
            continue
        handler = HANDLERS[opcode][0]
        if entry != handler | 1:
            raise OpcodeError("table entry 0x%02X is 0x%08X, not 0x%08X"
                              % (opcode, entry, handler | 1))
        for address, expected, _text in HANDLERS[opcode][2]:
            found = image[address - ROM_BASE:address - ROM_BASE + len(expected) // 2].hex()
            if found != expected:
                raise OpcodeError("0x%08X holds %s, not %s" % (address, found, expected))
    for opcode, (base, literal) in SUBTABLES.items():
        found = word(image, literal)
        if found != base:
            raise OpcodeError("opcode 0x%02X's sub-table literal is 0x%08X, not 0x%08X"
                              % (opcode, found, base))


def varint(image, at, end):
    value = 0
    cursor = at
    while True:
        if cursor >= end:
            return None
        byte = image[cursor]
        cursor += 1
        value = ((value << 7) | (byte & 0x7F)) & 0xFFFFFFFF
        if not byte & 0x80:
            return value, cursor


def varint_bytes(value):
    out = bytearray()
    shift = max(0, (value.bit_length() - 1) // 7)
    for index in range(shift, -1, -1):
        out.append(((value >> (7 * index)) & 0x7F) | (0x80 if index else 0))
    return bytes(out)


def decode(image, start, end):
    at = start
    out = []
    while at < end:
        opcode = image[at]
        if opcode == END:
            out.append((at, opcode, b""))
            return out, at + 1, None
        if opcode not in HANDLERS:
            return out, None, "opcode %#04x" % opcode
        kind = HANDLERS[opcode][1]
        if kind == "none":
            out.append((at, opcode, b""))
            at += 1
        elif kind in ("byte", "dispatch", "jump", "skip", "loop"):
            if at + 2 > end:
                return out, None, "operand"
            out.append((at, opcode, bytes(image[at + 1:at + 2])))
            at += 2
        elif kind == "varint":
            got = varint(image, at + 1, end)
            if got is None:
                return out, None, "varint"
            value, stop = got
            out.append((at, opcode, bytes(image[at + 1:stop]), value))
            at = stop
        elif kind == "counted":
            if at + 1 >= end:
                return out, None, "count"
            count = image[at + 1]
            cursor = at + 2
            values = []
            for _index in range(count):
                got = varint(image, cursor, end)
                if got is None:
                    return out, None, "varint"
                values.append(got[0])
                cursor = got[1]
            out.append((at, opcode, bytes(image[at + 1:cursor]), count, values))
            at = cursor
        else:
            return out, None, "kind %s" % kind
    return out, None, "no end"


def encode(instructions):
    out = bytearray()
    for item in instructions:
        opcode = item[1]
        out.append(opcode)
        if opcode == END:
            continue
        kind = HANDLERS[opcode][1]
        if kind in ("byte", "dispatch", "jump", "skip", "loop"):
            out += item[2]
        elif kind == "varint":
            out += varint_bytes(item[3])
        elif kind == "counted":
            out.append(item[3])
            for value in item[4]:
                out += varint_bytes(value)
    return bytes(out)


def streams(image):
    def read(offset):
        return struct.unpack_from("<I", image, offset)[0]

    table = QUEST_TABLE
    out = []
    offset = table
    while offset + QUEST_STRIDE <= len(image):
        first = read(offset)
        if first >= 0x10:
            break
        addresses = [read(offset + field) for field in QUEST_STREAMS]
        text = read(offset + QUEST_TEXT)
        if not all(ROM_BASE <= value < ROM_BASE + len(image) for value in addresses + [text]):
            break
        start = text - ROM_BASE
        if not all(0x20 <= byte < 0x7F for byte in image[start:start + 1]):
            break
        out.append((offset, addresses))
        offset += QUEST_STRIDE
    return out


def census(image):
    rows = []
    for record, addresses in streams(image):
        for field, address in zip(QUEST_STREAMS, addresses):
            instructions, stop, problem = decode(image, address - ROM_BASE,
                                                 min(len(image), address - ROM_BASE + 0x100))
            rows.append({"record": record, "field": field, "start": address - ROM_BASE,
                         "stop": stop, "problem": problem, "instructions": instructions})
    return rows


def totals(rows):
    clean = [row for row in rows if row["problem"] is None]
    ops = {}
    for row in clean:
        for item in row["instructions"]:
            ops[item[1]] = ops.get(item[1], 0) + 1
    subs = {}
    for row in clean:
        for item in row["instructions"]:
            if item[1] in SUBTABLES:
                subs[(item[1], item[2][0])] = subs.get((item[1], item[2][0]), 0) + 1
    return {"streams": len(rows), "clean": len(clean),
            "bytes": sum(row["stop"] - row["start"] for row in clean),
            "instructions": sum(len(row["instructions"]) for row in clean),
            "ends": sum(1 for row in clean if row["instructions"][-1][1] == END),
            "ops": ops, "subs": subs,
            "problems": sorted({row["problem"] for row in rows if row["problem"]})}


def table_text():
    lines = ["| opcode | handler | operands | quoted reads |", "|---|---|---|---|"]
    for opcode in range(TABLE_ENTRIES):
        if opcode == END:
            lines.append("| `0x%02X` | none | ends the stream | the table entry is null |" % opcode)
            continue
        handler, kind, quotes = HANDLERS[opcode]
        proof = ", ".join("`0x%08X` `%s` `%s`" % quote for quote in quotes)
        lines.append("| `0x%02X` | `0x%08X` | %s | %s |" % (opcode, handler, KIND_TEXT[kind],
                                                             proof))
    return "\n".join(lines) + "\n"


def read_rom(path=None):
    path = path or ROM
    if not os.path.exists(path):
        raise SystemExit("the opcode census needs the retail image at %s" % path)
    image = open(path, "rb").read()
    if hashlib.sha256(image).hexdigest() != ROM_SHA256:
        raise SystemExit("%s is not the canonical image" % path)
    return image


def check(image):
    pinned(image)
    rows = census(image)
    counts = totals(rows)
    problems = []
    for key, expected in PINNED.items():
        if counts[key] != expected:
            problems.append("%s is %d, not %d" % (key, counts[key], expected))
    if counts["clean"] != counts["streams"]:
        problems.append("%d of %d streams do not decode"
                        % (counts["streams"] - counts["clean"], counts["streams"]))
    if counts["ops"] != PINNED_OPS:
        problems.append("the opcode histogram is %s, not %s" % (counts["ops"], PINNED_OPS))
    if counts["subs"] != PINNED_SUBS:
        problems.append("the top/sub opcode histogram is %s" % (counts["subs"],))
    for row in rows:
        if row["problem"] is None:
            blob = encode(row["instructions"])
            if blob != image[row["start"]:row["stop"]]:
                problems.append("the stream at %#x does not re-emit its bytes" % row["start"])
    for problem in problems:
        print("OPCODE FAIL: %s" % problem)
    print("OPCODE %s" % ("PASS" if not problems else "FAIL"))
    return 0 if not problems else 1


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv not in ([], ["--check"], ["--table"]):
        print("usage: python tools\\research\\opcode_stream.py [--check|--table]")
        return 2
    image = read_rom()
    if argv == ["--table"]:
        pinned(image)
        sys.stdout.write(table_text())
        return 0
    pinned(image)
    rows = census(image)
    counts = totals(rows)
    print("streams=%d clean=%d bytes=%d instructions=%d ends=%d"
          % (counts["streams"], counts["clean"], counts["bytes"], counts["instructions"],
             counts["ends"]))
    print("ops=%s subs=%s problems=%s"
          % ([(hex(key), value) for key, value in sorted(counts["ops"].items())],
             [((hex(pair[0]), hex(pair[1])), value)
              for pair, value in sorted(counts["subs"].items())],
             counts["problems"]))
    for row in rows[:4]:
        print("  %#x..%#x %s" % (row["start"], row["stop"],
                                 [(hex(item[1]), item[2].hex()) for item in row["instructions"]]))
    if not argv:
        return 0
    return check(image)


if __name__ == "__main__":
    raise SystemExit(main())
