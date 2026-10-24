"""P1-31 行为测试：报告输入、严格 code 对象与无默认 ODE 提示词。

目标：普通统计图不再被默认微分方程污染；任何将进入执行器的表达式/代码对象
**先**通过固定输入契约（AST 白名单 + C04 严格 JSON），失败不靠贪婪正则或
"补半截 JSON"掩盖。

必证场景（对应卡片清单与 START_S08 第二节 P1-31 的"证据"）：

* 无 ODE 的图表提示词不含默认 ``f``、不含 ``x**2-y``、没有"必须遵守 ODE"段；
* 合法 ``x**2-y``/``sin(x)-y`` 被接受，仅改变一个语法节点的反例逐一被拒绝；
* 模型 code 必须是"唯一 JSON 对象里的非空字符串"：类型/空白/半 JSON/多对象失败；
* 0/1/8/9 张占位图的边界（9 → ``invalid_input``），零空格与多空格同一 match；
* 表达式拒绝发生在**调用 provider / 执行器之前**（用替身记录调用次序）；
* 纯输入函数无文件/网络副作用；生成服务的预算/截断边界不被绕过。
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from deeptutor.services.pdf import report as report_mod
from deeptutor.services.pdf import report_inputs as ri
from deeptutor.subjects import json_store
from deeptutor.subjects.errors import ErrorCode, SubjectOperationError
from deeptutor.subjects.model_output import ModelOutputError, parse_model_object
from tests.phase1 import helpers

# ---------------------------------------------------------------------------
# 提示词：没有 ODE 就没有方程
# ---------------------------------------------------------------------------
ODE_MARKERS = ("x**2", "x ** 2", "f(x, y)", "def f(", "微分方程", "必须严格遵守", "ode_rhs")


def test_plain_chart_prompt_carries_no_default_equation() -> None:
    prompt = ri.build_chart_code_prompt("画出各分数段人数柱状图", out_path="chart_1.png")

    assert "画出各分数段人数柱状图" in prompt
    assert "plt.savefig('chart_1.png'" in prompt
    assert '{"code"' in prompt
    for marker in ODE_MARKERS:
        assert marker not in prompt, f"普通图提示词仍出现 ODE 痕迹：{marker}"


def test_legacy_prompt_name_is_the_plain_template() -> None:
    """旧名字保留，但内容必须是"不含默认方程"的模板。"""
    assert report_mod.CHART_CODE_PROMPT == ri.PLAIN_CHART_CODE_PROMPT
    for marker in ODE_MARKERS:
        assert marker not in report_mod.CHART_CODE_PROMPT


def test_ode_prompt_inserts_the_verified_original_expression() -> None:
    prompt = ri.build_chart_code_prompt(
        "画方向场", out_path="chart_2.png", ode_rhs="  sin(x) - y  "
    )

    assert "f(x, y) = sin(x) - y" in prompt
    assert "def f(x, y): return sin(x) - y" in prompt
    assert "sin(x)  -  y" not in prompt  # 原样插入，不被改写
    assert "plt.savefig('chart_2.png'" in prompt


def test_blank_ode_is_no_ode_not_an_empty_equation() -> None:
    for blank in ("", "   ", "\n\t "):
        assert ri.validate_ode_expression(blank) == ""
        prompt = ri.build_chart_code_prompt("普通图", out_path="chart_1.png", ode_rhs=blank)
        assert "微分方程" not in prompt
        assert "f(x, y) =" not in prompt


def test_out_path_must_be_a_server_allocated_basename() -> None:
    for bad in ("../chart_1.png", "sub/chart_1.png", "", "  chart_1.png", "chart\\1.png", 7):
        with pytest.raises(json_store.InvalidInputError) as info:
            ri.build_chart_code_prompt("图", out_path=bad)
        assert info.value.code is ErrorCode.INVALID_INPUT


#: R1：固定图名是**完整匹配的真实文件名**，不是"合法的路径段"。
NON_SERVER_CHART_NAMES = [
    "chart_1.png\n",
    "chart_1.png ",
    " chart_1.png",
    "arbitrary.txt",
    "chart_1.exe",
    "chart_1",
    "chart_1.png');print('injected",
    'chart_1.png");print("injected',
    "chart_1.png\x00",
    "chart_1.png/../chart_2.png",
    "chart_0.png",
    "chart_9.png",
    "chart_10.png",
    "chart_1.PNG",
    "chart_1.png.png",
    "CHART_1.png",
    "chart_x.png",
    "../../etc/passwd",
    "/tmp/chart_1.png",
    "",
    7,
    None,
    b"chart_1.png",
]


@pytest.mark.parametrize("bad", NON_SERVER_CHART_NAMES)
def test_prompt_requires_exact_server_chart_basename(bad: object) -> None:
    """任何非 ``chart_1..8.png`` 的 out_path 都必须在提示词构造前被拒绝。"""
    with pytest.raises(json_store.InvalidInputError) as info:
        ri.build_chart_code_prompt("普通图", out_path=bad)

    assert info.value.code is ErrorCode.INVALID_INPUT
    # 拒绝信息不回显被拒文本（C02）。
    if isinstance(bad, str) and bad:
        assert bad not in info.value.detail


@pytest.mark.parametrize("good", ["chart_1.png", "chart_2.png", "chart_8.png"])
def test_server_chart_names_are_accepted_verbatim(good: str) -> None:
    assert ri.chart_target_basename(good) == good
    prompt = ri.build_chart_code_prompt("普通图", out_path=good)
    assert f"plt.savefig('{good}'" in prompt


def test_model_code_requires_utf8_encodable_text() -> None:
    """孤立 surrogate 能过 JSON 解析，却会在写脚本时炸成裸 UnicodeEncodeError。"""
    with pytest.raises(SubjectOperationError) as info:
        ri.parse_chart_code_response('{"code":"\\ud800"}')

    assert info.value.code is ErrorCode.INVALID_MODEL_OUTPUT
    assert info.value.http_status == 502
    assert "\\ud800" not in str(info.value)

    # 合法中文源码照常通过。
    chinese = "# 中文注释：画正弦曲线\nplt.plot([1, 2, 3])\n"
    assert ri.parse_chart_code_response(json.dumps({"code": chinese})) == chinese


def test_rejected_code_never_reaches_a_file_or_executor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R1 的负例必须发生在任何文件/执行器/provider 副作用之前。"""
    recorder = _Recorder()
    recorder.install(monkeypatch, [])

    with pytest.raises(json_store.InvalidInputError):
        ri.build_chart_code_prompt("图", out_path="arbitrary.txt")
    with pytest.raises(SubjectOperationError):
        ri.parse_chart_code_response('{"code":"\\ud800"}')

    assert recorder.prompts == []
    assert recorder.executed == []
    assert list(tmp_path.iterdir()) == []


