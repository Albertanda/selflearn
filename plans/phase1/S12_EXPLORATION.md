# S12 已探索文件与关键片段

本文件由 `.phase1-evidence/reviews/S11-final/build_s12_packet.py` 生成。哈希对应生成时工作树字节；片段保留原始行，行号为一基。此包不授权扩大任务范围。

## 阶段目标与边界

阶段 `S12`：启动、文档和lint收尾；顺序 P1-47 → P1-48；合同：C01, C13, C14。允许路径按 `stages.json` 动态读取并展开，新增补充路径也会进入索引。

P1-47 只更新活跃文档、Compose 注释和固定 home 启动 wrapper。wrapper 限定启动命令，从脚本位置推导仓库根，覆盖继承的 `DEEPTUTOR_HOME`，切换到仓库根并执行根 `.venv/bin/deeptutor start --home <repo>`；拒绝透传 `--home` 或 `--home=...`，缺失 venv/CLI 时明确报错。不得改 Compose 数据挂载/网络或历史上游归档。行为验收包括临时目录 fake CLI、缺 venv 报错、README 命令对照真实 CLI、UPSTREAM/资产 README 字节不变，以及说明未验收的 live provider。

P1-48 只清理当前 Ruff 的 3 个 I001 与 1 个 E741；只排序 import 和重命名局部变量，不做业务重构、不改 Ruff 忽略规则，保留延迟导入循环。

## 范围快照

原始模式 16 项，当前展开 29 个存在文件，3 个缺失路径/模式。缺失路径：plans/phase1/ENVIRONMENT.md, scripts/start_selflearn.sh, tests/phase1/test_p1_47.py。

| 文件 | SHA-256 | 字节 |
|---|---|---:|
| `AGENTS.md` | `9e6383e81df83ada2cec8539241bba7c912a03760a6cc70c2fbb1f0027e33395` | 7525 |
| `CONTAINERIZATION.md` | `bb9937ee609e6e21d1b9b353d849e032dfc58f328afdd6fb52e4a86e0854c867` | 20986 |
| `HANDOVER.md` | `e8ef1c40fd08553b2ae6e98a9627ec0d91335fe6f7a0bf079e8d13e75e16ae6f` | 51338 |
| `README.md` | `9bc184746afec0d8d7eaf75269c8a7ec69659d6e328e9251bfe2e6cb3ba954ad` | 4923 |
| `deeptutor/api/routers/chat.py` | `4f98f57993afcccf24da3174a88565c1533b4214ad96df88402805ee32af765c` | 14732 |
| `deeptutor/api/routers/subjects.py` | `adae1fb5bfadd9921adec8765e2432b1d8d3b57347afc5ce845da3face9e7816` | 42205 |
| `deeptutor/services/pdf/review_guide.py` | `29ea75717050b2673abc34c7442b2095c3f1fb750c1180100e0e061c287cb71c` | 9416 |
| `deeptutor/services/session/summarize.py` | `87353296c6bdf8491565405fc133d737994de9ed13ddd38de8d12080a719893e` | 2608 |
| `deeptutor/services/session/turn_runtime.py` | `6d138673b31ee786692f8e96c8ccc20a42efa610c14ddfdfc9b1bde5953d42fe` | 128886 |
| `deeptutor/services/storage/attachment_store.py` | `cd4fab7e0c8cf46907a9d4f75b55312bfdb464a7b077d94dcf4e56ebd164cfbc` | 9715 |
| `deeptutor/subjects/__init__.py` | `3720d6ce6bf4dfe5ab4794262547d46952875d6e8be9b2323b742c8f3bed0579` | 1055 |
| `deeptutor/subjects/errors.py` | `fd99442eb26315e3308bc2de9ad1bc0ea8649cdc17301bb1270765b941809b88` | 16060 |
| `deeptutor/subjects/exam_detection.py` | `2dbd47a9d4fc17d1ea1e3f60bc682691e1917ec2a5d4ab8fbdb95418e07468d7` | 14736 |
| `deeptutor/subjects/exam_points.py` | `00dd69bb8f4664a083aeabdefe47727ad2f101eccd632664666996283d8ab6d9` | 21060 |
| `deeptutor/subjects/export_bundle.py` | `295ef59c214038147ac8f1bf1b33211253122fbc5e28017d8358ec36c2dfdc53` | 28247 |
| `deeptutor/subjects/generation.py` | `831c50decd82ee2977e2e3046346044d7ab7f08659cd25c79070d015f63969bc` | 4556 |
| `deeptutor/subjects/grading.py` | `df4cb6d93606ca37615b957500a5d5195919d43af2edbb0efa4c95a3e24f12d9` | 7921 |
| `deeptutor/subjects/json_store.py` | `719522ccfe3b3981579fe5111759348b482a64b78e794efa81dc8d7fb014e2ca` | 28455 |
| `deeptutor/subjects/kb_scope.py` | `aae7a7a65662a6a7fdb6bf4d95b57095242b243be5fb1febf492c88ed2208eee` | 30367 |
| `deeptutor/subjects/knowledge_points.py` | `516d25402d055d3f2140d69b1cd7ef489c23056d5f7a90e35282e944606e7adc` | 17210 |
| `deeptutor/subjects/material_manifest.py` | `d80aaf5e653ff411d292001ef945b919fd5998d15793f5c303700883f422c79b` | 32015 |
| `deeptutor/subjects/model_output.py` | `7ebe1f77d497ed3dcf11914540f14e4d83d026160e3165d7311dc1a2c95e77f8` | 9741 |
| `deeptutor/subjects/profile.py` | `63cfe7f9ac7e5471e5072c2ce925469dea1a9eaf953eb82fc9d6c08d5a151c4a` | 6982 |
| `deeptutor/subjects/store.py` | `0a3d04dfdc9bb188a7e0caa1027aaf84c8dfbcabd96e1d9f7f927e165254eeff` | 24650 |
| `deeptutor/subjects/subject_operations.py` | `0fa585abebe8ef8a1fc11e6e80508222014fb5edbad620322bb048a87b8282e0` | 10491 |
| `deeptutor/subjects/uploads.py` | `77e5a3aff42168bdf665693d5aea4bb92befff2fa373ceb6fb9a0f64dd7c54a1` | 53387 |
| `deeptutor/subjects/wrong_book.py` | `b72c7128802572431a712cbc87cff54d4096af2e230a9889b1414dc4833db4e5` | 18088 |
| `docker-compose.ghcr.yml` | `4cb2566e3e129a9c7670b74f6e6919263e15f1869d7fb26993af9edf13103874` | 3067 |
| `docker-compose.yml` | `26b8605c7ec16db8e71426ffd227dd673feb20e9e0765e9e39d64a15f7ed5dd2` | 7975 |

## 只读参考文件

以下不因出现在探索包而获得写权限。

