# S11 已探索文件清单与关键片段

本包由 `.phase1-evidence/reviews/S10-final/build_s11_packet.py` 生成；SHA-256按生成时完整文件字节计算，片段给出一基源码行号。此包是定向探索，不代替阶段执行清单或源码审查。

## 范围与固定边界

- S11白名单共29项：原阶段26项加AGENTS.md、requirements/cli.txt、packaging/deeptutor-cli/pyproject.toml。6个新文件当前不存在，列于下表但未读取、未哈希。
- P42可在现有科目页增加最小导出按钮；必须使用既有导出API和真实outputs下载鉴权链。导出失败不打开新窗口。
- 不增加C10知识点UI；科目页 WrongEntry.mastery 仍为 C05 的 number，0/untracked语义保持。
- P44仅清理partner/tutorbot/matrix extras与requirements镜像；MCP SDK及共享依赖保留。requirements/cli.txt和CLI打包pyproject只改过时的兼容能力注释。
- P45允许AGENTS.md记录当前fork差异；不恢复deeptutor_cli/book.py、deeptutor_cli/partner.py或其他五项既有删除。
- P43仅移除不可用Obsidian创建入口，不删除501 API、MCP支持或其他共享provider/runtime依赖。
- P46保留PageIndex真实REST outline检索，明确 retrieval_kind=outline；不新增MCP client。

## 文件清单与完整 SHA-256

| 类别 | 文件 | SHA-256 / 状态 | 用途 |
|---|---|---|---|
| scope | `tests/phase1/test_p1_44.py` | absent (not read) | P44 focused packaging contract tests; listed for creation, not read. |
| scope | `tests/phase1/test_p1_45.py` | absent (not read) | P45 CLI pruning behavior tests; listed for creation, not read. |
| scope | `tests/phase1/test_p1_46.py` | absent (not read) | P46 PageIndex outline behavior tests; listed for creation, not read. |
| scope | `web/lib/subject-results.ts` | absent (not read) | P42 result/error projection helper; listed for creation, not read. |
| scope | `web/tests/phase1-42.test.ts` | absent (not read) | P42 node behavior tests; listed for creation, not read. |
| scope | `web/tests/phase1-43.test.ts` | absent (not read) | P43 node behavior tests; listed for creation, not read. |
| scope | `SKILL.md` | `92628ee175e80eefbf296e91d6986b0d16aa11f3bdeaf982107142903951a3b3` | P45: active user guidance still mentions removed CLI commands. |
| scope | `deeptutor/agents/chat/agentic_pipeline.py` | `ce83cb49de8f7ea639cea23e16630b33b2fc804f5e477af8340de348a0bcb10e` | P46: prompt/tool assembly has stale PageIndex MCP claims; preserve existing RAG path. |
| scope | `deeptutor/knowledge/kb_types.py` | `39cc6fcc0d875496ec6747949095429c9ebff27120c4a1392ffc24e219197c5c` | P46: retain connected-KB lifecycle and historical provider discriminators; this module has no PageIndex type to remove. |
| scope | `deeptutor/services/rag/pipelines/pageindex/pipeline.py` | `be6c2cc388d2cb9c7a84cf5214c20a9c4bdfcb96026450b0ca66d4a89d8339d9` | P46: the real PageIndex path is REST outline retrieval. |
| scope | `deeptutor_cli/README.md` | `f44f3eb8346b433cb4fdcc62ea1e0de35a51365cab419d19483faf170709efa0` | P45: installation and supported CLI examples. |
| scope | `deeptutor_cli/main.py` | `b6d90b2d8977d55e9bd040c7525cf3cc90f91ab2f0a237ad16821a931fe90ea4` | P45: current command registration; deleted book.py and partner.py stay deleted. |
| scope | `pyproject.toml` | `c4067bbb3cbdb12f214d3e97c1f4118629a953f35f1395015bfa4cb4c8f4801d` | P44: obsolete extras and MCP compatibility wording; keep MCP dependency. |
| scope | `requirements.txt` | `b8fde3a4d98677b6d547141be3001dd43499eabce30062b9dd2a0928adcd964a` | P44: default installation currently pulls a broad requirements mirror. |
| scope | `requirements/matrix-e2e.txt` | `a2b69353ba92a8540d80c57427100f4ff6f0ad1b1a3ba7aa286dec00246d28a1` | P44: obsolete Matrix mirror; check reverse -r references before removal. |
| scope | `requirements/matrix.txt` | `f3d900c290599e2b87475807b318d88599617b4be4b0ac5989fd422dcf0803b0` | P44: obsolete Matrix runtime mirror; avoid keyword-based shared dependency removal. |
| scope | `requirements/partners.txt` | `ebea2a5b64b5b1ea739e799066c00d6734e9154fd8a1e9316144b5add8f514b3` | P44: obsolete partner SDK mirror; retain dependencies used by supported capabilities. |
| scope | `requirements/server.txt` | `c5ec2be7194575dbfa6deea3c4c89ae2815ee2e7af23d18735a4ef68825cf685` | P44: supported server mirror and its include relationships. |
| scope | `tests/cli/test_provider_cli.py` | `70193e82a386535fa49ceba3b0d879058d7c151b1852ba2baa5c59c9ef645beb` | P45: preserve provider, knowledge, memory and start command behavior. |
| scope | `tests/test_matrix_requirements.py` | `bcfc3ec464a26ae2fde068e0f2a95dcbec4eb44402d08794b71cec6bef128482` | P44: existing assertions encode mirrors that are to be removed. |
| scope | `tests/test_packaging_metadata.py` | `a4cde074970dd892faac83bdc068c75aec9657fa0c06d962f5ee4236cb468ce5` | P44: preserve core MCP dependency checks while correcting stale automatic-injection claims. |
| scope | `web/app/(workspace)/subjects/[id]/page.tsx` | `073b995a789f46f9ce426898353a34fd97e14ae1c679f17fe3997defd40f7c7a` | P42: action boundaries and WrongEntry mastery remains number per C05. |
| scope | `web/app/(workspace)/subjects/page.tsx` | `6532a315459481bd897ef81fd207dac1a83466415168a87de5723d5864f8f73d` | P42: subject create/upload/delete and list feedback; add only the authorized minimal export button. |
| scope | `web/components/knowledge/CreateKbModal.tsx` | `28533688dc5797dc61987fe68e393ce3e0cdeff55fde03b21d702069c811e217` | P43: remove only the unavailable Obsidian entry and its callback wiring. |
| scope | `web/components/knowledge/KnowledgeHome.tsx` | `c233a950438c7c156e248e5cdc50704205818e46cd05c63ded01a73694581e1f` | P43: remove only the unavailable Obsidian entry; this component has no linked-folder callback to remove. |
| scope | `web/components/knowledge/KnowledgePage.tsx` | `080ed05ddaf0f7734fa93d04f7d0d3dd8d15563689b08df59ab53cd04625a0ee` | P43: callback and modal wiring; backend 501 remains. |
| scope | `AGENTS.md` | `fcfc6783e9699552efef19cb5427b26e8063260c455e1c1953f86eaa69621c79` | P45 only: add current-fork CLI pruning note; do not rewrite unrelated agent instructions. |
| scope | `requirements/cli.txt` | `6e1063f7435227eeba46729f512e32e1ca049220a99429d6f67dbb9ea0e1eef4` | P44 authorized comment-only MCP wording update; keep MCP dependency and shared runtime requirements. |
| scope | `packaging/deeptutor-cli/pyproject.toml` | `5655c60ed0ee060cba68413e250b7cd7677dd80ad649b06f737a174b2558a4ce` | P44 authorized comment-only compatibility wording update; retain dependency metadata. |
| reference | `plans/phase1/DATA_CONTRACTS.md` | `05a0a376ca08b64020f61de9f5ef50171eee7d9142e9fb6abfcd7adff81e9862` | Authority for C02/C07/C08/C12/C13; no C10 knowledge-point UI, C05 entry mastery stays numeric. |
| reference | `plans/phase1/stages/S11.md` | `60bc767872be328d8b7959f64be438fc9d0e2f9be31e3825cc9c3f872fab0e60` | Ordered stage boundary and 29-path scope; do not broaden card goals. |
| reference | `plans/phase1/cards/P1-42.md` | `08de9f370778e760a5ce9d36002bed03fc9ce8d5a0ed1344f9203c62f1926898` | P42 acceptance and authorized minimal subject export action. |
| reference | `plans/phase1/cards/P1-43.md` | `c0c6f0439b25e19faf58cce2d7263928074e05e524ac06ea6b73d645f0ff8caa` | P43 removes only the clickable Obsidian path; preserve other providers and 501 endpoint. |
| reference | `plans/phase1/cards/P1-44.md` | `4807ea0347ab502a8b539ae7277c6dcd426c2ebbdfdbf5f9aff5c88359c09787` | P44 dependency graph; remove retired mirrors/extras but retain MCP SDK. |
| reference | `plans/phase1/cards/P1-45.md` | `2cee5b374e933cbb8f856e21e9013f8cf50d2ea33aa45e7e34481f98761817c9` | P45 dead CLI command docs; preserve existing deletions. |
| reference | `plans/phase1/cards/P1-46.md` | `abe6a4fe088d6291ed35cc9afbe8fd084180ad9b52f28cfebe9cc8b735f1dfde` | P46 REST outline only; no invented MCP transport. |
| reference | `web/lib/api.ts` | `cd93ae4d5180251ef80e158889878638fa70fb0741d7cef7b8094e8b6a834de0` | Existing authenticated fetch wrapper for subject actions. |
| reference | `web/lib/knowledge-api.ts` | `4ad38aa993282636eb9d01a370ce82cd51ac5348ecbd0d724a6b64b0d7ceec47` | Legacy detail parser; P42 helper must retain compatibility. |
| reference | `deeptutor/api/routers/subjects.py` | `adae1fb5bfadd9921adec8765e2432b1d8d3b57347afc5ce845da3face9e7816` | Existing export API; export UI must follow this authenticated contract. |
| reference | `deeptutor/api/routers/outputs.py` | `ff89210fadad958b5e99efa0fc2955dd02e119f6f06493f49f280701a6719bed` | Actual authenticated download path, scoped to request user. |
| reference | `deeptutor/services/path_service.py` | `01505ea0a473ba16b09bd27a9afd1a6795f4ddff1eef4a7b34f89ee7c748bd3d` | Public output allowlist and private-suffix enforcement. |
| reference | `deeptutor/subjects/errors.py` | `fd99442eb26315e3308bc2de9ad1bc0ea8649cdc17301bb1270765b941809b88` | C02 fixed public error projection, relevant to UI safe messages. |
| reference | `web/scripts/run-node-tests.mjs` | `f67c84ce249ae9cfa6607038f6be0cad0a8428aa90186df0dcc69f8870681f74` | Actual node test compilation and discovery entrypoint. |
| reference | `web/package.json` | `bb41eb69e966ea306d3415bde85f006c52ece489c5b1b5cb02f29fd3e0db1991` | Node test script entrypoint. |

