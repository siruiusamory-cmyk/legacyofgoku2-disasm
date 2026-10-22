from __future__ import annotations

import hashlib
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "tools", "compress"))

import container

ROM = os.path.join(ROOT, "baserom.gba")
ROM_BASE = 0x08000000
ROM_SIZE = 0x800000
ROM_SHA256 = "6e6c370c339ec9171cb1956adf837a0d342a197f78964882ef46c3086656ff75"
BLOCK = 0x10000
FONT_TABLE = 0x0028724
FONT_CODES = 256
FONT_LIMIT = 0x1000
ROSTER = 0x6F8E40
ROSTER_RECORDS = 128
ROSTER_STRIDE = 20
ROSTER_FIELDS = (0, 4)
OBJECTIVES = 0x6D68DC
OBJECTIVE_RECORDS = 43
OBJECTIVE_STRIDE = 16
OBJECTIVE_TEXT = 12
TEXT_CONTAINER = 0x6F4394
TEXT_DECLARED = 0x10000
LIMIT = 2048
PRINTABLE = frozenset((9, 10, 13)) | frozenset(range(0x20, 0x7F))
DRAW = (
    (0x08004A70, "8149", "ldr r1,[pc,#0x204]"),
    (0x08004A74, "e960", "str r1,[r5,#0xc]"),
    (0x0801F718, "3878", "ldrb r0,[r7]"),
    (0x0801F71A, "0028", "cmp r0,#0"),
    (0x0801F71E, "2028", "cmp r0,#0x20"),
    (0x0801F740, "e168", "ldr r1,[r4,#0xc]"),
    (0x0801F742, "5b00", "lsls r3,r3,#1"),
    (0x0801F744, "cb5a", "ldrh r3,[r1,r3]"),
    (0x0801F746, "5b00", "lsls r3,r3,#1"),
    (0x0801F748, "c95a", "ldrh r1,[r1,r3]"),
    (0x0801F74A, "0131", "adds r1,#1"),
)
LITERAL = 0x004C78
LITERAL_VALUE = 0x08028724
SAMPLE = ((" ", 2, 3), ("A", 5, 6), ("a", 5, 6), (".", 1, 2))
PINNED = {"codes": 221, "records": 221, "roster_pointers": 256, "roster": 124,
          "roster_bytes": 15512, "objectives": 43, "objective_bytes": 1897,
          "contained": 124, "plain": 0, "null_whole": 0, "null_region": 0}


class TextError(ValueError):
    pass


def u16(image, offset):
    return struct.unpack_from("<H", image, offset)[0]


def u32(image, offset):
    return struct.unpack_from("<I", image, offset)[0]


def in_image(image, address):
    return ROM_BASE <= address < ROM_BASE + len(image)


def check_reader(image):
    for address, hex_bytes, text in DRAW:
        size = len(hex_bytes) // 2
        read = image[address - ROM_BASE:address - ROM_BASE + size].hex()
        if read != hex_bytes:
            raise TextError("0x%08X holds %s, not the quoted %s (%s)"
                            % (address, read, hex_bytes, text))
    if u32(image, LITERAL) != LITERAL_VALUE:
        raise TextError("the font literal at file 0x%X is 0x%08X, not 0x%08X"
                        % (LITERAL, u32(image, LITERAL), LITERAL_VALUE))


def font(image, table=FONT_TABLE):
    offsets = [u16(image, table + 2 * code) for code in range(FONT_CODES)]
    defined = [(code, offset) for code, offset in enumerate(offsets) if offset]
    widths = {}
    for code, offset in defined:
        if offset > FONT_LIMIT:
            raise TextError("code 0x%02X names offset %d, past the %d-unit table"
                            % (code, offset, FONT_LIMIT))
        widths[code] = u16(image, table + 2 * offset)
    return {"codes": len(defined), "records": len(set(offsets) - {0}),
            "widths": widths}


def string(image, address):
    if not in_image(image, address):
        raise TextError("0x%08X is outside the image" % address)
    at = address - ROM_BASE
    end = at
    while end < len(image) and image[end] != 0:
        if image[end] not in PRINTABLE:
            raise TextError("the string at 0x%08X holds 0x%02X at %d, not a printable byte"
                            % (address, image[end], end - at))
        if end - at >= LIMIT:
            raise TextError("the string at 0x%08X runs past %d bytes" % (address, LIMIT))
        end += 1
    if end >= len(image):
        raise TextError("the string at 0x%08X is not terminated" % address)
    return {"address": address, "bytes": image[at:end], "length": end - at}


