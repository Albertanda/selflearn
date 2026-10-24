# DeepTutor — Agent-Native Architecture

## Overview

DeepTutor is an **agent-native** intelligent learning companion organized
around a two-layer plugin model — single-shot **Tools** invoked by the
LLM, and multi-stage **Capabilities** that take over a turn — exposed
through three entry points: CLI, WebSocket API, and Python SDK.

## Architecture

```
Entry Points:  CLI (Typer)  |  WebSocket /api/v1/ws  |  Python SDK
                    ↓                   ↓                   ↓
              ┌─────────────────────────────────────────────────┐
              │              ChatOrchestrator                    │
              │   routes UnifiedContext → selected Capability    │
              │   (defaults to `chat`)                           │
              └──────────┬──────────────┬───────────────────────┘
                         │              │
              ┌──────────▼──┐  ┌────────▼──────────┐
              │ ToolRegistry │  │ CapabilityRegistry │
              │  (Level 1)   │  │   (Level 2)        │
              └──────────────┘  └────────────────────┘
```

All capabilities emit on a shared `StreamBus`; the orchestrator fans
events out to consumers. Runtime settings live in
`data/user/settings/*.json` — project-root `.env` files are intentionally
ignored.

### Level 1 — Tools

Single-function tools the LLM picks on demand. Four user-toggleable tools
surface in `/settings/tools`:

| Tool           | Description                                   |
| -------------- | --------------------------------------------- |
| `brainstorm`   | Breadth-first idea exploration with rationale |
| `web_search`   | Web search with citations                     |
| `paper_search` | arXiv preprint search                         |
| `reason`       | Dedicated deep-reasoning LLM call             |

