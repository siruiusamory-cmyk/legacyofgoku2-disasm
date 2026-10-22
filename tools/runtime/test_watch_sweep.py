from __future__ import annotations

import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import watch_sweep


def no_start(*args, **kwargs):
    raise AssertionError("the driver started a process")


class FakeSocket:
    def __init__(self, chunks):
        self.chunks = list(chunks)
        self.sent = b""

    def recv(self, size):
        return self.chunks.pop(0) if self.chunks else b""

    def settimeout(self, timeout):
        self.timeout = timeout

    def sendall(self, data):
        self.sent += data


def test_a_packet_carries_its_checksum():
    sock = FakeSocket([b"+", b"$", b"O", b"K", b"#", b"9", b"a"])
    client = watch_sweep.Client(sock)
    assert client.command("Z0,80000c0,2", 1) == "OK"
    assert sock.sent == b"$Z0,80000c0,2#9f+"


def test_a_stop_reply_keeps_its_trailing_byte():
    sock = FakeSocket([b"$", b"S", b"0", b"5", b"k", b"#", b"2", b"3"])
    client = watch_sweep.Client(sock)
    assert client.reply(1) == "S05k"


def test_a_register_block_yields_its_program_counter():
    registers = bytearray(68)
    registers[60:64] = (0x08000158).to_bytes(4, "little")
    registers[64:68] = (0x6000003F).to_bytes(4, "little")
    assert watch_sweep.pc_of(bytes(registers).hex()) == (0x08000158, 0x6000003F)


def test_a_run_needs_the_flag(tmp_path):
    with pytest.raises(SystemExit) as error:
        watch_sweep.main(["--rom", str(tmp_path / "copy.gba")])
    assert "--run" in str(error.value)


def test_a_run_needs_a_copy():
    with pytest.raises(SystemExit) as error:
        watch_sweep.main(["--run"])
    assert "--rom" in str(error.value)


def test_a_missing_copy_is_refused(tmp_path):
    with pytest.raises(SystemExit) as error:
        watch_sweep.main(["--run", "--rom", str(tmp_path / "absent.gba")])
    assert "not a file" in str(error.value)


def test_a_copy_with_another_digest_is_refused(tmp_path, monkeypatch):
    monkeypatch.setattr(watch_sweep.subprocess, "run", no_start)
    image = tmp_path / "copy.gba"
    image.write_bytes(b"\x00" * 16)
    with pytest.raises(SystemExit) as error:
        watch_sweep.main(["--run", "--rom", str(image), "--exe", "python"])
    assert "sha256" in str(error.value)


def test_a_missing_runtime_is_refused(tmp_path, monkeypatch):
    monkeypatch.setattr(watch_sweep, "digest", lambda path: watch_sweep.gate.CANONICAL_SHA256)
    monkeypatch.setattr(watch_sweep.subprocess, "run", no_start)
    image = tmp_path / "copy.gba"
    image.write_bytes(b"\x00" * 16)
    with pytest.raises(SystemExit) as error:
        watch_sweep.main(["--run", "--rom", str(image), "--exe", str(tmp_path / "absent")])
    assert "not a file" in str(error.value)


def test_the_plan_merges_overlapping_targets(tmp_path):
    targets = tmp_path / "targets.csv"
    targets.write_text("kind,start,end,bytes,mode,runtime\n"
                       "candidate-code,0x08000100,0x08000108,8,thumb,\n"
                       "bx-unresolved,0x08000104,0x08000106,2,thumb,\n"
                       "irq-slot,0x08000200,0x08000204,4,word,0x03000e3c\n", encoding="ascii")
    path, merged = watch_sweep.plan(str(tmp_path / "run"), watch_sweep.read_targets(str(targets)))
    assert merged == [[0x08000100, 0x08000108], [0x08000200, 0x08000204]]
    assert open(path, encoding="ascii").read() == ("0x08000100 0x08000108\n"
                                                   "0x08000200 0x08000204\n")


if __name__ == "__main__":
    print("PASS test_watch_sweep")
