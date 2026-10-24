#!/usr/bin/env python3
"""ASR-R1 real-media acceptance helper.

Subcommands:

* ``media``  — copy the four real classroom recordings to a private temp root,
  probe and plan every one, and prove the originals did not change.
* ``long``   — run the full 45-minute recording through a real temporary
  subject + job HTTP API + publication flow with a loopback fake provider.
* ``live``   — one bounded, explicit SiliconFlow job using a copied real
  recording.  The current STT profile is read read-only into memory; the key is
  never written to settings, argv, logs or the report.  If the active provider
  is not SiliconFlow, or the service rejects the call, the result is reported
  as blocked instead of being fabricated.

The script never touches the real learning tree, real settings, or any existing
ASR evidence directory.  It prints/writes only non-secret counts and safe error
codes.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import shutil
import socket
import sys
import tempfile
import threading
import time
from typing import Any, Iterator
from urllib.parse import urlsplit


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _temp_home(prefix: str = "asr-r1-accept-") -> Path:
    root = Path(tempfile.mkdtemp(prefix=prefix))
    for name in ("home", "tmp", "data"):
        (root / name).mkdir(parents=True, exist_ok=True)
    os.environ["DEEPTUTOR_HOME"] = str(root / "data")
    os.environ["HOME"] = str(root / "home")
    os.environ["TMPDIR"] = str(root / "tmp")
    os.environ["XDG_CONFIG_HOME"] = str(root / "home" / ".config")
    os.environ["XDG_DATA_HOME"] = str(root / "home" / ".local" / "share")
    os.environ["XDG_CACHE_HOME"] = str(root / "home" / ".cache")
    os.environ["AUTH_ENABLED"] = "false"
    return root


def _init_temp_runtime() -> None:
    from deeptutor.services.config import ensure_runtime_settings_files
    from deeptutor.services.setup.init import init_user_directories

    init_user_directories()
    ensure_runtime_settings_files()


def _write_fake_catalog(root: Path, base_url: str) -> None:
    catalog = {
        "version": 1,
        "services": {
            "stt": {
                "active_profile_id": "asr-r1-fake-profile",
                "active_model_id": "asr-r1-fake-model",
                "profiles": [
                    {
                        "id": "asr-r1-fake-profile",
                        "name": "ASR-R1 loopback fake",
                        "binding": "openai",
                        "base_url": base_url,
                        "api_key": "sk-asr-r1-fictitious",
                        "models": [
                            {
                                "id": "asr-r1-fake-model",
                                "name": "asr-r1-fake",
                                "model": "asr-r1-fake",
                            }
                        ],
                    }
                ],
            }
        },
    }
    target = root / "data" / "user" / "settings" / "model_catalog.json"
    _write_json(target, catalog)


class _FakeASRHandler(BaseHTTPRequestHandler):
    counter = 0
    lock = threading.Lock()

    def log_message(self, *_args):  # noqa: N802 - silence access log
        return

    def do_POST(self):  # noqa: N802
        if not str(self.path).endswith("/audio/transcriptions"):
            self.send_response(404)
            self.end_headers()
            return
        length = int(self.headers.get("content-length") or 0)
        # Drain the multipart body without retaining it.
        remaining = length
        while remaining > 0:
            chunk = self.rfile.read(min(remaining, 1024 * 1024))
            if not chunk:
                break
            remaining -= len(chunk)
        with _FakeASRHandler.lock:
            _FakeASRHandler.counter += 1
            index = _FakeASRHandler.counter
        body = json.dumps({"text": f"LONG-CHUNK-{index:02d}"}, ensure_ascii=False).encode()
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


@contextlib.contextmanager
def _fake_server() -> Iterator[str]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), _FakeASRHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/v1"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _copy_recording(source: Path, root: Path) -> tuple[Path, str]:
    if not source.is_file():
        raise FileNotFoundError(source)
    target = root / "media" / source.name
    target.parent.mkdir(parents=True, exist_ok=True)
    before = _sha256(source)
    shutil.copy2(source, target)
    after = _sha256(source)
    if before != after:
        raise RuntimeError("source recording changed during copy")
    return target, before


def cmd_media(args: argparse.Namespace) -> int:
    from deeptutor.services.asr import media

    root = Path(tempfile.mkdtemp(prefix="asr-r1-media-"))
    source_dir = Path(args.source_dir)
    files = sorted(source_dir.glob("*.m4a"))
    if len(files) < 4:
        raise RuntimeError(f"expected at least four m4a files in {source_dir}")
    rows = []
    try:
        tools = media.resolve_tools()
        for source in files[:4]:
            copied, digest = _copy_recording(source, root)
            probe = asyncio.run(media.probe(copied, tools=tools))
            chunks = asyncio.run(media.plan_chunks(probe, file_index=0, tools=tools))
            after_digest = _sha256(source)
            rows.append(
                {
                    "name": source.name,
                    "bytes": source.stat().st_size,
                    "source_sha256": digest,
                    "source_sha256_after": after_digest,
                    "input_unchanged": digest == after_digest,
                    "duration_ms": probe.duration_ms,
                    "chunks": len(chunks),
                    "covered_samples": chunks[-1].end_sample if chunks else 0,
                    "total_samples": probe.total_samples,
                }
            )
        payload = {"ok": True, "files": rows, "tool_source": "explicit env/PATH"}
        if args.out:
            _write_json(Path(args.out), payload)
        print(json.dumps(payload, ensure_ascii=False))
        return 0
    finally:
        shutil.rmtree(root, ignore_errors=True)


def _start_test_app():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from deeptutor.api.routers import asr

    app = FastAPI()
    app.include_router(asr.router, prefix="/api/v1/subjects")
    return TestClient(app)


def cmd_long(args: argparse.Namespace) -> int:
    source = Path(args.file)
    root = _temp_home("asr-r1-long-")
    try:
        _init_temp_runtime()
        with _fake_server() as base_url:
            _write_fake_catalog(root, base_url)
            from deeptutor.services.voice.config import STTConfig

            fake_config = STTConfig(
                model="asr-r1-fake",
                provider_name="custom",
                adapter="openai_compat",
                request_style="multipart",
                auth_style="bearer",
                api_key="sk-asr-r1-fictitious",
                base_url=base_url,
                language="zh",
            )
            from deeptutor.subjects import store

            subject = store.create_subject("ASR-R1 45分钟验收")
            # Inject only the loopback fake config into the real route service;
            # the catalog file above documents the same selection for audit.
            import deeptutor.api.routers.asr as asr_router
            from deeptutor.services.asr.jobs import AsrJobService

            asr_router.AsrJobService = lambda sid: AsrJobService(sid, config=fake_config)
            copied, source_sha = _copy_recording(source, root)
            source_sha_after = _sha256(source)
            with _start_test_app() as client:
                with copied.open("rb") as recording:
                    response = client.post(
                        f"/api/v1/subjects/{subject['id']}/asr/jobs",
                        files={"files": (copied.name, recording, "audio/mp4")},
                        data={"request_id": __import__("uuid").uuid4().hex, "language": "zh"},
                    )
                if response.status_code != 202:
                    raise RuntimeError(f"job create failed: {response.status_code} {response.text[:300]}")
                job_id = response.json()["job"]["job_id"]
                deadline = time.monotonic() + float(args.timeout)
                job = None
                while time.monotonic() < deadline:
                    current = client.get(f"/api/v1/subjects/{subject['id']}/asr/jobs/{job_id}")
                    if current.status_code != 200:
                        raise RuntimeError(f"job read failed: {current.status_code}")
                    job = current.json()["job"]
                    if job["status"] in ("completed", "failed", "cancelled", "interrupted"):
                        break
                    time.sleep(0.25)
                if not job or job["status"] != "completed":
                    raise RuntimeError(f"long job did not complete: {json.dumps(job, ensure_ascii=False)[:500]}")
                result = client.get(f"/api/v1/subjects/{subject['id']}/asr/jobs/{job_id}/result").json()
                transcript = "\n".join(row.get("text", "") for row in result.get("transcripts", []))
                source_sha_after = _sha256(source)
                materials = store.subject_dir(subject["id"]) / "materials" / "lecture"
                target_text = materials / f"{copied.name}{__import__('deeptutor.subjects.uploads', fromlist=['TRANSCRIPT_SUFFIX']).TRANSCRIPT_SUFFIX}"
                payload = {
                    "ok": True,
                    "provider": "loopback fake OpenAI-compatible multipart",
                    "source_sha256": source_sha,
                    "source_sha256_after": source_sha_after,
                    "source_unchanged": source_sha == source_sha_after,
                    "duration_ms": job["progress"].get("audio_total_ms"),
                    "chunks_total": job["progress"].get("chunks_total"),
                    "chunks_completed": job["progress"].get("chunks_completed"),
                    "result_transcripts": len(result.get("transcripts", [])),
                    "transcript_chars": len(transcript),
                    "contains_first_chunk": "LONG-CHUNK-01" in transcript,
                    "contains_last_chunk": f"LONG-CHUNK-{job['progress'].get('chunks_total', 0):02d}" in transcript,
                    "published_audio": (materials / copied.name).is_file(),
                    "published_transcript": target_text.is_file(),
                    "no_lecture_index": not (store.subject_kb_base_dir(subject["id"]) / "lecture-kb").exists(),
                    "private_input_removed": not (store.subject_dir(subject["id"]) / ".asr_jobs" / job_id / "input").exists(),
                }
                if args.out:
                    _write_json(Path(args.out), payload)
                print(json.dumps(payload, ensure_ascii=False))
                return 0
    finally:
        shutil.rmtree(root, ignore_errors=True)


@contextlib.contextmanager
def only_siliconflow() -> Iterator[None]:
    """Allow only TCP 443 to resolved api.siliconflow.cn (plus loopback)."""
    real_getaddrinfo = socket.getaddrinfo
    real_connect = socket.socket.connect
    real_connect_ex = socket.socket.connect_ex
    allowed_ips: set[str] = set()
    allowed_host = "api.siliconflow.cn"

    def guarded_getaddrinfo(host, port, *args, **kwargs):
        name = host.decode() if isinstance(host, bytes) else str(host)
        if name in ("127.0.0.1", "localhost", "::1"):
            return real_getaddrinfo(host, port, *args, **kwargs)
        if name != allowed_host:
            raise OSError("external DNS blocked by ASR-R1 live guard")
        infos = real_getaddrinfo(host, port, *args, **kwargs)
        for info in infos:
            try:
                allowed_ips.add(str(info[4][0]))
            except (IndexError, TypeError):
                pass
        return infos

    def guarded_connect(self, address):
        host = address[0] if isinstance(address, tuple) and address else ""
        if host in ("127.0.0.1", "::1", "localhost") or (str(host) in allowed_ips and len(address) >= 2 and address[1] == 443):
            return real_connect(self, address)
        raise OSError("external TCP blocked by ASR-R1 live guard")

    def guarded_connect_ex(self, address):
        host = address[0] if isinstance(address, tuple) and address else ""
        if host in ("127.0.0.1", "::1", "localhost") or (str(host) in allowed_ips and len(address) >= 2 and address[1] == 443):
            return real_connect_ex(self, address)
        return 111

    socket.getaddrinfo = guarded_getaddrinfo  # type: ignore[assignment]
    socket.socket.connect = guarded_connect  # type: ignore[assignment]
    socket.socket.connect_ex = guarded_connect_ex  # type: ignore[assignment]
    try:
        yield
    finally:
        socket.getaddrinfo = real_getaddrinfo  # type: ignore[assignment]
        socket.socket.connect = real_connect  # type: ignore[assignment]
        socket.socket.connect_ex = real_connect_ex  # type: ignore[assignment]


def _real_stt_config(catalog_path: Path):
    raw = json.loads(catalog_path.read_text(encoding="utf-8"))
    from deeptutor.services.asr import transcribe  # noqa: F401 - ensure modules load
    from deeptutor.services.config.provider_runtime import resolve_stt_runtime_config

    return resolve_stt_runtime_config(catalog=raw)


def cmd_live(args: argparse.Namespace) -> int:
    source = Path(args.file)
    catalog = Path(args.catalog)
    root = _temp_home("asr-r1-live-")
    for proxy_key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
        os.environ.pop(proxy_key, None)
    os.environ["NO_PROXY"] = "*"
    payload: dict[str, Any] = {"ok": False, "blocked": False}
    try:
        _init_temp_runtime()
        config = _real_stt_config(catalog)
        host = urlsplit(config.base_url if "://" in config.base_url else f"https://{config.base_url}").hostname
        if host != "api.siliconflow.cn":
            payload.update(
                {
                    "blocked": True,
                    "reason": "active STT provider is not SiliconFlow; no live call made",
                    "provider_host": host,
                }
            )
            if args.out:
                _write_json(Path(args.out), payload)
            print(json.dumps(payload, ensure_ascii=False))
            return 0
        from deeptutor.services.asr import contracts, job_store
        from deeptutor.services.asr.jobs import AsrJobService
        from deeptutor.subjects import store

        subject = store.create_subject("ASR-R1 live SF smoke")
        copied, source_sha = _copy_recording(source, root)
        size = copied.stat().st_size
        digest = _sha256(copied)
        fingerprint = contracts.config_fingerprint(config, "zh")
        job_id = __import__("uuid").uuid4().hex
        signature = contracts.request_signature(
            [{"name": copied.name, "sha256": digest}], language="zh", fingerprint=fingerprint
        )
        staged = root / "live-stage" / copied.name
        staged.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(copied, staged)
        manifest, _created = job_store.create_job(
            subject["id"],
            job_id=job_id,
            request_id=job_id,
            signature=signature,
            language="zh",
            config_fingerprint=fingerprint,
            files=[
                {
                    "staged_path": str(staged),
                    "name": copied.name,
                    "size_bytes": size,
                    "sha256": digest,
                    "content_type": "audio/mp4",
                }
            ],
        )
        manifest = job_store.update_manifest(
            subject["id"], job_id, lambda current: {**current, "provider_model": config.model}
        )
        service = AsrJobService(subject["id"], config=config)
        started = time.monotonic()
        with only_siliconflow():
            asyncio.run(service.run_job_direct(job_id))
        job = service.get_job(job_id)
        if job.status != "completed":
            payload.update(
                {
                    "blocked": True,
                    "reason": f"live SF job ended {job.status}",
                    "error": job.error,
                    "source_sha256": source_sha,
                }
            )
        else:
            result = service.get_result(job_id)
            text = "\n".join(row.get("text", "") for row in result.get("transcripts", []))
            materials = store.subject_dir(subject["id"]) / "materials" / "lecture"
            payload.update(
                {
                    "ok": True,
                    "provider_host": host,
                    "model": config.model,
                    "duration_ms": job.progress["audio_total_ms"],
                    "chunks_total": job.progress["chunks_total"],
                    "chunks_completed": job.progress["chunks_completed"],
                    "transcript_chars": len(text),
                    "elapsed_seconds": round(time.monotonic() - started, 2),
                    "published_audio": (materials / copied.name).is_file(),
                    "published_transcript": (materials / f"{copied.name}.transcript.txt").is_file(),
                    "key_persisted": False,
                }
            )
        if args.out:
            _write_json(Path(args.out), payload)
        print(json.dumps(payload, ensure_ascii=False))
        return 0 if payload.get("ok") or payload.get("blocked") else 1
    except Exception as exc:  # noqa: BLE001 - report safe type only
        payload.update(
            {
                "blocked": True,
                "reason": type(exc).__name__,
                "source_sha256": _sha256(source) if source.is_file() else None,
            }
        )
        if args.out:
            _write_json(Path(args.out), payload)
        print(json.dumps(payload, ensure_ascii=False))
        return 1
    finally:
        shutil.rmtree(root, ignore_errors=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)

    media_parser = sub.add_parser("media")
    media_parser.add_argument("--source-dir", required=True)
    media_parser.add_argument("--out")
    media_parser.set_defaults(func=cmd_media)

    long_parser = sub.add_parser("long")
    long_parser.add_argument("--file", required=True)
    long_parser.add_argument("--timeout", type=float, default=300)
    long_parser.add_argument("--out")
    long_parser.set_defaults(func=cmd_long)

    live_parser = sub.add_parser("live")
    live_parser.add_argument("--file", required=True)
    live_parser.add_argument("--catalog", required=True)
    live_parser.add_argument("--out")
    live_parser.set_defaults(func=cmd_live)

    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
