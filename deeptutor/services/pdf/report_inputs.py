"""报告流水线的**纯输入契约**（P1-31）。

这个模块是"任何将进入执行器的表达式/代码对象"的唯一入口，也是报告图表提示词
的唯一来源。它只做纯计算：不读文件、不联网、不调用 provider、不调用执行器，
因此可以在任何位置先于副作用运行——这正是本卡要固定的顺序。

三件事：

1. **ODE 表达式的 AST 白名单**（:func:`validate_ode_expression`）。仅允许
   ``x``/``y``、有限实数常量、二元 ``+ - * / **``、一元 ``+ -``，以及
   ``sin``/``cos``/``exp``/``log``/``sqrt``/``abs`` 六个名字的**单参数直接调用**。
   属性、下标、import、lambda、推导式、未知名字、双下划线、关键字参数一律拒绝。
   **绝不用宿主 ``eval`` 试算**模型/用户表达式——计算量属于受限 worker（P33）。
   校验通过的表达式原样返回，供提示词插入与隔离环境执行。

2. **图表占位符的统一识别**（:func:`find_chart_placeholders` /
   :func:`chart_placeholder_specs`）。最多 8 张，超过明确 ``invalid_input``；
   返回的 :class:`ChartPlaceholder` 同时带原文与描述，P35 用**同一个 match**
   做替换（零空格/多空格都支持），不需要第二套图表语言。

3. **模型图表响应的严格解析**（:func:`parse_chart_object` /
   :func:`parse_chart_code_response`）。复用 C04 已验收的
   :func:`deeptutor.subjects.model_output.parse_model_object`：唯一对象、拒绝截断
   JSON、拒绝尾随内容、拒绝非有限数字。不贪婪抠 JSON、不自动补半截 JSON、
   失败不返回空 ``dict`` 掩盖问题；``code`` 必须是非空**字符串**。

C02：本模块抛出的错误一律是表里的固定投影，被拒绝的输入原文只留在服务端
``cause``/``detail`` 诊断里，不进入对外 message。
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
import math
import re

from deeptutor.subjects import json_store
from deeptutor.subjects.errors import ErrorCode, subject_error
from deeptutor.subjects.model_output import (
    REASON_EMPTY,
    REASON_NOT_A_STRING,
    ModelOutputError,
    parse_model_object,
)

#: 每份报告最多 8 张图；超过是明确的输入错误，不是"截断到 8 张"。
MAX_CHARTS = 8

#: ODE 表达式的长度上限。纯粹是拒绝病态输入，不改变可表达的数学。
MAX_ODE_EXPRESSION_CHARS = 512

#: 单张图描述的长度上限（提示词注入预算）。
MAX_CHART_DESCRIPTION_CHARS = 2000

#: 允许在 ODE 表达式里调用的函数名（只这些，且只允许单参数直接调用）。
ALLOWED_ODE_FUNCTIONS = frozenset({"sin", "cos", "exp", "log", "sqrt", "abs"})

#: 允许出现在 ODE 表达式里的变量名。
ALLOWED_ODE_NAMES = frozenset({"x", "y"})

_ALLOWED_BINARY_OPS: tuple[type[ast.operator], ...] = (
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.Pow,
)
_ALLOWED_UNARY_OPS: tuple[type[ast.unaryop], ...] = (ast.UAdd, ast.USub)
_MAX_NODES = 200

#: ``{CHART: 描述}``：同一份 match 同时服务识别与替换（P35 复用）。
CHART_PLACEHOLDER_RE = re.compile(r"\{CHART:\s*([^}]*)\}")

#: 服务端预分配图名的**唯一**形态：``chart_1.png`` … ``chart_8.png``。
#: 这是 fullmatch 的真实文件名，不是"允许的路径段"——``chart_1.exe``、
#: ``chart_1.png');print('injected``、带换行或分隔符的名字都不是服务端分配的图名。
CHART_BASENAME_RE = re.compile(r"chart_([1-8])\.png")


def chart_target_basename(name: object, *, what: str = "图表文件名") -> str:
    """校验并返回服务端预分配的固定图名（``chart_N.png``，N 1..8）。

    纯输入 helper：report_inputs / chart_executor / report_store 共用同一份正则，
    避免三处各写一套"看起来差不多"的校验。非法输入抛 C02 ``invalid_input``。
    """
    if not isinstance(name, str):
        raise json_store.invalid_input(f"{what}必须是字符串")
    if CHART_BASENAME_RE.fullmatch(name) is None:
        raise json_store.invalid_input(
            f"{what}必须是服务端预分配的 chart_N.png（N=1..{MAX_CHARTS}）"
        )
    return name

# ---------------------------------------------------------------------------
# 提示词模板
# ---------------------------------------------------------------------------
#: 普通图表提示词：**没有**默认微分方程、没有 ``f(x, y)``、没有"必须遵守 ODE"段。
PLAIN_CHART_CODE_PROMPT = """为下面这张图生成 matplotlib Python 代码。

