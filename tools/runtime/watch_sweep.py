from __future__ import annotations

import argparse
import csv
import ctypes
import hashlib
import json
import os
import socket
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "tools", "gate"))

import gate

TARGETS = os.path.join(ROOT, "docs", "research", "RUNTIME_WATCH_TARGETS.csv")
LIVENESS = 0x03000824


def digest(path):
    handle = hashlib.sha256()
    with open(path, "rb") as source:
        for block in iter(lambda: source.read(1 << 20), b""):
            handle.update(block)
    return handle.hexdigest()


def read_targets(path=TARGETS):
    with open(path, newline="", encoding="utf-8") as handle:
        return [(row["kind"], int(row["start"], 16), int(row["end"], 16))
                for row in csv.DictReader(handle)]


def ranges(spans):
    out = []
    for start, end in sorted(spans):
        if out and start <= out[-1][1]:
            out[-1][1] = max(out[-1][1], end)
        else:
            out.append([start, end])
    return out


def refuse(message):
    raise SystemExit("refused: %s" % message)


def guard(args):
    if not args.run:
        refuse("a run needs --run")
    if not args.rom:
        refuse("a run needs --rom, a copy that is not the tracked image")
    if not os.path.isfile(args.rom):
        refuse("%s is not a file" % args.rom)
    measured = digest(args.rom)
    if measured != gate.CANONICAL_SHA256:
        refuse("%s has sha256 %s, not the recorded image" % (args.rom, measured))
    if not args.exe:
        refuse("a run needs --exe, a logging runtime")
    if not os.path.isfile(args.exe):
        refuse("%s is not a file" % args.exe)
    if not args.out:
        refuse("a run needs --out, a directory outside the tracked tree")
    if args.seconds <= 0:
        refuse("--seconds must be a positive duration bound")


def quiet(pid):
    kernel = ctypes.windll.kernel32
    handle = kernel.OpenProcess(0x0100 | 0x0200, False, pid)
    if handle:
        kernel.SetPriorityClass(handle, 0x4000)
        kernel.SetProcessAffinityMask(handle, 0x3F)
        kernel.CloseHandle(handle)


def checksum(text):
    return sum(text.encode("ascii")) & 0xFF


class Client:
    def __init__(self, sock):
        self.sock = sock

    def send(self, text):
        data = text.encode("ascii")
        self.sock.sendall(b"$" + data + b"#" + ("%02x" % checksum(text)).encode("ascii"))

    def read_byte(self, deadline):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError
        self.sock.settimeout(remaining)
        chunk = self.sock.recv(1)
        if not chunk:
            raise ConnectionError("closed")
        return chunk

    def reply(self, timeout):
        deadline = time.monotonic() + timeout
        while True:
            head = self.read_byte(deadline)
            if head == b"+":
                continue
            if head == b"-":
                return "-"
            if head != b"$":
                continue
            data = b""
            while True:
                chunk = self.read_byte(deadline)
                if chunk == b"#":
                    self.read_byte(deadline)
                    self.read_byte(deadline)
                    self.sock.sendall(b"+")
                    return data.decode("ascii", "replace")
                data += chunk

    def command(self, text, timeout):
        self.send(text)
        return self.reply(timeout)


def connect(exe, rom, port, seconds):
    process = subprocess.Popen([exe, "--gdb", rom])
    quiet(process.pid)
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            sock = socket.create_connection(("127.0.0.1", port), timeout=1)
            return process, Client(sock)
        except OSError:
            if process.poll() is not None:
                raise SystemExit("refused: the runtime exited before its debug port opened")
            time.sleep(0.5)
    process.kill()
    raise SystemExit("refused: the runtime did not open port %d inside the bound" % port)


def pc_of(text):
    raw = bytes.fromhex(text)
    return int.from_bytes(raw[60:64], "little"), int.from_bytes(raw[64:68], "little")


def plan(out, targets):
    os.makedirs(out, exist_ok=True)
    path = os.path.join(out, "ranges.txt")
    merged = ranges((start, end) for _kind, start, end in targets)
    with open(path, "w", encoding="ascii", newline="\n") as handle:
        for start, end in merged:
            handle.write("0x%08x 0x%08x\n" % (start, end))
    return path, merged


def run(args, targets, merged):
    log = os.path.join(args.out, "watch-log.csv")
    process, client = connect(args.exe, args.rom, args.port, 60)
    armed, refused = 0, []
    try:
        client.command("?", 10)
        for _kind, start, _end in targets:
            answer = client.command("Z0,%x,2" % start, 10)
            if answer == "OK":
                armed += 1
            else:
                refused.append(start)
        if client.command("Z0,%x,2" % LIVENESS, 10) != "OK":
            refuse("the liveness breakpoint did not arm")
        if refused:
            refuse("%d target(s) did not arm, first 0x%08x" % (len(refused), refused[0]))
        starts = {start for _kind, start, _end in targets}
        started = time.monotonic()
        liveness, stops, hit = 0, 0, []
        with open(log, "w", encoding="ascii", newline="\n") as handle:
            writer = csv.writer(handle, lineterminator="\n")
            writer.writerow(["pc", "elapsed", "kind"])
            while time.monotonic() - started < args.seconds:
                try:
                    answer = client.command("c", max(0.5, args.seconds - (time.monotonic()
                                                                           - started)))
                except TimeoutError:
                    break
                if not answer or not answer.startswith("S0"):
                    break
                try:
                    regs = client.command("g", 10)
                except (TimeoutError, ConnectionError):
                    break
                if not regs or regs == "-":
                    break
                pc, _cpsr = pc_of(regs)
                elapsed = time.monotonic() - started
                stops += 1
                if pc == LIVENESS:
                    liveness += 1
                    writer.writerow(["0x%08x" % pc, "%.3f" % elapsed, "liveness"])
                    continue
                if pc in starts:
                    hit.append(pc)
                    writer.writerow(["0x%08x" % pc, "%.3f" % elapsed, "target"])
                    client.command("z0,%x,2" % pc, 10)
                else:
                    writer.writerow(["0x%08x" % pc, "%.3f" % elapsed, "other"])
            handle.flush()
            elapsed = time.monotonic() - started
    finally:
        try:
            client.sock.close()
        except OSError:
            pass
        if process.poll() is None:
            process.kill()
        process.wait()
    record = {"rom_sha256": digest(args.rom), "exe_sha256": digest(args.exe),
              "armed": armed, "targets": len(targets), "ranges": len(merged),
              "liveness": liveness, "stops": stops, "executed": len(hit),
              "seconds": round(elapsed, 1), "bound": args.seconds,
              "liveness_pc": "0x%08x" % LIVENESS, "port": args.port}
    with open(os.path.join(args.out, "run.json"), "w", encoding="ascii", newline="\n") as handle:
        handle.write(json.dumps(record, indent=2, sort_keys=True) + "\n")
    for key in ("armed", "targets", "ranges", "liveness", "stops", "executed", "seconds"):
        print("%s: %s" % (key, record[key]))
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--rom")
    parser.add_argument("--exe")
    parser.add_argument("--out")
    parser.add_argument("--seconds", type=int, default=900)
    parser.add_argument("--port", type=int, default=2345)
    parser.add_argument("--targets", default=TARGETS)
    args = parser.parse_args(argv)
    guard(args)
    targets = read_targets(args.targets)
    path, merged = plan(args.out, targets)
    print("plan: %d target(s), %d merged range(s) -> %s" % (len(targets), len(merged), path))
    return run(args, targets, merged)


if __name__ == "__main__":
    sys.exit(main())