| 文件 | SHA-256 | 字节 |
|---|---|---:|
| `plans/phase1/stages/S12.md` | `da748e0b1d8cc1aff306aa4b7fb2c29df3f1d9f42d2d5e182a6d7b436221fc60` | 2920 |
| `plans/phase1/cards/P1-47.md` | `d810ef35044f8e690ff26fd7aeb5283011c50e7da89c4de865834d2ac8be9639` | 4523 |
| `plans/phase1/cards/P1-48.md` | `ead96b734c0b181ba3c5406eaf29c1cd80f17f924e95a1f9da14fbf48d08d274` | 3850 |
| `plans/phase1/FRAMEWORK.md` | `9190d8ad2f513a1fef09020c98d6bd8816274834cf9a2d8c75abae6397cc77f1` | 10573 |
| `plans/phase1/EXECUTION_GUIDE.md` | `eb688596ef5409a2b1c6dcbc92d4f30304102bb0a176df21d0ea375b30acb03e` | 2575 |
| `plans/phase1/STAGE_WORKFLOW.md` | `34f378797cde73adbcebd856ad37a7c6bd3b408aba68903a22997d2ac88745b0` | 9143 |
| `plans/phase1/DATA_CONTRACTS.md` | `05a0a376ca08b64020f61de9f5ef50171eee7d9142e9fb6abfcd7adff81e9862` | 31470 |
| `deeptutor/runtime/home.py` | `3a352f23e409a33670c3d00d513c0b50f0510f625d596ef42e838fb04b2513e3` | 1675 |
| `deeptutor/runtime/launcher.py` | `96a0994d06a955d48cadb942b7bcf019aa397079a657befcf7ef7940694d9c4d` | 40153 |
| `deeptutor_cli/main.py` | `b6d90b2d8977d55e9bd040c7525cf3cc90f91ab2f0a237ad16821a931fe90ea4` | 6397 |
| `deeptutor_cli/__main__.py` | `9ab4e0d9f41bd42c75751deb7c80dd75dad0e1672cb899796b9d8d88d18c7e78` | 114 |
| `deeptutor/__main__.py` | `3beb91b1a3e9f2a0882e85aa77e9ff8bbf8d913e831ccf49876ea3010c3604d8` | 129 |
| `pyproject.toml` | `25e77bb50f30ee18891f1d186d3551cd1ad684c8aab1eb47060c4ee4ffd35337` | 16482 |
| `README.md` | `9bc184746afec0d8d7eaf75269c8a7ec69659d6e328e9251bfe2e6cb3ba954ad` | 4923 |
| `AGENTS.md` | `9e6383e81df83ada2cec8539241bba7c912a03760a6cc70c2fbb1f0027e33395` | 7525 |
| `HANDOVER.md` | `e8ef1c40fd08553b2ae6e98a9627ec0d91335fe6f7a0bf079e8d13e75e16ae6f` | 51338 |
| `CONTAINERIZATION.md` | `bb9937ee609e6e21d1b9b353d849e032dfc58f328afdd6fb52e4a86e0854c867` | 20986 |
| `docker-compose.yml` | `26b8605c7ec16db8e71426ffd227dd673feb20e9e0765e9e39d64a15f7ed5dd2` | 7975 |
| `docker-compose.ghcr.yml` | `4cb2566e3e129a9c7670b74f6e6919263e15f1869d7fb26993af9edf13103874` | 3067 |
| `Dockerfile` | `e0950f5a754c1dc6d6b92eaa8b33b442cdfbba7d006a3def484fe5022b5395f0` | 19328 |
| `PROJECT_AUDIT_2026-10-10.md` | `4d70cc92fd0ec75c3ca285ee98fb9f14caec92900154f9900724d20c0ba48120` | 22666 |
| `tests/cli/test_docs_contract.py` | `b598405c9738dfb91be49f6401b6789763bb62894ee59f2880791996979f51a9` | 3791 |
| `tests/runtime/test_launcher.py` | `3730f1de6ed3d9c848635749348670ca530e3ca90b4c2ffae7f59eb1b49f961a` | 17560 |
| `tests/runtime/test_api_import_memory_boundary.py` | `7b24529e6dac4ec54800a2dfcc29d0ce0f97ee7eeca8280c371c919adeeb4ff3` | 812 |
| `deeptutor/services/session/summarize.py` | `87353296c6bdf8491565405fc133d737994de9ed13ddd38de8d12080a719893e` | 2608 |
| `.phase1-evidence/reviews/S11-final/environment_observation.json` | `bd7fb89a33470ecb847eff4df7f8dedda04c8bfc3f8bea48d235f5fcb6ba8878` | 464 |
| `UPSTREAM.md` | `cf9bfada3bee8ef3f52cfa43ae4751f393ebe8d22c8fc3f4e07ded1e46b29cff` | 66387 |
| `assets/README/README_CN.md` | `8be05c64626c790daca7202a5dfa381f6f92b7fa44f759a8ab379491f301266e` | 49439 |

## 环境工具与字体资产

S11-final 的 `environment-observation` benign 命令记录了 Python 3.12.14、Node 22.22.1、Typst 0.15.1；版本号引用该证据，不运行生成器来探测环境。

- `tools/bin/typst`：存在；bytes=55739488；sha256=29273eaa04f6d00edd0c2bec578f565fc9c65be856bfbffc894567c68ed0b237
- `tools/fonts/SimsunExtG.ttf`：存在；bytes=3549508；sha256=9cadcd0ab3d549446b51001d9896773d87ad012d93d842532f321eca514bffd8
- `tools/fonts/msyh.ttc`：存在；bytes=19704352；sha256=d79c55e68b1131eea0cc1c47be4f572d964f28c682e143db2ad09c1e4cb07a3f
- `tools/fonts/simhei.ttf`：存在；bytes=9745792；sha256=9b1959db3b3abeb7efdaec26edf7dfe871a6039de8d614af7248575207be629e

## 关键定位片段

### 1. `AGENTS.md:135-143`（定位词 ``deeptutor partner` and `deeptutor book` are not registered`）

```text

- The Partner (IM companion) runtime and the Book command are not part of this
  fork: `deeptutor partner` and `deeptutor book` are not registered. Use upstream
  DeepTutor if those features are required.
- The `.[partners]`, `.[tutorbot]`, `.[matrix]` and `.[matrix-e2e]` extras and
  their requirements mirrors are removed. `requirements.txt` installs the
  supported `requirements/server.txt` profile.
- PageIndex is available through the existing RAG outline pipeline
  (`retrieval_kind=outline`); this fork has no PageIndex MCP transport. The MCP
```

### 2. `AGENTS.md:141-144`（定位词 `retrieval_kind=outline`）

```text
  supported `requirements/server.txt` profile.
- PageIndex is available through the existing RAG outline pipeline
  (`retrieval_kind=outline`); this fork has no PageIndex MCP transport. The MCP
  SDK stays as a compatibility dependency pending review.
```

### 3. `AGENTS.md:141-144`（定位词 `MCP transport`）

```text
  supported `requirements/server.txt` profile.
- PageIndex is available through the existing RAG outline pipeline
  (`retrieval_kind=outline`); this fork has no PageIndex MCP transport. The MCP
  SDK stays as a compatibility dependency pending review.
```

### 4. `CONTAINERIZATION.md:149-157`（定位词 `data/partners`）

```text
(`data/user`, `data/memory`, `data/knowledge_bases`), so everything else —
`data/system` (the JWT signing secret, accounts, grants, audit log, per-owner
Codex tokens), `data/users` (per-user workspaces), `data/partners`,
`data/cli-apps` — lived in the container's writable layer and was discarded
on every recreate. It now mounts the whole tree, matching
`docker-compose.yml` and `compose.yaml`.

**Before your first `up -d` after upgrading**, copy that state out of the
running container, or the empty host directories shadow it and DeepTutor
```

### 5. `CONTAINERIZATION.md:150-158`（定位词 `cli-apps`）

