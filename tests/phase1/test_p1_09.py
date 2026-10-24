"""P1-09 行为测试：原子 JSON 写数组并拒绝非标准数字（C01）。

覆盖卡的五个必证场景，每个都有正例与独立反例：

* 数组与对象都能成功写入，中文往返正确；
* 序列化失败（``TypeError`` / ``RuntimeError``）时目标旧字节不变、无临时垃圾；
* ``fsync`` 故障发生在 replace **之前**：旧字节不变、无临时垃圾、异常上抛；
* ``replace`` 故障：旧字节不变、无临时垃圾；
* ``NaN`` / ``Infinity`` 被拒绝，原文件字节保持。

另外断言 replace **之后**再抛错时新字节已经生效——不把"替换已成功后抛错"误写成
"文件仍应是旧字节"。
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from deeptutor.services import file_io
from deeptutor.services.file_io import JSONDocument, atomic_write_json, atomic_write_text

CHINESE_OBJECT: JSONDocument = {"greeting": "你好", "nested": {"列表": [1, 2, 3]}}
CHINESE_ARRAY: JSONDocument = [
    {"id": "复变函数", "term": "2026春"},
    {"id": "常微分方程", "term": ""},
]


def _only_entries(directory: Path) -> list[str]:
    return sorted(p.name for p in directory.iterdir())


# ---------------------------------------------------------------------------
# 正向：对象与数组
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("payload", [CHINESE_OBJECT, CHINESE_ARRAY])
def test_object_and_array_round_trip_with_chinese(tmp_path: Path, payload) -> None:
    target = tmp_path / "data.json"

    atomic_write_json(target, payload)

    assert json.loads(target.read_text(encoding="utf-8")) == payload
    prefix = "[\n" if isinstance(payload, list) else "{\n"
    assert target.read_text(encoding="utf-8").startswith(prefix)
    assert _only_entries(tmp_path) == ["data.json"]


def test_array_write_replaces_a_previous_object_and_vice_versa(tmp_path: Path) -> None:
    target = tmp_path / "index.json"

    atomic_write_json(target, {"old": True})
    atomic_write_json(target, CHINESE_ARRAY)
    assert json.loads(target.read_text(encoding="utf-8")) == CHINESE_ARRAY

    atomic_write_json(target, {"new": True})
    assert json.loads(target.read_text(encoding="utf-8")) == {"new": True}
    assert _only_entries(tmp_path) == ["index.json"]


def test_unicode_is_written_verbatim_not_escaped(tmp_path: Path) -> None:
    target = tmp_path / "kb.json"

    atomic_write_json(target, ["概率论", "离散数学"])

    raw = target.read_text(encoding="utf-8")
    assert "概率论" in raw and "\\u" not in raw


# ---------------------------------------------------------------------------
# 反向：序列化失败
# ---------------------------------------------------------------------------
def test_serialization_failure_keeps_old_bytes_and_leaves_no_temp(tmp_path: Path) -> None:
    target = tmp_path / "metadata.json"
    original = b'{"ok": true}\n'
    target.write_bytes(original)

    with pytest.raises(TypeError):
        atomic_write_json(target, {"bad": object()})

    assert target.read_bytes() == original
    assert _only_entries(tmp_path) == ["metadata.json"]


def test_injected_dump_failure_keeps_old_bytes_and_leaves_no_temp(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "metadata.json"
    original = b'["old"]\n'
    target.write_bytes(original)

    def fail_dump(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("serialization failed")

    monkeypatch.setattr(file_io.json, "dump", fail_dump)

    with pytest.raises(RuntimeError, match="serialization failed"):
        atomic_write_json(target, CHINESE_ARRAY)

    assert target.read_bytes() == original
    assert _only_entries(tmp_path) == ["metadata.json"]


def test_write_into_a_new_directory_still_cleans_up_on_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "nested" / "settings.json"

    def fail_dump(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("serialization failed")

    monkeypatch.setattr(file_io.json, "dump", fail_dump)

    with pytest.raises(RuntimeError):
        atomic_write_json(target, {"value": 1})

    assert _only_entries(target.parent) == []


# ---------------------------------------------------------------------------
# 反向：fsync / replace 故障点
# ---------------------------------------------------------------------------
def test_fsync_failure_before_replace_keeps_old_bytes_and_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """fsync 在 replace **之前**失败：不能吞掉，旧字节必须保持。"""
    target = tmp_path / "metadata.json"
    original = b'{"version": 1}\n'
    target.write_bytes(original)

    def fail_fsync(_fd: int) -> None:
        raise OSError(5, "Input/output error")

    monkeypatch.setattr(file_io.os, "fsync", fail_fsync)

    with pytest.raises(OSError, match="Input/output error"):
        atomic_write_json(target, {"version": 2})

    assert target.read_bytes() == original
    assert _only_entries(tmp_path) == ["metadata.json"]


def test_replace_failure_keeps_old_bytes_and_leaves_no_temp(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "metadata.json"
    original = b'{"version": 1}\n'
    target.write_bytes(original)

    def fail_replace(self, _target):  # type: ignore[no-untyped-def]
        raise OSError(18, "Invalid cross-device link")

    monkeypatch.setattr(Path, "replace", fail_replace)

    with pytest.raises(OSError, match="Invalid cross-device link"):
        atomic_write_json(target, {"version": 2})

    assert target.read_bytes() == original
    assert _only_entries(tmp_path) == ["metadata.json"]


def test_failure_after_a_successful_replace_has_already_published_new_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """对照：替换**已经成功**之后再抛错，文件就是新字节——不能写成旧字节。"""
    target = tmp_path / "metadata.json"
    target.write_bytes(b'{"version": 1}\n')
    real_replace = Path.replace

    def replace_then_fail(self, new_path):  # type: ignore[no-untyped-def]
        real_replace(self, new_path)
        raise RuntimeError("post-replace bookkeeping failure")

    monkeypatch.setattr(Path, "replace", replace_then_fail)

    with pytest.raises(RuntimeError, match="post-replace bookkeeping failure"):
        atomic_write_json(target, {"version": 2})

    assert json.loads(target.read_text(encoding="utf-8")) == {"version": 2}
    assert _only_entries(tmp_path) == ["metadata.json"]


# ---------------------------------------------------------------------------
# 反向：非标准 JSON 数字
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "payload",
    [
        {"mastery": float("nan")},
        {"mastery": float("inf")},
        {"mastery": float("-inf")},
        [{"mastery": float("nan")}],
    ],
)
def test_nan_and_infinity_are_rejected_and_old_bytes_survive(
    tmp_path: Path, payload: JSONDocument
) -> None:
    target = tmp_path / "knowledge_points.json"
    original = b'[{"mastery": 0.8}]\n'
    target.write_bytes(original)

    with pytest.raises(ValueError):
        atomic_write_json(target, payload)

    assert target.read_bytes() == original
    assert _only_entries(tmp_path) == ["knowledge_points.json"]


def test_finite_floats_are_still_accepted(tmp_path: Path) -> None:
    target = tmp_path / "mastery.json"

    atomic_write_json(target, {"mastery": 0.8, "count": 3})

    assert json.loads(target.read_text(encoding="utf-8")) == {"mastery": 0.8, "count": 3}
    assert math.isfinite(json.loads(target.read_text(encoding="utf-8"))["mastery"])


# ---------------------------------------------------------------------------
# 既有行为：text 写入不受影响
# ---------------------------------------------------------------------------
def test_atomic_write_text_behaviour_is_unchanged(tmp_path: Path) -> None:
    target = tmp_path / "note.md"

    atomic_write_text(target, "第一版")
    atomic_write_text(target, "第二版")

    assert target.read_text(encoding="utf-8") == "第二版"
    assert _only_entries(tmp_path) == ["note.md"]
