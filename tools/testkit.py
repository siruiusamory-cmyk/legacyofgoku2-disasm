from __future__ import annotations

import hashlib
import os

import pytest


def rom_bytes(path, digest=None, size=None):
    if not os.path.exists(path):
        pytest.skip("%s is absent, so this ROM-gated test cannot run" % path)
    data = open(path, "rb").read()
    if size is not None:
        assert len(data) == size
    if digest is not None:
        assert hashlib.sha256(data).hexdigest() == digest
    return data


def refused(call):
    try:
        call()
    except ValueError as error:
        print("refused: %s" % error)
        return True
    return False


def require(path, reason):
    if not os.path.exists(path):
        pytest.skip(reason)