```text
`data/system` (the JWT signing secret, accounts, grants, audit log, per-owner
Codex tokens), `data/users` (per-user workspaces), `data/partners`,
`data/cli-apps` — lived in the container's writable layer and was discarded
on every recreate. It now mounts the whole tree, matching
`docker-compose.yml` and `compose.yaml`.

**Before your first `up -d` after upgrading**, copy that state out of the
running container, or the empty host directories shadow it and DeepTutor
regenerates the auth secret (logging everyone out) and starts with no
```

### 6. `HANDOVER.md:398-406`（定位词 `残留 10 处 `I001``）

```text
### 8.6 已知的非阻塞噪音

- **ruff**：残留 10 处 `I001`（import 排序）、1 处 `E741`（`summarize.py:71` 变量名 `l`）、3 处上游既有 `F841`（未使用变量）。属**上游遗留**，明确不在本项目修复范围。
- **SiliconFlow embedding 偶发 `ReadTimeout`**：日志里会看到重试警告，自动重试可恢复，但会让索引耗时从几十秒变成几分钟。**不是 bug**。

---

## 9. 改动全貌

```

### 7. `HANDOVER.md:304-312`（定位词 `回退到「当前工作目录」`）

```text
### 7.2 数据根目录的陷阱（**极易踩**）

数据根目录的解析顺序是：`DEEPTUTOR_HOME` 环境变量 → **未设置则回退到「当前工作目录」**。

> 🔴 **因此：必须在仓库根目录 `/home/albert/selflearn/selflearn` 下启动服务。** 从其它目录启动会**静默**在别处创建一棵空数据树，表现为"我的科目/知识库全不见了"，而实际数据完好。

### 7.3 数据目录结构

```
```

### 8. `README.md:26-34`（定位词 `./.venv/bin/deeptutor start`）

```text
```bash
# 方式一（推荐）：一条命令同时拉起后端 + 前端
./.venv/bin/deeptutor start

# 方式二：分开启动
# 后端（8001）
source .venv/bin/activate
PYTHONPATH=$PWD python -m uvicorn deeptutor.api.main:app --host 0.0.0.0 --port 8001

```

### 9. `README.md:40-48`（定位词 `回退为**当前工作目录**`）

```text
浏览器打开 `http://localhost:3782`（认证默认关闭，单用户模式）。

> **注意**：请在仓库根目录启动。数据根目录取自环境变量 `DEEPTUTOR_HOME`，未设置时回退为**当前工作目录**——从别的目录启动会静默生成一个空数据树，看不到已有科目。

### 环境准备

```bash
# Python 3.11–3.13（项目不支持 3.14）
python3.12 -m venv .venv
```

### 10. `README.md:79-87`（定位词 `Typst v0.15.1`）

```text
```bash
mkdir -p tools/bin tools/fonts
# Typst v0.15.1（静态 musl 版）
curl -L -o /tmp/typst.tar.xz https://github.com/typst/typst/releases/download/v0.15.1/typst-x86_64-unknown-linux-musl.tar.xz
tar -xJf /tmp/typst.tar.xz -C /tmp/ && cp /tmp/typst-x86_64-unknown-linux-musl/typst tools/bin/
# 中文字体（Windows 源码或任意 CJK 字体均可；代码默认读取 tools/fonts/SimsunExtG.ttf 与 msyh.ttc）
cp /mnt/c/Windows/Fonts/SimsunExtG.ttf /mnt/c/Windows/Fonts/msyh.ttc tools/fonts/ 2>/dev/null || true
```

```

### 11. `deeptutor/api/routers/chat.py:1-7`（定位词 `"""`）

```text
"""
Chat API Router
================

WebSocket endpoint for lightweight chat with session management.
REST endpoints for session operations.
"""
```

### 12. `deeptutor/api/routers/subjects.py:1-7`（定位词 `"""Subjects — subject-scoped learning data (M1).`）

```text
"""Subjects — subject-scoped learning data (M1).

Routes: subject CRUD, per-subject knowledge bases (upload → index → query).
Knowledge indexing reuses the LlamaIndex pipeline through the same
``KnowledgeBaseInitializer`` / ``run_initialization_task`` machinery as the
global knowledge center, but bound to ``data/subjects/<id>/knowledge_bases``.
"""
```

### 13. `deeptutor/services/pdf/review_guide.py:1-7`（定位词 `"""Review-pack generation (M6) — aggregate the subject's exam points,`）

```text
"""Review-pack generation (M6) — aggregate the subject's exam points,
wrong-question book and knowledge map into a printable review guide.

Pipeline: aggregate data -> LLM writes Markdown (Unicode math, no LaTeX)
-> renderer emits PDF (Typst) or DOCX (python-docx).
"""

```

### 14. `deeptutor/services/session/summarize.py:52-60`（定位词 `summary_lines`）

```text

def _parse(raw: str) -> tuple[str, list[str]]:
    summary_lines: list[str] = []
    facts: list[str] = []
    in_facts = False
    for line in raw.splitlines():
        line = line.strip()
        if line.startswith("新事实"):
            in_facts = True
```

### 15. `deeptutor/services/session/summarize.py:69-72`（定位词 `"\n".join(l for l in summary_lines if l)`）

```text
        if line.startswith("- ") or line.startswith("摘要"):
            summary_lines.append(line.lstrip("- ").strip())
    summary = "\n".join(l for l in summary_lines if l)
    return summary, facts
```

### 16. `deeptutor/services/session/turn_runtime.py:1-7`（定位词 `"""`）

```text
"""
Turn-level runtime manager for unified chat streaming.
"""

from __future__ import annotations

import asyncio
```

### 17. `deeptutor/services/storage/attachment_store.py:1-7`（定位词 `"""Persistent storage for chat attachments.`）

```text
"""Persistent storage for chat attachments.

The chat turn runtime writes the bytes of every uploaded attachment here
*before* the document extractor runs. Once persisted, the URL is recorded on
the message and the in-memory base64 is dropped (extractor still clears it
for office docs to save DB space). The frontend later fetches the original
file via the :mod:`deeptutor.api.routers.attachments` endpoint to render a
```

### 18. `deeptutor/subjects/__init__.py:6-14`（定位词 `from __future__ import annotations`）

```text
"""

from __future__ import annotations

#: Generation budget for the subject-feature LLM calls (M3 grading, M4
#: detection, M6 review guides, M7 reports).
#:
#: These calls target instruction models, but the everyday model may be a
#: *reasoning* model (e.g. DeepSeek ``deepseek-flash``), whose chain-of-thought
```

### 19. `deeptutor/subjects/errors.py:22-30`（定位词 `from __future__ import annotations`）

```text
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import re
from typing import Any, Mapping
```

### 20. `deeptutor/subjects/exam_detection.py:30-38`（定位词 `from __future__ import annotations`）

```text
"""

from __future__ import annotations

import re

from deeptutor.services.llm.config import get_llm_config
from deeptutor.subjects import model_output
from deeptutor.subjects.errors import SubjectOperationError, map_subject_exception
```

### 21. `deeptutor/subjects/exam_points.py:25-33`（定位词 `from __future__ import annotations`）

```text
"""

from __future__ import annotations

from pathlib import Path
import re
import time
import uuid

```

### 22. `deeptutor/subjects/export_bundle.py:24-32`（定位词 `from __future__ import annotations`）

```text
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
```

### 23. `deeptutor/subjects/generation.py:16-24`（定位词 `from __future__ import annotations`）

