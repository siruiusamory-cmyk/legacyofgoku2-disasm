from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "tools"))

import testkit
import thumb_vm

HEAP = 0x0801F08C
SLOT = 0x0801FC9C
RECT_FROM_FIELDS = 0x0800793A
QUEUE = 0x08026528
INCLUDE_POINT = 0x08028030
OVERLAPS = 0x0802805C
ADD_CAPPED = 0x080265AC
OUTRANKS = 0x08027E74
LIST = 0x02000000
MAX_SCALED = 0x08006D70
LOAD_POINT = 0x0800791A
FILL_CELLS = 0x080063E0
HALF_FILL_REQUEST = 0x0801F43C
WORD_FILL_REQUEST = 0x0801F46A
HALF_FILL_SOURCE = 0x03003910
WORD_FILL_SOURCE = 0x03003914
HEAD = 0x030022B4
NODE = 0x02000008
COPY_CHUNKS = 0x0801F412
ENABLE_DMA_INTERRUPT = 0x08021980
DISABLE_DMA_INTERRUPT = 0x08021A08
DMA_CHANNEL = 0x030038A0
SAVED_IME = 0x030038AC
DMA3 = 0x040000D4


def image():
    return testkit.rom_bytes(os.path.join(ROOT, "baserom.gba"), size=0x800000)


def run(address, registers, memory, stubs=None):
    data = image()
    return thumb_vm.run_function(data, address, registers=registers, memory=memory,
                                 body=thumb_vm.body_of(data, address), stubs=stubs)


def heap(size_words):
    memory = thumb_vm.Memory(image())
    memory.word(HEAD, NODE)
    memory.half(NODE + 2, size_words)
    memory.writes.clear()
    return memory


def writes_between(result, low, high):
    return [entry for entry in result["written"] if low <= entry[0] < high]


def test_heap_alloc_returns_distinct_non_overlapping_blocks_and_shrinks_the_free_list():
    memory = heap(0x40)
    first = run(HEAP, {0: 0x10}, memory)
    assert first["registers"][0] == 0x02000100
    assert first["calls"] == []
    assert memory.read(NODE + 2, 2) == 0x3A
    assert memory.read(NODE, 2) == 0x3E
    assert memory.read(0x020000F8 + 2, 2) == 4
    assert memory.read(0x020000F8 + 4, 2) == 2
    assert memory.read(0x020000F8 + 6, 1) == 1
    second = run(HEAP, {0: 0x10}, memory)
    assert second["registers"][0] == 0x020000E8
    assert memory.read(NODE + 2, 2) == 0x34
    assert memory.read(NODE, 2) == 0x38
    first_block = range(first["registers"][0], first["registers"][0] + 0x10)
    second_block = range(second["registers"][0], second["registers"][0] + 0x10)
    assert not set(first_block) & set(second_block)


def test_heap_alloc_returns_the_node_body_and_records_the_free_splice_for_an_exact_fit():
    memory = heap(4)
    result = run(HEAP, {0: 0x10}, memory)
    assert result["registers"][0] == NODE + 8
    assert result["calls"] == [(0x0801F0AA, 0x0801EFBC)]
    assert writes_between(result, 0x02000000, 0x02000400) == []


def test_slot_claim_takes_the_first_free_slot_and_initialises_its_fields():
    memory = thumb_vm.Memory(image())
    memory.blob(0x02000010, b"\x01")
    memory.writes.clear()
    result = run(SLOT, {0: 0x02000000, 1: 0x11111111, 2: 0x22, 3: 0x33}, memory)
    assert result["registers"][0] == 0x02000040
    assert writes_between(result, 0x02000000, 0x02001000) == [
        (0x02000068, 4, 0x11111111), (0x02000070, 4, 0x4000),
        (0x02000052, 1, 0x22), (0x02000053, 1, 0x33),
        (0x02000050, 1, 0x1F)]
    assert memory.read(0x02000010, 1) == 1


def test_slot_claim_returns_zero_when_every_slot_is_busy():
    memory = thumb_vm.Memory(image())
    for index in range(16):
        memory.blob(0x02000000 + 0x40 * index + 0x10, b"\x01")
    memory.writes.clear()
    result = run(SLOT, {0: 0x02000000, 1: 0x11111111, 2: 0x22, 3: 0x33}, memory)
    assert result["registers"][0] == 0
    assert writes_between(result, 0x02000000, 0x02001000) == []


