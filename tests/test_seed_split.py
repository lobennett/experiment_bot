"""Wave C4: pure seed -> program assignment helper."""
from collections import Counter

import pytest

from experiment_bot.behavior.seed_split import split_seeds


def test_split_is_even_and_index_mod_k():
    seeds = list(range(730001, 730011))  # 10 seeds
    mapping = split_seeds(seeds, ["p0", "p1"])
    assert mapping[730001] == "p0"
    assert mapping[730002] == "p1"
    assert mapping[730003] == "p0"
    assert Counter(mapping.values()) == Counter({"p0": 5, "p1": 5})


def test_split_is_deterministic():
    seeds = [7, 3, 9, 1]  # assignment follows list order, not seed value
    m1 = split_seeds(seeds, ["a", "b"])
    m2 = split_seeds(seeds, ["a", "b"])
    assert m1 == m2
    assert m1 == {7: "a", 3: "b", 9: "a", 1: "b"}


def test_split_k1_assigns_all_to_single_program():
    mapping = split_seeds([1, 2, 3], ["only"])
    assert set(mapping.values()) == {"only"}


def test_split_uneven_k3():
    mapping = split_seeds(list(range(10)), ["a", "b", "c"])
    assert Counter(mapping.values()) == Counter({"a": 4, "b": 3, "c": 3})


def test_split_requires_a_program():
    with pytest.raises(ValueError):
        split_seeds([1, 2], [])
