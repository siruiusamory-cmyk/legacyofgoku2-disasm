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
ROM_SHA256 = "6e6c370c339ec9171cb1956adf837a0d342a197f78964882ef46c3086656ff75"
ROM_BASE = 0x08000000
TABLE = 0x3B4E74
TABLE_ENTRIES = 154
TABLE_NULL = 3
DEFINITION = 30
COUNT_FIELD = 0x04
SLOT_FIELD = 0x4C
PIECE = 12
PIECE_POINTER = 8
LITERAL = 0x959C
LITERAL_VALUE = 0x083B4E90
QUOTE = (
    (0x08009364, "8d49", "ldr r1,[pc,#0x234]"),
    (0x08009366, "8000", "lsls r0,r0,#2"),
    (0x08009368, "4018", "adds r0,r0,r1"),
    (0x0800936A, "4038", "subs r0,#0x40"),
    (0x0800936C, "406a", "ldr r0,[r0,#0x24]"),
)
BF_TABLE = 0x6B6BDC
BF_ENTRIES = 297
BF_SLOT_FIELD = 0x54


def u32(image, offset):
    return struct.unpack_from("<I", image, offset)[0]


def check_reader(image):
    for address, halfword, _text in QUOTE:
        site = address - ROM_BASE
        if image[site:site + 2].hex() != halfword:
            raise ValueError("0x%08X holds %s, not the quoted %s"
                             % (address, image[site:site + 2].hex(), halfword))
    if u32(image, LITERAL) != LITERAL_VALUE:
        raise ValueError("the resolver literal at file 0x%X is 0x%08X, not 0x%08X"
                         % (LITERAL, u32(image, LITERAL), LITERAL_VALUE))


def table(image):
    for index in range(TABLE_NULL):
        if u32(image, TABLE + 4 * index) != 0:
            raise ValueError("the table's null slot %d is 0x%08X"
                             % (index, u32(image, TABLE + 4 * index)))
    entries = []
    for index in range(TABLE_ENTRIES):
        address = u32(image, TABLE + 4 * (TABLE_NULL + index))
        if not ROM_BASE <= address < ROM_BASE + len(image):
            raise ValueError("entry %d holds 0x%08X, not an image address" % (index, address))
        entries.append(address)
    return entries


def pieces(image, address):
    site = address - ROM_BASE
    x, y, w, h = struct.unpack_from("<bbBB", image, site)
    attribute = u32(image, site + 4)
    graphics = u32(image, site + PIECE_POINTER)
    if not ROM_BASE <= graphics < ROM_BASE + len(image):
        raise ValueError("the piece at 0x%08X holds 0x%08X" % (address, graphics))
    kind, declared = container.read_header(image, graphics - ROM_BASE)
    if kind not in (container.STORED,) + container.PACKED_KINDS:
        raise ValueError("the piece's graphics word 0x%08X is not a container header" % graphics)
    return {"address": address, "box": (x, y, w, h), "attribute": attribute,
            "container": graphics, "kind": kind, "declared": declared}


def measure(image):
    check_reader(image)
    entries = table(image)
    definition = u32(image, TABLE + 4 * DEFINITION)
    if not ROM_BASE <= definition < ROM_BASE + len(image):
        raise ValueError("id %d holds 0x%08X" % (DEFINITION, definition))
    site = definition - ROM_BASE
    slots = u32(image, site + COUNT_FIELD)
    if not 0 < slots <= 64:
        raise ValueError("id %d declares %d slots" % (DEFINITION, slots))
    found = []
    for index in range(slots):
        pointer = u32(image, site + SLOT_FIELD + 4 * index)
        if not ROM_BASE <= pointer < ROM_BASE + len(image):
            raise ValueError("slot %d holds 0x%08X" % (index, pointer))
        found.append(pieces(image, pointer))
    containers = sorted({hit["container"] for hit in found})
    declared = sorted({hit["declared"] for hit in found})
    first = found[0]
    decoded = container.unpack(image, first["container"] - ROM_BASE, maximum_output=0x40000)
    return {"entries": len(entries), "null_slots": TABLE_NULL, "definition_id": DEFINITION,
            "definition": definition, "slots": slots, "containers": len(containers),
            "container_addresses": containers, "declared": declared, "kind": first["kind"],
            "piece_box": first["box"], "piece_attribute": first["attribute"],
            "piece_container": first["container"], "payload": len(decoded.data)}


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv:
        print("usage: python tools\\research\\asset_directory.py")
        return 2
    if not os.path.exists(ROM):
        print("the asset directory needs the retail image at %s" % ROM)
        return 1
    image = open(ROM, "rb").read()
    if hashlib.sha256(image).hexdigest() != ROM_SHA256:
        print("the image at %s is not the canonical image" % ROM)
        return 1
    result = measure(image)
    print("directory entries=%d null=%d id=%d definition=0x%08X slots=%d containers=%d "
          "declared=%s piece=%s container=0x%08X payload=%d"
          % (result["entries"], result["null_slots"], result["definition_id"],
             result["definition"], result["slots"], result["containers"],
             result["declared"], result["piece_box"], result["piece_container"],
             result["payload"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