def test_rect_from_fields_builds_the_rectangle_from_the_structure_words_and_bytes():
    memory = thumb_vm.Memory(image())
    memory.word(0x03000158, 0x00002000)
    memory.word(0x0300015C, 0x00003000)
    memory.blob(0x03000154, b"\x10\x20")
    result = run(RECT_FROM_FIELDS, {0: 0x02000200, 1: 0x03000000}, memory)
    assert result["registers"][0] == 0x02000210
    assert result["written"][-4:] == [(0x02000200, 4, 0x20), (0x02000204, 4, 0x30),
                                      (0x02000208, 4, 0x30), (0x0200020C, 4, 0x50)]
    memory.word(0x03000158, 0xFFFFF800)
    negative = run(RECT_FROM_FIELDS, {0: 0x02000200, 1: 0x03000000}, memory)
    assert negative["written"][-4:] == [(0x02000200, 4, 0xFFFFFFF8), (0x02000204, 4, 0x30),
                                        (0x02000208, 4, 0x8), (0x0200020C, 4, 0x50)]


def test_rect_include_point_grows_the_rectangle_to_cover_the_point():
    memory = thumb_vm.Memory(image())
    for index, value in enumerate([10, 20, 30, 40]):
        memory.word(0x02000000 + 4 * index, value)
    memory.word(0x02000010, 5)
    memory.word(0x02000014, 50)
    memory.writes.clear()
    result = run(INCLUDE_POINT, {0: 0x02000000, 1: 0x02000010}, memory)
    assert memory.read(0x02000000, 4) == 5
    assert memory.read(0x02000004, 4) == 20
    assert memory.read(0x02000008, 4) == 30
    assert memory.read(0x0200000C, 4) == 50
    assert result["written"] == [(0x02000000, 4, 5), (0x0200000C, 4, 0x32)]


def test_rect_overlaps_reports_whether_two_rectangles_intersect():
    memory = thumb_vm.Memory(image())
    for index, value in enumerate([10, 20, 30, 40]):
        memory.word(0x02000000 + 4 * index, value)
    for index, value in enumerate([20, 30, 50, 60]):
        memory.word(0x02000010 + 4 * index, value)
    for index, value in enumerate([40, 20, 50, 60]):
        memory.word(0x02000020 + 4 * index, value)
    inside = run(OVERLAPS, {0: 0x02000000, 1: 0x02000010}, memory)
    beside = run(OVERLAPS, {0: 0x02000000, 1: 0x02000020}, memory)
    assert inside["registers"][0] == 1
    assert beside["registers"][0] == 0


def test_queue_remove_shifts_the_following_entries_down_through_dma3():
    memory = thumb_vm.Memory(image())
    memory.word(0x02000000, 4)
    for index in range(4):
        memory.word(0x02000004 + 4 * index, 0x100 + index)
    memory.writes.clear()
    result = run(QUEUE, {0: 0x02000000, 1: 1}, memory)
    assert memory.read(0x02000000, 4) == 3
    assert result["written"] == [(0x02000000, 4, 3), (0x040000D4, 4, 0x0200000C),
                                 (0x040000D8, 4, 0x02000008), (0x040000DC, 2, 2),
                                 (0x040000DE, 2, 0x8400)]


def test_queue_remove_of_the_last_entry_writes_the_count_and_no_dma_register():
    memory = thumb_vm.Memory(image())
    memory.word(0x02000000, 4)
    for index in range(4):
        memory.word(0x02000004 + 4 * index, 0x100 + index)
    memory.writes.clear()
    result = run(QUEUE, {0: 0x02000000, 1: 3}, memory)
    assert memory.read(0x02000000, 4) == 3
    assert result["written"] == [(0x02000000, 4, 3)]


def test_counter_add_capped_stores_the_sum_until_the_limit_is_reached():
    memory = thumb_vm.Memory(image())
    memory.half(0x02000000, 10)
    memory.half(0x02000002, 20)
    memory.writes.clear()
    lower = run(ADD_CAPPED, {0: 0x02000000, 1: 5}, memory)
    assert memory.read(0x02000000, 2) == 15
    assert lower["written"] == [(0x02000000, 2, 15)]
    memory.half(0x02000000, 18)
    memory.writes.clear()
    capped = run(ADD_CAPPED, {0: 0x02000000, 1: 5}, memory)
    assert memory.read(0x02000000, 2) == 20
    assert capped["written"] == [(0x02000000, 2, 20)]

