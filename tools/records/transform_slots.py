from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "tools", "maprecords"))

import maprecords

ROM = os.path.join(ROOT, "baserom.gba")
BUILD = os.path.join(ROOT, "build", "slots")
ROM_BASE = 0x08000000
ROM_SHA256 = "6e6c370c339ec9171cb1956adf837a0d342a197f78964882ef46c3086656ff75"
CENSUS_BYTES = 408
WIDTH = 12
PINNED = {"slot": 34}
SPECS = {
    "slot": [("source_00", 0x00, 4, "u32"), ("flags_04", 0x04, 1, "u8"),
             ("pad_05", 0x05, 1, "bytes"), ("clip_start_06", 0x06, 2, "u16"),
             ("clip_end_08", 0x08, 2, "u16"), ("step_0a", 0x0A, 2, "u16")],
}
ADDRESSES = (0x080E15F8, 0x080E161C, 0x080E164C, 0x080E1658, 0x080E176C, 0x080E1778,
             0x080E17F0, 0x080E17FC, 0x0814A8BC, 0x0814A8C8, 0x0814A8F8, 0x0814A910,
             0x0814A964, 0x0814A97C, 0x0814A9A0, 0x0814AA18, 0x0814AA24, 0x0814AA30,
             0x0814AA3C, 0x0814AA54, 0x0814AA60, 0x0814AAC0, 0x0814AB68, 0x0814ABB0,
             0x0814ABBC, 0x0814ABC8, 0x0814AC04, 0x0814AC40, 0x0814AC4C, 0x0814AC58,
             0x0814AC88, 0x0814ACA0, 0x0814AD00, 0x0814AD24)


def u16(image, offset):
    return int.from_bytes(image[offset:offset + 2], "little")


def u32(image, offset):
    return int.from_bytes(image[offset:offset + 4], "little")


def in_image(image, address):
    return ROM_BASE <= address < ROM_BASE + len(image)


def label(index):
    return "slot_%03d" % index


def record(image, offset):
    return {"source": u32(image, offset), "flags": image[offset + 4],
            "start": u16(image, offset + 6), "end": u16(image, offset + 8),
            "step": u16(image, offset + 0x0A)}


def structural(image, offset):
    row = record(image, offset)
    return (in_image(image, row["source"]) and 0 < row["step"] <= 0xFFFF
            and row["start"] <= row["end"])


def walk(image):
    places = []
    for address in ADDRESSES:
        if not in_image(image, address):
            raise ValueError("the slot descriptor %08x is outside the image" % address)
        if not structural(image, address - ROM_BASE):
            raise ValueError("the slot descriptor %08x is not a slot record" % address)
        places.append((address - ROM_BASE, WIDTH))
    if len({offset for offset, _width in places}) != PINNED["slot"]:
        raise ValueError("the record addresses repeat")
    return {"slot": places}


def tables(directory=None):
    return maprecords.load_tables(PINNED, SPECS, directory or HERE)


def build_records(rows, found, gaps=None):
    return maprecords.build_records(rows, maprecords.container_extents() if gaps is None else gaps,
                                    found, SPECS, PINNED)


def tokens(image, rows=None):
    return [(begin, end, "build\\slots\\rec_%x_%x.bin" % (begin, end))
            for begin, end in maprecords.runs(build_records(rows or tables(), walk(image)))]


def write(image, rows=None):
    return maprecords.write_runs(build_records(rows or tables(), walk(image)), BUILD, "rec")


def check(image, rows=None):
    return maprecords.check_records(build_records(rows or tables(), walk(image)), image)


def extract(image):
    places = walk(image)["slot"]
    rows = []
    for index, (offset, _width) in enumerate(places):
        found = record(image, offset)
        rows.append({"label": label(index), "address": "%08x" % (offset + ROM_BASE),
                     "source_00": "%08x" % found["source"],
                     "flags_04": "%02x" % found["flags"],
                     "pad_05": image[offset + 5:offset + 6].hex(),
                     "clip_start_06": "%04x" % found["start"],
                     "clip_end_08": "%04x" % found["end"],
                     "step_0a": "%04x" % found["step"]})
    return {"slot": rows}


def spans_of(found):
    return [(offset, offset + width) for offset, width in found["slot"]]


def null(image):
    other = maprecords.permuted(image, spans_of(walk(image)))
    left = sum(1 for offset, _width in walk(image)["slot"] if structural(other, offset))
    return {"slot": left}


def differing(image, rows=None):
    rows = rows or tables()
    labels = maprecords.labels_of(rows)
    other = maprecords.permuted(image, spans_of(walk(image)))
    found = walk(image)["slot"]
    if len(found) != len(rows["slot"]):
        raise ValueError("slot holds %d row(s) for %d record(s)" % (len(rows["slot"]), len(found)))
    return {"slot": sum(1 for (offset, width), row in zip(found, rows["slot"])
                        if other[offset:offset + width]
                        != maprecords.encode_row("slot", row, labels, SPECS))}


def uncited_fields(text):
    return maprecords.uncited_fields(text, SPECS)


def write_tables(tables, directory=None):
    maprecords.write_tables(tables, SPECS, directory or HERE)


def read_rom():
    return maprecords.read_rom(ROM, ROM_SHA256)


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv == ["--null"]:
        image = read_rom()
        result = null(image)
        print("permuted slot=%d" % result["slot"])
        differ = differing(image)
        print("differing records slot=%d" % differ["slot"])
        return 0 if not result["slot"] and differ["slot"] == PINNED["slot"] else 1
    return maprecords.generator_main(sys.modules[__name__], "transform_slots", argv)


if __name__ == "__main__":
    raise SystemExit(main())
