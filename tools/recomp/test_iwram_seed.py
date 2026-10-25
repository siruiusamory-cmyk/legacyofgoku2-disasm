from __future__ import annotations

import hashlib
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import iwram_seed


def image(fill):
    data = bytearray(0x800000)
    data[iwram_seed.SOURCE - iwram_seed.ROM_BASE:iwram_seed.SOURCE
         - iwram_seed.ROM_BASE + iwram_seed.SIZE] = bytes([fill]) * iwram_seed.SIZE
    return bytes(data)


def test_the_blob_round_trips_its_mask():
    data = image(0x5A)
    sha = hashlib.sha256(data).hexdigest()
    written = iwram_seed.blob(iwram_seed.seed(data, sha))
    assert written[:len(iwram_seed.MAGIC)] == b"gba-iwram v1\n"
    assert len(written) == len(iwram_seed.MAGIC) + 2 * iwram_seed.IWRAM_LEN
    body = written[len(iwram_seed.MAGIC):]
    img, mask = body[:iwram_seed.IWRAM_LEN], body[iwram_seed.IWRAM_LEN:]
    assert img[:iwram_seed.SIZE] == bytes([0x5A]) * iwram_seed.SIZE
    assert mask[:iwram_seed.SIZE] == b"\x01" * iwram_seed.SIZE
    assert mask[iwram_seed.SIZE:] == bytes(iwram_seed.IWRAM_LEN - iwram_seed.SIZE)
    assert img[iwram_seed.SIZE:] == bytes(iwram_seed.IWRAM_LEN - iwram_seed.SIZE)


def test_a_wrong_image_is_refused():
    data = image(0x00)
    with pytest.raises(SystemExit):
        iwram_seed.seed(data)
    assert hashlib.sha256(data).hexdigest() != iwram_seed.SHA256


def test_a_blob_inside_the_tree_is_refused():
    with pytest.raises(SystemExit):
        iwram_seed.target_path(os.path.join(iwram_seed.ROOT, "iwram-blob"))
    outside = iwram_seed.target_path(os.path.join(os.environ.get("TEMP", "/tmp"), "x.iwram"))
    assert not outside.startswith(iwram_seed.ROOT)


def test_the_seed_names_the_cited_bounds():
    assert iwram_seed.SHA256 == "6e6c370c339ec9171cb1956adf837a0d342a197f78964882ef46c3086656ff75"
    assert (iwram_seed.SOURCE, iwram_seed.DEST, iwram_seed.SIZE) == (0x087FD6BC, 0x03000000, 0xE7C)
    assert iwram_seed.blob_path(iwram_seed.SHA256).endswith(
        os.path.join("gba-recomp", "labels", "%s.iwram" % iwram_seed.SHA256))