```text
"""

from __future__ import annotations

from typing import Any

from deeptutor.services.llm.exceptions import (
    LLMEmptyResponseError,
    LLMReasoningBudgetExhausted,
```

### 24. `deeptutor/subjects/grading.py:28-36`（定位词 `from __future__ import annotations`）

```text
"""

from __future__ import annotations

from dataclasses import dataclass

from deeptutor.services.llm.config import get_llm_config
from deeptutor.subjects.errors import (
    SubjectOperationError,
```

### 25. `deeptutor/subjects/json_store.py:50-58`（定位词 `from __future__ import annotations`）

```text
"""

from __future__ import annotations

from contextlib import contextmanager
import copy
from dataclasses import dataclass
import errno
import json
```

### 26. `deeptutor/subjects/kb_scope.py:34-42`（定位词 `from __future__ import annotations`）

```text
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import re
from typing import Any, Iterable, Sequence
```

### 27. `deeptutor/subjects/knowledge_points.py:8-16`（定位词 `from __future__ import annotations`）

```text
"""

from __future__ import annotations

from pathlib import Path
import time
import uuid

from deeptutor.subjects import json_store, store
```

### 28. `deeptutor/subjects/material_manifest.py:20-28`（定位词 `from __future__ import annotations`）

```text
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
```

### 29. `deeptutor/subjects/model_output.py:15-23`（定位词 `from __future__ import annotations`）

```text
"""

from __future__ import annotations

import json
import math
import re
from typing import Any

```

### 30. `deeptutor/subjects/profile.py:11-19`（定位词 `from __future__ import annotations`）

```text
"""

from __future__ import annotations

from pathlib import Path
import time

from deeptutor.subjects import json_store, store

```

### 31. `deeptutor/subjects/store.py:31-39`（定位词 `from __future__ import annotations`）

```text
"""

from __future__ import annotations

from contextlib import contextmanager
import os
from pathlib import Path
import re
import shutil
```

### 32. `deeptutor/subjects/subject_operations.py:24-32`（定位词 `from __future__ import annotations`）

```text
"""

from __future__ import annotations

from dataclasses import dataclass, field
import errno
import os
from pathlib import Path
import stat
```

### 33. `deeptutor/subjects/uploads.py:26-34`（定位词 `from __future__ import annotations`）

```text
"""

from __future__ import annotations

import asyncio
from contextlib import contextmanager
from dataclasses import dataclass, field
import hashlib
import logging
```

### 34. `deeptutor/subjects/wrong_book.py:14-22`（定位词 `from __future__ import annotations`）

```text
"""

from __future__ import annotations

from pathlib import Path
import time
import uuid

from deeptutor.learning.mastery import compute_mastery
```

### 35. `docker-compose.ghcr.yml:55-63`（定位词 `./data:/app/data`）

```text
      # layout needs a one-time copy out of the running container first; see
      # CONTAINERIZATION.md → "One-time migration".
      - ./data:/app/data

    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:${DEEPTUTOR_DOCKER_BACKEND_PORT:-8001}/"]
      interval: 30s
      timeout: 10s
      retries: 3
```

### 36. `docker-compose.ghcr.yml:51-59`（定位词 `data/partners`）

```text
      # This used to mount only data/user, data/memory and data/knowledge_bases,
      # which left data/system (auth secret, accounts, grants, per-owner Codex
      # tokens), data/users, data/partners and data/cli-apps in the container's
      # writable layer — discarded on every recreate. Upgrading from that
      # layout needs a one-time copy out of the running container first; see
      # CONTAINERIZATION.md → "One-time migration".
      - ./data:/app/data

    healthcheck:
```

### 37. `docker-compose.yml:66-74`（定位词 `data/partners`）

```text
      # Everything DeepTutor persists lives under ./data — one tree to mount
      # and back up: admin workspace + runtime settings (data/user), per-user
      # workspaces (data/users), partners (data/partners), accounts/grants/
      # audit (data/system), knowledge bases, memory.
      # The sandbox-runner gets a narrower slice of this volume: never
      # data/system, which holds auth state, provider API keys, and per-owner
      # secrets. What it *does* carry for non-admin accounts is wider than
      # workspace subtrees — see the scope note on that service's own volumes.
      - ./data:/app/data
```

### 38. `docker-compose.yml:72-80`（定位词 `./data:/app/data`）

```text
      # secrets. What it *does* carry for non-admin accounts is wider than
      # workspace subtrees — see the scope note on that service's own volumes.
      - ./data:/app/data

    environment:
      # Route untrusted shell exec to the runner sidecar (SYSTEM isolation).
      # When this is set, the main app NEVER runs untrusted code in its own
      # process — see deeptutor/services/sandbox/config.py:build_backend().
      # On bare-metal / macOS deployments where the runner is not started, leave
```

### 39. `plans/phase1/stages/S12.md:1-1`（定位词 `# S12`）

```text
# S12：启动、文档和lint收尾
```

### 40. `plans/phase1/stages/S12.md:5-13`（定位词 `## 目标与前置`）

```text
按STAGE_WORKFLOW.md执行。小卡是阶段内编码单元，不是人工交接关口；完成一单元本地验证后继续本阶段下一单元，阶段末一次提交审查。

## 目标与前置

完成 启动、文档和lint收尾 的现有修复，契约 C01, C13, C14。
跨阶段依赖：S03, S04, S06, S07, S09, S10, S11；当前source需与相应review receipt一致。

## 实施顺序与范围

```

### 41. `plans/phase1/stages/S12.md:12-12`（定位词 `## 实施顺序与范围`）

```text
## 实施顺序与范围
```

### 42. `plans/phase1/stages/S12.md:31-39`（定位词 `scripts/start_selflearn.sh`）

```text
- `docker-compose.yml`
- `plans/phase1/ENVIRONMENT.md`
- `scripts/start_selflearn.sh`
- `tests/phase1/test_p1_47.py`

## 证据与完成条件

- 开始前留阶段source/data基线；阶段内逐单元使用定向测试，不重复读取全部仓库与全部卡。
- 有效负例先从合法正例只改变目标字段/故障点；错误响应不回显输入值；高风险单元用独立坏对照确认断言能拦缺陷。
```

### 43. `plans/phase1/cards/P1-47.md:1-7`（定位词 `# P1-47`）

```text
# P1-47：修正活跃文档与固定启动数据根

状态：planned；类型：python；审阅风险：normal。依赖：P1-25, P1-27, P1-37, P1-41, P1-44, P1-45, P1-46。

## 目标

启动不会误落新空数据树，说明清楚本阶段能力/限制及重建产物要求。
```

### 44. `plans/phase1/cards/P1-47.md:36-44`（定位词 `DEEPTUTOR_HOME固定正确root`）

```text
## 执行步骤

1. wrapper根据脚本所在repo解析home，export DEEPTUTOR_HOME固定正确root，使用该root .venv deeptutor；不硬编码本机账号。
2. 更新当前路径、支持extras、PageIndex outline、图片覆盖、backup exclusions、事实提取入口差异、sandbox前置条件。
3. 环境文档记录实际版本和Typst/font路径hash，不拷贝密钥/二进制，不创建完整Python依赖锁或升级。
4. HANDOVER保留历史自述并加修复/验收入口，不篡改当时测试记录。

## 证据：如何证明完成

```

### 45. `plans/phase1/cards/P1-47.md:45-53`（定位词 `从tmp调用wrapper的fake CLI`）