def test_bitmap_fill_cells_sets_or_clears_one_bit_for_each_eight_pixel_cell():
    memory = thumb_vm.Memory(image())
    for index, value in enumerate([8, 16, 40, 40]):
        memory.word(0x02000100 + 4 * index, value)
    memory.blob(0x02000200, bytes(0x60))
    memory.writes.clear()
    set_cells = run(FILL_CELLS, {0: 0x02000100, 1: 0x02000200, 2: 1}, memory)
    assert memory.read(0x02000240, 4) == 0x1E
    assert memory.read(0x02000260, 4) == 0x1E
    assert memory.read(0x02000280, 4) == 0x1E
    assert memory.read(0x02000220, 4) == 0
    written = writes_between(set_cells, 0x02000200, 0x02000300)
    assert [entry[2] for entry in written] == [2, 6, 0xE, 0x1E] * 3
    assert [entry[0] for entry in written] == [0x02000240] * 4 + [0x02000260] * 4 \
        + [0x02000280] * 4
    memory.blob(0x02000200, b"\xff" * 0x60)
    memory.writes.clear()
    run(FILL_CELLS, {0: 0x02000100, 1: 0x02000200, 2: 0}, memory)
    assert memory.read(0x02000240, 4) == 0xFFFFFFE1
    for index, value in enumerate([-8, -8, 8, 8]):
        memory.word(0x02000100 + 4 * index, value)
    memory.blob(0x02000200, bytes(0x60))
    memory.writes.clear()
    run(FILL_CELLS, {0: 0x02000100, 1: 0x02000200, 2: 1}, memory)
    assert memory.read(0x02000200, 4) == 1

def test_record_outranks_by_a_higher_byte_then_a_lower_word():
    memory = thumb_vm.Memory(image())
    memory.word(0x02000100, 0x02000200)
    memory.word(0x02000110, 0x02000300)
    memory.blob(0x02000208, b"\x01")
    memory.blob(0x02000308, b"\x02")
    assert run(OUTRANKS, {0: 0x02000100, 1: 0x02000110}, memory)["registers"][0] == 0
    memory.blob(0x02000208, b"\x03")
    assert run(OUTRANKS, {0: 0x02000100, 1: 0x02000110}, memory)["registers"][0] == 1
    memory.blob(0x02000208, b"\x02")
    memory.word(0x02000204, 5)
    memory.word(0x02000304, 7)
    assert run(OUTRANKS, {0: 0x02000100, 1: 0x02000110}, memory)["registers"][0] == 1
    memory.word(0x02000204, 0xFFFFFFF9)
    assert run(OUTRANKS, {0: 0x02000100, 1: 0x02000110}, memory)["registers"][0] == 1
    memory.word(0x02000204, 9)
    assert run(OUTRANKS, {0: 0x02000100, 1: 0x02000110}, memory)["registers"][0] == 0
    memory.word(0x02000204, 7)
    assert run(OUTRANKS, {0: 0x02000100, 1: 0x02000110}, memory)["registers"][0] == 0

def test_list_max_scaled_returns_the_largest_halfword_of_the_chain_times_sixty_four():
    memory = thumb_vm.Memory(image())
    memory.word(LIST + 4, 0)
    memory.blob(LIST, b"\x00")
    memory.half(0x02000698, 3)
    memory.blob(0x0200069C, b"\x01")
    memory.half(0x020006A2, 5)
    memory.blob(0x020006A6, b"\xff")
    assert run(MAX_SCALED, {0: LIST}, memory)["registers"][0] == 0x140
    memory.half(0x020006A2, 0xFFFF)
    assert run(MAX_SCALED, {0: LIST}, memory)["registers"][0] == 0x3FFFC0
    memory.word(LIST + 4, 0x80)
    assert run(MAX_SCALED, {0: LIST}, memory)["registers"][0] == 0
    memory.word(LIST + 4, 0)
    memory.blob(LIST, b"\xff")
    assert run(MAX_SCALED, {0: LIST}, memory)["registers"][0] == 0


def test_a_halfword_fill_request_stores_the_halfword_it_copies_in_the_dma3_source_word():
    memory = thumb_vm.Memory(image())
    memory.writes.clear()
    result = run(HALF_FILL_REQUEST,
                 {0: 0x02000100, 1: 0x06001000, 2: 0x89ABCDEF, 3: 0x2000}, memory)
    assert writes_between(result, HALF_FILL_SOURCE, HALF_FILL_SOURCE + 2) == [
        (HALF_FILL_SOURCE, 2, 0xCDEF), (HALF_FILL_SOURCE, 2, 0xCDEF)]
    assert [entry for entry in result["written"] if 0x02000100 <= entry[0] < 0x02000110] == [
        (0x02000100, 4, HALF_FILL_SOURCE), (0x02000104, 4, 0x06001000),
        (0x02000108, 2, 0x800), (0x0200010A, 2, 0x8100),
        (0x02000100, 4, HALF_FILL_SOURCE), (0x02000104, 4, 0x06002000),
        (0x02000108, 2, 0x800), (0x0200010A, 2, 0x8100)]


