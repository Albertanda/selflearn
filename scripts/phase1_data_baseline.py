"""Validate the user's single S14 catalog exception without changing old evidence.

Only opaque file inventories are loaded. No real settings content is parsed.
The manifest and both snapshots are pinned by the subsequent reviewer receipt.
"""

from __future__ import annotations

from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "phase1_snapshot_for_data_baseline", Path(__file__).with_name("phase1_snapshot.py")
)
_snapshot = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_snapshot)
compare_data = _snapshot.compare_data

MANIFEST = "plans/phase1/data_baseline_exception.json"
ORIGINAL_SHA = "630dbac8a405233f2b946e3a60e42d6f9a5ebe43aedb81a3b702109e3f51110e"
APPROVED_SHA = "65db48a600816207a3b6f366fbb227ef06960d3eacd519b2e281e8978a23d5a0"


def load_data_baseline(root: Path, original: Path) -> dict:
    """Use the historical baseline unless the exact approved exception validates.

    A malformed/stale manifest fails closed; it never selects today's data as a
    new baseline. All six root inventories must match S13 except this one file's
    approved size/hash, including modes, directories and supplementary trees.
    """
    root = root.resolve()
    historical = json.loads(original.read_text(encoding="utf-8"))
    path = root / MANIFEST
    if not path.exists():
        return historical
    record = json.loads(path.read_text(encoding="utf-8"))
    if (
        record.get("schema_version") != 1
        or record.get("exception_id") != "S14-model-catalog-20261020"
        or record.get("status") != "user_authorized"
        or record.get("authorization", {}).get("actor") != "user"
        or record.get("authorization", {}).get("text")
        != "接受单项例外，允许建立新配置基线"
        or record.get("allowed_path") != "data/user/settings/model_catalog.json"
    ):
        raise ValueError("Invalid S14 data-baseline exception authorization")

    def snapshot(name: str) -> dict:
        reference = record[name]
        relative = Path(reference["path"])
        target = (root / relative).resolve()
        if relative.is_absolute() or ".." in relative.parts or not target.is_relative_to(root):
            raise ValueError("Data-baseline reference escapes repository")
        raw = target.read_bytes()
        if hashlib.sha256(raw).hexdigest() != reference["sha256"]:
            raise ValueError("Data-baseline evidence hash mismatch")
        return json.loads(raw)

    if record["historical"]["path"] != original.relative_to(root).as_posix():
        raise ValueError("Exception references a different historical baseline")
    if snapshot("historical") != historical:
        raise ValueError("Historical baseline mismatch")
    prior, approved = snapshot("previous"), snapshot("baseline")
    if not compare_data(historical, prior)["ok"]:
        raise ValueError("S13 baseline does not preserve historical data")
    for value in (prior, approved):
        if value["root"] != str(root):
            raise ValueError("Data baseline belongs to another repository")
        if set(value["roots"]) != {"learning_tree", "public_outputs", "settings"}:
            raise ValueError("Incomplete primary data inventory")
        if set(value["supplementary_roots"]) != {"global_knowledge_bases", "memory", "system"}:
            raise ValueError("Incomplete supplementary data inventory")
    old = prior["roots"]["settings"]["files"]["model_catalog.json"]
    new = approved["roots"]["settings"]["files"]["model_catalog.json"]
    if old.get("sha256") != ORIGINAL_SHA or old.get("size") != 3608:
        raise ValueError("Unexpected original catalog identity")
    if new != {**old, "sha256": APPROVED_SHA, "size": 3117}:
        raise ValueError("Exception authorizes only the specified catalog bytes")
    projected = deepcopy(approved)
    projected["roots"]["settings"]["files"]["model_catalog.json"] = old
    for field in ("roots", "supplementary_roots"):
        if projected[field] != prior[field]:
            raise ValueError("Additional data changes are not authorized")
    return approved
