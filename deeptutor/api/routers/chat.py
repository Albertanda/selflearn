"""
Chat API Router
================

WebSocket endpoint for lightweight chat with session management.
REST endpoints for session operations.
"""

import logging

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect

from deeptutor.agents.chat import ChatAgent, SessionManager
from deeptutor.services.config import PROJECT_ROOT, load_config_with_main
from deeptutor.services.llm.config import get_llm_config
from deeptutor.services.settings.interface_settings import get_response_language

config = load_config_with_main("main.yaml", PROJECT_ROOT)
log_dir = config.get("paths", {}).get("user_log_dir") or config.get("logging", {}).get("log_dir")
logger = logging.getLogger(__name__)

router = APIRouter()


def _get_session_manager() -> SessionManager:
    return SessionManager()


# =============================================================================
# REST Endpoints for Session Management
# =============================================================================


@router.get("/chat/sessions")
async def list_sessions(limit: int = 20):
    return _get_session_manager().list_sessions(limit=limit, include_messages=False)


@router.get("/chat/sessions/{session_id}")
async def get_session(session_id: str):
    session = _get_session_manager().get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


@router.delete("/chat/sessions/{session_id}")
async def delete_session(session_id: str):
    if _get_session_manager().delete_session(session_id):
        return {"status": "deleted", "session_id": session_id}
    raise HTTPException(status_code=404, detail="Session not found")


# =============================================================================
# WebSocket Endpoint for Chat
# =============================================================================


