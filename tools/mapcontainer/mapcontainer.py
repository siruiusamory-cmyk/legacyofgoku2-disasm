from __future__ import annotations

import hashlib
import os
import random
import struct
import sys

ROM_BASE = 0x08000000
ROM_SIZE = 8388608
ROM_SHA256 = "6e6c370c339ec9171cb1956adf837a0d342a197f78964882ef46c3086656ff75"
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
ROM = os.path.join(ROOT, "baserom.gba")

ENTRY_TABLE = 0x409368
ENTRY_STRIDE = 0x38
ENTRY_ROOT = 0x2C
ENTRY_COUNT = 327
ROOT_EXTENT = 0x50
ROOT_TILE_BANKS = 0x4C
TILE_BANK_TABLE = 0x084DF574
TILE_BANK_COUNT = 32
TILE_BANK_DECLARED = 0x4000
SLOT_BASE = 0x14
SLOT_COUNT = 4
FACTORY = 0x080056A1
ROW_FIELD = 0x14
COLUMN_FIELD = 0x15
CHUNK_FIELD = 0x18
ROOT_TABLE_COUNT = 0x24
ROOT_TABLE_BASE = 0x28
ROOT_TABLE_STRIDE = 24
ROOT_POINTER_COUNT = 0x40
ROOT_POINTER_BASE = 0x44
ROOT_POINTER_STRIDE = 4
BLOCK = 0x10000
KIND_HEADER = 1
PINNED = {"entries": 327, "roots": 336, "layers": 1344, "factories": 1294, "others": 50,
          "record_bytes": 99184, "chunks": 5249, "declared_payload": 10749952,
          "root_table_rows": 710, "root_table_bytes": 17040}


class MapContainerError(ValueError):
    pass


def u32(image, offset):
    return struct.unpack_from("<I", image, offset)[0]


def in_image(image, address):
    return ROM_BASE <= address < ROM_BASE + len(image)


def container_header(image, address):
    if not in_image(image, address):
        return None
    site = address - ROM_BASE
    if site + 8 > len(image):
        return None
    kind, declared = struct.unpack_from("<II", image, site)
    if kind not in (0, 1, 2) or not 1 <= declared <= 0x100000:
        return None
    return kind, declared


def tile_banks(image):
    table = TILE_BANK_TABLE - ROM_BASE
    out = []
    for index in range(TILE_BANK_COUNT):
        address = u32(image, table + 4 * index)
        header = container_header(image, address)
        if header != (KIND_HEADER, TILE_BANK_DECLARED):
            raise MapContainerError("tile bank %d at %#010x is %s, not a kind-%d container declaring "
                                    "%d bytes" % (index, address, header, KIND_HEADER,
                                                  TILE_BANK_DECLARED))
        out.append(address - ROM_BASE)
    return out


def entries(image):
    out = []
    offset = ENTRY_TABLE
    while offset + ENTRY_STRIDE <= len(image):
        if not in_image(image, u32(image, offset + ENTRY_ROOT)):
            break
        out.append(offset)
        offset += ENTRY_STRIDE
    return out


def root_arrays(image):
    arrays = []
    for offset in entries(image):
        base = u32(image, offset + ENTRY_ROOT) - ROM_BASE
        later = [u32(image, other + ENTRY_ROOT) - ROM_BASE for other in entries(image)
                 if u32(image, other + ENTRY_ROOT) - ROM_BASE > base]
        arrays.append((base, min(later) if later else base + ROOT_EXTENT))
    return arrays


def root_slot(image, address):
    if not in_image(image, address):
        return False
    site = address - ROM_BASE
    return site + ROOT_EXTENT <= len(image) and u32(image, site + ROOT_TILE_BANKS) == TILE_BANK_TABLE


def root_slots(image):
    out = []
    for base, limit in root_arrays(image):
        slots = []
        while base + 4 <= limit and root_slot(image, u32(image, base)):
            slots.append(u32(image, base) - ROM_BASE)
            base += 4
        out.append(slots)
    return out


def map_roots(image):
    arrays = root_slots(image)
    for index, slots in enumerate(arrays):
        if not slots:
            raise MapContainerError("map entry %d's +0x%02X array holds no root"
                                    % (index, ENTRY_ROOT))
    return sorted({root for slots in arrays for root in slots})


def layer_records(image):
    out = {}
    for root in map_roots(image):
        for slot in range(SLOT_COUNT):
            address = u32(image, root + SLOT_BASE + 4 * slot)
            if not in_image(image, address):
                continue
            out[address - ROM_BASE] = u32(image, address - ROM_BASE)
    return out


def dominant_records(image):
    return {site: factory for site, factory in layer_records(image).items() if factory == FACTORY}


def chunk_count(image, site):
    return image[site + ROW_FIELD] * image[site + COLUMN_FIELD]