The rest are **context-gated**: the chat capability auto-mounts them from
`ToolMountFlags` (presence of a KB, attachments, sandbox availability, …), and
any of them can also be force-enabled via `--tool`. Auto-mounted set: `rag`,
`read_source`, `read_memory`, `write_memory`, `read_skill`, `load_tools`,
`exec`, `code_execution` (sandboxed Python: NL intent → code → run),
`list_notebook`, `write_note`, `web_fetch`, `github`, `cron`,
`ask_user` (pauses the turn and resumes with the user's reply), plus the
mastery-path tools. `geogebra_analysis` is parked under
`COMING_SOON_TOOL_TYPES`.

### Level 2 — Capabilities

Multi-stage pipelines that own the turn:

| Capability       | Stages                                                |
| ---------------- | ----------------------------------------------------- |
| `chat`           | exploring → responding (single agentic loop, default) |
| `mastery_path`   | responding (Guided Learning — chat loop + mastery tools, gated per topic type) |
| `deep_solve`     | planning → reasoning → writing                        |
| `deep_question`  | ideation → generation                                 |
| `deep_research`  | rephrasing → decomposing → researching → reporting    |
| `visualize`      | analyzing → generating → reviewing (SVG / Chart.js / Mermaid / HTML; or routes to Manim sub-stages via `render_type`) |
| `math_animator`  | concept_analysis → concept_design → code_generation → code_retry → summary → render_output |

All capabilities converge on `emit_capability_result()` in
`deeptutor/capabilities/_shared.py` so every turn emits the same envelope
(response payload + `cost_summary` from `UsageTracker`). Status copy and
prompts are i18n'd via `capabilities/prompts/{en,zh}/<name>.yaml`.

## CLI Usage

```bash
# Install
pip install deeptutor      # Full app (CLI + Web/API + packaged Web assets)
pip install deeptutor-cli  # CLI-only

# Preferred fixed-home launcher (works from any cwd; overrides inherited DEEPTUTOR_HOME)
./scripts/start_selflearn.sh

# Run any capability
deeptutor run chat "Explain Fourier transform"
deeptutor run deep_solve "Solve x^2=4" -t rag --kb my-kb
deeptutor run visualize "Animate sine wave" --config render_mode=manim_video

# Interactive REPL
deeptutor chat
# (inside the REPL: /regenerate or /retry re-runs the last user message)

# Knowledge bases, memory, server
deeptutor kb list
deeptutor kb create my-kb --doc textbook.pdf
deeptutor memory show
deeptutor serve --port 8001       # API server only
deeptutor start                   # backend + frontend together
```

## Key Files

| Path                                       | Purpose                              |
| ------------------------------------------ | ------------------------------------ |
| `deeptutor/runtime/orchestrator.py`        | `ChatOrchestrator` — unified entry   |
| `deeptutor/runtime/launcher.py`            | Backend + frontend lifecycle / port discovery |
| `deeptutor/runtime/registry/`              | Tool + Capability registries         |
| `deeptutor/runtime/bootstrap/builtin_capabilities.py` | Built-in capability class paths |
| `deeptutor/services/config/runtime_settings.py` | JSON settings + process-env overrides |
| `deeptutor/core/stream.py`, `stream_bus.py` | StreamEvent protocol + async fan-out |
| `deeptutor/core/tool_protocol.py`          | `BaseTool` + `ToolDefinition`         |
| `deeptutor/core/capability_protocol.py`    | `BaseCapability` + `CapabilityManifest` |
| `deeptutor/core/context.py`                | `UnifiedContext` dataclass            |
| `deeptutor/tools/builtin/__init__.py`      | All built-in tool wrappers           |
| `deeptutor/capabilities/`                  | Built-in capability implementations  |
| `deeptutor/app.py`                         | `DeepTutorApp` — Python SDK facade    |
| `deeptutor_cli/main.py`                    | Typer CLI entry point                |
| `deeptutor/api/routers/unified_ws.py`      | Unified WebSocket endpoint           |

## Dependency Layers

Public install paths and source extras are defined in `pyproject.toml`.
Requirements files mirror the same dependency groups for Docker/CI installs.

```
pip install deeptutor      — Full app (CLI + Web/API + packaged Web assets)
pip install deeptutor-cli  — CLI-only (LLM + RAG + providers + document parsing)
pip install -e .           — Source install for development

Source extras (.[ extra ], defined in pyproject.toml):
.[cli]            — CLI-only dependency set
.[server]         — Web/API server dependencies
.[math-animator]  — Manim addon (powers `visualize` Manim renders + `deeptutor run math_animator`)
.[dev]            — Test / lint tooling
.[all]            — Server + math-animator + dev tools
```

## Current Fork Differences

- The Partner (IM companion) runtime and the Book command are not part of this
  fork: `deeptutor partner` and `deeptutor book` are not registered. Use upstream
  DeepTutor if those features are required.
- The `.[partners]`, `.[tutorbot]`, `.[matrix]` and `.[matrix-e2e]` extras and
  their requirements mirrors are removed. `requirements.txt` installs the
  supported `requirements/server.txt` profile.
- PageIndex is available through the existing RAG outline pipeline
  (`retrieval_kind=outline`); this fork has no PageIndex MCP transport. The MCP
  SDK stays as a compatibility dependency pending review.
- `scripts/start_selflearn.sh` is the supported fixed-home launcher: it resolves
  this checkout from the script path, overrides inherited `DEEPTUTOR_HOME`, changes
  to the checkout and execs its `.venv/bin/deeptutor start --home <checkout>`.
  It rejects caller `--home`/`--home=` and makes missing venv/CLI a named failure.
  `deeptutor/runtime/home.py` itself still falls back to cwd when no explicit
  home/env is supplied; do not describe that global behavior as fixed.
- Document upload (`index`) and audio upload (`transcribe`) are different: audio
  transcripts go to `materials/lecture` and do not auto-build an index.
  Image coverage that is unmeasured/skipped must not be reported as complete.
  Knowledge points without attempt evidence are `mastery=null` / unassessed.
  Subject export excludes chat history and offers no import/restore.
- Learner facts are extracted only by the subject-scoped chat history summarizer
  (`services/session/summarize.py` via `api/routers/chat.py`); uploads and subject
  endpoints do not extract new profile facts automatically.
- The report-only chart/ODE executor requires its qualified bwrap-backed boundary;
  unavailable/unsupported backends return 503 with no host fallback. The normal
  shared sandbox runner is not proof of report isolation. S13/P50 OS, S14
  HTTP/WS and S15 Chromium browser gates have passed locally with deterministic
  model fixtures. Phase 1 is closed; there is no S16 or automatic Phase 2.
  There is no live-provider/deployment claim. The user approved one catalog
  integrity exception; see plans/phase1/data_baseline_exception.json. The old
  configuration has not been restored. See plans/phase1/PHASE1_ACCEPTANCE.md.

## Isolated Python tests

Use `.venv/bin/python scripts/run_tests_isolated.py [pytest arguments]`. With no arguments it runs the configured full suite. Direct unisolated collection fails before application imports; do not bypass the guard. Preserve both historical data evidence and the explicitly approved S14 catalog exception baseline. The runner separately pins current opaque inventories before bootstrap and checks all six trees after tests; any change during the run fails. Legitimate user activity after phase closure is not a reason to restore old data or rewrite historical receipts.

## Browser evidence preservation

The S15 Playwright configuration refuses sealed evidence directories. An explicitly requested rerun must set `S15_EVIDENCE_DIR` to a fresh directory under this checkout’s `.phase1-evidence/`; reuse the installed browser and isolated source runner. Never point `S15_SOURCE_COPY` at this checkout, its ancestors, or existing data. Read-only handoff instructions and verified source excerpts are in `plans/phase1/PHASE1_HANDOFF.txt`.

## Live LLM test preference

For an explicitly requested, bounded external LLM smoke after the CP-R1 migration, `agnes-3.0-flash` on the existing Agnes connection is an approved test option. This is not permission to route the automated test suite, background jobs, or default model through Agnes. Use only synthetic prompts, make at most three inference calls, keep `max_tokens` at 64 or below, disable retries, use a timeout of at most 45 seconds, and never fall back to another paid provider. The isolated fixtures remain the default for all automated tests. See `scripts/agnes_llm_smoke.py` and `plans/custom-providers-r1/CONTRACTS.md` C7.