```text
以下必须成为独立的行为断言/场景；至少记录输入、预期、实际和对应测试名，不能只断言源码字符串或helper被调用：

- [ ] 从tmp调用wrapper的fake CLI得到正确home/cwd
- [ ] 缺venv明确报错
- [ ] README命令可对照源码、无removed extras
- [ ] 历史UPSTREAM/assets README字节不变
- [ ] ENVIRONMENT明确哪些live provider未验收

执行命令（从项目根开始；带 cd web 的条目为独立命令，不延续前一条 cwd）：
```

### 46. `plans/phase1/cards/P1-48.md:1-7`（定位词 `# P1-48`）

```text
# P1-48：清零明确的业务目录lint基线

状态：planned；类型：lint；审阅风险：normal。依赖：P1-06, P1-08, P1-14, P1-37, P1-39, P1-47。

## 目标

当前3个I001/1个E741清零，新增subject修复不引入新的基础lint问题。
```

### 47. `plans/phase1/cards/P1-48.md:5-13`（定位词 `3个I001/1个E741清零`）

```text
## 目标

当前3个I001/1个E741清零，新增subject修复不引入新的基础lint问题。

## 已有问题证据

历史审计曾有12项；前序修复后本轮实际只剩3个I001和1个E741，具体见S11-final日志s12-lint-inventory。

## 必读输入
```

### 48. `plans/phase1/cards/P1-48.md:43-51`（定位词 `delay import cycle测试继续通过`）

```text
- [ ] ruff deeptutor deeptutor_cli退出0
- [ ] 没有新增忽略/删除rule
- [ ] delay import cycle测试继续通过

执行命令（从项目根开始；带 cd web 的条目为独立命令，不延续前一条 cwd）：

```bash
./.venv/bin/ruff check deeptutor deeptutor_cli
git diff --check
```

### 49. `plans/phase1/FRAMEWORK.md:41-49`（定位词 `阶段内串行完成`）

```text
任务卡通常只有一个行为目标，修改 1–3 个生产文件、1 个主要测试文件。存储、响应契约等共同依赖先独立实现，业务卡只接入；相互共享大文件的卡必须串行。单元的确定性来自精确输入/输出与反例，而不是“改了几行”。

每张卡独立列目标、已有证据、读取入口、允许文件与符号范围、执行步骤、测试命令、完成条件和禁止事项。卡上的依赖是必需前置，不允许为了省事跨卡实施。一个会话执行一个已授权阶段（2–6张卡）；阶段内串行完成，阶段结束一次独立审查。小卡保持编码粒度，禁止自由选阶段外任务。批改与模型解析、数据写入分开；科目作用域编码与聊天接线、检索接入分开；报告目录、沙箱、图像验证、编排、接口、核查分开。

约250行现作为阶段复杂度提醒，不机械触发人工补卡；文件范围/目标或契约确需扩大时才blocked_scope。阶段内已授权单元为集成需要作小修可以直接实现并复测。禁止顺手重构、全仓格式化、机械删所有 MCP/book/partner 字符串。

## 5. 执行与验收顺序

所有单元和依赖在tasks.json；stages.json定义阶段顺序与阶段内单元顺序，dispatch_order已同步展开。默认一名执行者串行按阶段工作，阶段边界才人工交接，不能按卡编号盲跑。若调度者以后使用并行执行，必须同时满足依赖已验收和 allowed_files/符号范围不重叠；不要让多个 agent 同时改 subjects.py、agentic_pipeline.py、builtin/__init__.py 或同一测试文件。
```

### 50. `plans/phase1/FRAMEWORK.md:41-49`（定位词 `阶段结束一次独立审查`）

```text
任务卡通常只有一个行为目标，修改 1–3 个生产文件、1 个主要测试文件。存储、响应契约等共同依赖先独立实现，业务卡只接入；相互共享大文件的卡必须串行。单元的确定性来自精确输入/输出与反例，而不是“改了几行”。

每张卡独立列目标、已有证据、读取入口、允许文件与符号范围、执行步骤、测试命令、完成条件和禁止事项。卡上的依赖是必需前置，不允许为了省事跨卡实施。一个会话执行一个已授权阶段（2–6张卡）；阶段内串行完成，阶段结束一次独立审查。小卡保持编码粒度，禁止自由选阶段外任务。批改与模型解析、数据写入分开；科目作用域编码与聊天接线、检索接入分开；报告目录、沙箱、图像验证、编排、接口、核查分开。

约250行现作为阶段复杂度提醒，不机械触发人工补卡；文件范围/目标或契约确需扩大时才blocked_scope。阶段内已授权单元为集成需要作小修可以直接实现并复测。禁止顺手重构、全仓格式化、机械删所有 MCP/book/partner 字符串。

## 5. 执行与验收顺序

所有单元和依赖在tasks.json；stages.json定义阶段顺序与阶段内单元顺序，dispatch_order已同步展开。默认一名执行者串行按阶段工作，阶段边界才人工交接，不能按卡编号盲跑。若调度者以后使用并行执行，必须同时满足依赖已验收和 allowed_files/符号范围不重叠；不要让多个 agent 同时改 subjects.py、agentic_pipeline.py、builtin/__init__.py 或同一测试文件。
```

### 51. `plans/phase1/EXECUTION_GUIDE.md:10-18`（定位词 `阶段report.json`）

```text
阶段内按指定卡顺序实现、定向测试和自修，完成一单元不询问下一卡，不重新阅读57卡或另写全项目计划。
限定阶段白名单并集和卡目标；不提交、不调用真实供应商、不动真实配置/数据、不做第二阶段功能。
只保留阶段report.json和共享追加日志，按C14和StageReport schema记录各单元结果与实际命令。
阶段结束停止，由协调者一次独立复核；不自行执行下阶段或标accepted。
```

当前待执行阶段以stages.json的next_stage与最新签收receipt为准，具体指令见对应START_Sxx.txt；原START_P1_00.txt/旧审查报告是历史记录。

## 必须保持的约束
```

### 52. `plans/phase1/EXECUTION_GUIDE.md:11-19`（定位词 `阶段结束停止`）

```text
限定阶段白名单并集和卡目标；不提交、不调用真实供应商、不动真实配置/数据、不做第二阶段功能。
只保留阶段report.json和共享追加日志，按C14和StageReport schema记录各单元结果与实际命令。
阶段结束停止，由协调者一次独立复核；不自行执行下阶段或标accepted。
```

当前待执行阶段以stages.json的next_stage与最新签收receipt为准，具体指令见对应START_Sxx.txt；原START_P1_00.txt/旧审查报告是历史记录。

## 必须保持的约束

```

### 53. `plans/phase1/STAGE_WORKFLOW.md:1-7`（定位词 `阶段`）

```text
# 执行与审查流程 2.1：按阶段交接与探索包复用

生效日期：2026-10-11；由用户明确要求替换逐卡人工交接。业务目标和C01–C13保持，小卡仍是编码/测试单元，授权、会话、汇报、独立审查改为阶段。此文件优先于历史单卡提示词中“完成一张卡就停止”的说明。

## 1. 两种粒度

