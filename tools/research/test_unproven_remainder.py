import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import unproven_remainder as ur


def test_union_merges_touching_and_overlapping_intervals():
    assert ur.union([(10, 20), (20, 30), (5, 8), (40, 50), (45, 60)]) == [(5, 8), (10, 30),
                                                                          (40, 60)]


def test_subtract_removes_the_holes_and_keeps_the_ends():
    assert ur.subtract([(0, 100)], [(10, 20), (90, 95)]) == [(0, 10), (20, 90), (95, 100)]
    assert ur.subtract([(0, 100)], [(100, 200)]) == [(0, 100)]


def test_overlap_counts_only_the_shared_bytes():
    shared = ur.overlap([(0, 10), (20, 30)], [(5, 25)])
    assert shared == [(5, 10), (20, 25)]
    assert sum(end - begin for begin, end in shared) == 10