@router.websocket("/chat")
async def websocket_chat(websocket: WebSocket):
    from deeptutor.api.routers.auth import ws_auth_failed, ws_require_auth
    from deeptutor.multi_user.context import reset_current_user

    user_token = await ws_require_auth(websocket)
    if user_token is ws_auth_failed:
        return

    await websocket.accept()

    try:
        while True:
            data = await websocket.receive_json()
            requested_language = str(data.get("language") or "").lower().strip()
            language = (
                "zh"
                if requested_language.startswith("zh")
                else "en"
                if requested_language.startswith("en")
                else get_response_language(default=config.get("system", {}).get("language", "en"))
            )
            message = data.get("message", "").strip()
            session_id = data.get("session_id")
            explicit_history = data.get("history")
            kb_name = data.get("kb_name", "")
            subject_id = data.get("subject_id", "")
            enable_rag = data.get("enable_rag", False)
            enable_web_search = data.get("enable_web_search", False)

            if not message:
                await websocket.send_json({"type": "error", "message": "Message is required"})
                continue

            logger.info(
                f"Chat request: session={session_id}, "
                f"message={message[:50]}..., rag={enable_rag}, web={enable_web_search}"
            )

            try:
                sm = _get_session_manager()

                if session_id:
                    session = sm.get_session(session_id)
                    if not session:
                        session = sm.create_session(
                            title=message[:50] + ("..." if len(message) > 50 else ""),
                            settings={
                                "kb_name": kb_name,
                                "subject_id": subject_id,
                                "enable_rag": enable_rag,
                                "enable_web_search": enable_web_search,
                            },
                        )
                        session_id = session["session_id"]
                else:
                    session = sm.create_session(
                        title=message[:50] + ("..." if len(message) > 50 else ""),
                        settings={
                            "kb_name": kb_name,
                            "subject_id": subject_id,
                            "enable_rag": enable_rag,
                            "enable_web_search": enable_web_search,
                        },
                    )
                    session_id = session["session_id"]

                await websocket.send_json(
                    {
                        "type": "session",
                        "session_id": session_id,
                    }
                )

                if explicit_history is not None:
                    history = explicit_history
                else:
                    history = [
                        {"role": msg["role"], "content": msg["content"]}
                        for msg in session.get("messages", [])
                    ]

                # M5+: subject-scoped sessions inject the lightweight context
                # layer: knowledge-point index + term exam points + wrong-book
                # summary + learner profile (answer-style preference, facts).
                subject_context_tokens = 0
                context_mode = "none"
                history_summarized = False
                if subject_id:
                    try:
                        from deeptutor.services.pdf.review_guide import estimate_tokens
                        from deeptutor.subjects import (
                            exam_points,
                            knowledge_points,
                            wrong_book,
                        )
                        from deeptutor.subjects import (
                            profile as subject_profile,
                        )

                        blocks = [
                            knowledge_points.context_summary(subject_id),
                            exam_points.term_summary(subject_id),
                            wrong_book.context_summary(subject_id),
                            subject_profile.context_summary(subject_id),
                        ]
                        block = "\n\n".join(b for b in blocks if b)
                        if block:
                            subject_context_tokens = estimate_tokens(block)
                            logger.warning(
                                "subject context injected: %d chars, ~%d tokens",
                                len(block),
                                subject_context_tokens,
                            )
                            history = [
                                {"role": "system", "content": block},
                                *history,
                            ]
                    except Exception:
                        logger.warning("subject context injection failed", exc_info=True)

                # Token-saver policy: full context vs bounded/compressed history.
                try:
                    from deeptutor.services.llm.context_window import (
                        resolve_effective_context_window,
                    )
                    from deeptutor.services.settings.token_budget import (
                        get_token_budget_settings,
                    )

                    budget = get_token_budget_settings()
                    # Resolve the model actually in use so the window is sized
                    # from the real model. The previous probe,
                    # ``llm_config.model if "llm_config" in dir() else ""``, read
                    # a name assigned further down in this same loop body: on the
                    # FIRST message of a session it was unbound, so the window
                    # fell back to "unknown", while every later message reused
                    # the previous iteration's binding — one session behaving two
                    # different ways. Guarded locally so a config-resolution
                    # failure cannot skip the rest of the budget policy.
                    try:
                        llm_model = get_llm_config().model or ""
                    except Exception:
                        llm_model = ""
                    context_window = resolve_effective_context_window(model=llm_model or "unknown")
                    if budget.get("enabled", True):
                        context_mode = "saved"
                        history_budget_tokens = 4000
                    else:
                        context_mode = "full"
                        ratio = float(budget.get("context_ratio", 0.7))
                        history_budget_tokens = max(4000, int(context_window * ratio))

                    ctx_total = sum(
                        estimate_tokens(str(m.get("content", ""))) for m in history
                    )
                    if ctx_total > history_budget_tokens and len(history) > 8:
                        from deeptutor.services.session.summarize import summarize

                        early, recent = history[:-6], history[-6:]
                        try:
                            summary, facts = await summarize(early)
                            if summary:
                                history = [
                                    {
                                        "role": "system",
                                        "content": f"【此前对话摘要】\n{summary}",
                                    },
                                    *recent,
                                ]
                                history_summarized = True
                                if subject_id:
                                    for f in facts:
                                        subject_profile.add_fact(subject_id, f)
                        except Exception:
                            logger.warning("history summarization failed", exc_info=True)
                except Exception:
                    logger.warning("token budget policy failed", exc_info=True)

                sm.add_message(
                    session_id=session_id,
                    role="user",
                    content=message,
                )

                try:
                    llm_config = get_llm_config()
                    api_key = llm_config.api_key
                    base_url = llm_config.base_url
                    api_version = getattr(llm_config, "api_version", None)
                except Exception:
                    api_key = None
                    base_url = None
                    api_version = None

                agent = ChatAgent(
                    language=language,
                    config=config,
                    api_key=api_key,
                    base_url=base_url,
                    api_version=api_version,
                    # History policy is handled above (token-saver switch);
                    # keep the agent's internal truncation out of the way.
                    max_history_tokens=10**9,
                )

                if enable_rag and kb_name:
                    await websocket.send_json(
                        {
                            "type": "status",
                            "stage": "rag",
                            "message": f"Searching knowledge base: {kb_name}...",
                        }
                    )

                if enable_web_search:
                    await websocket.send_json(
                        {
                            "type": "status",
                            "stage": "web",
                            "message": "Searching the web...",
                        }
                    )

                await websocket.send_json(
                    {
                        "type": "status",
                        "stage": "generating",
                        "message": "Generating response...",
                    }
                )

                full_response = ""
                sources = {"rag": [], "web": []}

                stream_generator = await agent.process(
                    message=message,
                    history=history,
                    kb_name=kb_name,
                    enable_rag=enable_rag,
                    enable_web_search=enable_web_search,
                    stream=True,
                )

                async for chunk_data in stream_generator:
                    if chunk_data["type"] == "chunk":
                        await websocket.send_json(
                            {
                                "type": "stream",
                                "content": chunk_data["content"],
                            }
                        )
                        full_response += chunk_data["content"]
                    elif chunk_data["type"] == "complete":
                        full_response = chunk_data["response"]
                        sources = chunk_data.get("sources", {"rag": [], "web": []})

                if sources.get("rag") or sources.get("web"):
                    await websocket.send_json({"type": "sources", **sources})

                await websocket.send_json(
                    {
                        "type": "result",
                        "content": full_response,
                        "subject_context_tokens": subject_context_tokens,
                        "history_chars": sum(len(m.get("content", "")) for m in history),
                        "context_mode": context_mode,
                        "history_summarized": history_summarized,
                    }
                )

                sm.add_message(
                    session_id=session_id,
                    role="assistant",
                    content=full_response,
                    sources=sources if (sources.get("rag") or sources.get("web")) else None,
                )

                logger.info(f"Chat completed: session={session_id}, {len(full_response)} chars")

            except Exception as e:
                logger.error(f"Chat processing error: {e}")
                await websocket.send_json({"type": "error", "message": str(e)})

    except WebSocketDisconnect:
        logger.debug("Client disconnected from chat")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        try:
            await websocket.send_json({"type": "error", "message": str(e)})
        except Exception:
            pass
    finally:
        if user_token is not None:
            try:
                reset_current_user(user_token)
            except Exception:
                pass