## 图表需求
{description}

## 代码要求
1. 完整可运行的脚本：import numpy 和 matplotlib.pyplot as plt。
2. 中文字体设置：plt.rcParams['font.sans-serif'] = ['Microsoft YaHei']；plt.rcParams['axes.unicode_minus'] = False。
3. 图内文字可用中文或英文（数学变量用 x, y, t）。
4. 保存：plt.savefig('{out_path}', dpi=150, bbox_inches='tight')；不要 plt.show()。
5. 只输出 JSON：{{"code": "..."}}（code 为完整脚本字符串，转义换行）。
"""

#: 只有题目确实给了 ODE 时才插入的段落；``ode_rhs`` 已经过 AST 白名单校验。
ODE_SECTION = """
## 微分方程（必须严格遵守，禁止修改）
本题微分方程为 y′ = f(x, y)，其中：
f(x, y) = {ode_rhs}
代码中必须定义：def f(x, y): return {ode_rhs}，不得使用其他任何方程！
"""

#: 声明了 ODE 时的提示词：普通模板 + 校验后的原表达式段落。
ODE_CHART_CODE_PROMPT = """为下面这张图生成 matplotlib Python 代码。
{ode_section}
## 图表需求
{description}

## 代码要求
1. 完整可运行的脚本：import numpy 和 matplotlib.pyplot as plt。
2. 中文字体设置：plt.rcParams['font.sans-serif'] = ['Microsoft YaHei']；plt.rcParams['axes.unicode_minus'] = False。
3. 图内文字可用中文或英文（数学变量用 x, y, t）。
4. 保存：plt.savefig('{out_path}', dpi=150, bbox_inches='tight')；不要 plt.show()。
5. 只输出 JSON：{{"code": "..."}}（code 为完整脚本字符串，转义换行）。
"""


# ---------------------------------------------------------------------------
# ODE 表达式：AST 白名单
# ---------------------------------------------------------------------------
def _ode_reject(detail: str, node: ast.AST | None = None) -> json_store.InvalidInputError:
    """构造拒绝错误；只带节点类型与列号，绝不把表达式原文放进诊断。"""
    where = ""
    if node is not None:
        where = f"（节点 {type(node).__name__}，列 {getattr(node, 'col_offset', -1)}）"
    return json_store.invalid_input(f"ODE 表达式不被接受：{detail}{where}")


def _check_ode_node(node: ast.AST, state: list[int]) -> None:
    """递归校验一个节点；``state[0]`` 累计节点数，避免病态输入。

    只数节点、不设"深度"上限：``x+x+...`` 这类平坦链在 AST 里也是左深链，
    按深度拒绝会误伤正常表达式；节点总数上限（配合表达式长度上限）已经足够
    把递归规模压在安全范围内。
    """
    state[0] += 1
    if state[0] > _MAX_NODES:
        raise _ode_reject("表达式过长", node)

    if isinstance(node, ast.Expression):
        _check_ode_node(node.body, state)
        return
    if isinstance(node, ast.Constant):
        value = node.value
        # bool 是 int 的子类：``True``/``False`` 必须显式拒绝。
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise _ode_reject("只允许有限实数常量", node)
        if isinstance(value, float) and not math.isfinite(value):
            raise _ode_reject("常量不是有限实数", node)
        return
    if isinstance(node, ast.Name):
        if node.id not in ALLOWED_ODE_NAMES:
            raise _ode_reject("出现未知变量名", node)
        return
    if isinstance(node, ast.BinOp):
        if type(node.op) not in _ALLOWED_BINARY_OPS:
            raise _ode_reject("出现不允许的二元运算符", node)
        _check_ode_node(node.left, state)
        _check_ode_node(node.right, state)
        return
    if isinstance(node, ast.UnaryOp):
        if type(node.op) not in _ALLOWED_UNARY_OPS:
            raise _ode_reject("出现不允许的一元运算符", node)
        _check_ode_node(node.operand, state)
        return
    if isinstance(node, ast.Call):
        func = node.func
        if not isinstance(func, ast.Name):
            raise _ode_reject("只允许直接调用 6 个受支持函数", node)
        if func.id not in ALLOWED_ODE_FUNCTIONS:
            raise _ode_reject("调用了不受支持的名字", node)
        if node.keywords:
            raise _ode_reject("不允许关键字参数", node)
        if len(node.args) != 1:
            raise _ode_reject("函数只接受一个参数", node)
        if any(isinstance(arg, ast.Starred) for arg in node.args):
            raise _ode_reject("不允许星号参数", node)
        _check_ode_node(node.args[0], state)
        return
    # Attribute/Subscript/Lambda/comprehension/Import/JoinedStr/IfExp/BoolOp/Compare/
    # NamedExpr/Dict/List/Tuple/Set/Await/Starred/... 全部落到这里。
    raise _ode_reject("出现不允许的语法节点", node)


def validate_ode_expression(expression: object) -> str:
    """校验 ODE 右端表达式；返回可安全插入的原文（空表达式返回 ``""``）。

    ``""``/纯空白表示"本题没有 ODE"，返回 ``""``，调用方据此构造普通图表提示词。
    非空表达式必须通过 AST 白名单，否则抛 C02 ``invalid_input``。

    本函数**不做数值试算**：既不用宿主 ``eval``，也不展开表达式——计算量归 P33 的
    受限 worker。校验通过的文本原样返回，保证提示词里插入的就是用户声明的方程。
    """
    if not isinstance(expression, str):
        raise json_store.invalid_input("ODE 表达式必须是字符串")
    text = expression.strip()
    if not text:
        return ""
    if len(text) > MAX_ODE_EXPRESSION_CHARS:
        raise json_store.invalid_input(
            f"ODE 表达式超过 {MAX_ODE_EXPRESSION_CHARS} 字符上限"
        )
    try:
        tree = ast.parse(text, mode="eval")
    except (SyntaxError, ValueError, MemoryError, RecursionError) as exc:
        raise _ode_reject("语法无法解析") from exc
    _check_ode_node(tree, [0])
    return text


# ---------------------------------------------------------------------------
# 图表占位符
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class ChartPlaceholder:
    """一处 ``{CHART: ...}`` 占位：``raw`` 是原文（替换用），``spec`` 是描述。"""

    raw: str
    spec: str


def find_chart_placeholders(markdown: object) -> tuple[ChartPlaceholder, ...]:
    """按出现顺序返回全部占位符；不做数量/内容校验（纯识别）。"""
    if not isinstance(markdown, str):
        raise json_store.invalid_input("报告正文必须是字符串")
    return tuple(
        ChartPlaceholder(raw=match.group(0), spec=match.group(1).strip())
        for match in CHART_PLACEHOLDER_RE.finditer(markdown)
    )


def validated_chart_placeholders(markdown: object) -> tuple[ChartPlaceholder, ...]:
    """识别并校验占位符：每张都要有描述，且总数不超过 :data:`MAX_CHARTS`。

    这是 report.py 与后续 P35 共用的入口——数量超限是明确失败，不是静默截断。
    返回的对象同时带 ``raw`` 与 ``spec``，调用方替换时用**同一个 match** 的原文，
    不需要按描述重新拼一遍占位符。
    """
    placeholders = find_chart_placeholders(markdown)
    if len(placeholders) > MAX_CHARTS:
        raise json_store.invalid_input(
            f"报告声明的图表数量超过上限（最多 {MAX_CHARTS} 张）"
        )
    for placeholder in placeholders:
        if not placeholder.spec:
            raise json_store.invalid_input("图表占位符缺少描述")
        if len(placeholder.spec) > MAX_CHART_DESCRIPTION_CHARS:
            raise json_store.invalid_input(
                f"单张图的描述超过 {MAX_CHART_DESCRIPTION_CHARS} 字符上限"
            )
    return placeholders


def chart_placeholder_specs(markdown: object) -> tuple[str, ...]:
    """:func:`validated_chart_placeholders` 的描述列表投影。"""
    return tuple(placeholder.spec for placeholder in validated_chart_placeholders(markdown))


def build_chart_code_prompt(
    description: object, *, out_path: object, ode_rhs: object = ""
) -> str:
    """构造单张图的代码提示词。

    ``ode_rhs`` 为空（``""``/空白）时使用 :data:`PLAIN_CHART_CODE_PROMPT`：没有默认
    方程、没有 ``f(x, y)``、没有"必须遵守 ODE"段。非空时**先**通过
    :func:`validate_ode_expression`，再插入校验后的原表达式。

    ``out_path`` 必须是服务端预分配的**真实文件名** ``chart_N.png``（N 1..8）：
    这里用 :func:`chart_target_basename` 做完整匹配，任何扩展名、引号、换行或
    路径分隔符都被拒绝，绝不会被"当作一个合法的路径段"放过去。
    """
    if not isinstance(description, str) or not description.strip():
        raise json_store.invalid_input("图表描述不能为空")
    text = description.strip()
    if len(text) > MAX_CHART_DESCRIPTION_CHARS:
        raise json_store.invalid_input(
            f"单张图的描述超过 {MAX_CHART_DESCRIPTION_CHARS} 字符上限"
        )
    name = chart_target_basename(out_path)
    expression = validate_ode_expression(ode_rhs)
    if not expression:
        return PLAIN_CHART_CODE_PROMPT.format(description=text, out_path=name)
    return ODE_CHART_CODE_PROMPT.format(
        ode_section=ODE_SECTION.format(ode_rhs=expression),
        description=text,
        out_path=name,
    )


# ---------------------------------------------------------------------------
# 模型响应
# ---------------------------------------------------------------------------
def parse_chart_object(raw: object) -> dict:
    """严格解析模型返回的**唯一** JSON 对象；失败抛 C02 固定错误。

    与旧 ``_extract_json`` 的区别是本函数**不会**在失败时返回 ``{}``：空/非字符串
    响应映射为 ``empty_model_output``，其余解析失败（截断、多对象、尾随内容、
    非有限数字……）映射为 ``invalid_model_output``。被拒绝的原文只留在 ``cause``。
    """
    try:
        return parse_model_object(raw)  # type: ignore[arg-type]
    except ModelOutputError as exc:
        if exc.reason in (REASON_EMPTY, REASON_NOT_A_STRING):
            raise subject_error(ErrorCode.EMPTY_MODEL_OUTPUT, cause=exc) from exc
        raise subject_error(ErrorCode.INVALID_MODEL_OUTPUT, cause=exc) from exc


def parse_chart_code_response(raw: object) -> str:
    """从模型响应里取出图表代码：``{"code": "<非空字符串>"}``。

    ``code`` 缺失、不是字符串（list/dict/数字/bool/None）、只有空白，都是
    ``invalid_model_output``。返回前还要证明这段文本**可以 UTF-8 编码**：孤立
    surrogate（JSON 里的 ``"\\ud800"``）能通过 JSON 解析，却会在写脚本文件时炸成
    裸 ``UnicodeEncodeError``；这里提前映射成同一个固定 C02 错误。
    """
    payload = parse_chart_object(raw)
    if "code" not in payload:
        raise subject_error(ErrorCode.INVALID_MODEL_OUTPUT)
    code = payload["code"]
    if not isinstance(code, str) or not code.strip():
        raise subject_error(ErrorCode.INVALID_MODEL_OUTPUT)
    try:
        code.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise subject_error(ErrorCode.INVALID_MODEL_OUTPUT, cause=exc) from exc
    return code


__all__ = [
    "ALLOWED_ODE_FUNCTIONS",
    "ALLOWED_ODE_NAMES",
    "CHART_BASENAME_RE",
    "CHART_PLACEHOLDER_RE",
    "MAX_CHARTS",
    "MAX_CHART_DESCRIPTION_CHARS",
    "MAX_ODE_EXPRESSION_CHARS",
    "ODE_CHART_CODE_PROMPT",
    "ODE_SECTION",
    "PLAIN_CHART_CODE_PROMPT",
    "ChartPlaceholder",
    "build_chart_code_prompt",
    "chart_placeholder_specs",
    "chart_target_basename",
    "find_chart_placeholders",
    "parse_chart_code_response",
    "parse_chart_object",
    "validate_ode_expression",
    "validated_chart_placeholders",
]
