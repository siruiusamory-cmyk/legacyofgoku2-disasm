from __future__ import annotations

import argparse
import hashlib
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
ROM = os.path.join(ROOT, "baserom.gba")
ROM_BASE = 0x08000000
SHA256 = "6e6c370c339ec9171cb1956adf837a0d342a197f78964882ef46c3086656ff75"
SOURCE = 0x087FD6BC
DEST = 0x03000000
SIZE = 0xE7C
MAGIC = b"gba-iwram v1\n"
IWRAM_LEN = 0x8000


def blob_path(sha):
    root = os.environ.get("APPDATA") or os.path.expanduser("~")
    return os.path.join(root, "gba-recomp", "labels", "%s.iwram" % sha)


def seed(image, sha=SHA256):
    digest = hashlib.sha256(image).hexdigest()
    if digest != sha:
        raise SystemExit("this image has sha256 %s, and the seed is cut from %s"
                         % (digest, sha))
    start = SOURCE - ROM_BASE
    if start < 0 or start + SIZE > len(image):
        raise SystemExit("%08x+%x does not lie in a %d-byte image" % (SOURCE, SIZE, len(image)))
    return image[start:start + SIZE]


def blob(copied):
    image = bytearray(IWRAM_LEN)
    mask = bytearray(IWRAM_LEN)
    image[:len(copied)] = copied
    mask[:len(copied)] = b"\x01" * len(copied)
    return MAGIC + bytes(image) + bytes(mask)


def target_path(out):
    target = os.path.abspath(out)
    try:
        inside = os.path.commonpath([target, ROOT]) == ROOT
    except ValueError:
        inside = False
    if inside:
        raise SystemExit("refused: %s is inside the tree, and the blob holds image bytes" % out)
    return target


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--rom", default=ROM)
    parser.add_argument("--out")
    arguments = parser.parse_args(argv)
    if not os.path.exists(arguments.rom):
        raise SystemExit("no image at %s, so there is no seed to cut" % arguments.rom)
    data = open(arguments.rom, "rb").read()
    copied = seed(data)
    target = target_path(arguments.out or blob_path(hashlib.sha256(data).hexdigest()))
    os.makedirs(os.path.dirname(target), exist_ok=True)
    with open(target, "wb") as handle:
        handle.write(blob(copied))
    print("wrote %s size=%d valid=%d" % (target, len(MAGIC) + 2 * IWRAM_LEN, len(copied)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
