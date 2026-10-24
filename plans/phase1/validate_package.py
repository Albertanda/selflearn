"""Validate planning artifacts only; never run repair cards or change application data."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re

import jsonschema


def validate() -> dict:
    root = Path(__file__).resolve().parent
    manifest = json.loads((root / "tasks.json").read_text(encoding="utf-8"))
    schema = json.loads((root / "schemas.json").read_text(encoding="utf-8"))
    examples = json.loads((root / "examples.json").read_text(encoding="utf-8"))
    contract_text = (root / "DATA_CONTRACTS.md").read_text(encoding="utf-8")
    cards = manifest["cards"]
    by_id = {card["id"]: card for card in cards}
    assert len(by_id) == len(cards) == manifest["card_count"], "card count/ids mismatch"
    assert set(manifest["dispatch_order"]) == set(by_id), "dispatch ids mismatch"
    assert len(manifest["dispatch_order"]) == len(by_id), "duplicate dispatch"
    dispatched: set[str] = set()
    required_sections = (
        "## 目标", "## 已有问题证据", "## 允许更改范围",
        "## 证据：如何证明完成", "## 完成条件", "## 越界或失败处理",
    )
    for card_id in manifest["dispatch_order"]:
        card = by_id[card_id]
        assert set(card["depends_on"]) <= dispatched, f"unsatisfied dependency: {card_id}"
        dispatched.add(card_id)
        text = (root / card["path"]).read_text(encoding="utf-8")
        assert all(section in text for section in required_sections), card_id
        assert card["allowed_files"], f"empty scope: {card_id}"
        assert all(f"`{path}`" in text for path in card["allowed_files"]), f"scope mismatch: {card_id}"
        for dependency in card["depends_on"]:
            assert dependency in text, f"dependency missing in card: {card_id}:{dependency}"
        for contract in card["contracts"]:
            assert re.search(r"^## " + contract + r"[：:]", contract_text, re.M), contract
            assert contract in text, f"contract missing in card: {card_id}:{contract}"
        assert text.count("```") % 2 == 0, f"unclosed code block: {card_id}"

    jsonschema.Draft202012Validator.check_schema(schema)
    for case in examples["valid"]:
        validator = jsonschema.Draft202012Validator(schema | {"$ref": "#/$defs/" + case["schema"]})
        validator.validate(case["value"])
    for case in examples["invalid"]:
        validator = jsonschema.Draft202012Validator(schema | {"$ref": "#/$defs/" + case["schema"]})
        assert list(validator.iter_errors(case["value"])), f"invalid example accepted: {case}"
    stages = json.loads((root / "stages.json").read_text(encoding="utf-8"))
    covered = []
    seen_stages = set()
    for stage in stages["stages"]:
        assert set(stage["depends_on_stages"]) <= seen_stages, stage["id"]
        assert (root / stage["entry_path"]).exists(), stage["id"]
        union = set()
        for card_id in stage["cards"]:
            assert set(by_id[card_id]["depends_on"]) <= set(covered), card_id
            union.update(by_id[card_id]["allowed_files"])
            covered.append(card_id)
        assert set(stage["allowed_files"]) == union, stage["id"]
        seen_stages.add(stage["id"])
    assert covered == manifest["dispatch_order"] and set(covered) == set(by_id)
    assert len(covered) == len(by_id)
    for path in root.rglob("*.md"):
        text = path.read_text(encoding="utf-8")
        for target in re.findall(r"\]\(([^)]+)\)", text):
            if "://" in target or target.startswith("#"):
                continue
            assert (path.parent / target.split("#")[0]).exists(), f"missing link: {path}:{target}"
        assert "docs/phase1" not in text, f"stale ignored path in {path}"
        assert text.endswith("\n") and not text.endswith("\n\n"), f"trailing newline: {path}"
    assert "P1-50" in by_id["P1-51"]["depends_on"], "HTTP report acceptance must depend on real sandbox"
    assert "P1-04" in by_id["P1-26"]["depends_on"], "image description must share completion checks"
    return {
        "status": "planning_package_validated",
        "card_count": len(cards),
        "stage_count": len(stages["stages"]),
        "execution_policy": "stage-based-2.0",
        "contract_sections": 14,
        "dependency_layers": len(manifest["dependency_layers"]),
        "schema_definitions": len(schema["$defs"]),
        "valid_examples_accepted": len(examples["valid"]),
        "invalid_examples_rejected": len(examples["invalid"]),
        "checks": ["DAG/topological order", "required card fields", "file whitelist alignment",
                   "contract references", "JSON Schema", "positive/negative examples", "relative links",
                   "non-ignored documentation path", "formatting", "critical gate dependencies",
                   "stage coverage and dependency order", "stage scope unions"],
        "business_repairs_executed_by_this_validator": False,
        "implementation_tests_run_by_this_validator": False,
        "limitations": ["This validates the plan, not application behavior or completed repair evidence."],
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--write-report", action="store_true", help="Write planning-only validation report.")
    args = parser.parse_args()
    result = validate()
    payload = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.write_report:
        (Path(__file__).resolve().parent / "PACKAGE_VALIDATION.json").write_text(payload, encoding="utf-8")
    print(payload, end="")