57张小卡保留，作为明确的目标、符号范围、文件范围、必需行为测试和完成条件。每个阶段包含2–6张卡，执行者在同一个阶段会话里按顺序完成、测试、自修，阶段内不再请求下一张卡批准。阶段结束提交一份汇总，协调者一次复核；不自动进入未授权的下一阶段。
```

### 54. `plans/phase1/STAGE_WORKFLOW.md:29-37`（定位词 `review.json`）

```text
.phase1-evidence/stages/Sxx/report.json      阶段汇总与各单元结果
.phase1-evidence/stages/Sxx/execution.log    命令、时间、原始输出、实际exit code；仅追加
.phase1-evidence/stages/Sxx/review.json      协调者审查、补修、当前源码hash和签收
```

另加必要的source/data基线和一个阶段完成source归档；不为每条断言、每次检查、每卡反复建目录。先前P1-00的原始证据保持不变，新的协调者修补在reviews/P1-00，不覆盖原completion或失败日志。

report.json内card_results记录卡ID、verified_local/blocked、目标是否达成、修改文件、满足的完成条件、测试名和日志定位；直接复用命令记录，不强制每卡completion.json。历史Completion schema和单卡证据仍可读；新阶段使用StageReport schema。

```

### 55. `plans/phase1/DATA_CONTRACTS.md:3-11`（定位词 `## C01`）

```text
状态：执行规范，尚未实现。仅作用于本阶段新修复的 subject 路径；全局上游 API 不做统一重构。数据源是当前工作树及旧数组 JSON，字段以当前既有格式兼容为先。C 编号供任务卡精准读取。

## C01：存储、身份与兼容

- subject_id 使用 `subjects/store.py` 的 slug 校验，中文合法；不是用户显示名，也不接受路径/百分号/分隔符。先校验再转路径，存在性再由当前用户作用域中的注册表确认。路径 resolve 后必须仍在该用户 subjects 根内，防 symlink 越界。
- 学习数据根：当前 PathService 的 `get_workspace_dir()/subjects`；产物根：当前 `get_public_outputs_root()/subjects`。不能硬编码管理员 data/user，也不能让调用者/模型传 base_dir。已存在结构不移动。
- subject 读写使用直接且严格的当前用户 PathService 解析；当前路径解析失败必须报错，不使用通用 get_path_service 的异常后默认管理员实例 fallback。报告和导出辅助也复用这个严格入口。
- index.json、knowledge.json、wrong_book.json、exam_points.json、knowledge_points.json 顶层仍是数组；profile.json 顶层仍是对象。不切换成统一 envelope，不给所有历史对象批量补 schema_version。新增字段只能可选且读旧数据有确定默认。
- 文件不存在时按集合定义返回 []/profile defaults。存在但 JSON 损坏、顶层类型错误或读取权限失败时抛明确 StorageError；不得返回空集合，不得随后覆盖坏文件。不自动修复/删坏文件。
```

### 56. `plans/phase1/DATA_CONTRACTS.md:173-181`（定位词 `## C13`）

```text
先检查该科没有活跃资料更新/索引/报告发布，再在 subject snapshot 锁下把权威数据和 completed 产物复制到私有 staging，释放锁后压缩；内容变化/hash不符则失败或重试一次，不产出假 complete 清单。任何 symlink 或越界源条目拒绝导出，不跟随到外面，不把当前 ZIP 加入下一份。用户删除科目与导出必须互斥。归档失败只清理本次 staging/临时 ZIP，不删除旧导出。

## C13：UI、裁剪与能力说明

- 所有修改的 async action 有 try/catch/finally，失败解除 busy，不显示成功计数/生成链接。post 非 2xx 不继续按成功刷新；读取 error.message，兼容旧 detail 文本。界面不展示 traceback/provider密钥/宿主路径。
- subject selector 提供无科目选项；从当前 session 的 preferences 恢复，能力参数与 subject_id 合并不能覆盖彼此。刷新恢复未完成时不能发送旧科目的请求。
- 上传 operation=transcribe 时显示转写完成与文本去向；index 时显示任务/状态；documents从C07，coverage降级可见。不新增“音频自动建库”或全新批改界面。
- 去掉 Obsidian 可点击创建入口及活跃宣传。保留 501 API 和合法历史数据读取拒绝；不删除用户原 vault/旧 KB 目录。
- 删除 partners/tutorbot/matrix 依赖 extras 和 requirements 镜像，root requirements 改 server；修对应打包断言。保留 CLI、scheduler、sandbox runner、office skills、built-in deferred_tools、load_tools、多用户上下文和现有内置 capability。不按词删 runtime/providers。
```

### 57. `plans/phase1/DATA_CONTRACTS.md:183-191`（定位词 `## C14`）

```text
- 新部署文档不建议安装已删伙伴功能；历史迁移说明和 UPSTREAM.md/assets/README 上游存档保持原样。AGENTS.md 标当前 fork 差异或同步最小命令表，不把源上游全文视为本项目运行清单。

## C14：证据与阶段验收（2026-10-11修订）

每张小卡仍需正向和独立反向行为证据；合法负例从已证明有效的base只改一个字段/故障点。高风险用一个针对性坏对照确认断言捕获真实效果，禁止只看源码contains或mock自证。该义务不要求每卡交付一份独立人工报告。

每阶段一个执行会话，阶段内按stages.json既定顺序串行卡。报告/审查为阶段粒度，规则见STAGE_WORKFLOW.md。新阶段使用StageReport schema：stage_id/status/baseline_id/card_results/commands/scope_check/real_data_unchanged/limitations。card_results含卡ID、目标、修改路径、断言、命令定位和限制；commands保存实际命令、cwd、exit、共享execution.log行号，不能只写摘要“通过”。

单元状态verified_local表示本地验证；阶段末由协调者独立复核并写review.json的accepted，执行者不能自签。历史P1-00/completion.json保持原样，协调修补/签收另存reviews/P1-00；旧Completion schema继续兼容明确单卡调用，不强制后续每卡创建文件。
```

### 58. `deeptutor/runtime/home.py:6-14`（定位词 `DEEPTUTOR_HOME_ENV =`）

```text
from pathlib import Path

DEEPTUTOR_HOME_ENV = "DEEPTUTOR_HOME"
PACKAGE_ROOT = Path(__file__).resolve().parents[2]


def validate_runtime_home(home: str | Path) -> None:
    """Reject runtime homes that point inside this checkout's data tree."""

```

### 59. `deeptutor/runtime/home.py:26-34`（定位词 `def get_runtime_home(`）

```text


def get_runtime_home(home: str | Path | None = None) -> Path:
    """Return the directory that owns runtime data for this process.

    Priority:
    1. Explicit *home* argument.
    2. ``DEEPTUTOR_HOME`` environment variable.
    3. Current working directory.
```

### 60. `deeptutor/runtime/home.py:40-48`（定位词 `return Path.cwd().resolve()`）

```text
    raw = home if home is not None else os.getenv(DEEPTUTOR_HOME_ENV)
    if raw is None or str(raw).strip() == "":
        return Path.cwd().resolve()
    return Path(raw).expanduser().resolve()


def get_runtime_data_root(home: str | Path | None = None) -> Path:
    """Return ``<runtime-home>/data``."""

```

### 61. `deeptutor/runtime/home.py:10-18`（定位词 `def validate_runtime_home(`）

```text


def validate_runtime_home(home: str | Path) -> None:
    """Reject runtime homes that point inside this checkout's data tree."""

    resolved = Path(home).expanduser().resolve()
    invalid_homes = {
        PACKAGE_ROOT / "data",
        PACKAGE_ROOT / "data" / "user",
```

### 62. `deeptutor/runtime/launcher.py:933-941`（定位词 `def start(home:`）