def test_chart_description_bounds() -> None:
    with pytest.raises(json_store.InvalidInputError):
        ri.build_chart_code_prompt("   ", out_path="chart_1.png")
    with pytest.raises(json_store.InvalidInputError):
        ri.build_chart_code_prompt("x" * (ri.MAX_CHART_DESCRIPTION_CHARS + 1), out_path="chart_1.png")
    assert ri.build_chart_code_prompt("x" * ri.MAX_CHART_DESCRIPTION_CHARS, out_path="chart_1.png")


# ---------------------------------------------------------------------------
# ODE 表达式：AST 白名单
# ---------------------------------------------------------------------------
ACCEPTED_EXPRESSIONS = [
    "x**2 - y",
    "sin(x) - y",
    "cos(x) * y + exp(-x)",
    "-x + y",
    "+x - -y",
    "sqrt(abs(x)) + log(abs(y) + 1)",
    "1.5 * x ** 2 - 0.25",
    "x / (y + 2)",
    "abs(sin(x) - cos(y)) ** 2",
    "2",
    "x",
]


@pytest.mark.parametrize("expression", ACCEPTED_EXPRESSIONS)
def test_accepted_ode_expressions_are_returned_verbatim(expression: str) -> None:
    assert ri.validate_ode_expression(expression) == expression
    assert ri.validate_ode_expression(f"  {expression}  ") == expression


