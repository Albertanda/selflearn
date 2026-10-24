#!/usr/bin/env python3
"""Explicit live Qwen ASR acceptance in a disposable learning workspace.

The key file is read verbatim (opaque keys may contain dots). Credentials and
upstream response bodies never appear in reports. Real settings are untouched.
Only the copied recording is uploaded; the source is hashed before and after.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import uuid


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


async def run(args, root: Path) -> dict:
    from starlette.datastructures import UploadFile

    from deeptutor.services.asr import job_store, media
    from deeptutor.services.asr.jobs import AsrJobService
    from deeptutor.services.config import ensure_runtime_settings_files
    from deeptutor.services.setup.init import init_user_directories
    from deeptutor.services.voice import transcribe_audio
    from deeptutor.subjects import store

    init_user_directories()
    ensure_runtime_settings_files()
    key = args.key_file.read_text(encoding="utf-8-sig").strip()
    if not key or not key.isascii() or any(c.isspace() for c in key):
        raise ValueError("key_file_must_contain_only_the_complete_key")
    catalog = {
        "services": {
            "stt": {
                "active_profile_id": "aliyun-test",
                "active_model_id": "qwen-asr-test",
                "profiles": [
                    {
                        "id": "aliyun-test",
                        "binding": "aliyun",
                        "api_key": key,
                        "base_url": args.base_url,
                        "models": [{"id": "qwen-asr-test", "model": "qwen3-asr-flash"}],
                    }
                ],
            }
        }
    }
    probe = media.make_silent_wav(root / "probe.wav")
    await transcribe_audio(probe.read_bytes(), catalog=catalog, filename="probe.wav")
    print("live_voice_probe_ok", flush=True)
    from deeptutor.services.config.provider_runtime import resolve_stt_runtime_config

    cfg = resolve_stt_runtime_config(catalog=catalog)
    source_sha = sha(args.recording)
    copied = root / args.recording.name
    shutil.copy2(args.recording, copied)
    subject = store.create_subject("阿里云 ASR 临时验收")
    service = AsrJobService(subject["id"], config=cfg)
    with copied.open("rb") as handle:
        view, _ = await service.create_job(
            [UploadFile(filename=copied.name, file=handle)],
            request_id=str(uuid.uuid4()),
            language="auto",
        )
    previous = None
    async with asyncio.timeout(args.timeout):
        while True:
            view = service.get_job(view.job_id)
            progress = (view.status, view.phase, view.progress)
            if str(progress) != previous:
                print(
                    json.dumps(
                        {"status": view.status, "phase": view.phase, "progress": view.progress}
                    ),
                    flush=True,
                )
                previous = str(progress)
            if view.status in ("completed", "failed", "cancelled", "interrupted"):
                break
            await asyncio.sleep(0.5)
    manifest = job_store.read_manifest(subject["id"], view.job_id)
    report = {
        "ok": view.status == "completed",
        "status": view.status,
        "model": cfg.model,
        "provider": cfg.provider_name,
        "base_url": cfg.base_url,
        "source_sha256": source_sha,
        "source_sha256_after": sha(args.recording),
        "source_unchanged": source_sha == sha(args.recording),
        "voice_probe": "passed",
        "error": view.error,
        "duration_ms": sum(int(row.get("duration_ms") or 0) for row in manifest["files"]),
        "chunks": len(manifest.get("chunks", [])),
        "chunks_success": sum(row["status"] == "success" for row in manifest.get("chunks", [])),
    }
    if report["ok"]:
        result = service.get_result(view.job_id)
        text = result["transcripts"][0]["text"]
        transcript = args.output_dir / "transcript.txt"
        transcript.write_text(text, encoding="utf-8")
        transcript.chmod(0o600)
        published = (
            store.subject_dir(subject["id"])
            / "materials"
            / "lecture"
            / (copied.name + ".transcript.txt")
        )
        report["published_matches_result"] = published.read_text(encoding="utf-8") == text
        report["transcript_chars"] = len(text)
        report["transcript_sha256"] = sha(transcript)
        report["sample_coverage_contiguous"] = all(
            int(left["end_sample"]) == int(right["start_sample"])
            for left, right in zip(manifest["chunks"], manifest["chunks"][1:])
        )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--key-file", type=Path, required=True)
    parser.add_argument("--recording", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--base-url", default="https://dashscope.aliyuncs.com/compatible-mode/v1")
    parser.add_argument("--timeout", type=int, default=1800)
    args = parser.parse_args()
    args.key_file = args.key_file.resolve()
    args.recording = args.recording.resolve()
    args.output_dir = args.output_dir.resolve()
    # Refuse overwriting evidence, source recordings or real application data.
    if args.output_dir.exists():
        raise ValueError("output_dir_must_be_fresh")
    repo = Path(__file__).resolve().parents[1]
    if args.output_dir.is_relative_to(repo) and not args.output_dir.is_relative_to(
        repo / ".phase1-evidence"
    ):
        raise ValueError("output_dir_inside_repo_must_be_evidence")
    args.output_dir.mkdir(parents=True, mode=0o700)
    sys.path.insert(0, str(repo))
    with tempfile.TemporaryDirectory(prefix="aliyun-asr-live-") as temporary:
        root = Path(temporary)
        os.environ["DEEPTUTOR_HOME"] = str(root / "runtime")
        try:
            report = asyncio.run(run(args, root))
        except Exception as exc:
            # Do not serialize exception text: it can contain a URL or key.
            report = {"ok": False, "exception_type": type(exc).__name__}
        target = args.output_dir / "live.json"
        target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        target.chmod(0o600)
        print(json.dumps(report, ensure_ascii=False), flush=True)
        return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