## 关键片段

### `SKILL.md`

P45: active user guidance still mentions removed CLI commands.

L76–L85

```text
```bash
deeptutor partner list                              # List all partners
deeptutor partner create <id> -n "My Tutor"         # Create and start a new partner
#   -n/--name <text>   Display name
#   -s/--soul <md>     Soul markdown (the persona)
#   -m/--model <id>    Model override
deeptutor partner start <id>                        # Start a partner
deeptutor partner stop <id>                         # Stop a running partner
```

```

L102–L111

```text
```bash
deeptutor book list                                 # List all books (flags stale pages)
deeptutor book health <book_id>                     # Inspect KB drift + log.md health
deeptutor book refresh-fingerprints <book_id>       # Re-snapshot KB fingerprints
```

### Memory

```bash
deeptutor memory show [<target>]    # target: L3 (all global docs, default) | L2 (all surfaces) | a doc name (e.g. profile, chat)
```

### `deeptutor/agents/chat/agentic_pipeline.py`

P46: prompt/tool assembly has stale PageIndex MCP claims; preserve existing RAG path.

L708–L717

```text

    def _compose_enabled_tools(self, context: UnifiedContext) -> list[str]:
        is_partner = self._is_partner_turn(context)
        composed = compose_enabled_tools(
            registry=self.tool_lookup,
            requested_tools=context.enabled_tools,
            optional_whitelist=CHAT_OPTIONAL_TOOLS,
            mount_flags=ToolMountFlags(
                # PageIndex KBs are read via the preloaded MCP tools, not rag —
                # a conversation with only PageIndex KBs doesn't mount rag at all.
```

L1582–L1591

```text

    def _rag_kbs(self, context: UnifiedContext) -> list[str]:
        """Attached KBs reachable through the rag tool.

        PageIndex libraries are included: their *outline* (``retrieval_kind=
        outline``) is served by the existing PageIndex RAG pipeline, which is the
        only PageIndex retrieval this build has (no MCP transport exists). The
        KB-specific doc-id note in the prompt explains what that outline offers.
        """
        return self._selected_kbs(context)
```

L1797–L1806

```text

    def _pageindex_system_note(self) -> str:
        """Doc list + retrieval instructions for attached PageIndex KBs.

        Populated by ``_prepare_deferred_tools`` once per turn, so the system
        prompt stays byte-stable for the whole turn (KB cache prefix).
        """
        doc_maps = getattr(self, "_pageindex_docs", None) or {}
        if not doc_maps:
            return ""
```

### `deeptutor/knowledge/kb_types.py`

P46: retain connected-KB lifecycle and historical provider discriminators; this module has no PageIndex type to remove.

L52–L61

```text
# capability navigates the live files. See ``capabilities/obsidian``.
OBSIDIAN_KB_TYPE = "obsidian"

# A linked engine index: a pointer (``external_path``) to a folder that already
# contains a self-contained index built by one of our local providers. We mount
# it in place and retrieve via the bound provider — no copy, no re-index.
LINKED_KB_TYPE = "linked"

# A connected subagent: a pointer to a local agent CLI (Claude Code / Codex).
# No path on disk — ``agent_kind`` names the backend, optional ``cwd`` is the
```

L78–L87

```text
# skip the index pipeline, the orphan prune and the embedding reconcile.
CONNECTED_KB_TYPES = frozenset(
    {
        OBSIDIAN_KB_TYPE,
        LINKED_KB_TYPE,
        SUBAGENT_KB_TYPE,
        LIGHTRAG_SERVER_KB_TYPE,
        IMA_KB_TYPE,
    }
)
```

L89–L98

```text

def is_connected_kb(entry: Any) -> bool:
    """True for pointer KBs whose data lives outside ``data/knowledge_bases``."""
    return isinstance(entry, dict) and entry.get("type") in CONNECTED_KB_TYPES


def supports_local_raw_files(entry: Any) -> bool:
    """Whether the KB owns a DeepTutor-managed local ``raw/`` directory.

    Connected KBs are pointers to external resources.  Some point at a local
```

### `deeptutor/services/rag/pipelines/pageindex/pipeline.py`

P46: the real PageIndex path is REST outline retrieval.

L164–L173

```text
    #: passage-level answer without guessing, so every result carries it.
    RETRIEVAL_KIND = "outline"

    async def search(self, query: str, kb_name: str, **_kwargs) -> Dict[str, Any]:
        """Return each document's tree outline (titles / pages / summaries).

        The deprecated REST retrieval endpoint is gone and this build has no
        PageIndex MCP tools: what remains is the *outline* — the documents' real
        structure (titles, pages, per-section summaries) — which is shallow but
        honest grounding for a programmatic caller. Every result therefore
```

L166–L175

```text

    async def search(self, query: str, kb_name: str, **_kwargs) -> Dict[str, Any]:
        """Return each document's tree outline (titles / pages / summaries).

        The deprecated REST retrieval endpoint is gone and this build has no
        PageIndex MCP tools: what remains is the *outline* — the documents' real
        structure (titles, pages, per-section summaries) — which is shallow but
        honest grounding for a programmatic caller. Every result therefore
        declares ``retrieval_kind="outline"``, including the branches that
        return no outline at all, so a caller never mistakes "no pages here" for
```

### `deeptutor_cli/README.md`

P45: installation and supported CLI examples.

L16–L25

```text
python -m pip install --upgrade pip
python -m pip install -e ./packaging/deeptutor-cli
deeptutor init --cli

# CLI + Web/API 服务
pip install deeptutor
deeptutor init

# 源码开发
pip install -e .
```

L33–L42

```text

`deeptutor init --cli` 和普通 `deeptutor init` 使用同一套 `data/user/settings/` 配置目录；区别是 `--cli` 不询问 Web 后端/前端端口，仍会创建 `system.json`、`auth.json`、`integrations.json`、`model_catalog.json`、`main.yaml` 和 `agents.yaml`，并继续询问 LLM 配置。Embedding 配置默认跳过；如果要使用 `deeptutor kb ...` 或 RAG，请在向导里选择配置 embedding，或稍后编辑 `data/user/settings/model_catalog.json`。

Windows PowerShell 可使用：

```powershell
py -3.11 -m venv .venv-cli
.\.venv-cli\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ./packaging/deeptutor-cli
```

### `deeptutor_cli/main.py`

P45: current command registration; deleted book.py and partner.py stay deleted.

L26–L35

```text

app = typer.Typer(
    name="deeptutor",
    help="DeepTutor CLI – agent-first interface for capabilities, tools, and knowledge.",
    no_args_is_help=True,
    add_completion=False,
)

# NOTE: `partner` and `book` are intentionally NOT registered. Their backing
# modules (`deeptutor.services.partners`, `deeptutor.book`) were removed by the
```

L173–L179

```text

def main() -> None:
    app()


if __name__ == "__main__":
    main()
```

### `pyproject.toml`

P44: obsolete extras and MCP compatibility wording; keep MCP dependency.

L92–L101

```text

[project.optional-dependencies]
# Compatibility extra for source installs and older docs. These packages are
# already included in the public `deeptutor` wheel; the local CLI-only project
# under `packaging/deeptutor-cli` uses the same list without Web assets/server deps.
cli = [
    # LLM provider SDKs
    "anthropic>=0.30.0",
    "dashscope>=1.14.0",
    "perplexityai>=0.1.0",
```

L155–L164

```text
# (see `mcp` above), not a partners-only one.
partners = [
    "deeptutor[server]",
    "python-telegram-bot[socks]>=22.6,<23.0",
    "wecom-aibot-sdk>=1.0.8,<2.0.0",
    "lark-oapi>=1.5.0,<2.0.0",
    "dingtalk-stream>=0.24.0,<1.0.0",
    "slack-sdk>=3.39.0,<4.0.0",
    "slackify-markdown>=0.2.0,<1.0.0",
    "qq-botpy>=1.2.0,<2.0.0",
```

L205–L214

```text
# Legacy alias kept for one release: `pip install deeptutor[tutorbot]`.
tutorbot = ["deeptutor[partners]"]

# Matrix (Element) channel for partners. Mirrors requirements/matrix.txt.
# Default Matrix install is non-E2EE so it works without libolm/python-olm.
matrix = [
    "matrix-nio>=0.25.2,<1.0.0",
    "mistune>=3.0.0,<4.0.0",
    "nh3>=0.2.18,<1.0.0",
]
```

L209–L218

```text
# Default Matrix install is non-E2EE so it works without libolm/python-olm.
matrix = [
    "matrix-nio>=0.25.2,<1.0.0",
    "mistune>=3.0.0,<4.0.0",
    "nh3>=0.2.18,<1.0.0",
]

# Optional Matrix E2EE addon. Mirrors requirements/matrix-e2e.txt and requires libolm.
matrix-e2e = [
    "deeptutor[matrix]",
```

L216–L225

```text
# Optional Matrix E2EE addon. Mirrors requirements/matrix-e2e.txt and requires libolm.
matrix-e2e = [
    "deeptutor[matrix]",
    "matrix-nio[e2e]>=0.25.2,<1.0.0",
]

# Math Animator addon (Manim). Mirrors requirements/math-animator.txt.
# System prerequisites (installed outside pip): LaTeX, pkg-config, cairo, cmake, ffmpeg.
math-animator = ["manim>=0.19.0"]

```

L45–L54

```text
    # the full connect timeout.
    "mcp>=1.26.0,<2.0.0",
    # Full app dependencies included by default for `pip install deeptutor`.
    "anthropic>=0.30.0",
    "dashscope>=1.14.0",
    "perplexityai>=0.1.0",
    "oauth-cli-kit>=0.1.1",
    "llama-index>=0.14.12",
    "llama-index-retrievers-bm25>=0.7.1,<0.8.0",
    # FAISS vector store: vectorized ANN retrieval that replaces SimpleVectorStore's
```

### `requirements.txt`

P44: default installation currently pulls a broad requirements mirror.

L21–L22

```text

-r requirements/partners.txt
```

### `requirements/matrix-e2e.txt`

P44: obsolete Matrix mirror; check reverse -r references before removal.

L15–L19

```text

-r matrix.txt

# --- Matrix E2EE support ---
matrix-nio[e2e]>=0.25.2,<1.0.0
```

L9–L18

```text
#
# Note: matrix-nio[e2e] pulls python-olm, which requires the libolm native library.
# On macOS:
#   brew install libolm
# On Debian/Ubuntu:
#   apt-get install libolm-dev

-r matrix.txt

# --- Matrix E2EE support ---
```

### `requirements/matrix.txt`

P44: obsolete Matrix runtime mirror; avoid keyword-based shared dependency removal.

L15–L18

```text
# --- Matrix channel ---
matrix-nio>=0.25.2,<1.0.0
mistune>=3.0.0,<4.0.0
nh3>=0.2.18,<1.0.0
```

### `requirements/partners.txt`

P44: obsolete partner SDK mirror; retain dependencies used by supported capabilities.

L13–L22

```text

-r server.txt

# --- Channel SDKs ---
python-telegram-bot[socks]>=22.6,<23.0
# wecom (WeCom AI Bot WebSocket client)
wecom-aibot-sdk>=1.0.8,<2.0.0
lark-oapi>=1.5.0,<2.0.0
dingtalk-stream>=0.24.0,<1.0.0
slack-sdk>=3.39.0,<4.0.0
```

### `requirements/server.txt`

P44: supported server mirror and its include relationships.

L10–L19

```text

-r cli.txt

# --- API server ---
fastapi>=0.100.0
uvicorn[standard]>=0.24.0
websockets>=12.0
python-multipart>=0.0.6

# --- Authentication ---
```

### `tests/cli/test_provider_cli.py`

P45: preserve provider, knowledge, memory and start command behavior.

L15–L24

```text
class ProviderCliDocsContractTest(unittest.TestCase):
    def test_provider_contract_describes_copilot_as_validation_not_oauth_login(self) -> None:
        self.assertIn(
            '"Provider: openai-codex (OAuth login) | github-copilot "',
            PROVIDER_CMD,
        )
        self.assertIn("| codebuddy (validate CodeBuddy SDK auth)", PROVIDER_CMD)
        self.assertIn('"""Authenticate or validate provider access."""', PROVIDER_CMD)
        self.assertIn("GitHub Copilot auth validation succeeded.", PROVIDER_CMD)
        self.assertIn("GitHub Copilot auth validation failed:", PROVIDER_CMD)
```

L3–L12

```text

from typer.testing import CliRunner

from deeptutor_cli import provider_cmd
from deeptutor_cli.main import app

ROOT = Path(__file__).resolve().parents[2]
PROVIDER_CMD = (ROOT / "deeptutor_cli" / "provider_cmd.py").read_text(encoding="utf-8")
CLI_README = (ROOT / "deeptutor_cli" / "README.md").read_text(encoding="utf-8")
ROOT_README = (ROOT / "README.md").read_text(encoding="utf-8")
```

### `tests/test_matrix_requirements.py`

P44: existing assertions encode mirrors that are to be removed.

L7–L16

```text

def test_matrix_default_requirements_do_not_install_e2e() -> None:
    text = (ROOT / "requirements" / "matrix.txt").read_text(encoding="utf-8")

    assert "matrix-nio[e2e]" not in text
    assert "matrix-nio>=0.25.2,<1.0.0" in text


def test_matrix_e2e_requirements_are_separate() -> None:
    text = (ROOT / "requirements" / "matrix-e2e.txt").read_text(encoding="utf-8")
```

L14–L19

```text

def test_matrix_e2e_requirements_are_separate() -> None:
    text = (ROOT / "requirements" / "matrix-e2e.txt").read_text(encoding="utf-8")

    assert "-r matrix.txt" in text
    assert "matrix-nio[e2e]>=0.25.2,<1.0.0" in text
```

### `tests/test_packaging_metadata.py`

P44: preserve core MCP dependency checks while correcting stale automatic-injection claims.

L34–L43

```text
)
def test_mcp_client_is_a_core_dependency(metadata_path: Path) -> None:
    """`mcp` must install by default, not only via an extra (issue #792).

    Both distributions ship ``deeptutor.services.mcp``, and the connection
    manager overlays the built-in PageIndex MCP server onto the config whenever
    a PageIndex API key is set. That happens on a plain install, so an
    extra-gated ``mcp`` leaves the connection task dying with
    ``ModuleNotFoundError`` on every turn.
    """
```

L50–L59

```text

def test_partners_extra_does_not_redeclare_the_core_mcp_client() -> None:
    """The `partners` extra is IM channel SDKs only; `mcp` is core now."""
    with (REPOSITORY_ROOT / "pyproject.toml").open("rb") as file:
        extras = tomllib.load(file)["project"]["optional-dependencies"]

    assert not [item for item in extras["partners"] if item.split(">")[0].strip() == "mcp"]


def test_requirements_mirror_the_core_mcp_client() -> None:
```

L58–L67

```text

def test_requirements_mirror_the_core_mcp_client() -> None:
    """Docker/CI installs read requirements/, which must agree with pyproject."""
    requirements = REPOSITORY_ROOT / "requirements"
    cli_text = (requirements / "cli.txt").read_text(encoding="utf-8")
    partners_text = (requirements / "partners.txt").read_text(encoding="utf-8")

    # cli.txt mirrors the core dependency set, so the client belongs there...
    assert "mcp>=1.26.0,<2.0.0" in cli_text
    # ...and partners.txt inherits it transitively rather than redeclaring it.
```

### `web/app/(workspace)/subjects/[id]/page.tsx`

P42: action boundaries and WrongEntry mastery remains number per C05.

L9–L18

```text

type WrongEntry = {
  id: string;
  kp: string;
  question: string;
  answer: string;
  status: string;
  mastery: number;
  attempts: { correct: boolean }[];
  archived: boolean;
```

L92–L101

```text

  async function recordAttempt(entryId: string, correct: boolean) {
    await post(`/wrong-book/${entryId}/attempt`, { correct: String(correct) });
    await refresh();
  }

  async function archiveEntry(entryId: string) {
    await post(`/wrong-book/${entryId}/archive`, {});
    await refresh();
  }
```

L266–L275

```text
          >
            保存画像
          </button>
        </div>
      )}

      {tab === "review" && (
        <div className="mt-4 max-w-lg space-y-3 rounded-xl border p-4">
          <div className="text-sm">
            基于期末考点 + 错题集 + 知识点索引生成复习指南。
```

L296–L305

```text
              >
                生成 {fmt === "pdf" ? "PDF" : "Word"}
              </button>
            ))}
          </div>
        </div>
      )}

      </div>
    </div>
```

L314–L323

```text

  async function uploadAudio(files: FileList | null) {
    if (!files || files.length === 0) return;
    setBusy(true);
    setAsrMsg("正在上传录音并转写（ASR）…");
    const body = new FormData();
    body.append("type", "lecture");
    for (const f of Array.from(files)) body.append("files", f);
    const res = await apiFetch(`/api/v1/subjects/${subjectId}/knowledge/upload`, {
      method: "POST",
```

L341–L350

```text

  async function run() {
    if (!transcript.trim()) return;
    setBusy(true);
    const body = new FormData();
    body.append("transcript", transcript);
    body.append("term", "");
    const res = await apiFetch(`/api/v1/subjects/${subjectId}/exam-points/detect`, {
      method: "POST",
      body,
```

### `web/app/(workspace)/subjects/page.tsx`

P42: subject create/upload/delete and list feedback; add only the authorized minimal export button.

L36–L45

```text

  const refresh = useCallback(async () => {
    const res = await apiFetch("/api/v1/subjects");
    if (res.ok) {
      const data = await res.json();
      setSubjects(data.subjects ?? []);
      const kb: Record<string, KnowledgeRecord[]> = {};
      await Promise.all(
        (data.subjects ?? []).map(async (s: Subject) => {
          const kr = await apiFetch(`/api/v1/subjects/${s.id}/knowledge`);
```

L58–L67

```text

  async function createSubject(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim()) return;
    const body = new FormData();
    body.append("name", name);
    body.append("term", term);
    const res = await apiFetch("/api/v1/subjects", { method: "POST", body });
    setMsg(res.ok ? "创建成功" : await res.text());
    setName("");
```

L71–L80

```text

  async function uploadFiles(subjectId: string, files: FileList | null, type: string) {
    if (!files || files.length === 0) return;
    setUploading((u) => ({ ...u, [subjectId]: true }));
    try {
      const body = new FormData();
      body.append("type", type);
      for (const f of Array.from(files)) body.append("files", f);
      const res = await apiFetch(`/api/v1/subjects/${subjectId}/knowledge/upload`, {
        method: "POST",
```

L89–L98

```text

  async function deleteSubject(id: string) {
    if (!confirm(`删除科目 ${id}？将同时删除其全部数据`)) return;
    await apiFetch(`/api/v1/subjects/${id}`, { method: "DELETE" });
    await refresh();
  }

  return (
    <div className="h-full overflow-y-auto [scrollbar-gutter:stable]">
      <div className="mx-auto max-w-5xl px-6 py-10">
```

### `web/components/knowledge/CreateKbModal.tsx`

P43: remove only the unavailable Obsidian entry and its callback wiring.

L72–L81

```text
  /** Connect a live Obsidian vault (no index). */
  onConnectObsidian: (params: {
    name: string;
    vaultPath: string;
  }) => Promise<void>;
  /** Connect an external LightRAG server (retrieval only, no local index). */
  onConnectLightRagServer: (params: {
    name: string;
    serverUrl: string;
    apiKey?: string;
```

L71–L80

```text
  }) => Promise<void>;
  /** Connect a live Obsidian vault (no index). */
  onConnectObsidian: (params: {
    name: string;
    vaultPath: string;
  }) => Promise<void>;
  /** Connect an external LightRAG server (retrieval only, no local index). */
  onConnectLightRagServer: (params: {
    name: string;
    serverUrl: string;
```

L66–L75

```text
  /** Link a pre-built engine index folder in place (no copy, no re-index). */
  onConnectLinkedFolder: (params: {
    name: string;
    folderPath: string;
    provider: string;
  }) => Promise<void>;
  /** Connect a live Obsidian vault (no index). */
  onConnectObsidian: (params: {
    name: string;
    vaultPath: string;
```

### `web/components/knowledge/KnowledgeHome.tsx`

P43: remove only the unavailable Obsidian entry; this component has no linked-folder callback to remove.

L39–L48

```text
  /** Open the create flow pre-set to link an Obsidian vault. */
  onConnectObsidian: () => void;
}

const ENGINE_ICONS: Record<string, LucideIcon> = {
  llamaindex: Boxes,
  pageindex: Cloud,
  graphrag: Network,
  lightrag: Workflow,
  "lightrag-server": Server,
```

L218–L227

```text
                {t(
                  "Connect your Obsidian vault. The tutor navigates and writes notes in place — no upload, no index. Local / self-hosted only.",
                )}
              </p>
              <div className="mt-auto flex items-center gap-2 pt-1 text-[11px] text-[var(--muted-foreground)]">
                <span className="inline-flex items-center gap-1">
                  <FolderOpen className="h-3 w-3" />
                  {t("Connect vault")}
                </span>
                <ChevronRight className="ml-auto h-3.5 w-3.5 opacity-0 transition-opacity group-hover:opacity-60" />
```

### `web/components/knowledge/KnowledgePage.tsx`

P43: callback and modal wiring; backend 501 remains.

L71–L80

```text
  // the unified create flow, pre-set to "link existing → Obsidian".
  const openObsidian = useCallback(() => {
    setCreatePreset({ mode: "link", source: "obsidian" });
    setCreateOpen(true);
  }, []);
  // Lands on the Overview console unless deep-linked to a KB or an engine.
  const [view, setView] = useState<"home" | "kb" | "engine">(
    initialEngine ? "engine" : initialKb ? "kb" : "home",
  );

```

L258–L267

```text
              onCreate={openCreate}
              onConnectObsidian={openObsidian}
            />
          ) : view === "engine" && selectedProvider ? (
            <EngineDetail
              provider={selectedProvider}
              kbs={kbs}
              onBack={() => setView("home")}
              onOpenKb={openKb}
              onSelectMode={handleSelectMode}
```

L11–L20

```text
import EngineDetail from "./EngineDetail";
import CreateKbModal from "./CreateKbModal";
import PageIndexSettingsModal from "./PageIndexSettingsModal";

export default function KnowledgePage() {
  const { t } = useTranslation();
  const router = useRouter();
  const searchParams = useSearchParams();
  const initialKb = searchParams.get("kb");
  const initialEngine = searchParams.get("engine");
```

### `AGENTS.md`

P45 only: add current-fork CLI pruning note; do not rewrite unrelated agent instructions.

L89–L98

```text
# Partners (IM-connected companions)
deeptutor partner list

# Knowledge bases, memory, server
deeptutor kb list
deeptutor kb create my-kb --doc textbook.pdf
deeptutor memory show
deeptutor serve --port 8001       # API server only
deeptutor start                   # backend + frontend together
```
```

L131–L138

```text
.[server]         — Web/API server dependencies
.[partners]       — Partner channel SDKs  (legacy alias: .[tutorbot])
.[matrix]         — Matrix channel for Partners (matrix-nio; needs libolm)
.[matrix-e2e]     — Matrix with end-to-end encryption (matrix-nio[e2e])
.[math-animator]  — Manim addon (powers `visualize` Manim renders + `deeptutor run math_animator`)
.[dev]            — Test / lint tooling
.[all]            — Everything above
```
```

### `requirements/cli.txt`

P44 authorized comment-only MCP wording update; keep MCP dependency and shared runtime requirements.

L72–L73

```text
# pageindex server whenever a PageIndex API key is configured (issue #792).
mcp>=1.26.0,<2.0.0
```

L69–L73

```text

# --- MCP client (deferred tools; built-in PageIndex MCP server) ---
# Core, not partners-only: the connection manager injects the built-in
# pageindex server whenever a PageIndex API key is configured (issue #792).
mcp>=1.26.0,<2.0.0
```

### `packaging/deeptutor-cli/pyproject.toml`

P44 authorized comment-only compatibility wording update; retain dependency metadata.

L34–L43

```text
    # is configured, so it needs the client too (issue #792).
    "mcp>=1.26.0,<2.0.0",
    "anthropic>=0.30.0",
    "dashscope>=1.14.0",
    "perplexityai>=0.1.0",
    "oauth-cli-kit>=0.1.1",
    "llama-index>=0.14.12",
    "llama-index-retrievers-bm25>=0.7.1,<0.8.0",
    # FAISS vector store: ANN retrieval replacing SimpleVectorStore brute force for
    # large KBs (issue #552); imported lazily with SimpleVectorStore fallback.
```

L32–L41

```text
    # MCP client. This distribution ships `deeptutor.services.mcp`, including the
    # built-in PageIndex MCP server that is injected whenever a PageIndex API key
    # is configured, so it needs the client too (issue #792).
    "mcp>=1.26.0,<2.0.0",
    "anthropic>=0.30.0",
    "dashscope>=1.14.0",
    "perplexityai>=0.1.0",
    "oauth-cli-kit>=0.1.1",
    "llama-index>=0.14.12",
    "llama-index-retrievers-bm25>=0.7.1,<0.8.0",
```

### `plans/phase1/DATA_CONTRACTS.md`

Authority for C02/C07/C08/C12/C13; no C10 knowledge-point UI, C05 entry mastery stays numeric.

L18–L27

```text

## C02：错误与各入口的一致性

subject HTTP 业务错误保留旧 `detail: string`，增加结构化 `error`。不把 detail 从字符串改成对象，不改全局 FastAPI 校验形状。

```json
{"detail":"批改服务返回的结果无法解析，请重试。","error":{"code":"invalid_model_output","message":"批改服务返回的结果无法解析，请重试。","retryable":true}}
```

| code | HTTP | retryable | 约束 |
```

L81–L90

```text

## C07：资料上传与索引源

```json
{"operation":"index","kb_name":"assignment-kb","type":"assignment","files":["notes.txt"],"task_id":"...","message":"已保存，正在建立索引"}
```

```json
{"operation":"transcribe","type":"lecture","files":["lecture.wav"],"transcripts":[{"file":"lecture.wav","text":"课堂文本","model":"..."}],"message":"转写完成"}
```
```

L101–L110

```text

## C08：聊天科目作用域与知识库标识

输入 subject_id 采用三态：未提供沿用当前 session.preferences.subject_id，null/空字符串明确清空，非空字符串设置。支持顶层字段及旧 config.subject_id；两者同时提供且不相等为 invalid_input。不能用 `a or b` 丢掉清空值。验证发生在创建 turn/写用户消息前。新 session 无值即 null；切换 session 不继承另一 session 的选择。

复用已存在 preferences_json 保存 subject_id，不新增 SQLite 列或配置数据库，不改变 session store API。运行 metadata 带 resolved subject_id，request_snapshot 保存本轮 resolved 值，以便重试/再生成使用原作用域；UI 恢复 preferences 后才允许发送。被删科目的历史会话提示 subject_not_found，用户显式清空后恢复普通聊天，不静默选别科。

subject KB wire id：`subject:kb:<subject_id>:<kb_name>`。subject_id/kb_name 均不含冒号；中文按字符串存储，URL 路径各段单独编码。既有 admin:kb:/user:kb: 保留。不修改知识库磁盘名字。

内部 resolved resource 包含 wire id、真实 name、subject_id|null、当前用户 base_dir、read_only；base_dir 不进入模型工具 schema/公开响应。显式 subject ref 必须属于本轮 subject，且该科/KB存在、权限通过；scope mismatch 报 403，缺库报 404，不回退全局。所有构造路径在服务端。
```

L157–L166

```text

## C12：导出内容与完整性

保留 `GET /subjects/{id}/export`；用 uuid 导出文件名，响应保留 url 并增加 export_id/schema_version。ZIP schema_version=1，内容固定：

```text
manifest.json                        版本、subject元信息、文件清单、覆盖/排除声明
subject.json                         index.json 中该 subject 的完整记录
learning/                            该科材料、KB原件/已完成索引、学情JSON
artifacts/                           该科 completed PDF/DOCX/图表/正文
```

L174–L183

```text

## C13：UI、裁剪与能力说明

- 所有修改的 async action 有 try/catch/finally，失败解除 busy，不显示成功计数/生成链接。post 非 2xx 不继续按成功刷新；读取 error.message，兼容旧 detail 文本。界面不展示 traceback/provider密钥/宿主路径。
- subject selector 提供无科目选项；从当前 session 的 preferences 恢复，能力参数与 subject_id 合并不能覆盖彼此。刷新恢复未完成时不能发送旧科目的请求。
- 上传 operation=transcribe 时显示转写完成与文本去向；index 时显示任务/状态；documents从C07，coverage降级可见。不新增“音频自动建库”或全新批改界面。
- 去掉 Obsidian 可点击创建入口及活跃宣传。保留 501 API 和合法历史数据读取拒绝；不删除用户原 vault/旧 KB 目录。
- 删除 partners/tutorbot/matrix 依赖 extras 和 requirements 镜像，root requirements 改 server；修对应打包断言。保留 CLI、scheduler、sandbox runner、office skills、built-in deferred_tools、load_tools、多用户上下文和现有内置 capability。不按词删 runtime/providers。
- PageIndex 可用 REST outline 能力保留且如实标注 retrieval_kind=outline，不宣称有不存在的 MCP 深度检索工具。当前 prompt/挂载应能走既有概览检索，不引入外部 transport。MCP SDK 暂保留但注释标“兼容待审查”，不是“当前自动注入client”；后续若需要移除，另立有完整动态插件/打包证据的卡。
- 新部署文档不建议安装已删伙伴功能；历史迁移说明和 UPSTREAM.md/assets/README 上游存档保持原样。AGENTS.md 标当前 fork 差异或同步最小命令表，不把源上游全文视为本项目运行清单。
```

L129–L138

```text

entry 层保持 C05 的 0/untracked。聚合 knowledge point 无有作答证据的关联错题时 mastery=null、evidence_count=0、assessment_status=unassessed；有证据时沿用有效关联 entry mastery 均值（三位），assessment_status=assessed。没有证据不等于已掌握。旧接口新增字段而不重写历史 stored mastery；模板/前端消费 null 显示“未评估”，不能显示 None/NaN。

知识点关联从本 subject 的未归档 wrong entry 和对应学期考点派生。build 可重复执行，新增/归档/删除后 aggregate 不把不存在或已归档记录计入。现有人工点保留；不自动从教材抽知识点，不把整个学习库迁到 Guided Learning 数据模型。

## C11：报告、执行与产物

report_id 使用服务端 uuid hex（无时间秒碰撞）。私有 staging：`workspace/subjects/<sid>/_report_runs/<rid>`；成功正式产物：`public outputs/subjects/<sid>/reports/<rid>`。旧报告目录不迁移，受约束的 legacy review 可以读同科旧正文。新任务不共享 _chart.py、_ode_check.py、chart_1.png 或错误日志。

create 两入口统一调用同一 pipeline，持久化 report.md、report.pdf、chart_N.png、私有 report metadata，保留 markdown_tokens/chart_count/url/path 旧字段并增加 report_id/status。URL 从实际 server 相对路径构造；path 若继续保留只能指本科正式产物，不暴露任意 path 参数。
```

### `plans/phase1/stages/S11.md`

Ordered stage boundary and 29-path scope; do not broaden card goals.

L1–L2

```text
# S11：现有UI与裁剪残留收敛

```

L11–L13

```text

## 实施顺序与范围

```

L4–L13

```text

按STAGE_WORKFLOW.md执行。小卡是阶段内编码单元，不是人工交接关口；完成一单元本地验证后继续本阶段下一单元，阶段末一次提交审查。

## 目标与前置

完成 现有UI与裁剪残留收敛 的现有修复，契约 C02, C07, C08, C12, C13。
跨阶段依赖：S01, S04, S05, S07, S10；当前source需与相应review receipt一致。

## 实施顺序与范围

```

### `plans/phase1/cards/P1-42.md`

P42 acceptance and authorized minimal subject export action.

L4–L13

```text

## 目标

网络/业务错误不假成功或卡busy；ASR/索引/导出文案符合真实结果。

## 已有问题证据

多个await缺try/finally；upload总说正在建索引，检测故障曾显示0。

## 必读输入
```

L19–L28

```text

## 允许更改范围

- `web/app/(workspace)/subjects/page.tsx`
- `web/app/(workspace)/subjects/[id]/page.tsx`
- `web/lib/subject-results.ts`
- `web/tests/phase1-42.test.ts`


2026-10-19明确现有页面内增加最小科目导出按钮与范围文案，调用既有export/outputs链路；不新增C10知识点UI，不改变C05 WrongEntry.mastery的number/0-untracked语义。
```

L47–L56

```text
- [ ] index rebuild/coverage warning明确
- [ ] 导出失败不开新窗口
- [ ] legacy detail兼容

执行命令（从项目根开始；带 cd web 的条目为独立命令，不延续前一条 cwd）：

```bash
cd web && node ./scripts/run-node-tests.mjs
cd web && ./node_modules/.bin/tsc --noEmit -p .
```
```

### `plans/phase1/cards/P1-43.md`

P43 removes only the clickable Obsidian path; preserve other providers and 501 endpoint.

L4–L13

```text

## 目标

用户不再点击必定501的入口，仍可正常上传笔记文档。

## 已有问题证据

当前CreateKbModal调用onConnectObsidian，backend固定501。

## 必读输入
```

L19–L28

```text

## 允许更改范围

- `web/components/knowledge/CreateKbModal.tsx`
- `web/components/knowledge/KnowledgeHome.tsx`
- `web/components/knowledge/KnowledgePage.tsx`
- `web/tests/phase1-43.test.ts`

符号范围：Obsidian选项、连接callback/UI文案；不改其他knowledge provider与501接口。

```

L40–L49

```text
- [ ] 可选入口没有Obsidian
- [ ] 旧501API仍保留解释
- [ ] 本地文件夹/正常文档/IMA选项不回归
- [ ] tsc无残余required prop

执行命令（从项目根开始；带 cd web 的条目为独立命令，不延续前一条 cwd）：

```bash
cd web && node ./scripts/run-node-tests.mjs
cd web && ./node_modules/.bin/tsc --noEmit -p .
```

### `plans/phase1/cards/P1-44.md`

P44 dependency graph; remove retired mirrors/extras but retain MCP SDK.

L42–L51

```text

1. root requirements改server；删extras/mirror，all仅指仍保留extras。
2. 旧伙伴断言改成当前负向安装契约，说明确属已删功能，不删有效server测试。
3. MCP SDK本阶段保持，修误称client正在运行的注释；不要搜到mcp就删。
4. pyproject/requirements一致性只本卡检查，不升级依赖或实际联网安装。

## 证据：如何证明完成

以下必须成为独立的行为断言/场景；至少记录输入、预期、实际和对应测试名，不能只断言源码字符串或helper被调用：

```

L44–L53

```text
2. 旧伙伴断言改成当前负向安装契约，说明确属已删功能，不删有效server测试。
3. MCP SDK本阶段保持，修误称client正在运行的注释；不要搜到mcp就删。
4. pyproject/requirements一致性只本卡检查，不升级依赖或实际联网安装。

## 证据：如何证明完成

以下必须成为独立的行为断言/场景；至少记录输入、预期、实际和对应测试名，不能只断言源码字符串或helper被调用：

- [ ] tomllib extras不存在partners/tutorbot/matrix
- [ ] root/server/cli引用链存在且无broken -r
```

### `plans/phase1/cards/P1-45.md`

P45 dead CLI command docs; preserve existing deletions.

L10–L19

```text

book.py/partner.py已在工作树删除但HEAD还在；活跃SKILL/README仍提partner。

## 必读输入

- 仓库 AGENTS.md、plans/phase1/EXECUTION_GUIDE.md 和 FRAMEWORK.md 的阶段边界。
- DATA_CONTRACTS.md 的 C13；此处不得自行改契约。
- 本卡允许的现有实现和依赖卡 completion.json，核实前置通过后再编辑。
- PROJECT_AUDIT_2026-10-10.md 对应发现；源码行号可能已随前置卡变化，应按符号定位。

```

L37–L46

```text

1. 确认main不import/register删模块，CLI help无book/partner，不把已完成修复重写回来。
2. 清理活跃安装/命令说明；保留UPSTREAM存档。
3. tests覆盖help和保留kb/memory/start命令可加载，不使用真实密钥。

## 证据：如何证明完成

以下必须成为独立的行为断言/场景；至少记录输入、预期、实际和对应测试名，不能只断言源码字符串或helper被调用：

- [ ] CLI --help成功且无removed commands
```

### `plans/phase1/cards/P1-46.md`

P46 REST outline only; no invented MCP transport.

L32–L41

```text

1. PageIndex在本fork通过既有rag调用outline；metadata retrieval_kind=outline且用户/模型说明只是概览。
2. 去掉mcp_pageindex_*的运行指令和不存在自动接入承诺。
3. 无目录/服务故障不伪造查询命中；LlamaIndex等检索行为不变。

## 证据：如何证明完成

以下必须成为独立的行为断言/场景；至少记录输入、预期、实际和对应测试名，不能只断言源码字符串或helper被调用：

- [ ] PageIndex-only能挂真实可用rag
```

L26–L35

```text

符号范围：PageIndex挂载/rag过滤、_pageindex_system_note/REST search metadata和stale capability注释；不建MCP client。

历史单卡模式的证据目录为 `.phase1-evidence/P1-46/` ；阶段模式改用所属 `.phase1-evidence/stages/<stage_id>/` 写共享证据。允许编辑测试不是允许删除有效断言/添加skip。依赖卡文件可以读取；未列文件不得写。

## 执行步骤

1. PageIndex在本fork通过既有rag调用outline；metadata retrieval_kind=outline且用户/模型说明只是概览。
2. 去掉mcp_pageindex_*的运行指令和不存在自动接入承诺。
3. 无目录/服务故障不伪造查询命中；LlamaIndex等检索行为不变。
```

### `web/lib/api.ts`

Existing authenticated fetch wrapper for subject actions.

L76–L85

```text
 */
export async function apiFetch(
  input: RequestInfo | URL,
  init?: RequestInit & { skipAuthRedirect?: boolean },
): Promise<Response> {
  const { skipAuthRedirect, ...fetchInit } = init ?? {};
  const res = await fetch(input, { credentials: "include", ...fetchInit });

  if (
    res.status === 401 &&
```

### `web/lib/knowledge-api.ts`

Legacy detail parser; P42 helper must retain compatibility.

L590–L599

```text

async function readErrorDetail(
  res: Response,
  fallback: string,
): Promise<string> {
  try {
    const body = await res.json();
    if (body?.detail) return String(body.detail);
  } catch {
    // body wasn't JSON; fall through
```

### `deeptutor/api/routers/subjects.py`

Existing export API; export UI must follow this authenticated contract.

L1089–L1098

```text
@router.get("/{subject_id}/export")
async def export_subject_data(subject_id: str, _: None = Depends(require_auth)):
    """Snapshot the current subject into a verified ZIP and return its URL.

    The heavy snapshot/compression runs in a worker thread and only prepares a
    private file; this live request commits the public name after the await.
    If the request is cancelled, the preparation is discarded when its thread
    finishes: no public ZIP and no URL from this attempt survive.
    """
    _require_subject(subject_id)
```

L1125–L1127

```text
        "export_id": result["export_id"],
        "schema_version": export_bundle.SCHEMA_VERSION,
    }
```

### `deeptutor/api/routers/outputs.py`

Actual authenticated download path, scoped to request user.

L18–L27

```text

def _request_path_service() -> PathService:
    """Resolve the workspace installed by ``require_auth`` without fallback.

    The general-purpose ``get_path_service()`` retains a compatibility fallback
    to the local admin workspace for non-request callers.  A download endpoint
    must fail closed instead: otherwise an authentication/context regression
    could expose an administrator artifact to an ordinary request.
    """
    user = get_current_user_or_none()
```

L40–L47

```text
@router.api_route("/{output_path:path}", methods=["GET", "HEAD"])
async def read_output(
    output_path: str,
    _auth: TokenPayload | None = Depends(require_auth),
) -> FileResponse:
    """Serve one allowlisted artifact from the authenticated user's workspace."""
    path = _resolve_output(_request_path_service(), output_path)
    return FileResponse(path)
```

### `deeptutor/services/path_service.py`

Public output allowlist and private-suffix enforcement.

L134–L143

```text

    def resolve_public_output_path(self, path: str | Path) -> Path | None:
        """Return a safe, public output file below this service's user root.

        Resolving and authorizing the path in one operation gives callers the
        exact canonical path they may read.  In particular, callers should not
        validate against one workspace and then reconstruct the file path from
        a different root.
        """
        candidate = Path(path)
```

### `deeptutor/subjects/errors.py`

C02 fixed public error projection, relevant to UI safe messages.

L38–L47

```text

class ErrorCode(str, Enum):
    """C02 表中的全部 code。"""

    INVALID_INPUT = "invalid_input"
    INVALID_SUBJECT_ID = "invalid_subject_id"
    SUBJECT_NOT_FOUND = "subject_not_found"
    ENTRY_NOT_FOUND = "entry_not_found"
    KB_NOT_FOUND = "kb_not_found"
    SCOPE_FORBIDDEN = "scope_forbidden"
```

L333–L342

```text

def map_subject_exception(exc: BaseException) -> SubjectOperationError:
    """把服务端异常映射成 C02 投影；未知异常安全兜底为 ``internal_error``。

    顺序很重要：``LLMReasoningBudgetExhausted`` 是 ``LLMProviderError`` 的子类，
    而 ``LLMEmptyResponseError`` **不是** ``LLMProviderError`` 的子类，两者都必须
    在各自的基类之前判断。

    这里**不猜**：泛型 ``ValueError``/``TypeError``/``KeyError`` 以及类名里带
    "timeout" 的普通异常都不是领域依据，一律按 :data:`ErrorCode.INTERNAL_ERROR`
```

L392–L401

```text

def to_http_payload(error: SubjectOperationError) -> dict[str, Any]:
    """HTTP 投影：保留旧 ``detail: string``，增加结构化 ``error``。"""
    return {"detail": error.message, "error": to_error_dict(error)}


def to_ws_error_metadata(error: SubjectOperationError) -> dict[str, Any]:
    """WS terminal error / DONE failed 的 metadata 片段。"""
    return to_error_dict(error)

```

### `web/scripts/run-node-tests.mjs`

Actual node test compilation and discovery entrypoint.

L11–L20

```text

function run(cmd, args) {
  const result = spawnSync(cmd, args, {
    cwd: webRoot,
    stdio: "inherit",
    env: process.env,
  });
  if (result.status !== 0) {
    process.exit(result.status ?? 1);
  }
```

L22–L31

```text

function collectTests(dir) {
  const entries = readdirSync(dir)
    .map((name) => path.join(dir, name))
    .sort((a, b) => a.localeCompare(b));
  const files = [];
  for (const entry of entries) {
    const stats = statSync(entry);
    if (stats.isDirectory()) {
      files.push(...collectTests(entry));
```

### `web/package.json`

Node test script entrypoint.

L10–L19

```text
    "lint": "eslint .",
    "test:node": "node ./scripts/run-node-tests.mjs",
    "perf:check": "node ./scripts/route_budgets.mjs",
    "build:perf": "npm run build && npm run perf:check",
    "i18n:parity": "node ./scripts/i18n_parity.mjs",
    "i18n:audit": "node ./scripts/i18n_audit.mjs",
    "i18n:audit:strict": "node ./scripts/i18n_audit.mjs --strict",
    "i18n:check": "npm run i18n:parity && npm run i18n:audit",
    "audit": "playwright test --project=ui-audit",
    "audit:ui": "playwright test --ui --project=ui-audit",
```