def record_extents(image):
    roots = map_roots(image)
    dominant = dominant_records(image)
    root_rows = []
    for root in roots:
        count, base = u32(image, root + ROOT_TABLE_COUNT), u32(image, root + ROOT_TABLE_BASE)
        if not count or not in_image(image, base):
            continue
        for index in range(count):
            root_rows.append((base - ROM_BASE + ROOT_TABLE_STRIDE * index,
                              ROOT_TABLE_STRIDE))
    return {"root_record": [(root, ROOT_EXTENT) for root in roots],
            "dominant_layer_record": [(site, CHUNK_FIELD + 4 * chunk_count(image, site))
                                      for site in dominant],
            "root_table_record": root_rows}


def chunk_pointers(image):
    out = set()
    for site in dominant_records(image):
        for index in range(chunk_count(image, site)):
            address = u32(image, site + CHUNK_FIELD + 4 * index)
            if in_image(image, address):
                out.add(address - ROM_BASE)
    return sorted(out)


def census(image):
    extents = record_extents(image)
    chunks = chunk_pointers(image)
    roots = map_roots(image)
    layers = layer_records(image)
    factories = dominant_records(image)
    record_bytes = sum(size for rows in extents.values() for _start, size in rows)
    declared = 0
    headers = 0
    for site in chunks:
        header = container_header(image, ROM_BASE + site)
        if header is not None:
            headers += 1
            declared += header[1]
    return {"entries": len(entries(image)), "roots": len(roots), "layers": len(layers),
            "factories": len(factories), "others": len(layers) - len(factories),
            "record_bytes": record_bytes, "chunks": len(chunks),
            "chunk_headers": headers, "declared_payload": declared,
            "root_table_rows": len(extents["root_table_record"]),
            "root_table_bytes": sum(size for _start, size in extents["root_table_record"])}


def permuted(image, span=None, seed=20261021):
    out = bytearray(image)
    low, high = (0, len(image)) if span is None else span
    generator = random.Random(seed)
    for start in range(low, high, BLOCK):
        block = bytearray(image[start:min(start + BLOCK, high)])
        generator.shuffle(block)
        out[start:start + len(block)] = block
    return bytes(out)


def null_census(image):
    try:
        return census(image)
    except MapContainerError:
        return {"entries": len(entries(image)), "roots": 0, "layers": 0, "factories": 0,
                "record_bytes": 0, "chunks": 0, "chunk_headers": 0, "declared_payload": 0,
                "root_table_rows": 0, "root_table_bytes": 0}


def measure(image):
    banks = tile_banks(image)
    result = census(image)
    result["tile_banks"] = len(banks)
    whole = null_census(permuted(image))
    region = null_census(permuted(image, (ENTRY_TABLE + ENTRY_STRIDE * ENTRY_COUNT, len(image))))
    return result, whole, region


def print_census(label, values):
    print("%s entries=%d roots=%d layers=%d factories=%d record_bytes=%d chunks=%d "
          "chunk_headers=%d declared_payload=%d root_table_rows=%d root_table_bytes=%d"
          % (label, values["entries"], values["roots"], values["layers"], values["factories"],
             values["record_bytes"], values["chunks"], values["chunk_headers"],
             values["declared_payload"], values["root_table_rows"],
             values["root_table_bytes"]))


def read_rom(path=None):
    path = path or ROM
    if not os.path.exists(path):
        raise SystemExit("the map container census needs the retail image at %s" % path)
    image = open(path, "rb").read()
    if hashlib.sha256(image).hexdigest() != ROM_SHA256:
        raise SystemExit("%s is not the canonical image" % path)
    return image


def check(image):
    result, whole, region = measure(image)
    problems = []
    for key, expected in PINNED.items():
        if result[key] != expected:
            problems.append("%s is %d, not %d" % (key, result[key], expected))
    if result["chunks"] != result["chunk_headers"]:
        problems.append("%d of %d chunk pointers are not container headers"
                        % (result["chunks"] - result["chunk_headers"], result["chunks"]))
    for label, values in (("whole-image", whole), ("region", region)):
        for key in ("roots", "layers", "factories"):
            if values[key]:
                problems.append("the %s null finds %d %s" % (label, values[key], key))
    for problem in problems:
        print("MAP FAIL: %s" % problem)
    print("MAP %s" % ("PASS" if not problems else "FAIL"))
    return 0 if not problems else 1


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv not in ([], ["--check"]):
        print("usage: python tools\\mapcontainer\\mapcontainer.py [--check]")
        return 2
    image = read_rom()
    result, whole, region = measure(image)
    print_census("image", result)
    print("tile_banks=%d tile_bank_declared=%d" % (result["tile_banks"], TILE_BANK_DECLARED))
    print_census("null-whole", whole)
    print_census("null-region", region)
    if not argv:
        return 0
    return check(image)


if __name__ == "__main__":
    raise SystemExit(main())
