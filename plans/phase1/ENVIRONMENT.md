# S12 acceptance environment (observed 2026-10-20)

This record captures the coordinator's independent S12 acceptance environment. It is not a
dependency lock, does not contain settings or credentials, and does not freeze
the full Python/Node dependency graph.

## Reproducible observation and provenance

The saved observation is
`.phase1-evidence/reviews/S12-final/environment_observation.json`.
Its exact command, output and exit code are recorded under command ID
`environment-observation` in that directory's `execution.log` and `commands.jsonl`.
Run the following from the checkout root to reproduce the observation without
importing application settings:

```bash
./.venv/bin/python .phase1-evidence/reviews/S12-final/observe_environment.py
```

## Interpreter and platform

| Item | Observed value |
|---|---|
| Python | `3.12.14 (main, Sep  1 2026, 14:16:52) [Clang 22.1.3 ]` |
| Interpreter | `/home/albert/selflearn/selflearn/.venv/bin/python` |
| Platform | `Linux-6.18.33.2-microsoft-standard-WSL2-x86_64-with-glibc2.43` |
| Node.js | `v22.22.1`, executable `/usr/bin/node` |
| Git HEAD | `9723f953cb6ca56f13603f76c5d07e1e2f1f4473` |

The original S12 reply/document claimed Node `v24.22.0`, but its saved command
log contains no Node version observation to substantiate that claim. The
coordinator independently observed `v22.22.1` above; the original worker report
and evidence remain unchanged. This does not establish which executable the
worker previously used or imply that any version was installed or changed.
S11-final also recorded `v22.22.1`; the observation here is a separate run.

## Python packages (installed metadata)

| Package | Version |
|---|---|
| pytest | 9.1.1 |
| ruff | 0.16.7 |
| fastapi | 0.141.1 |
| matplotlib | 3.11.2 |
| python-docx | 1.2.0 |
| pydantic | 2.13.5 |
| typer | 0.27.2 |

These are observations from `importlib.metadata.version()`, not a new
`pip freeze` and not an instruction to install a specific set.

## Typst and fonts

All four assets below are present in this checkout; no binary or font is copied
into the repository by this document or by S12.

| Path | Bytes | SHA-256 |
|---|---:|---|
| `tools/bin/typst` | 55,739,488 | `29273eaa04f6d00edd0c2bec578f565fc9c65be856bfbffc894567c68ed0b237` |
| `tools/fonts/SimsunExtG.ttf` | 3,549,508 | `9cadcd0ab3d549446b51001d9896773d87ad012d93d842532f321eca514bffd8` |
| `tools/fonts/msyh.ttc` | 19,704,352 | `d79c55e68b1131eea0cc1c47be4f572d964f28c682e143db2ad09c1e4cb07a3f` |
| `tools/fonts/simhei.ttf` | 9,745,792 | `9b1959db3b3abeb7efdaec26edf7dfe871a6039de8d614af7248575207be629e` |

`./tools/bin/typst --version` printed `typst 0.15.1 (9dfd3a08)`.

## Tool availability (observed, not exercised)

- `bwrap`: `/usr/bin/bwrap` is present.
- `docker`: a Docker Desktop CLI path exists; S12 did **not** start a container or
  contact a Docker daemon.
- `tsc` and `playwright` binaries exist under `web/node_modules/.bin`; S12 does not
  re-run the browser suite (that remains S15).
- `curl` and `git` are present.

## Not verified by this environment record

- Live LLM, embedding, web-search, ASR, PageIndex and MCP provider calls were
  not made. No credential or API key is printed here.
- No real indexing, upload, export, delete, report generation, service restart or
  deployment was performed.
- The report-only chart/ODE sandbox is documented by its source/tests, but the
  S13/P50 OS gate subsequently passed locally on 2026-10-20 (S13-final receipt);
  HTTP/WS remains S14 and browser remains S15. This environment observation itself
  does not provide those later execution results.
- `pytest`/Node versions are observations, not a promise that a fresh machine
  will resolve to the same versions without the existing environment.