#: 每个反例只比上面的正例改变**一个**语法节点。
REJECTED_EXPRESSIONS = [
    "__import__('os').system('true')",  # 未知名字 + 属性
    "eval('x')",  # 未知名字
    "x.real",  # 属性
    "x[0]",  # 下标
    "lambda x: x",  # lambda
    "[i for i in x]",  # 推导式
    "{i for i in x}",  # 集合推导式
    "(i for i in x)",  # 生成器表达式
    "open('a')",  # 未知函数名
    "min(x, y)",  # 未列入白名单的调用
    "float('nan')",  # 白名单外调用
    "x if y else 1",  # IfExp
    "x and y",  # BoolOp
    "x < y",  # Compare
    "not x",  # UnaryOp Not
    "~x",  # UnaryOp Invert
    "True",  # bool 常量
    "False",  # bool 常量
    "None",  # None 常量
    "'text'",  # 字符串常量
    "b'bytes'",  # bytes 常量
    "1e400",  # 非有限常量（inf）
    "x @ y",  # 矩阵乘
    "x // y",  # 整除
    "x % y",  # 取模
    "x << y",  # 位运算
    "x | y",  # 位运算
    "x; y",  # 语句
    "import os",  # 语句
    "sin(x, y)",  # 参数个数
    "sin(x, y=1)",  # 关键字参数
    "sin(*x)",  # 星号参数
    "x.__class__",  # 双下划线属性
    "__builtins__",  # 双下划线名字
    "(y := x)",  # 赋值表达式
    "x**y**x**y if x else y",  # 组合
    "{}",  # 字典常量
    "[1, 2]",  # 列表常量
    "(1, 2)",  # 元组常量
    "f'{x}'",  # f-string
    "await x",  # await
]


@pytest.mark.parametrize("expression", REJECTED_EXPRESSIONS)
def test_single_node_mutations_are_rejected(expression: str) -> None:
    with pytest.raises(json_store.InvalidInputError) as info:
        ri.validate_ode_expression(expression)

    error = info.value
    assert error.code is ErrorCode.INVALID_INPUT
    assert error.http_status == 400
    # C02：对外只有表里的固定消息，被拒绝的表达式原文不出现在任何投影里。
    assert str(error) == "请求参数无效，请检查后重试。"
    assert error.message == "请求参数无效，请检查后重试。"
    assert expression not in error.message
    assert expression not in error.detail
    assert expression not in " ".join(str(arg) for arg in error.args)


