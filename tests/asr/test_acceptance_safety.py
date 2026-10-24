from __future__ import annotations

from pathlib import Path

from deeptutor.services.asr import contracts
from deeptutor.subjects import export_bundle

REPO = Path(__file__).resolve().parents[2]


def _text(path: str) -> str:
    return (REPO / path).read_text(encoding="utf-8")


def test_no_aliyun_adapter_or_new_dependency_is_added():
    asr = "\n".join(
        (REPO / "deeptutor" / "services" / "asr" / name).read_text(encoding="utf-8")
        for name in ("contracts.py", "provider.py", "media.py", "job_store.py", "jobs.py", "transcribe.py")
    )
    assert "dashscope" not in asr.lower()
    assert "aliyunsdk" not in asr.lower()
    assert "oss2" not in asr.lower()
    assert "boto3" not in asr.lower()
    assert "celery" not in asr.lower()
    assert "redis" not in asr.lower()


def test_live_acceptance_is_sf_only_and_never_reads_key_file():
    script = _text("scripts/asr_acceptance.py")
    assert "api.siliconflow.cn" in script
    assert "Qwen key.txt" not in script
    assert "key.txt" not in script
    assert "dashscope" not in script.lower()
    assert "aliyunsdk" not in script.lower()
    assert "only_siliconflow" in script


def test_export_excludes_private_asr_job_tree():
    assert ".asr_jobs" in export_bundle._TRANSIENT_PARTS
    assert ".upload-staging" in export_bundle._TRANSIENT_PARTS


def test_limits_are_frozen_and_old_sync_limit_is_not_widened():
    assert contracts.MAX_FILES == 16
    assert contracts.MAX_FILE_BYTES == 200 * 1024 * 1024
    assert contracts.MAX_BATCH_BYTES == 200 * 1024 * 1024
    assert contracts.MAX_TOTAL_DURATION_MS == 4 * 60 * 60 * 1000
    assert contracts.MAX_CHUNK_SECONDS == 180
    assert contracts.CHUNK_SAMPLE_RATE == 16000


def test_browser_harness_uses_65s_delay_and_ffmpeg_env_but_not_global_timeout():
    config = _text("web/playwright.phase1.config.ts")
    assert "S15_ASR_DELAY_MS" in config
    assert "SELFLEARN_FFMPEG_BIN" in config
    assert "SELFLEARN_FFPROBE_BIN" in config
    asr_config = _text("web/playwright.asr.config.ts")
    assert "asr-long-audio.spec.ts" in asr_config
    assert "65000" in asr_config
    assert "browser-asr" in asr_config
    e2e = _text("web/e2e/asr-long-audio.spec.ts")
    assert "33_000" in e2e
    assert "202" in e2e
    assert "asr/jobs" in e2e
    # A single global bump of the S15 timeout is not the remedy.
    assert "timeout: 300_000" not in config


def test_asr_proxy_is_one_exact_collection_and_children_stay_on_rewrite():
    proxy = _text("web/proxy.ts")
    assert "api/v1/subjects/[^/]+/asr/jobs$" in proxy
    route = _text("web/app/api/v1/subjects/[subjectId]/asr/jobs/route.ts")
    assert "export function POST" in route
    assert "export function GET" in route
    assert "forwardBackendUpload" in route