def test_a_word_fill_request_stores_the_word_it_copies_in_the_dma3_source_word():
    memory = thumb_vm.Memory(image())
    memory.writes.clear()
    result = run(WORD_FILL_REQUEST,
                 {0: 0x02000100, 1: 0x06001000, 2: 0x89ABCDEF, 3: 0x2000}, memory)
    assert writes_between(result, WORD_FILL_SOURCE, WORD_FILL_SOURCE + 4) == [
        (WORD_FILL_SOURCE, 4, 0x89ABCDEF), (WORD_FILL_SOURCE, 4, 0x89ABCDEF)]
    assert [entry for entry in result["written"] if 0x02000100 <= entry[0] < 0x02000110] == [
        (0x02000100, 4, WORD_FILL_SOURCE), (0x02000104, 4, 0x06001000),
        (0x02000108, 2, 0x400), (0x0200010A, 2, 0x8500),
        (0x02000100, 4, WORD_FILL_SOURCE), (0x02000104, 4, 0x06002000),
        (0x02000108, 2, 0x400), (0x0200010A, 2, 0x8500)]


def test_point_load_scaled_writes_the_two_global_words_shifted_into_the_structure():
    memory = thumb_vm.Memory(image())
    memory.word(0x03000158, 0x00002000)
    memory.word(0x0300015C, 0x00003000)
    memory.writes.clear()
    result = run(LOAD_POINT, {0: 0x02000100, 1: 0x03000000}, memory)
    assert writes_between(result, 0x02000100, 0x02000110) == [
        (0x02000100, 4, 0x20), (0x02000104, 4, 0x30)]
    memory.word(0x03000158, 0xFFFFF800)
    memory.writes.clear()
    result = run(LOAD_POINT, {0: 0x02000100, 1: 0x03000000}, memory)
    assert writes_between(result, 0x02000100, 0x02000110)[0] == (0x02000100, 4, 0xFFFFFFF8)

def test_dma3_copy_chunks_splits_a_copy_at_four_thousand_ninety_six_bytes_into_requests():
    memory = thumb_vm.Memory(image())
    memory.writes.clear()
    result = run(COPY_CHUNKS, {0: DMA3, 1: 0x06000000, 2: 0x02000000, 3: 0x1800}, memory)
    assert writes_between(result, DMA3, DMA3 + 0x10) == [
        (DMA3, 4, 0x02000000), (DMA3 + 4, 4, 0x06000000),
        (DMA3 + 8, 2, 0x400), (DMA3 + 0xA, 2, 0x8400),
        (DMA3, 4, 0x02001000), (DMA3 + 4, 4, 0x06001000),
        (DMA3 + 8, 2, 0x200), (DMA3 + 0xA, 2, 0x8400)]


def test_the_dma_interrupt_enable_saves_the_master_enable_and_raises_the_channel_bit():
    memory = thumb_vm.Memory(image())
    memory.half(0x04000208, 1)
    memory.half(0x04000200, 0)
    memory.half(0x04000202, 0)
    memory.blob(DMA_CHANNEL, b"\x02")
    memory.word(0x030038A8, 0x02000100)
    memory.half(0x02000000, 0x1234)
    memory.half(0x02000002, 0x5678)
    memory.half(0x02000004, 0x9ABC)
    memory.writes.clear()
    result = run(ENABLE_DMA_INTERRUPT, {0: 0x02000000}, memory)
    assert result["calls"] == []
    assert memory.read(SAVED_IME, 2) == 1
    assert memory.read(0x04000208, 2) == 1
    assert memory.read(0x04000200, 2) == 0x20
    assert memory.read(0x04000202, 2) == 0x20
    assert memory.read(0x030038A2, 2) == 0x1234
    assert memory.read(0x02000100, 2) == 0x5678
    assert memory.read(0x02000102, 2) == 0x9ABC
    assert memory.read(0x030038A8, 4) == 0x02000100


def test_the_dma_interrupt_disable_clears_the_channel_bit_and_restores_the_master_enable():
    memory = thumb_vm.Memory(image())
    memory.half(SAVED_IME, 1)
    memory.half(0x04000208, 0)
    memory.half(0x04000200, 0x20)
    memory.blob(DMA_CHANNEL, b"\x02")
    memory.word(0x030038A8, 0x02000100)
    memory.writes.clear()
    run(DISABLE_DMA_INTERRUPT, {}, memory)
    assert memory.read(0x04000200, 2) == 0
    assert memory.read(0x04000208, 2) == 1
    assert memory.read(0x02000100, 4) == 0
