from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from config import LabConfig, load_config
from memory_store import estimate_tokens
from model_provider import build_chat_model


@dataclass
class SessionState:
    messages: list[dict[str, str]] = field(default_factory=list)
    token_usage: int = 0
    prompt_tokens_processed: int = 0


class BaselineAgent:
    """Agent A: Baseline Agent.

    Requirements:
    - Within-session memory only (maintains conversation state per thread_id).
    - No persistent `User.md` (does not read or write long-term user profiles).
    - Forgets all facts across new threads/sessions (cross-session recall = 0%).
    - Accumulates full uncompressed context over conversation turns.
    """

    def __init__(self, config: LabConfig | None = None, force_offline: bool = False) -> None:
        self.config = config or load_config()
        self.force_offline = force_offline
        self.sessions: dict[str, SessionState] = {}
        self.langchain_agent = None if force_offline else self._maybe_build_langchain_agent()

    def _ensure_session(self, thread_id: str) -> SessionState:
        if thread_id not in self.sessions:
            self.sessions[thread_id] = SessionState()
        return self.sessions[thread_id]

    def reply(self, user_id: str, thread_id: str, message: str) -> dict[str, Any]:
        """Return the agent response and token accounting."""
        if not self.force_offline and self.langchain_agent is not None:
            try:
                # Live path if LLM is available
                session = self._ensure_session(thread_id)
                prompt_tokens = 15 + sum(estimate_tokens(m["content"]) for m in session.messages) + estimate_tokens(message)
                session.prompt_tokens_processed += prompt_tokens

                session.messages.append({"role": "user", "content": message})
                res = self.langchain_agent.invoke(session.messages)
                content = res.content if hasattr(res, "content") else str(res)
                gen_tokens = estimate_tokens(content)

                session.token_usage += gen_tokens
                session.messages.append({"role": "assistant", "content": content})
                return {
                    "response": content,
                    "tokens": gen_tokens,
                    "prompt_tokens": prompt_tokens,
                    "thread_id": thread_id,
                }
            except Exception:
                # Fallback to deterministic offline mode on any live failure
                pass

        return self._reply_offline(thread_id, message)

    def token_usage(self, thread_id: str) -> int:
        """Return cumulative agent tokens generated for one thread."""
        if thread_id in self.sessions:
            return self.sessions[thread_id].token_usage
        return 0

    def prompt_token_usage(self, thread_id: str) -> int:
        """Return cumulative prompt context tokens processed for one thread."""
        if thread_id in self.sessions:
            return self.sessions[thread_id].prompt_tokens_processed
        return 0

    def total_token_usage(self) -> int:
        """Return cumulative agent tokens across all sessions."""
        return sum(s.token_usage for s in self.sessions.values())

    def total_prompt_token_usage(self) -> int:
        """Return cumulative prompt tokens processed across all sessions."""
        return sum(s.prompt_tokens_processed for s in self.sessions.values())

    def compaction_count(self, thread_id: str) -> int:
        """Baseline agent does not have compact memory."""
        return 0

    def _reply_offline(self, thread_id: str, message: str) -> dict[str, Any]:
        """Deterministic offline baseline behavior.

        Key properties:
        - Maintains full message history within the same thread_id.
        - Calculates prompt tokens as full accumulation of previous history + system prompt.
        - Never remembers facts across different thread_ids (forgets in new sessions).
        """
        session = self._ensure_session(thread_id)

        # Prompt context load: System prompt (~15 tokens) + entire prior history + current turn
        prior_tokens = sum(estimate_tokens(m["content"]) for m in session.messages)
        current_msg_tokens = estimate_tokens(message)
        turn_prompt_tokens = 15 + prior_tokens + current_msg_tokens
        session.prompt_tokens_processed += turn_prompt_tokens

        # Record incoming message
        session.messages.append({"role": "user", "content": message})

        # If this is a fresh thread with only 1 message, check if it's asking a recall question
        is_fresh_thread = len(session.messages) <= 1
        msg_lower = message.lower()

        is_query = (
            "?" in message
            or any(
                q in msg_lower for q in [
                    "là gì", "ở đâu", "con gì", "thế nào", "nhắc lại", "bạn có biết",
                    "đâu mới là", "tóm tắt ngắn về mình", "mình là ai", "mình tên gì",
                    "mình làm nghề gì", "đồ uống yêu thích là gì", "món ăn yêu thích"
                ]
            )
        )

        if is_fresh_thread and is_query:
            # Baseline forgets everything across sessions!
            response_text = (
                "Chào bạn, trong phiên làm việc này mình chưa có thông tin nào về bạn. "
                "Bạn có thể chia sẻ lại giúp mình được không?"
            )
        else:
            # Within-session normal response
            response_text = (
                "Chào bạn, mình đã ghi nhận thông tin của bạn trong phiên trò chuyện này. "
                "Bạn có cần hỗ trợ gì thêm không?"
            )

        gen_tokens = estimate_tokens(response_text)
        session.token_usage += gen_tokens
        session.messages.append({"role": "assistant", "content": response_text})

        return {
            "response": response_text,
            "tokens": gen_tokens,
            "prompt_tokens": turn_prompt_tokens,
            "thread_id": thread_id,
        }

    def _maybe_build_langchain_agent(self):
        """Optional wire-up for live LangChain model when provider dependencies exist."""
        try:
            if not self.config.model.api_key and self.config.model.provider in (
                "openai", "gemini", "anthropic", "openrouter"
            ):
                return None
            return build_chat_model(self.config.model)
        except Exception:
            return None
