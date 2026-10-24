"""P1-02 行为测试：固定凭证时间夹具的冻结时钟与过期边界。

背景（卡的"已有问题证据"）：``tests/services/test_codebuddy_credentials.py`` 里的
``expiresAt=1791055241000``（= 2026-10-04）早已过期，于是 ``is_expired() is False``
断言在真实时钟下必然失败。修法是把测试时钟冻结到固定时刻，而不是改生产逻辑或把
日期改到远未来。

本文件覆盖卡要求的三个场景，并给出两条反向证明：

* 夹具时刻之前未过期 / 恰好到 ``expires_at - skew`` 即过期 / 结论与真实日期无关；
* **反向 1**：不冻结模块时钟时，结论由**受控注入**的标准库 ``time.time`` 决定
  （取值相对夹具常量计算，任何真实年份结果相同）；
* **反向 2**：把标准库 ``time.time`` 设成两个极端值，冻结下的结论都不变 ——
  证明真实时钟根本没有被读取（若生产代码偷读真实时钟，这两条会失败）。

全部断言都以夹具常量（``expiresAt`` = 2026-10-04）为基准，**不读取今天**，也不设
skip/xfail。
"""

from __future__ import annotations

import json
from pathlib import Path
import time

import pytest

from deeptutor.services.codebuddy_credentials import CodeBuddyCredentials, load_credentials
from tests.phase1 import helpers

MODULE = "deeptutor.services.codebuddy_credentials"

EXPIRES_AT_MS = 1791055241000
REFRESH_EXPIRES_AT_MS = 1793647241000
EXPIRES_AT = 1791055241.0
REFRESH_EXPIRES_AT = 1793647241.0
SKEW = 300.0
#: ``is_expired()`` 翻转的确切时刻：now >= expires_at - skew
BOUNDARY = EXPIRES_AT - SKEW

#: 固定"现在"：远早于边界，且与真实当前日期无关。
FIXTURE_NOW = 1791000000.0

WALL_CLOCK_1980 = 315532800.0
WALL_CLOCK_2100 = 4102444800.0


def _write_auth_file(tmp_path: Path, monkeypatch, **overrides) -> Path:
    auth = {
        "accessToken": "access-token",
        "refreshToken": "refresh-token",
        "tokenType": "Bearer",
        "expiresAt": EXPIRES_AT_MS,
        "refreshExpiresAt": REFRESH_EXPIRES_AT_MS,
        "domain": "www.codebuddy.cn",
    }
    auth.update(overrides)
    path = Path(tmp_path) / "Tencent-Cloud.coding-copilot.info"
    path.write_text(
        json.dumps({"account": {"uid": "uid-1", "nickname": "tester"}, "auth": auth}),
        encoding="utf-8",
    )
    monkeypatch.setenv("DEEPTUTOR_CODEBUDDY_AUTH_FILE", str(path))
    return path


@pytest.fixture
def credentials(tmp_path, monkeypatch):
    """在冻结时钟下从固定 auth 文件读出的凭证对象。"""
    _write_auth_file(tmp_path, monkeypatch)
    with helpers.frozen_time(MODULE, FIXTURE_NOW):
        loaded = load_credentials()
    assert loaded is not None
    return loaded


# ---------------------------------------------------------------------------
# 正向：毫秒解析与边界
# ---------------------------------------------------------------------------
def test_millisecond_values_are_parsed_as_seconds(credentials):
    """保留原有的毫秒→秒解析断言。"""
    assert credentials.expires_at == pytest.approx(EXPIRES_AT)
    assert credentials.refresh_expires_at == pytest.approx(REFRESH_EXPIRES_AT)
    assert credentials.expires_at == pytest.approx(EXPIRES_AT_MS / 1000.0)


def test_not_expired_before_the_skew_boundary(credentials):
    with helpers.frozen_time(MODULE, BOUNDARY - 1.0):
        assert credentials.is_expired() is False
    with helpers.frozen_time(MODULE, FIXTURE_NOW):
        assert credentials.is_expired() is False


def test_expired_exactly_at_the_skew_boundary(credentials):
    with helpers.frozen_time(MODULE, BOUNDARY):
        assert credentials.is_expired() is True


def test_expired_after_the_boundary_and_at_expiry(credentials):
    for now in (BOUNDARY + 1.0, EXPIRES_AT - 1.0, EXPIRES_AT, EXPIRES_AT + 86_400.0):
        with helpers.frozen_time(MODULE, now):
            assert credentials.is_expired() is True, now


def test_the_skew_argument_decides_the_verdict(credentials):
    """同一个冻结时刻，结论只由 skew 决定。"""
    now = EXPIRES_AT - 100.0
    with helpers.frozen_time(MODULE, now):
        assert credentials.is_expired(skew=0.0) is False
        assert credentials.is_expired(skew=99.0) is False
        assert credentials.is_expired(skew=100.0) is True
        assert credentials.is_expired(skew=SKEW) is True