def test_expression_input_type_and_length_limits() -> None:
    for bad in (None, 5, 1.5, ["x"], {"x": 1}, b"x"):
        with pytest.raises(json_store.InvalidInputError):
            ri.validate_ode_expression(bad)
    with pytest.raises(json_store.InvalidInputError):
        ri.validate_ode_expression("x+" * (ri.MAX_ODE_EXPRESSION_CHARS // 2))
    # 超长括号串在长度上限处就被拒绝，解析器不会看到病态输入。
    with pytest.raises(json_store.InvalidInputError):
        ri.validate_ode_expression("(" * 2000 + "x" + ")" * 2000)


def test_deeply_nested_but_legal_expression_is_bounded() -> None:
    """节点数上限只拒绝病态输入，不改变正常数学（平坦链不会被误判为嵌套）。"""
    legal = "+".join(["x"] * 40)
    assert ri.validate_ode_expression(legal) == legal
    nested = "sin(" * 20 + "x" + ")" * 20
    assert ri.validate_ode_expression(nested) == nested
    with pytest.raises(json_store.InvalidInputError):
        ri.validate_ode_expression("+" * 250 + "x")


# ---------------------------------------------------------------------------
# 占位图：同一 match 的识别与边界
# ---------------------------------------------------------------------------
def test_placeholder_counts_zero_one_eight_are_accepted() -> None:
    assert ri.chart_placeholder_specs("没有任何图") == ()
    assert ri.chart_placeholder_specs("前\n{CHART: 一张图}\n后") == ("一张图",)
    markdown = "\n".join(f"{{CHART: 图 {i}}}" for i in range(1, 9))
    assert ri.chart_placeholder_specs(markdown) == tuple(f"图 {i}" for i in range(1, 9))


def test_nine_placeholders_are_an_explicit_invalid_input() -> None:
    markdown = "\n".join(f"{{CHART: 图 {i}}}" for i in range(1, 10))
    with pytest.raises(json_store.InvalidInputError) as info:
        ri.chart_placeholder_specs(markdown)
    assert info.value.code is ErrorCode.INVALID_INPUT
    # 识别本身不做截断：九张就是九处。
    assert len(ri.find_chart_placeholders(markdown)) == 9


def test_spacing_variants_use_one_match_and_keep_the_raw_text() -> None:
    markdown = "{CHART:零空格}\n{CHART:   多空格   }\n{CHART:\n跨行\n}"
    placeholders = ri.validated_chart_placeholders(markdown)

    assert [p.spec for p in placeholders] == ["零空格", "多空格", "跨行"]
    assert [p.raw for p in placeholders] == [
        "{CHART:零空格}",
        "{CHART:   多空格   }",
        "{CHART:\n跨行\n}",
    ]
    # 用同一个 match 的原文替换：替换后不再残留任何占位符。
    rewritten = markdown
    for index, placeholder in enumerate(placeholders, start=1):
        rewritten = rewritten.replace(placeholder.raw, f"![chart {index}](chart_{index}.png)", 1)
    assert "{CHART" not in rewritten


def test_empty_placeholder_description_is_rejected() -> None:
    with pytest.raises(json_store.InvalidInputError):
        ri.validated_chart_placeholders("{CHART:   }")
    with pytest.raises(json_store.InvalidInputError):
        ri.chart_placeholder_specs(None)


# ---------------------------------------------------------------------------
# 模型 code 对象
# ---------------------------------------------------------------------------
CODE = "import matplotlib.pyplot as plt\nplt.savefig('chart_1.png')\n"


def test_code_object_positive_forms() -> None:
    assert ri.parse_chart_code_response(json.dumps({"code": CODE})) == CODE
    assert ri.parse_chart_code_response(f"```json\n{json.dumps({'code': CODE})}\n```") == CODE
    assert ri.parse_chart_code_response(f"<think>考虑一下</think>{json.dumps({'code': CODE})}") == CODE
    # 额外字段允许保留，只取 code。
    assert ri.parse_chart_code_response(json.dumps({"code": CODE, "note": "x"})) == CODE


BAD_CODE_PAYLOADS = [
    json.dumps({"code": 5}),
    json.dumps({"code": ["import this"]}),
    json.dumps({"code": {"text": "import this"}}),
    json.dumps({"code": None}),
    json.dumps({"code": True}),
    json.dumps({"code": "   \n\t "}),
    json.dumps({"note": "no code"}),
    '{"code": "import os"',  # 半截 JSON
    '{"code": "a"} {"code": "b"}',  # 两个对象
    '{"code": "a"} trailing text',  # 尾随内容
    '{"code": "a",}',  # 尾随逗号（不再自动修复）
    json.dumps([{"code": CODE}]),  # 顶层是数组
    json.dumps({"code": "a", "extra": float("nan")}),  # 非有限数字
]


@pytest.mark.parametrize("raw", BAD_CODE_PAYLOADS)
def test_bad_code_objects_are_rejected(raw: str) -> None:
    with pytest.raises(SubjectOperationError) as info:
        ri.parse_chart_code_response(raw)
    assert info.value.code is ErrorCode.INVALID_MODEL_OUTPUT
    assert info.value.http_status == 502
    assert str(info.value) == "模型返回的结果无法解析，请重试。"
    assert CODE not in repr(info.value)


def test_empty_response_maps_to_empty_model_output() -> None:
    for raw in ("", "   ", "<think>只有推理</think>"):
        with pytest.raises(SubjectOperationError) as info:
            ri.parse_chart_object(raw)
        assert info.value.code is ErrorCode.EMPTY_MODEL_OUTPUT
    with pytest.raises(SubjectOperationError) as info:
        ri.parse_chart_object(None)
    assert info.value.code is ErrorCode.EMPTY_MODEL_OUTPUT


def test_legacy_extract_json_no_longer_masks_failure() -> None:
    """旧 ``_extract_json`` 返回 ``{}`` 的路径必须变成显式失败。"""
    assert report_mod._extract_json(json.dumps({"code": "x"})) == {"code": "x"}
    for raw in ('{"code": "x"', '{"a": 1} {"b": 2}', "not json at all", ""):
        with pytest.raises(SubjectOperationError):
            report_mod._extract_json(raw)
    # 严格解析器本身仍然只认唯一对象。
    with pytest.raises(ModelOutputError):
        parse_model_object('{"a": 1} {"b": 2}')


# ---------------------------------------------------------------------------
# generate_report：拒绝顺序与端到端接缝
# ---------------------------------------------------------------------------
class _Recorder:
    """P1-35 seam: fake provider/executor, real store + real PDF bytes.

    The old recorder patched the retired host helpers and returned ``True`` from
    a renderer that wrote nothing.  The seams now are the accepted P34
    executor/validator and the trusted renderer; the fakes still produce
    *actual* PNG/PDF bytes so the publication gate is exercised for real.
    """

    def __init__(self) -> None:
        self.prompts: list[str] = []
        self.executed: list[str] = []
        self.ode_checks: list[str] = []
        self.renders = 0

    def install(self, monkeypatch: pytest.MonkeyPatch, responses: list[str]) -> None:
        from PIL import Image

        from deeptutor.services.pdf.chart_executor import ChartExecutionResult
        from deeptutor.subjects.errors import subject_error

        pending = list(responses)

        async def fake_llm(prompt: str, system: str) -> str:
            self.prompts.append(prompt)
            if not pending:
                raise AssertionError("模型替身被调用的次数超过预期")
            return pending.pop(0)

        async def fake_execute(code: str, *, run, expected_png: str, policy=None):
            self.executed.append(code)
            if code == "FAIL":
                raise subject_error(ErrorCode.CHART_FAILED)
            target = Path(run.workdir) / expected_png
            Image.new("RGB", (24, 24), (30, 120, 220)).save(target, format="PNG")
            return ChartExecutionResult(
                exit_code=0,
                timed_out=False,
                error="",
                mode="chart",
                status="ok",
                artifact={"name": expected_png, "size": target.stat().st_size, "sha256": "0" * 64},
            )

        def fake_validate(run, expected_png: object, *, policy=None) -> dict:
            import hashlib

            name = ri.chart_target_basename(expected_png)
            data = (Path(run.workdir) / name).read_bytes()
            return {
                "path": name,
                "size": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
                "role": "chart",
            }

        async def fake_ode(run, expression: object, *, policy=None) -> dict:
            self.ode_checks.append(str(expression))
            return {"status": "passed", "max_abs_error": 0.0, "points": 5}

        def fake_render(markdown: str, chart_names, out_path: Path, typst_bin: Path) -> bool:
            import pymupdf

            self.renders += 1
            document = pymupdf.open()
            page = document.new_page()
            page.insert_text((72, 72), "课程报告（测试）")
            for index, name in enumerate(chart_names):
                top = 96 + index * 140
                page.insert_image(
                    pymupdf.Rect(72, top, 260, top + 110),
                    filename=str(Path(out_path).parent / name),
                )
            document.save(str(out_path))
            document.close()
            return True

        monkeypatch.setattr(report_mod, "_llm", fake_llm)
        monkeypatch.setattr(report_mod.chart_executor, "execute_chart_code", fake_execute)
        monkeypatch.setattr(report_mod.chart_validation, "validate_chart_output", fake_validate)
        monkeypatch.setattr(report_mod.chart_validation, "check_ode_numeric", fake_ode)
        monkeypatch.setattr(report_mod, "_render_report_pdf", fake_render)


def _run_report(tmp_path: Path, **kwargs: object) -> dict:
    """Run the real pipeline in an isolated runtime with a registered subject."""
    with helpers.isolated_runtime(tmp_path / "runtime") as admin_root:
        subject = helpers.make_subject(admin_root, "报告科")
        return asyncio.run(
            report_mod.generate_report(
                subject.subject_id,
                title="标题",
                requirements="要求",
                **kwargs,  # type: ignore[arg-type]
            )
        )


def test_invalid_expression_is_rejected_before_any_provider_or_executor_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    recorder = _Recorder()
    recorder.install(monkeypatch, [])

    with pytest.raises(json_store.InvalidInputError):
        _run_report(tmp_path, ode_rhs="__import__('os')")

    assert recorder.prompts == []
    assert recorder.executed == []
    assert recorder.ode_checks == []
    assert recorder.renders == 0
    assert not (tmp_path / "reports").exists()


def test_nine_chart_placeholders_stop_before_chart_provider(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    body = "# 报告\n" + "\n".join(f"{{CHART: 图 {i}}}" for i in range(1, 10))
    recorder = _Recorder()
    recorder.install(monkeypatch, [body])

    with pytest.raises(json_store.InvalidInputError):
        _run_report(tmp_path)

    assert len(recorder.prompts) == 1  # 只生成了正文，没有为图调用模型
    assert recorder.executed == []


def test_bad_code_response_never_reaches_the_executor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """C11: a declared chart that cannot be produced fails the **whole** report.

    The old assertion expected a successful report with a text note; that was
    the fake success the card removes.  The rejected response still never
    reaches the executor, and no public report is created.
    """
    body = "# 报告\n{CHART: 柱状图}\n"
    recorder = _Recorder()
    recorder.install(monkeypatch, [body, *['{"code": [1, 2]}'] * 3])

    with pytest.raises(SubjectOperationError) as info:
        _run_report(tmp_path)

    assert info.value.code is ErrorCode.CHART_FAILED
    assert recorder.executed == []
    assert recorder.renders == 0


def test_no_ode_chart_prompt_and_validated_expression_plumbing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    body = "# 报告\n{CHART:方向场}\n"
    recorder = _Recorder()
    recorder.install(monkeypatch, [body, json.dumps({"code": CODE})])

    result = _run_report(tmp_path, ode_rhs="x**2 - y")

    chart_prompt = recorder.prompts[1]
    assert "x**2 - y" in chart_prompt
    assert recorder.executed == [CODE]
    assert recorder.ode_checks == ["x**2 - y"]  # 提示词与检查器拿到同一段已校验原文
    assert result["chart_count"] == 1
    assert "![chart 1](chart_1.png)" in result["markdown"]


def test_plain_chart_prompt_is_used_when_no_ode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    body = "# 报告\n{CHART:各分数段人数}\n"
    recorder = _Recorder()
    recorder.install(monkeypatch, [body, json.dumps({"code": CODE})])

    result = _run_report(tmp_path)

    chart_prompt = recorder.prompts[1]
    for marker in ODE_MARKERS:
        assert marker not in chart_prompt, f"无 ODE 却出现：{marker}"
    assert recorder.ode_checks == []  # 没有 ODE 就不做数值检查
    assert result["chart_count"] == 1


def test_zero_space_placeholder_is_recognised_and_replaced(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    body = "# 报告\n{CHART:零空格图}\n"
    recorder = _Recorder()
    recorder.install(monkeypatch, [body, json.dumps({"code": CODE})])

    result = _run_report(tmp_path)

    assert "零空格图" in recorder.prompts[1]
    assert "{CHART" not in result["markdown"]
    assert "![chart 1](chart_1.png)" in result["markdown"]


def test_truncated_generation_is_not_masked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """沿用生成服务的预算/截断边界：``_llm`` 抛出的截断错误必须原样传播。"""
    from deeptutor.subjects.errors import ErrorCode as _Code
    from deeptutor.subjects.errors import subject_error

    async def truncating_llm(prompt: str, system: str) -> str:
        raise subject_error(_Code.OUTPUT_TRUNCATED)

    monkeypatch.setattr(report_mod, "_llm", truncating_llm)

    with helpers.isolated_runtime(tmp_path / "runtime") as admin_root:
        subject = helpers.make_subject(admin_root, "报告科")
        with pytest.raises(SubjectOperationError) as info:
            asyncio.run(
                report_mod.generate_report(
                    subject.subject_id, title="t", requirements="r"
                )
            )
    assert info.value.code is _Code.OUTPUT_TRUNCATED


# ---------------------------------------------------------------------------
# 纯输入：无文件/网络副作用
# ---------------------------------------------------------------------------
def test_pure_input_helpers_have_no_filesystem_or_network_side_effects(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    work = tmp_path / "cwd"
    work.mkdir()
    monkeypatch.chdir(work)
    before = helpers.tree_digest(work)

    with helpers.block_external_network():
        assert ri.validate_ode_expression("sin(x) - y") == "sin(x) - y"
        ri.build_chart_code_prompt("图", out_path="chart_1.png", ode_rhs="x - y")
        ri.chart_placeholder_specs("{CHART: 一}")
        ri.parse_chart_code_response(json.dumps({"code": CODE}))
        with pytest.raises(json_store.InvalidInputError):
            ri.validate_ode_expression("__import__('os')")

    assert helpers.tree_digest(work) == before
    assert list(work.iterdir()) == []


def test_report_inputs_module_stays_pure() -> None:
    """输入模块不导入 provider / 执行器，也不在导入期建立任何东西。"""
    source = Path(ri.__file__).read_text(encoding="utf-8")
    for forbidden in (
        "import subprocess",
        "from deeptutor.services.llm",
        "chart_executor import",
        "import os",
        "os.environ",
    ):
        assert forbidden not in source, f"纯输入模块不应出现：{forbidden}"
    assert callable(ri.parse_chart_object)
