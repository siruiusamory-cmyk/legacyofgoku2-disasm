import struct

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import unproven_remainder as ur
import code_split


def test_union_merges_touching_and_overlapping_intervals():
    assert ur.union([(10, 20), (20, 30), (5, 8), (40, 50), (45, 60)]) == [(5, 8), (10, 30),
                                                                          (40, 60)]


def test_subtract_removes_the_holes_and_keeps_the_ends():
    assert ur.subtract([(0, 100)], [(10, 20), (90, 95)]) == [(0, 10), (20, 90), (95, 100)]
    assert ur.subtract([(0, 100)], [(100, 200)]) == [(0, 100)]


def test_table_words_marks_a_run_of_two_odd_words_and_a_repeated_word():
    rom = bytearray(0x100)
    struct.pack_into("<II", rom, 0x10, 0x08000011, 0x08000013)
    for offset in (0x40, 0x50, 0x60, 0x70):
        struct.pack_into("<I", rom, offset, 0x08000021)
    runs = ur.table_words(bytes(rom))
    assert (0x10, 0x18) in runs
    assert (0x40, 0x44) in runs
    assert (0x60, 0x64) in runs


def test_table_words_skips_a_lone_word_that_names_the_image():
    rom = bytearray(0x100)
    struct.pack_into("<I", rom, 0x10, 0x08000011)
    assert ur.table_words(bytes(rom)) == []


def test_a_closing_null_at_the_bar_moves_the_class_to_the_named_residual():
    spare = bytearray([ur.CLOSING_CODE] * 10 + [0] * 5 + [4] * 3)
    ur.apply_closing_bar(spare, 5, 100)
    assert list(spare) == [ur.BELOW_BAR_CODE] * 10 + [0] * 5 + [4] * 3
    assert ur.CLOSING_REASON in ur.CLASSES


def test_a_closing_null_under_the_bar_keeps_the_class():
    spare = bytearray([ur.CLOSING_CODE] * 10 + [0] * 5)
    ur.apply_closing_bar(spare, 4, 100)
    assert list(spare) == [ur.CLOSING_CODE] * 10 + [0] * 5


def test_an_empty_closing_class_claims_no_bytes_at_any_bar():
    spare = bytearray(5)
    ur.apply_closing_bar(spare, 0, 0)
    assert list(spare) == [0] * 5


def test_the_closing_test_reads_the_named_word_and_its_linear_run():
    rom = bytearray(0x100)
    struct.pack_into("<HH", rom, 0x20, 0x2000, 0x4770)
    classes = bytearray(len(rom))
    modes = bytearray(len(rom))
    assert code_split.closure(bytes(rom), 0x08000020, classes, modes)[0] == "return"


def test_named_words_are_the_odd_words_that_name_the_image():
    rom = bytearray(0x100)
    struct.pack_into("<I", rom, 0x10, 0x08000041)
    struct.pack_into("<I", rom, 0x20, 0x08000043)
    struct.pack_into("<I", rom, 0x30, 0x08000040)
    struct.pack_into("<I", rom, 0x40, 0x03000001)
    assert ur.named(bytes(rom)) == [0x08000040, 0x08000042]


def test_the_null_counts_an_overlapping_closure_once(monkeypatch):
    rom = bytearray(0x100)
    struct.pack_into("<I", rom, 0x10, 0x08000041)
    struct.pack_into("<I", rom, 0x20, 0x08000043)
    struct.pack_into("<HHH", rom, 0x40, 0x2000, 0x2101, 0x4770)
    rom = bytes(rom)
    monkeypatch.setattr(code_split, "permute", lambda image: image)
    monkeypatch.setattr(code_split, "measure_null",
                        lambda image: {"pre": bytearray(len(image)),
                                       "modes": bytearray(len(image))})
    mask = bytearray(len(rom))
    mask[0x40:0x48] = b"\x01" * 8
    assert ur.null(rom, mask) == 6