```text


def start(home: str | Path | None = None, *, dev: bool = False) -> None:
    _relax_console_encoding()
    runtime_home = get_runtime_home(home)
    try:
        validate_runtime_home(runtime_home)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
```

### 63. `deeptutor/runtime/launcher.py:935-943`（定位词 `runtime_home = get_runtime_home(home)`）

```text
def start(home: str | Path | None = None, *, dev: bool = False) -> None:
    _relax_console_encoding()
    runtime_home = get_runtime_home(home)
    try:
        validate_runtime_home(runtime_home)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    runtime_home.mkdir(parents=True, exist_ok=True)
    os.environ[DEEPTUTOR_HOME_ENV] = str(runtime_home)
```

### 64. `deeptutor/runtime/launcher.py:1033-1041`（定位词 `common_env[DEEPTUTOR_HOME_ENV] = str(runtime_home)`）

```text
    common_env = os.environ.copy()
    common_env.update(runtime_env)
    common_env[DEEPTUTOR_HOME_ENV] = str(runtime_home)
    common_env["BACKEND_PORT"] = str(backend_port)
    common_env["FRONTEND_PORT"] = str(frontend_port)
    common_env["PORT"] = str(frontend_port)
    common_env["HOSTNAME"] = "0.0.0.0"
    common_env["NEXT_PUBLIC_API_BASE"] = api_base
    common_env["NEXT_PUBLIC_AUTH_ENABLED"] = "true" if auth_enabled else "false"
```

### 65. `deeptutor_cli/main.py:32-40`（定位词 `NOTE: `partner` and `book``）

```text
)

# NOTE: `partner` and `book` are intentionally NOT registered. Their backing
# modules (`deeptutor.services.partners`, `deeptutor.book`) were removed by the
# M0 fork trim, so the commands could only ever fail with ModuleNotFoundError.
# Use upstream DeepTutor if you need either feature.
chat_app = typer.Typer(help="Interactive chat REPL.")
kb_app = typer.Typer(help="Manage knowledge bases.")
skill_app = typer.Typer(help="Manage skills and install from hubs (ClawHub, …).")
```

### 66. `deeptutor_cli/main.py:112-120`（定位词 `def start(`）

```text

@app.command()
def start(
    home: Path | None = typer.Option(None, "--home", help="Runtime workspace root."),
    dev: bool = typer.Option(
        False,
        "--dev",
        help="Use the Next.js development server for frontend work.",
    ),
```

### 67. `deeptutor_cli/main.py:123-131`（定位词 `start_web(home=home, dev=dev)`）

```text
    from deeptutor.runtime.launcher import start as start_web

    start_web(home=home, dev=dev)


@app.command()
def serve(
    host: str = typer.Option("0.0.0.0", help="Bind address."),
    port: int | None = typer.Option(None, help="Port number."),
```

### 68. `deeptutor_cli/__main__.py:1-5`（定位词 `from deeptutor_cli.main import main`）

```text
"""Allow running as ``python -m deeptutor_cli`` or ``deeptutor``."""

from deeptutor_cli.main import main

main()
```

### 69. `deeptutor_cli/__main__.py:3-5`（定位词 `main()`）

```text
from deeptutor_cli.main import main

main()
```

### 70. `deeptutor/__main__.py:1-6`（定位词 `from deeptutor_cli.main import main`）

```text
"""Run DeepTutor CLI via ``python -m deeptutor``."""

from deeptutor_cli.main import main

if __name__ == "__main__":
    main()
```

### 71. `deeptutor/__main__.py:4-6`（定位词 `main()`）

```text

if __name__ == "__main__":
    main()
```

### 72. `pyproject.toml:86-94`（定位词 `deeptutor = "deeptutor_cli.main:main"`）

```text

[project.scripts]
deeptutor = "deeptutor_cli.main:main"

[project.optional-dependencies]
# Compatibility extra for source installs and older docs. These packages are
# already included in the public `deeptutor` wheel; the local CLI-only project
# under `packaging/deeptutor-cli` uses the same list without Web assets/server deps.
cli = [
```

### 73. `pyproject.toml:276-284`（定位词 `[tool.ruff]`）

```text
# Ruff linter and formatter configuration
# ============================================
[tool.ruff]
# Target Python version
target-version = "py311"
line-length = 100

[tool.ruff.lint]
# Enable only foundational lint rules (intentionally relaxed)
```

### 74. `pyproject.toml:373-381`（定位词 `[tool.ruff.lint.isort]`）

```text
# Ruff import sorting (isort replacement)
# ============================================
[tool.ruff.lint.isort]
known-first-party = ["deeptutor", "deeptutor_cli", "scripts"]
force-sort-within-sections = true
split-on-trailing-comma = true

# ============================================
# Ruff per-file-ignores
```

### 75. `pyproject.toml:38-46`（定位词 `MCP SDK (compatibility pending review)`）

```text
    "prompt_toolkit>=3.0.36",
    "pyte>=0.8.1",  # in-memory terminal emulator: scrape Claude Code's /model TUI on sync
    # MCP SDK (compatibility pending review). Kept because the shared MCP
    # modules still import it; this fork's PageIndex overview runs through the
    # existing RAG outline pipeline and does not claim an auto-injected client.
    "mcp>=1.26.0,<2.0.0",
    # Full app dependencies included by default for `pip install deeptutor`.
    "anthropic>=0.30.0",
    "dashscope>=1.14.0",
```

### 76. `Dockerfile:23-31`（定位词 `WORKDIR /app`）

```text
FROM --platform=$BUILDPLATFORM node:22-slim AS frontend-builder

WORKDIR /app/web

# Copy package files first for better caching
COPY web/package.json web/package-lock.json* ./

# Install dependencies with generous timeout for CI environments
RUN npm config set fetch-timeout 600000 && \
```

### 77. `Dockerfile:437-445`（定位词 `ENTRYPOINT ["/app/entrypoint.sh"]`）

```text

# Set entrypoint
ENTRYPOINT ["/app/entrypoint.sh"]

# ============================================
# Stage 4: Development Image (Optional)
# ============================================
FROM production AS development

```

### 78. `PROJECT_AUDIT_2026-10-10.md:78-86`（定位词 `12 个告警：11 个 I001、1 个 E741`）

```text
| 前端 node 测试 | **403 passed、0 failed** |
| `web/node_modules/.bin/tsc --noEmit -p .` | 退出码 0，无错误 |
| Ruff，只查 deeptutor/deeptutor_cli | 12 个告警：11 个 I001、1 个 E741 |
| `git diff --check` | 通过 |
| 临时数据离线探针 | 18 项，详见下节；模型/ASR 调用使用模拟响应，PDF 编译使用真实 Typst |

后端失败项是 `tests/services/test_codebuddy_credentials.py:57`：夹具固定 `expiresAt=1791055241000`，即北京时间 **2026-10-04 03:20:41**，如今却仍断言未过期。单独重跑也失败。这是上游测试的时间依赖，不能据此认定真实 CodeBuddy 凭证解析坏了。

原文的 Ruff 数量与“均为上游遗留”不准确：实际告警包含本 fork 新增的 subjects/PDF 代码；F841 在当前规则中被忽略。该检查范围与原文可能不同，不能直接用数字作全仓库对比。
```

### 79. `PROJECT_AUDIT_2026-10-10.md:55-63`（定位词 `Typst 二进制与中文字体实际存在`）

