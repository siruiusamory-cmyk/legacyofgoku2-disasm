from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "tools", "maprecords"))
sys.path.insert(0, os.path.join(ROOT, "tools", "research"))
sys.path.insert(0, os.path.join(ROOT, "tools", "code"))

import data_census
import emit_code
import maprecords

ROM = os.path.join(ROOT, "baserom.gba")
BUILD = os.path.join(ROOT, "build", "addr")
ROM_BASE = 0x08000000
ROM_SHA256 = data_census.ROM_SHA256
CENSUS_BYTES = 7892
SPECS = {"run": [("words", 0x00, 4, "refs")]}
PINNED = {"run": 822}
THUMB = 1


def u32(image, offset):
    return int.from_bytes(image[offset:offset + 4], "little")


def code_labels(rom):
    result = emit_code.fragments(rom)
    positions = {position for _begin, _end, _mode, _tag, lines in result["kept"]
                 for position, _operation, _operands in lines}
    names = {}
    for begin, _end, name in result["segments"]:
        stem = name[:-2]
        names.setdefault(begin, stem if not stem.startswith("code_") else "sub_%08X" % begin)
    for address in result["targets"] | result["entries"]:
        if address in positions:
            names.setdefault(address, "loc_%08X" % address)
    return {name: address for address, name in names.items()}


def measure(image):
    mask = data_census.region_mask(image)
    families = data_census.family_rows(image, data_census.literal_loads(image))
    marks = bytearray(len(image))
    for number, family in enumerate(families, start=1):
        data_census.claim(marks, mask, number, family["extents"])
    fill_number = len(families) + 1
    data_census.claim(marks, mask, fill_number, data_census.fill_runs(image, mask))
    address_number = len(families) + 2
    data_census.claim(marks, mask, address_number, data_census.address_runs(image, mask))
    names = code_label_cache(image)
    runs = []
    for begin, end in class_runs(marks, mask, address_number):
        words = words_of([(begin, end)])
        if words and all(u32(image, at) & ~THUMB in names for at in words):
            runs.append((words[0], 4 * len(words)))
    return runs, names


_CODE = {}


def labels_map(image):
    if "by_name" not in _CODE:
        by_name = code_labels(maprecords.read_rom(ROM, ROM_SHA256))
        _CODE["by_name"] = by_name
        _CODE["by_addr"] = {address: name for name, address in by_name.items()}
    return _CODE["by_name"]


def code_label_cache(image):
    labels_map(image)
    return _CODE["by_addr"]


def tables(directory=None):
    return maprecords.load_tables(PINNED, SPECS, directory or HERE)


def found_of(rows):
    return [(int(row["address"], 16) - ROM_BASE,
             4 * len([token for token in row["words"].split() if token]))
            for row in rows["run"]]


def encode_row(family, row, labels, specs=None):
    if family != "run":
        raise ValueError("%s is not a family of this table" % family)
    out = bytearray()
    for token in row["words"].split():
        name, _, odd = token.partition("+")
        if name not in labels:
            raise ValueError("%s is not a code label the emitter writes" % name)
        value = labels[name] + (THUMB if odd else 0)
        out += value.to_bytes(4, "little")
    return bytes(out)


def build_records(rows, gaps=None):
    holes = maprecords.container_extents() if gaps is None else gaps
    labels = labels_map(read_rom())
    found = found_of(rows)
    if len(found) != len(rows["run"]):
        raise ValueError("the table holds %d row(s) for %d run(s)"
                         % (len(rows["run"]), len(found)))
    out = []
    for row, (offset, width) in zip(rows["run"], found):
        data = encode_row("run", row, labels)
        if len(data) != width:
            raise ValueError("%s encodes %d B, not %d" % (row["label"], len(data), width))
        out.append((offset, data, maprecords.uncovered(offset, len(data), holes)))
    return sorted(out)


def tokens(image, rows=None):
    return [(begin, end, "build\\addr\\rec_%x_%x.bin" % (begin, end))
            for begin, end in maprecords.runs(build_records(rows or tables()))]


def write(image, rows=None):
    return maprecords.write_runs(build_records(rows or tables()), BUILD, "rec")


def check(image, rows=None):
    return maprecords.check_records(build_records(rows or tables()), image)


def class_runs(marks, mask, number):
    out = []
    for begin, end in data_census.region_extents(mask):
        index = begin
        while index < end:
            value = marks[index]
            run = index
            while run < end and marks[run] == value:
                run += 1
            if value == number:
                out.append((index, run))
            index = run
    return out


def words_of(runs):
    out = []
    for begin, end in runs:
        index = (begin + 3) & ~3
        while index + 4 <= end:
            out.append(index)
            index += 4
    return out


def extract(image):
    runs, _labels = measure(image)
    names = code_label_cache(image)
    rows = {"run": []}
    for index, (offset, width) in enumerate(runs):
        labels = []
        for at in range(offset, offset + width, 4):
            value = u32(image, at)
            labels.append(names[value & ~THUMB] + ("+1" if value & THUMB else ""))
        rows["run"].append({"label": "run_%04d" % index,
                            "address": "%08x" % (offset + ROM_BASE),
                            "words": " ".join(labels)})
    return rows


def write_tables(tables, directory=None):
    maprecords.write_tables(tables, SPECS, directory or HERE)


def read_rom():
    return maprecords.read_rom(ROM, ROM_SHA256)


def spans_of(rows):
    return [(int(row["address"], 16) - ROM_BASE,
             int(row["address"], 16) - ROM_BASE + 4 * len(row["words"].split()))
            for row in rows["run"]]


def null(image):
    rows = tables()
    other = maprecords.permuted(image, spans_of(rows))
    names = code_label_cache(image)
    resolving = 0
    for row in rows["run"]:
        for at in range(int(row["address"], 16) - ROM_BASE,
                        int(row["address"], 16) - ROM_BASE + 4 * len(row["words"].split()), 4):
            if u32(other, at) & ~THUMB in names:
                resolving += 1
    return {"run": resolving}


def differing(image):
    rows = tables()
    labels = code_labels(read_rom())
    other = maprecords.permuted(image, spans_of(rows))
    return {"run": sum(1 for row in rows["run"]
                       if other[int(row["address"], 16) - ROM_BASE:
                                int(row["address"], 16) - ROM_BASE + 4 * len(row["words"].split())]
                       != encode_row("run", row, labels))}


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv == ["--extract"]:
        rows = extract(read_rom())
        write_tables(rows)
        print("wrote run.csv rows=%d" % len(rows["run"]))
        return 0
    if argv == ["--null"]:
        image = read_rom()
        print("permuted " + " ".join("%s=%d" % (family, count)
                                     for family, count in null(image).items()))
        print("differing rows " + " ".join("%s=%d" % (family, count)
                                           for family, count in differing(image).items()))
        return 0 if not any(null(image).values()) and all(differing(image).values()) else 1
    result = check(read_rom())
    print("runs=%d mismatched=%d bytes=%d emitted=%d"
          % (result["records"], result["mismatched_records"], result["bytes"],
             result["emitted_bytes"]))
    if argv == ["--write"]:
        written, records = write(read_rom())
        print("wrote %d run(s) holding %d record(s)" % (written, records))
        return 0
    if result["mismatched_records"] or result["emitted_bytes"] != CENSUS_BYTES:
        print("ADDRESS_RUNS FAIL: %d record(s) differ, %d B emitted of %d"
              % (result["mismatched_records"], result["emitted_bytes"], CENSUS_BYTES))
        return 1
    print("ADDRESS_RUNS PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