def test_refresh_expiry_uses_the_frozen_clock_too(credentials):
    with helpers.frozen_time(MODULE, FIXTURE_NOW):
        assert credentials.can_refresh() is True
    with helpers.frozen_time(MODULE, REFRESH_EXPIRES_AT):
        assert credentials.can_refresh() is False


# ---------------------------------------------------------------------------
# 反向 1：未冻结的模块时钟由注入的 time.time 控制（不依赖真实日期）
# ---------------------------------------------------------------------------
def test_unfrozen_module_clock_is_driven_by_the_injected_stdlib_time(
    tmp_path, monkeypatch
):
    """坏对照：不冻结模块时钟时，结论由**受控注入**的 ``time.time`` 决定。

    这里 monkeypatch 的是标准库 ``time.time``（生产模块在未冻结时用的就是它），
    取值是相对夹具 ``expiresAt`` 计算出来的常量，因此任何真实当前年份都得到同一结果：
    注入到 boundary 之后 -> 过期；注入到 boundary 之前 -> 未过期。
    """
    _write_auth_file(tmp_path, monkeypatch)
    loaded = load_credentials()
    assert loaded is not None

    monkeypatch.setattr(time, "time", lambda: BOUNDARY - 1.0)
    assert loaded.is_expired() is False
    assert loaded.can_refresh() is True

    monkeypatch.setattr(time, "time", lambda: BOUNDARY)
    assert loaded.is_expired() is True

    monkeypatch.setattr(time, "time", lambda: EXPIRES_AT + 86_400.0)
    assert loaded.is_expired() is True


def test_credential_suite_is_independent_of_the_real_current_date(monkeypatch):
    """两个受控"外部日期"下，**冻结后**的整组过期语义断言必须给出相同结论。

    注意这里控制的是标准库时间，而不是把日期推到远未来来逃避验证；
    夹具的 ``expiresAt`` 常量本身保持 2026-10-04 不变。
    """
    credentials = CodeBuddyCredentials(
        access_token="fixture",
        refresh_token="fixture-refresh",
        expires_at=EXPIRES_AT,
        refresh_expires_at=REFRESH_EXPIRES_AT,
    )
    verdicts = []
    for injected in (WALL_CLOCK_1980, WALL_CLOCK_2100):
        monkeypatch.setattr(time, "time", lambda injected=injected: injected)
        with helpers.frozen_time(MODULE, FIXTURE_NOW):
            verdicts.append(
                (
                    credentials.is_expired(),
                    credentials.is_expired(skew=0.0),
                    credentials.can_refresh(),
                )
            )
        with helpers.frozen_time(MODULE, BOUNDARY):
            verdicts.append((credentials.is_expired(),))
    assert verdicts[0] == verdicts[2], verdicts
    assert verdicts[1] == verdicts[3], verdicts
    # 冻结在夹具时刻 -> 未过期；冻结在 boundary -> 过期。与外部日期无关。
    assert verdicts[0] == (False, False, True)
    assert verdicts[1] == (True,)


# ---------------------------------------------------------------------------
# 反向 2：结论与真实日期无关
# ---------------------------------------------------------------------------
def test_verdict_ignores_the_real_wall_clock(credentials, monkeypatch):
    """把标准库 ``time.time`` 设成 1980 / 2100，冻结下的结论必须不变。

    若生产代码某处偷读真实时钟，2100 那一轮会判为已过期、1980 那一轮会判为未过期，
    与冻结值矛盾，断言即失败。
    """
    monkeypatch.setattr(time, "time", lambda: WALL_CLOCK_2100)
    with helpers.frozen_time(MODULE, FIXTURE_NOW):
        assert credentials.is_expired() is False
        assert credentials.can_refresh() is True

    monkeypatch.setattr(time, "time", lambda: WALL_CLOCK_1980)
    with helpers.frozen_time(MODULE, BOUNDARY):
        assert credentials.is_expired() is True

    monkeypatch.setattr(time, "time", lambda: WALL_CLOCK_2100)
    with helpers.frozen_time(MODULE, BOUNDARY - 1.0):
        assert credentials.is_expired() is False


def test_frozen_clock_is_restored_after_use(credentials):
    import deeptutor.services.codebuddy_credentials as creds_module

    real_clock = creds_module.time
    with helpers.frozen_time(MODULE, FIXTURE_NOW):
        assert creds_module.time is not real_clock
        assert creds_module.time.time() == FIXTURE_NOW
    assert creds_module.time is real_clock, "frozen clock leaked out of the context"
