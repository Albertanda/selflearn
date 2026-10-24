"""P1-15 行为测试：PATCH 的缺省与清空语义（C03）。

目标：只修改用户实际提交的字段 —— 未提交保留原值、显式空字符串明确清空、空 PATCH
不写注册表。

关键点：FastAPI 会把**显式提交的空字符串**也解析成 ``None``（``Form(None)``），所以
单看参数 ``is not None`` 无法区分"没提交"和"提交了空值"。附包里的独立实测
（``.phase1-evidence/reviews/S03-final/probe_patch_form.py``）已经证明这一点；本文件全部
用例都通过**真实 HTTP 表单**发送，并同时检查保留字段的值与 ``index.json`` 的字节，
不靠直接调用 Python 函数传 ``""``。

覆盖的必证场景：

* 只提交 description → term 保留；只提交 term → description 保留；
* 显式 ``description=""`` / ``term=""`` → 明确清空，另一个字段不动；
* multipart 形式的空字段同样清空；
* 空 PATCH → 返回当前 subject，``index.json`` 字节完全不变；
* 把文件当字符串提交 → 原样保留 FastAPI 的 422，且不写任何东西；
* 未知科目 404；响应形状满足 SubjectRecord schema。

最后一个用例是**有效坏对照**：旧实现的 ``description or ""`` / ``term or ""`` 在只提交
一个字段时会把另一个字段清空，证明上面的"保留"断言承重。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from deeptutor.subjects import store
from tests.phase1 import helpers

REPO_ROOT = Path(__file__).resolve().parents[2]
ROUTE_PREFIX = helpers.ROUTE_PREFIX


def _schema(name: str) -> dict:
    doc = json.loads((REPO_ROOT / "plans" / "phase1" / "schemas.json").read_text(encoding="utf-8"))
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$ref": f"#/$defs/{name}",
        "$defs": doc["$defs"],
    }


def _index_path(admin_root: Path) -> Path:
    return helpers.learning_root(admin_root) / "index.json"


def _record(admin_root: Path, subject_id: str) -> dict:
    records = json.loads(_index_path(admin_root).read_text(encoding="utf-8"))
    return next(r for r in records if r["id"] == subject_id)


def _patch(client, subject_id: str, **kwargs):
    return client.patch(f"{ROUTE_PREFIX}/{subject_id}", **kwargs)


# ---------------------------------------------------------------------------
# 只提交一个字段：另一个必须保留
# ---------------------------------------------------------------------------
def test_patching_only_description_keeps_the_term(p1_subjects, p1_route_client):
    from jsonschema import validate

    subject = p1_subjects["科目A"]
    before = _record(subject.admin_root, subject.subject_id)
    assert before["term"] == "2026春"
    assert before["description"] == ""

    response = _patch(p1_route_client, subject.subject_id, data={"description": "只改描述"})

    assert response.status_code == 200
    body = response.json()
    validate(instance=body["subject"], schema=_schema("SubjectRecord"))
    assert body["subject"]["description"] == "只改描述"
    assert body["subject"]["term"] == "2026春"
    stored = _record(subject.admin_root, subject.subject_id)
    assert stored["description"] == "只改描述"
    assert stored["term"] == "2026春"
    # 其它字段（名称/创建时间/未知历史字段）逐字段不变
    for key in ("id", "name", "created_at", "marker"):
        assert stored[key] == before[key]


def test_patching_only_term_keeps_the_description(p1_subjects, p1_route_client):
    subject = p1_subjects["科目A"]
    seed = _patch(p1_route_client, subject.subject_id, data={"description": "原有描述"})
    assert seed.status_code == 200

    response = _patch(p1_route_client, subject.subject_id, data={"term": "2027春"})

    assert response.status_code == 200
    body = response.json()
    assert body["subject"]["term"] == "2027春"
    assert body["subject"]["description"] == "原有描述"
    stored = _record(subject.admin_root, subject.subject_id)
    assert stored["description"] == "原有描述"
    assert stored["term"] == "2027春"


# ---------------------------------------------------------------------------
# 显式空字符串：明确清空
# ---------------------------------------------------------------------------
def test_an_explicit_empty_description_clears_it_and_keeps_the_term(p1_subjects, p1_route_client):
    subject = p1_subjects["科目A"]
    _patch(p1_route_client, subject.subject_id, data={"description": "先写上"})

    response = _patch(p1_route_client, subject.subject_id, data={"description": ""})

    assert response.status_code == 200
    body = response.json()
    assert body["subject"]["description"] == ""
    assert body["subject"]["term"] == "2026春"
    stored = _record(subject.admin_root, subject.subject_id)
    assert stored["description"] == ""
    assert stored["term"] == "2026春"


def test_an_explicit_empty_term_clears_it_and_keeps_the_description(p1_subjects, p1_route_client):
    subject = p1_subjects["科目A"]
    _patch(p1_route_client, subject.subject_id, data={"description": "保留我"})

    response = _patch(p1_route_client, subject.subject_id, data={"term": ""})

    assert response.status_code == 200
    body = response.json()
    assert body["subject"]["term"] == ""
    assert body["subject"]["description"] == "保留我"
    stored = _record(subject.admin_root, subject.subject_id)
    assert stored["term"] == ""
    assert stored["description"] == "保留我"


def test_both_fields_can_be_cleared_in_one_request(p1_subjects, p1_route_client):
    subject = p1_subjects["科目A"]
    _patch(p1_route_client, subject.subject_id, data={"description": "d", "term": "t"})

    response = _patch(p1_route_client, subject.subject_id, data={"description": "", "term": ""})

    assert response.status_code == 200
    assert response.json()["subject"]["description"] == ""
    assert response.json()["subject"]["term"] == ""


def test_a_multipart_empty_field_also_clears(p1_subjects, p1_route_client):
    """multipart 表单里的空字段同样必须被识别为"提交了空值"。"""
    subject = p1_subjects["科目B"]
    _patch(p1_route_client, subject.subject_id, data={"description": "multipart 前"})

    response = _patch(
        p1_route_client,
        subject.subject_id,
        data={"description": ""},
        files={"unused": ("u.txt", b"z")},
    )

    assert response.status_code == 200
    assert response.json()["subject"]["description"] == ""
    assert response.json()["subject"]["term"] == "2026春"
    assert _record(subject.admin_root, subject.subject_id)["description"] == ""


def test_a_multipart_field_with_a_value_is_applied(p1_subjects, p1_route_client):
    subject = p1_subjects["科目B"]

    response = _patch(
        p1_route_client,
        subject.subject_id,
        data={"term": "2028春"},
        files={"unused": ("u.txt", b"z")},
    )

    assert response.status_code == 200
    assert response.json()["subject"]["term"] == "2028春"


# ---------------------------------------------------------------------------
# 空 PATCH：不写注册表
# ---------------------------------------------------------------------------
def test_an_empty_patch_returns_the_current_subject_without_writing(p1_subjects, p1_route_client):
    subject = p1_subjects["科目A"]
    index = _index_path(subject.admin_root)
    before_bytes = index.read_bytes()
    before_record = _record(subject.admin_root, subject.subject_id)

    response = _patch(p1_route_client, subject.subject_id, data={})

    assert response.status_code == 200
    assert response.json()["subject"] == before_record
    assert index.read_bytes() == before_bytes  # 一个字节都没写


def test_a_multipart_patch_without_the_two_fields_does_not_write(p1_subjects, p1_route_client):
    subject = p1_subjects["科目B"]
    index = _index_path(subject.admin_root)
    before_bytes = index.read_bytes()

    response = _patch(
        p1_route_client, subject.subject_id, files={"unused": ("u.txt", b"z")}
    )

    assert response.status_code == 200
    assert index.read_bytes() == before_bytes


def test_an_empty_patch_after_a_real_change_is_still_read_only(p1_subjects, p1_route_client):
    subject = p1_subjects["科目A"]
    _patch(p1_route_client, subject.subject_id, data={"description": "一次真实修改"})
    index = _index_path(subject.admin_root)
    before_bytes = index.read_bytes()

    response = _patch(p1_route_client, subject.subject_id, data={})

    assert response.status_code == 200
    assert response.json()["subject"]["description"] == "一次真实修改"
    assert index.read_bytes() == before_bytes


# ---------------------------------------------------------------------------
# 原生校验与错误语义
# ---------------------------------------------------------------------------
def test_a_file_part_where_a_string_is_expected_keeps_the_native_422(p1_subjects, p1_route_client):
    subject = p1_subjects["科目A"]
    index = _index_path(subject.admin_root)
    before_bytes = index.read_bytes()

    response = _patch(
        p1_route_client, subject.subject_id, files={"description": ("d.txt", b"z")}
    )

    assert response.status_code == 422
    assert index.read_bytes() == before_bytes


def test_an_unknown_subject_is_404_and_writes_nothing(p1_subjects, p1_route_client):
    index = _index_path(p1_subjects["_admin_root"])
    before_bytes = index.read_bytes()

    response = _patch(p1_route_client, "不存在的科目", data={"description": "x"})

    assert response.status_code == 404
    assert index.read_bytes() == before_bytes


def test_the_patch_response_only_carries_the_subject(p1_subjects, p1_route_client):
    from jsonschema import validate

    subject = p1_subjects["科目A"]

    response = _patch(p1_route_client, subject.subject_id, data={"description": "形状"})

    assert set(response.json()) == {"subject"}
    validate(instance=response.json()["subject"], schema=_schema("SubjectRecord"))


def test_patching_does_not_change_the_subject_id_or_create_a_tree(p1_subjects, p1_route_client):
    subject = p1_subjects["科目A"]
    before_tree = helpers.tree_digest(subject.root)

    response = _patch(p1_route_client, subject.subject_id, data={"description": "只改注册表"})

    assert response.status_code == 200
    assert response.json()["subject"]["id"] == subject.subject_id
    assert helpers.tree_digest(subject.root) == before_tree


def test_an_unknown_form_field_is_ignored_and_does_not_write(p1_subjects, p1_route_client):
    """改名不在本阶段范围：多余的 name 字段既不生效也不触发写入。"""
    subject = p1_subjects["科目A"]
    index = _index_path(subject.admin_root)
    before_bytes = index.read_bytes()
    before_name = _record(subject.admin_root, subject.subject_id)["name"]

    response = _patch(p1_route_client, subject.subject_id, data={"name": "偷偷改名"})

    assert response.status_code == 200
    assert response.json()["subject"]["name"] == before_name
    assert index.read_bytes() == before_bytes


def test_repeating_the_same_value_keeps_everything_else_intact(p1_subjects, p1_route_client):
    subject = p1_subjects["科目A"]
    first = _patch(p1_route_client, subject.subject_id, data={"description": "同一个值"}).json()

    second = _patch(p1_route_client, subject.subject_id, data={"description": "同一个值"}).json()

    assert second["subject"] == first["subject"]
    assert second["subject"]["term"] == "2026春"


def test_a_whitespace_only_value_follows_the_store_trim_policy(p1_subjects, p1_route_client):
    """store 既有策略：文本先 trim 再存，因此纯空白等于清空（不是参数错误）。"""
    subject = p1_subjects["科目A"]
    _patch(p1_route_client, subject.subject_id, data={"description": "先写上"})

    response = _patch(p1_route_client, subject.subject_id, data={"description": "   "})

    assert response.status_code == 200
    assert response.json()["subject"]["description"] == ""
    assert response.json()["subject"]["term"] == "2026春"


# ---------------------------------------------------------------------------
# 有效坏对照：旧表达式会清空未提交字段
# ---------------------------------------------------------------------------
def test_bad_control_the_old_or_empty_expression_wiped_the_other_field(p1_runtime: Path):
    """坏对照：旧实现的 ``description or ""``/``term or ""`` 清空未提交字段。

    旧代码把 FastAPI 解析结果（显式空串也会是 ``None``）直接做 ``or ""`` 后**两个字段
    都**传给 store，因此"只改描述"的请求会把 term 一起抹掉。
    """
    legacy_id = store.create_subject("坏对照科目", description="原描述", term="2026春")["id"]
    fixed_id = store.create_subject("修正科目", description="原描述", term="2026春")["id"]

    # 旧行为：只提交 description，参数解析结果是 (description="新描述", term=None)，
    # 但旧代码把两个结果都下了 `or ""`。
    store.update_subject(legacy_id, description=("新描述" or ""), term=(None or ""))
    legacy = store.get_subject(legacy_id)
    assert legacy["description"] == "新描述"
    assert legacy["term"] == ""  # term 被误清空 —— 这正是本卡要修的行为

    # 新行为：只把实际提交的字段传下去
    store.update_subject(fixed_id, description="新描述")
    fixed = store.get_subject(fixed_id)
    assert fixed["description"] == "新描述"
    assert fixed["term"] == "2026春"  # 保留原值
