from experiment_bot.taskcard.hashing import canonical_json_dumps, taskcard_sha256


def test_canonical_json_stable_across_key_order():
    a = {"b": 1, "a": 2, "c": [1, 2, 3]}
    b = {"a": 2, "c": [1, 2, 3], "b": 1}
    assert canonical_json_dumps(a) == canonical_json_dumps(b)


def test_canonical_json_strips_extra_whitespace():
    a = canonical_json_dumps({"a": 1})
    assert "\n" not in a
    assert "  " not in a


def test_taskcard_sha256_excludes_hash_field():
    base = {"schema_version": "2.0", "produced_by": {"taskcard_sha256": "OLDHASH"}}
    h1 = taskcard_sha256(base)
    base["produced_by"]["taskcard_sha256"] = "DIFFERENTHASH"
    h2 = taskcard_sha256(base)
    assert h1 == h2  # hash field itself not part of hash


def test_taskcard_sha256_changes_on_content_change():
    a = {"schema_version": "2.0", "produced_by": {"taskcard_sha256": ""}, "task": {"name": "stroop"}}
    b = {"schema_version": "2.0", "produced_by": {"taskcard_sha256": ""}, "task": {"name": "flanker"}}
    assert taskcard_sha256(a) != taskcard_sha256(b)
