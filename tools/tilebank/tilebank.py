from __future__ import annotations

import hashlib
import os
import random
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
TILE = 32
BLOCK = 0x10000
MAP_TABLE = 0x084DF574
MAP_COUNT = 32
MAP_DECLARED = 0x4000
CHARACTER_BANKS = ((0x0820E77C, 0x1000), (0x0820F178, 0x1000), (0x0820FB14, 0x1000))
MAP_LOADER = (
    (0x0800510C, "0120", "movs r0,#1"),
    (0x0800510E, "8003", "lsls r0,r0,#0xe"),
    (0x08005110, "19f0bcff", "bl #0x801f08c"),
    (0x08005148, "c96c", "ldr r1,[r1,#0x4c]"),
    (0x0800514A, "0858", "ldr r0,[r1,r0]"),
    (0x0800514E, "1af021f9", "bl #0x801f394"),
    (0x08005156, "3149", "ldr r1,[pc,#0xc4]"),
    (0x08005168, "4e60", "str r6,[r1,#4]"),
    (0x0800516C, "0881", "strh r0,[r1,#8]"),
)
CHARACTER_LOADER = (
    (0x080072CC, "4068", "ldr r0,[r0,#4]"),
    (0x080072CE, "17f0ddfe", "bl #0x801f08c"),
    (0x080072DA, "18f05bf8", "bl #0x801f394"),
    (0x080072E0, "5e49", "ldr r1,[pc,#0x178]"),
    (0x080072E2, "4001", "lsls r0,r0,#5"),
    (0x080072E4, "4118", "adds r1,r0,r1"),
    (0x080072EC, "4368", "ldr r3,[r0,#4]"),
    (0x080072F0, "18f08ff8", "bl #0x801f412"),
)
DECODER = (
    (0x0801F39A, "1368", "ldr r3,[r2]"),
    (0x0801F39C, "111c", "adds r1,r2,#8"),
    (0x0801F3A4, "012b", "cmp r3,#1"),
    (0x0801F3AC, "04f07cf9", "bl #0x80236a8"),
)
PINNED = {"map_banks": 32, "map_declared": 0x4000, "map_stored": 166796,
          "map_span": 166844, "character_banks": 3, "character_declared": 0x1000}


class TileBankError(ValueError):
    pass


def u32(image, offset):
    return struct.unpack_from("<I", image, offset)[0]


def in_image(image, address):
    return ROM_BASE <= address < ROM_BASE + len(image)


def check_quotes(image, quotes):
    for address, hex_bytes, text in quotes:
        size = len(hex_bytes) // 2
        site = address - ROM_BASE
        read = image[site:site + size].hex()
        if read != hex_bytes:
            raise TileBankError("0x%08X holds %s, not the quoted %s (%s)"
                                % (address, read, hex_bytes, text))


def check_reader(image):
    check_quotes(image, MAP_LOADER)
    check_quotes(image, CHARACTER_LOADER)
    check_quotes(image, DECODER)


def bank(image, address, declared):
    if not in_image(image, address):
        raise TileBankError("0x%08X is outside the image" % address)
    if declared % TILE:
        raise TileBankError("%d bytes is not a whole number of %d-byte tiles"
                            % (declared, TILE))
    kind, size = container.read_header(image, address - ROM_BASE)
    if size != declared:
        raise TileBankError("0x%08X declares %d, not the %d its population expects"
                            % (address, size, declared))
    decoded = container.unpack(image, address - ROM_BASE, maximum_output=declared)
    if len(decoded.data) != declared:
        raise TileBankError("0x%08X decoded %d bytes against a declared %d"
                            % (address, len(decoded.data), declared))
    return {"address": address, "kind": kind, "declared": declared,
            "stored": decoded.packed_size, "tiles": declared // TILE}


def table_banks(image, table=MAP_TABLE, count=MAP_COUNT, declared=MAP_DECLARED):
    rows = []
    for index in range(count):
        address = u32(image, table - ROM_BASE + 4 * index)
        rows.append(bank(image, address, declared))
    return rows


def survivors(image, table=MAP_TABLE, count=MAP_COUNT, declared=MAP_DECLARED):
    kept = 0
    for index in range(count):
        try:
            bank(image, u32(image, table - ROM_BASE + 4 * index), declared)
        except (TileBankError, container.ContainerError):
            continue
        kept += 1
    return kept


def span(rows):
    return (min(row["address"] for row in rows) - ROM_BASE,
            max(row["address"] + row["stored"] for row in rows) - ROM_BASE)


def permuted(image, low=0, high=None, seed=20261021):
    high = len(image) if high is None else high
    roll = random.Random(seed)
    blocks = []
    for start in range(low, high, BLOCK):
        piece = list(image[start:min(start + BLOCK, high)])
        roll.shuffle(piece)
        blocks.append(bytes(piece))
    out = bytearray(image)
    out[low:high] = b"".join(blocks)
    return bytes(out)


def measure(image):
    check_reader(image)
    banks = table_banks(image)
    low, high = span(banks)
    characters = [bank(image, address, declared) for address, declared in CHARACTER_BANKS]
    whole = survivors(permuted(image))
    region = survivors(permuted(image, low, high))
    return {"map_banks": len(banks), "map_declared": banks[0]["declared"],
            "map_stored": sum(row["stored"] for row in banks),
            "map_span": high - low, "map_tiles": banks[0]["tiles"],
            "character_banks": len(characters), "character_declared": characters[0]["declared"],
            "character_tiles": characters[0]["tiles"], "null_whole": whole,
            "null_region": region}


def check(image):
    result = measure(image)
    problems = []
    for key, expected in PINNED.items():
        if result[key] != expected:
            problems.append("%s is %d, not %d" % (key, result[key], expected))
    for key in ("null_whole", "null_region"):
        if result[key]:
            problems.append("the %s null decodes %d bank(s)" % (key, result[key]))
    for problem in problems:
        print("TILEBANK FAIL: %s" % problem)
    print("TILEBANK %s" % ("PASS" if not problems else "FAIL"))
    return 0 if not problems else 1


def read_rom(path=None):
    path = path or ROM
    if not os.path.exists(path):
        raise SystemExit("the tile-bank check needs the retail image at %s" % path)
    image = open(path, "rb").read()
    if hashlib.sha256(image).hexdigest() != ROM_SHA256:
        raise SystemExit("%s is not the canonical image" % path)
    return image


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv not in ([], ["--check"]):
        print("usage: python tools\\tilebank\\tilebank.py [--check]")
        return 2
    image = read_rom()
    result = measure(image)
    print("map banks=%d declared=%d tiles=%d stored=%d span=%d"
          % (result["map_banks"], result["map_declared"], result["map_tiles"],
             result["map_stored"], result["map_span"]))
    print("character banks=%d declared=%d tiles=%d"
          % (result["character_banks"], result["character_declared"],
             result["character_tiles"]))
    print("null whole-image=%d region-permuted=%d" % (result["null_whole"],
                                                      result["null_region"]))
    if not argv:
        return 0
    return check(image)


if __name__ == "__main__":
    raise SystemExit(main())