def records(image, table, count, stride, fields):
    rows = []
    for index in range(count):
        for field in fields:
            rows.append(u32(image, table + stride * index + field))
    return rows


def roster(image):
    return [string(image, address) for address in records(
        image, ROSTER, ROSTER_RECORDS, ROSTER_STRIDE, ROSTER_FIELDS)]


def objectives(image):
    return [string(image, address) for address in records(
        image, OBJECTIVES, OBJECTIVE_RECORDS, OBJECTIVE_STRIDE, (OBJECTIVE_TEXT,))]


def text_container(image):
    site = TEXT_CONTAINER
    kind, declared = container.read_header(image, site)
    if kind != container.STORED or declared != TEXT_DECLARED:
        raise TextError("0x%08X is kind %d declaring %d, not a stored %d-byte container"
                        % (TEXT_CONTAINER, kind, declared, TEXT_DECLARED))
    return {"low": site + container.HEADER_SIZE,
            "high": site + container.HEADER_SIZE + declared}


def inside(row, blob):
    return blob["low"] <= row["address"] - ROM_BASE < blob["high"]


def permuted(image, low=0, high=None):
    low = low or 0
    high = len(image) if high is None else high
    out = bytearray(image)
    for start in range(low, high, BLOCK):
        stop = min(start + BLOCK, high)
        pairs = [out[at:at + 2] for at in range(start, stop - 1, 2)]
        pairs.reverse()
        flat = b"".join(pairs)
        out[start:start + len(flat)] = flat
    return bytes(out)


def survivors(image):
    kept = 0
    for address in records(image, ROSTER, ROSTER_RECORDS, ROSTER_STRIDE, ROSTER_FIELDS):
        try:
            string(image, address)
        except TextError:
            continue
        kept += 1
    return kept


def measure(image):
    check_reader(image)
    shapes = font(image)
    for code, width, advance in SAMPLE:
        found = shapes["widths"].get(ord(code))
        if found != width or found + 1 != advance:
            raise TextError("the glyph for %r is %s wide, not %d with an advance of %d"
                            % (code, found, width, advance))
    names = roster(image)
    tasks = objectives(image)
    blob = text_container(image)
    distinct = {row["address"]: row for row in names}
    contained = [row for row in distinct.values() if inside(row, blob)]
    plain = [row for row in tasks if inside(row, blob)]
    return {"codes": shapes["codes"], "records": shapes["records"],
            "roster_pointers": len(names), "roster": len(distinct),
            "roster_bytes": sum(row["length"] + 1 for row in distinct.values()),
            "objectives": len(tasks),
            "objective_bytes": sum(row["length"] + 1 for row in tasks),
            "contained": len(contained), "plain": len(plain),
            "null_whole": survivors(permuted(image)),
            "null_region": survivors(permuted(image, blob["low"], blob["high"]))}


def check(image):
    result = measure(image)
    problems = ["%s is %d, not %d" % (key, result[key], expected)
                for key, expected in PINNED.items() if result[key] != expected]
    problems += ["the %s null resolves %d string(s)" % (key, result[key])
                 for key in ("null_whole", "null_region") if result[key]]
    for problem in problems:
        print("TEXT FAIL: %s" % problem)
    print("TEXT %s" % ("PASS" if not problems else "FAIL"))
    return 0 if not problems else 1


def read_rom(path=None):
    path = path or ROM
    if not os.path.exists(path):
        raise SystemExit("the text check needs the retail image at %s" % path)
    image = open(path, "rb").read()
    if hashlib.sha256(image).hexdigest() != ROM_SHA256:
        raise SystemExit("%s is not the canonical image" % path)
    return image


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv not in ([], ["--check"]):
        print("usage: python tools\\text\\text_storage.py [--check]")
        return 2
    image = read_rom()
    result = measure(image)
    print("font codes=%d records=%d" % (result["codes"], result["records"]))
    print("roster strings=%d bytes=%d objectives strings=%d bytes=%d"
          % (result["roster"], result["roster_bytes"], result["objectives"],
             result["objective_bytes"]))
    print("inside the stored container roster=%d objectives=%d"
          % (result["contained"], result["plain"]))
    print("null whole-image=%d payload-permuted=%d" % (result["null_whole"],
                                                       result["null_region"]))
    if not argv:
        return 0
    return check(image)


if __name__ == "__main__":
    raise SystemExit(main())