```text

- Python 3.12.14；主要已安装依赖与原交接文档列出的版本一致；前端声明 Next 16.2.3。
- Typst 二进制与中文字体实际存在，模型目录文件未被 Git 跟踪，当前权限为 `0600`。本报告不记录密钥。
- 配置端口仍为后端 8001、前端 3782，但核查时 `ss -ltnp` 显示两者均没有监听，未启动应用或重建生产前端。
- 六个科目注册记录仍存在。每科各有 1 个 assignment KB，配置状态均为 ready、各有 1 个 raw 文件；**这是磁盘元数据检查，没有进行在线检索验证**。
- 其中复变函数当前各有 1 个错题、1 个考点、1 个知识点，产物目录有 17 个 PDF；另外五科的这些记录为空。原文“六科完好”只能理解为数据仍在，不能理解为六科都已有丰富学习记录或已全面验证。

实际数据分布：

```

### 80. `tests/cli/test_docs_contract.py:77-85`（定位词 `def test_documented_deeptutor_subcommands_exist`）

```text


def test_documented_deeptutor_subcommands_exist() -> None:
    # Follow actual registration, including aliases and implicitly named Typer
    # commands. A historical hand-maintained allowlist accepted retired commands.
    cli = get_command(app)
    top_level = cli.commands
    provider_subcommands = cli.commands["provider"].commands

```

### 81. `tests/cli/test_docs_contract.py:80-88`（定位词 `cli = get_command(app)`）

```text
    # Follow actual registration, including aliases and implicitly named Typer
    # commands. A historical hand-maintained allowlist accepted retired commands.
    cli = get_command(app)
    top_level = cli.commands
    provider_subcommands = cli.commands["provider"].commands

    for command in _deeptutor_commands():
        first_segment = command.split("|", 1)[0].split("#", 1)[0].strip()
        tokens = shlex.split(first_segment)
```

### 82. `tests/cli/test_docs_contract.py:81-89`（定位词 `top_level = cli.commands`）

```text
    # commands. A historical hand-maintained allowlist accepted retired commands.
    cli = get_command(app)
    top_level = cli.commands
    provider_subcommands = cli.commands["provider"].commands

    for command in _deeptutor_commands():
        first_segment = command.split("|", 1)[0].split("#", 1)[0].strip()
        tokens = shlex.split(first_segment)
        if len(tokens) < 2:
```

### 83. `tests/runtime/test_launcher.py:40-48`（定位词 `test_runtime_home_rejects_project_data_paths`）

```text


def test_runtime_home_rejects_project_data_paths(monkeypatch, tmp_path: Path) -> None:
    package_root = tmp_path / "package"
    monkeypatch.setattr("deeptutor.runtime.home.PACKAGE_ROOT", package_root)

    with pytest.raises(ValueError, match="Invalid DeepTutor runtime home"):
        validate_runtime_home(package_root / "data")
    with pytest.raises(ValueError, match="Invalid DeepTutor runtime home"):
```

### 84. `tests/runtime/test_launcher.py:50-58`（定位词 `test_start_does_not_create_nested_data_tree`）

```text


def test_start_does_not_create_nested_data_tree(monkeypatch, tmp_path: Path) -> None:
    package_root = tmp_path / "package"
    bad_home = package_root / "data" / "user"
    monkeypatch.setattr("deeptutor.runtime.home.PACKAGE_ROOT", package_root)
    monkeypatch.setattr(launcher, "get_runtime_home", lambda _home=None: bad_home)

    with pytest.raises(SystemExit, match="Invalid DeepTutor runtime home"):
```

### 85. `tests/runtime/test_api_import_memory_boundary.py:7-15`（定位词 `test_api_import_keeps_optional_heavy_dependencies_cold`）

```text


def test_api_import_keeps_optional_heavy_dependencies_cold() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    probe = """
import json
import sys

import deeptutor.api.main  # noqa: F401
```

### 86. `.phase1-evidence/reviews/S11-final/environment_observation.json:1-8`（定位词 `"python"`）

```text
{
  "python": "3.12.14 (main, Sep  1 2026, 14:16:52) [Clang 22.1.3 ]",
  "executable": "/home/albert/selflearn/selflearn/.venv/bin/python",
  "platform": "Linux-6.18.33.2-microsoft-standard-WSL2-x86_64-with-glibc2.43",
  "packages": {
    "pytest": "9.1.1",
    "ruff": "0.16.7",
    "fastapi": "0.141.1",
```

### 87. `.phase1-evidence/reviews/S11-final/environment_observation.json:12-15`（定位词 `"typst"`）

```text
  "command_id": "environment-observation",
  "node": "v22.22.1",
  "typst": "0.15.1 (9dfd3a08)"
}
```

### 88. `UPSTREAM.md:1-9`（定位词 `DeepTutor`）

```text
<div align="center">

<p align="center"><img src="assets/figs/logo/logo.png" alt="DeepTutor logo" height="56" style="vertical-align: middle;">&nbsp;<img src="assets/figs/logo/banner.png" alt="DeepTutor" height="48" style="vertical-align: middle;"></p>

# DeepTutor: Lifelong Personalized Tutoring

<p align="center">
  <a href="https://deeptutor.info" target="_blank"><img alt="Docs — deeptutor.info" src="https://img.shields.io/badge/Docs-deeptutor.info%20%E2%86%97-0A0A0A?style=for-the-badge&labelColor=F5F5F4" height="36"></a>
</p>
```

### 89. `assets/README/README_CN.md:1-9`（定位词 `DeepTutor`）

```text
<div align="center">

<p align="center"><img src="../../assets/figs/logo/logo.png" alt="DeepTutor logo" height="56" style="vertical-align: middle;">&nbsp;<img src="../../assets/figs/logo/banner.png" alt="DeepTutor" height="48" style="vertical-align: middle;"></p>

# DeepTutor：终身个性化辅导

<p align="center">
  <a href="https://deeptutor.info" target="_blank"><img alt="Docs — deeptutor.info" src="https://img.shields.io/badge/Docs-deeptutor.info%20%E2%86%97-0A0A0A?style=for-the-badge&labelColor=F5F5F4" height="36"></a>
</p>
```

## 易误导的历史文字与范围问题

- README 的 M0 将 MCP 一概列为删除；当前契约区分已删除的 MCP 配置/传输界面与保留的 MCP SDK 兼容依赖。PageIndex 当前是 REST outline，不应宣称深度 MCP 检索。
- HANDOVER 保留历史记录是 P1-47 明确要求；其中旧 Ruff 10 I001/1 E741/3 F841，以及 PROJECT_AUDIT_2026-10-10 的 11 I001/1 E741，均为历史基线。当前阶段基线为 3 I001/1 E741；旧‘全部可用’也被 HANDOVER 的 2026-10-10 补充限定为历史结论。新增修正说明，不改写旧记录。
- Compose 与 CONTAINERIZATION 中 `data/partners` 等目录文字可能涉及共享多用户数据布局；仅按 P1-47 更新事实和注释，不以关键词命中为由删挂载或网络配置。
- S11-final 已把 `tests/cli/test_docs_contract.py` 的旧手工白名单改为真实 Typer 注册发现，消除了允许退役命令导致的假阴性；该文件仍只读。新 `test_p1_47.py` 当前缺失。
- 新文件当前缺失：`plans/phase1/ENVIRONMENT.md`、`scripts/start_selflearn.sh`、`tests/phase1/test_p1_47.py`。不得借 P47 清理其它既有未跟踪/脏文件。
