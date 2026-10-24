from __future__ import annotations

import argparse
import csv
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "tools", "split"))

import code_split
import runtime_watch_targets

TARGETS = os.path.join(ROOT, "tools", "research", "RUNTIME_WATCH_TARGETS.csv")
RUNS = os.path.join(ROOT, "tools", "research", "RUNTIME_WATCH_RUNS.csv")
HITS = os.path.join(ROOT, "tools", "research", "RUNTIME_WATCH_HITS.csv")
LABELS = os.path.join(ROOT, "tools", "code", "RUNTIME_LABELS.csv")
ROM = os.path.join(ROOT, "baserom.gba")
CSV_OUT = os.path.join(ROOT, "tools", "research", "RUNTIME_WATCH_RESULTS.csv")
DOC_OUT = os.path.join(ROOT, "tools", "research", "RUNTIME_WATCH_RESULTS.md")
EXPORT = os.path.join(ROOT, "tools", "recomp", "RECOMP_INPUTS.toml")
FIELDS = ("kind", "start", "end", "elapsed")
LABEL_FIELDS = ("region", "address", "mode")
RUN_FIELDS = ("run", "seconds", "bound", "armed", "targets", "ranges", "liveness", "stops",
              "executed", "liveness_pc")
KINDS = ("candidate-code", "bx-unresolved", "irq-slot")


