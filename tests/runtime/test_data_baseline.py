"""An approved exception must not admit any extra or later data mutation."""
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location(
    "phase1_data_baseline_under_test",
    Path(__file__).resolve().parents[2] / "scripts/phase1_data_baseline.py",
)
_guard = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_guard)
APPROVED_SHA, MANIFEST, ORIGINAL_SHA = _guard.APPROVED_SHA, _guard.MANIFEST, _guard.ORIGINAL_SHA
load_data_baseline, compare_data = _guard.load_data_baseline, _guard.compare_data


@pytest.fixture
def authorized(tmp_path):
    def tree():
        return {"exists": True, "kind": "dir", "files": {}, "dirs": [], "mode": 448,
                "dir_modes": {}, "inventory_policy": "all", "file_count": 0, "dir_count": 0}

    previous = {
        "root": str(tmp_path),
        "roots": {name: tree() for name in ("learning_tree", "public_outputs", "settings")},
        "supplementary_roots": {name: tree() for name in ("global_knowledge_bases", "memory", "system")},
    }
    previous["roots"]["settings"]["files"]["model_catalog.json"] = {
        "kind": "file", "mode": 384, "sha256": ORIGINAL_SHA, "size": 3608,
    }
    previous["roots"]["settings"]["file_count"] = 1
    baseline = deepcopy(previous)
    baseline["roots"]["settings"]["files"]["model_catalog.json"].update(
        sha256=APPROVED_SHA, size=3117
    )
    record = {
        "schema_version": 1, "exception_id": "S14-model-catalog-20261020",
        "status": "user_authorized", "allowed_path": "data/user/settings/model_catalog.json",
        "authorization": {"actor": "user", "text": "接受单项例外，允许建立新配置基线"},
    }
    for name, value in (("historical", previous), ("previous", previous), ("baseline", baseline)):
        path = tmp_path/f"{name}.json"
        raw = (json.dumps(value)+"\n").encode()
        path.write_bytes(raw)
        record[name] = {"path": path.name, "sha256": hashlib.sha256(raw).hexdigest()}
    manifest = tmp_path/MANIFEST
    manifest.parent.mkdir(parents=True)
    manifest.write_text(json.dumps(record))
    return tmp_path, record, previous, baseline


def test_only_exact_approved_baseline_loads_and_history_is_preserved(authorized):
    root, _, previous, baseline = authorized
    historical = (root/"historical.json").read_bytes()
    assert load_data_baseline(root, root/"historical.json") == baseline
    assert (root/"historical.json").read_bytes() == historical
    assert not compare_data(previous, baseline)["ok"]


@pytest.mark.parametrize("damage", ["catalog", "other_file", "system", "directory", "mode", "authorization", "hash", "escape"])
def test_exception_rejects_broader_or_unpinned_changes(authorized, damage):
    root, record, _, baseline = authorized
    if damage == "catalog":
        baseline["roots"]["settings"]["files"]["model_catalog.json"]["sha256"] = "a"*64
    elif damage == "other_file":
        baseline["roots"]["settings"]["files"]["another.json"] = {"kind": "file", "sha256": "b"*64, "size": 2}
    elif damage == "system":
        baseline["supplementary_roots"]["system"]["mode"] = 511
    elif damage == "directory":
        baseline["roots"]["learning_tree"]["dirs"].append("new")
    elif damage == "mode":
        baseline["roots"]["settings"]["files"]["model_catalog.json"]["mode"] = 511
    elif damage == "authorization":
        record["authorization"]["actor"] = "worker"
    elif damage == "hash":
        record["baseline"]["sha256"] = "0"*64
    elif damage == "escape":
        record["baseline"]["path"] = "../outside.json"
    raw = json.dumps(baseline).encode()
    (root/"baseline.json").write_bytes(raw)
    if damage != "hash":
        record["baseline"]["sha256"] = hashlib.sha256(raw).hexdigest()
    (root/MANIFEST).write_text(json.dumps(record))
    with pytest.raises(ValueError):
        load_data_baseline(root, root/"historical.json")


def test_no_manifest_preserves_original_guard_and_later_changes_still_fail(authorized):
    root, _, previous, baseline = authorized
    approved = load_data_baseline(root, root/"historical.json")
    later = deepcopy(baseline)
    later["roots"]["settings"]["files"]["model_catalog.json"]["sha256"] = "c"*64
    assert not compare_data(approved, later)["ok"]
    (root/MANIFEST).unlink()
    assert load_data_baseline(root, root/"historical.json") == previous