def read_targets(path=TARGETS):
    with open(path, newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    for row in rows:
        row["start"] = int(row["start"], 16)
        row["end"] = int(row["end"], 16)
        row["bytes"] = row["end"] - row["start"]
    return rows


def executed(path):
    found, lines = set(), 0
    with open(path, encoding="ascii") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                address = int(line.split(",")[0], 16)
            except ValueError:
                continue
            lines += 1
            found.add(address)
    return sorted(found), lines


def fold(targets, addresses):
    rows = []
    for target in targets:
        hits = [address for address in addresses if target["start"] <= address < target["end"]]
        rows.append({"kind": target["kind"], "start": target["start"], "end": target["end"],
                     "bytes": target["bytes"], "status": "hit" if hits else "silent",
                     "hits": len(hits), "first": "0x%08x" % hits[0] if hits else ""})
    return rows


def merge_spans(spans):
    out = []
    for start, end in sorted(spans):
        if out and start <= out[-1][1]:
            out[-1][1] = max(out[-1][1], end)
        else:
            out.append([start, end])
    return out


def proposed(rows):
    return merge_spans((row["start"], row["end"]) for row in rows if row["status"] == "hit")


def read_labels(path=LABELS):
    with open(path, newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    for row in rows:
        row["address"] = int(row["address"], 16)
    return rows


def image(path=ROM):
    if not os.path.exists(path):
        raise SystemExit("no image at %s, so the recorded entries cannot be checked"
                         % os.path.relpath(path, ROOT))
    return open(path, "rb").read()


def label_spans(rows, rom, export=EXPORT):
    copy = runtime_watch_targets.export_blocks(export, "code_copy")[0]
    runtime_start = int(copy["runtime_start"], 16)
    source_start = int(copy["source_start"], 16)
    size = int(copy["size"], 16)
    spans = []
    for row in rows:
        address = row["address"]
        if row["region"] == "iwram":
            if not runtime_start <= address < runtime_start + size:
                raise SystemExit("0x%08x is outside the code copy the export names" % address)
            address = source_start + (address - runtime_start)
        if not 0x08000000 <= address < 0x08000000 + len(rom):
            raise SystemExit("0x%08x is outside the image" % address)
        if row["mode"] == "thumb":
            width = code_split.thumb_length(rom, address)
            if width is None:
                raise SystemExit("0x%08x does not start a Thumb instruction the walk decodes"
                                 % address)
        else:
            if address % 4 or not code_split.has_word(rom, address):
                raise SystemExit("0x%08x is not a word boundary in the image" % address)
            width = 4
        spans.append((address, address + width))
    return spans


def totals(rows):
    out = {}
    for kind in KINDS:
        mine = [row for row in rows if row["kind"] == kind]
        out[kind] = (len(mine), sum(1 for row in mine if row["status"] == "hit"),
                     sum(row["bytes"] for row in mine if row["status"] == "hit"))
    return out


def read_hits(path=HITS):
    with open(path, newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    for row in rows:
        row["start"] = int(row["start"], 16)
        row["end"] = int(row["end"], 16)
        row["bytes"] = row["end"] - row["start"]
    return rows


def read_runs(path=RUNS):
    with open(path, newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def named_rows(rom):
    return [(code_split.ROM_BASE + start, code_split.ROM_BASE + stop)
            for start, stop, _name, _mode in code_split.measure(rom)["function_rows"]]


def export_code(rom, path=EXPORT):
    return [(int(block["addr"], 16), int(block["addr"], 16) + int(block["size"]))
            for block in runtime_watch_targets.export_blocks(path, "code")
            if code_split.in_image(rom, int(block["addr"], 16))]


def overlap(spans, extents):
    total = 0
    for start, end in spans:
        for low, high in extents:
            low, high = max(start, low), min(end, high)
            if low < high:
                total += high - low
    return total


def hits_rows(targets, log):
    by_start = {target["start"]: target for target in targets}
    rows, seen = [], set()
    with open(log, encoding="ascii") as handle:
        for line in handle:
            cells = line.strip().split(",")
            if len(cells) < 3 or cells[2] != "target":
                continue
            address = int(cells[0], 16)
            if address in seen or address not in by_start:
                continue
            seen.add(address)
            target = by_start[address]
            rows.append({"kind": target["kind"], "start": address, "end": target["end"],
                         "elapsed": cells[1]})
    rows.sort(key=lambda row: (KINDS.index(row["kind"]), row["start"]))
    return rows


def import_run(directory, runs=RUNS, hits=HITS, targets=None):
    record = json.load(open(os.path.join(directory, "run.json"), encoding="ascii"))
    log = os.path.join(directory, "watch-log.csv")
    rows = hits_rows(read_targets() if targets is None else targets, log)
    with open(hits, "w", encoding="ascii", newline="\n") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(FIELDS)
        for row in rows:
            writer.writerow([row["kind"], "0x%08x" % row["start"], "0x%08x" % row["end"],
                             row["elapsed"]])
    exists = os.path.exists(runs)
    index = len(read_runs(runs)) + 1 if exists else 1
    with open(runs, "a" if exists else "w", encoding="ascii", newline="\n") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        if not exists:
            writer.writerow(RUN_FIELDS)
        writer.writerow([index, record["seconds"], record["bound"], record["armed"],
                         record["targets"], record["ranges"], record["liveness"],
                         record["stops"], record["executed"], record["liveness_pc"]])
    print("imported %d executed target(s) and one run row" % len(rows))
    return rows


def summary(targets, hits, runs, labels=(), named=(), carried=()):
    by_kind = {}
    for kind in KINDS:
        mine = [row for row in hits if row["kind"] == kind]
        by_kind[kind] = (sum(1 for row in targets if row["kind"] == kind), len(mine),
                         sum(row["bytes"] for row in mine))
    recorded = merge_spans(labels)
    merged = merge_spans([(row["start"], row["end"]) for row in hits]
                         + [(start, end) for start, end in recorded])
    named_bytes = overlap(merged, named)
    carried_bytes = overlap(merged, carried)
    return {"by_kind": by_kind, "extents": merged,
            "bytes": sum(end - start for start, end in merged),
            "named": named_bytes, "carried": carried_bytes,
            "new": sum(end - start for start, end in merged) - carried_bytes,
            "code_named": sum(end - start for start, end in named),
            "code_carried": sum(end - start for start, end in carried),
            "run": runs[-1] if runs else None,
            "label_extents": len(recorded),
            "label_bytes": sum(end - start for start, end in recorded),
            "label_named": overlap(recorded, named)}


def table_lines(found):
    lines = ["| kind | targets | hit | bytes |", "|---|---|---|---|"]
    for kind in KINDS:
        count, hit, size = found["by_kind"][kind]
        lines.append("| `%s` | %d | %d | %d |" % (kind, count, hit, size))
    lines.append("| **total** | **%d** | **%d** | **%d** |"
                 % (sum(value[0] for value in found["by_kind"].values()),
                    sum(value[1] for value in found["by_kind"].values()),
                    sum(value[2] for value in found["by_kind"].values())))
    return lines


def doc_text(targets, hits, runs, labels=(), named=(), carried=()):
    found = summary(targets, hits, runs, labels, named, carried)
    run = found["run"]
    lines = ["# Runtime watch results", "",
             "Generated by `tools/research/runtime_watch_results.py --write`; `--check`"
             " byte-compares this page and its CSV with the tracked run, hit, target and"
             " recorded-entry tables.",
             "", "## Run", "",
             "| bound (s) | lasted (s) | targets | armed | ranges | liveness hits | stops |"
             " executed |", "|---|---|---|---|---|---|---|---|"]
    if run:
        lines.append("| %s | %s | %s | %s | %s | %s | %s | %s |"
                     % (run["bound"], run["seconds"], run["targets"], run["armed"],
                        run["ranges"], run["liveness"], run["stops"], run["executed"]))
        lines += ["", "Liveness pc `%s`: one breakpoint on the handler the startup block"
                  " installs at the interrupt vector, so every hit is a frame that handler ran."
                  % run["liveness_pc"]]
    lines += ["", "## Executed targets", "", *table_lines(found), ""]
    if labels:
        lines += ["## Recorded label entries", "",
                  "%d recorded entries, each an instruction start the walk decodes: %d extent(s)"
                  " / %d B, %d B inside the named code."
                  % (len(labels), found["label_extents"], found["label_bytes"],
                     found["label_named"]), ""]
    sources = "the executed target ranges and the recorded entries" if labels \
        else "the executed target ranges"
    lines += ["## Proposed runtime class", "",
              "%d extent(s) / %d B: %s, merged. %d B lie inside the"
              " %d B of code the split already names, and %d B inside the %d B of image"
              " code the export carries, so %d B would be new."
              % (len(found["extents"]), found["bytes"], sources, found["named"],
                 found["code_named"], found["carried"], found["code_carried"],
                 found["new"]), "",
              "The class is a proposal: the split is not edited and no byte moves until a"
              " separate promotion.", "", "## Chance channels scored", ""]
    for kind in ("candidate-code", "bx-unresolved", "irq-slot"):
        count, hit, size = found["by_kind"][kind]
        lines.append("* `%s`: %d of %d target(s) executed, %d B." % (kind, hit, count, size))
    lines += ["", "The candidate rows are the prologue sweep the split measured but did not"
              " count as code, because its permuted null was above its accept rate; a hit is"
              " one of those rows executed, not a bound on how many run.", "",
              "A slot row is a data word the interrupt dispatcher reads, so an execute watch"
              " cannot score it; a slot's 0 is not a read negative.", ""]
    return "\n".join(lines)


def csv_text(targets, hits):
    lines = [",".join(("kind", "start", "end", "bytes", "status", "elapsed"))]
    seen = {row["start"]: row for row in hits}
    starts = {target["start"] for target in targets}
    rows = [(target["kind"], target["start"], target["end"], target["bytes"],
             "executed" if target["start"] in seen else "silent",
             seen[target["start"]]["elapsed"] if target["start"] in seen else "")
            for target in targets]
    rows += [(row["kind"], row["start"], row["end"], row["bytes"], "executed", row["elapsed"])
             for row in hits if row["start"] not in starts]
    rows.sort(key=lambda row: (KINDS.index(row[0]), row[1]))
    for kind, start, end, size, status, elapsed in rows:
        lines.append(",".join([kind, "0x%08x" % start, "0x%08x" % end, str(size),
                               status, elapsed]))
    return "\n".join(lines) + "\n"


def write():
    rom = image()
    targets, hits, runs = read_targets(), read_hits(), read_runs()
    labels = label_spans(read_labels(), rom)
    with open(CSV_OUT, "w", encoding="ascii", newline="\n") as handle:
        handle.write(csv_text(targets, hits))
    with open(DOC_OUT, "w", encoding="ascii", newline="\n") as handle:
        handle.write(doc_text(targets, hits, runs, labels, named_rows(rom), export_code(rom)))
    print("wrote %s and %s (%d executed target(s), %d recorded entr(y/ies))"
          % (os.path.relpath(CSV_OUT, ROOT), os.path.relpath(DOC_OUT, ROOT), len(hits),
             len(labels)))


def check():
    rom = image()
    targets, hits, runs = read_targets(), read_hits(), read_runs()
    labels = label_spans(read_labels(), rom)
    for path, text in ((CSV_OUT, csv_text(targets, hits)),
                       (DOC_OUT, doc_text(targets, hits, runs, labels, named_rows(rom),
                                          export_code(rom)))):
        if not os.path.exists(path):
            raise SystemExit("%s is absent, so there is nothing to check"
                             % os.path.relpath(path, ROOT))
        with open(path, encoding="ascii") as handle:
            if handle.read() != text:
                raise SystemExit("%s does not match the tracked tables"
                                 % os.path.relpath(path, ROOT))
    print("CHECK: the results page and its CSV match the run, hit, target and recorded-entry"
          " tables")


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--import", dest="directory")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--runs", default=RUNS)
    parser.add_argument("--hits", default=HITS)
    args = parser.parse_args(argv)
    if args.directory:
        import_run(args.directory, args.runs, args.hits)
        return 0
    if args.check:
        check()
        return 0
    if args.write:
        write()
        return 0
    rom = image()
    found = summary(read_targets(), read_hits(), read_runs(), label_spans(read_labels(), rom),
                    named_rows(rom), export_code(rom))
    for line in table_lines(found):
        print(line)
    print("proposed: %d extent(s) / %d B, %d B new, %d recorded extent(s) / %d B"
          % (len(found["extents"]), found["bytes"], found["new"],
             found["label_extents"], found["label_bytes"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
