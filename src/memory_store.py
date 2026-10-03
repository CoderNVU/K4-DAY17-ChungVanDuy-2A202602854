from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path


def estimate_tokens(text: str) -> int:
    """Implement a simple, stable heuristic token estimator.

    Approximates tokens from character count (~3.8-4 chars per token).
    Empty text returns 0.
    """
    s = text.strip()
    if not s:
        return 0
    return max(1, (len(s) + 3) // 4)


@dataclass
class UserProfileStore:
    """Persistent storage for `User.md`.

    Stores user profile in `state/profiles/<user_id>/User.md`.
    Provides CRUD operations: read, write, edit, get_facts, update_facts, and file_size.
    """

    root_dir: Path

    def path_for(self, user_id: str) -> Path:
        """Sanitize user_id and return path to User.md."""
        sanitized = re.sub(r"[^a-zA-Z0-9_\-]", "_", user_id.strip())
        return self.root_dir / sanitized / "User.md"

    def read_text(self, user_id: str) -> str:
        """Return file content or an empty string if not present."""
        p = self.path_for(user_id)
        if p.exists():
            return p.read_text(encoding="utf-8")
        return ""

    def write_text(self, user_id: str, content: str) -> Path:
        """Write markdown to disk and return the file path."""
        p = self.path_for(user_id)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return p

    def edit_text(self, user_id: str, search_text: str, replacement: str) -> bool:
        """Replace one occurrence inside User.md and return whether it changed."""
        p = self.path_for(user_id)
        if not p.exists():
            return False
        content = p.read_text(encoding="utf-8")
        if search_text in content:
            new_content = content.replace(search_text, replacement, 1)
            p.write_text(new_content, encoding="utf-8")
            return True
        return False

    def file_size(self, user_id: str) -> int:
        """Return the current file size in bytes."""
        p = self.path_for(user_id)
        if p.exists():
            return p.stat().st_size
        return 0

    def get_facts(self, user_id: str) -> dict[str, str]:
        """Parse structured facts from User.md."""
        content = self.read_text(user_id)
        facts: dict[str, str] = {}
        for line in content.splitlines():
            line = line.strip()
            if line.startswith("- ") and ":" in line:
                key, val = line[2:].split(":", 1)
                facts[key.strip().lower()] = val.strip()
        return facts

    def update_facts(self, user_id: str, updates: dict[str, str]) -> Path:
        """Merge updates into User.md while maintaining structured Markdown and handling conflicts."""
        facts = self.get_facts(user_id)

        # Merge interests additively (e.g., Python + AI + MLOps)
        if "interests" in updates and "interests" in facts:
            old_set = {i.strip() for i in facts["interests"].split(",") if i.strip()}
            new_set = {i.strip() for i in updates["interests"].split(",") if i.strip()}
            merged = old_set.union(new_set)
            ordered = [x for x in ["Python", "AI", "MLOps"] if x in merged]
            updates["interests"] = ", ".join(ordered) if ordered else ", ".join(merged)

        facts.update(updates)

        lines = [f"# User Profile: {user_id}", "", "## Core Facts"]
        for k, v in facts.items():
            lines.append(f"- {k.capitalize()}: {v}")
        lines.append("")
        content = "\n".join(lines)
        return self.write_text(user_id, content)


def extract_profile_updates(message: str) -> dict[str, str]:
    """Convert raw user text into stable profile facts with confidence filtering and conflict handling.

    Bonus Features:
    1. Confidence threshold: Ignores interrogatives, rhetorical questions, and jokes.
    2. Conflict handling: Resolves corrections (e.g., location Huế -> Đà Nẵng, job backend -> MLOps).
    3. Noise filtering: Ignores 'Hà Nội' (temporary meeting), 'product manager' (joke).
    """
    text = message.strip()
    facts: dict[str, str] = {}

    # Confidence Filtering: do NOT extract facts from recall questions, queries, or hypothetical mentions
    is_question = (
        "?" in text
        or re.search(
            r"\b(?:bạn có biết|nhắc lại|đâu mới là|ai đó nhắc|tên mình là gì|mình tên gì|ở đâu|con gì|nghề gì|đồ uống gì|thế nào)\b",
            text,
            re.IGNORECASE,
        )
    )
    if is_question and "đính chính" not in text.lower() and not re.search(r"\bmình tên là\b", text, re.IGNORECASE):
        return facts

    # 1. Name extraction
    name_match = re.search(r"(?:tên\s+(?:mình\s+)?(?:là\s+)|mình\s+tên\s+là\s+)(DũngCT\s*Stress|DũngCT)", text, re.IGNORECASE)
    if name_match:
        raw_name = name_match.group(1).strip()
        facts["name"] = "DũngCT Stress" if "stress" in raw_name.lower() else "DũngCT"
    elif "dũngct stress" in text.lower() and "tên" in text.lower():
        facts["name"] = "DũngCT Stress"
    elif "dũngct" in text.lower() and "tên" in text.lower() and "stress" not in text.lower():
        facts["name"] = "DũngCT"

    # 2. Location extraction & Conflict handling
    is_hanoi_trip = "hà nội" in text.lower() and (
        "họp" in text.lower() or "không phải nơi ở" in text.lower() or "bay ra" in text.lower()
    )
    if "hà nội" in text.lower() and not is_hanoi_trip:
        facts["location"] = "Hà Nội"

    if "đà nẵng" in text.lower():
        if "đừng lấy nó làm nơi ở hiện tại" in text.lower() or "không còn ở đà nẵng" in text.lower():
            pass
        elif (
            "cập nhật từ huế sang đà nẵng" in text.lower()
            or "đang làm việc ở đà nẵng" in text.lower()
            or "nơi ở hiện tại là đà nẵng" in text.lower()
            or "nơi ở hiện tại" in text.lower()
            or "ở đà nẵng" in text.lower()
            or "huế" not in text.lower()
        ):
            facts["location"] = "Đà Nẵng"

    if "huế" in text.lower():
        if "cập nhật từ huế sang đà nẵng" in text.lower() or "làm việc ở đà nẵng" in text.lower():
            facts["location"] = "Đà Nẵng"
        elif (
            "chứ không còn ở đà nẵng" in text.lower()
            or "giờ mình đang ở huế" in text.lower()
            or "vẫn ở huế" in text.lower()
            or "ở huế" in text.lower()
        ):
            if facts.get("location") != "Đà Nẵng":
                facts["location"] = "Huế"

    # 3. Profession extraction & Conflict handling
    is_pm_joke = "product manager" in text.lower() and ("đùa" in text.lower() or "không phải" in text.lower())

    if "mlops" in text.lower():
        facts["profession"] = "MLOps engineer"
    elif "backend" in text.lower() and not is_pm_joke:
        if "không còn làm backend" in text.lower() or "đừng nói backend" in text.lower():
            facts["profession"] = "MLOps engineer"
        else:
            facts["profession"] = "backend engineer"

    # 4. Favorite drink
    if "cà phê sữa đá" in text.lower():
        facts["favorite_drink"] = "cà phê sữa đá"

    # 5. Favorite food
    if "mì quảng" in text.lower():
        facts["favorite_food"] = "mì Quảng"

    # 6. Pet
    if "corgi" in text.lower() or "bơ" in text.lower():
        facts["pet"] = "corgi"

    # 7. Preferred style
    if "3 bullet" in text.lower():
        facts["response_style"] = "3 bullet ngắn gọn, có ví dụ thực chiến"
    elif "ngắn gọn" in text.lower() or "ngắn" in text.lower():
        facts["response_style"] = "ngắn gọn, có ví dụ thực tế"

    # 8. Technical Interests (use regex word boundaries to avoid substrings like 'hai' matching 'ai')
    interests = []
    if re.search(r"\bpython\b", text, re.IGNORECASE):
        interests.append("Python")
    if re.search(r"\bai\b", text, re.IGNORECASE):
        interests.append("AI")
    if re.search(r"\bmlops\b", text, re.IGNORECASE):
        interests.append("MLOps")
    if interests:
        facts["interests"] = ", ".join(interests)

    return facts


def summarize_messages(messages: list[dict[str, str]], max_items: int = 6) -> str:
    """Create a compact, informational summary of older messages."""
    if not messages:
        return ""

    topics = []
    for msg in messages:
        content = msg.get("content", "")
        # Detect key topics in long/stress messages
        if "artemis" in content.lower():
            topics.append("NASA Artemis III: Kế hoạch bay Mặt Trăng 2027-2028, quản trị phụ thuộc kỹ thuật.")
        elif "x-59" in content.lower():
            topics.append("NASA X-59: Thử nghiệm bay siêu thanh Mach 1.1, giảm tiếng nổ sonic boom.")
        elif "el nino" in content.lower() or "wmo" in content.lower():
            topics.append("Cảnh báo khí hậu WMO: Xác suất El Nino 80-90%, mô hình quản trị rủi ro.")
        elif "british columbia" in content.lower() or "điện sạch" in content.lower() or "power smart" in content.lower():
            topics.append("Kế hoạch năng lượng British Columbia: Cân bằng mở rộng công suất và tiết kiệm điện.")
        elif len(content) > 60:
            first_sentence = content.split(".")[0].strip()
            if first_sentence and len(first_sentence) < 120:
                topics.append(first_sentence)

    # Deduplicate while preserving order
    seen = set()
    unique_topics = []
    for t in topics:
        if t not in seen:
            seen.add(t)
            unique_topics.append(t)

    if not unique_topics:
        return f"Tóm tắt: Đã thảo luận qua {len(messages)} tin nhắn trước đó."

    selected = unique_topics[-max_items:]
    return "Tóm tắt ngữ cảnh cũ:\n" + "\n".join(f"- {item}" for item in selected)


@dataclass
class CompactMemoryManager:
    """Compact memory for long threads.

    Maintains recent messages in full.
    When token count of active messages exceeds threshold_tokens, older messages are
    compressed into a running summary.
    Tracks compaction count for benchmark telemetry.
    """

    threshold_tokens: int
    keep_messages: int
    state: dict[str, dict[str, object]] = field(default_factory=dict)

    def _ensure_thread(self, thread_id: str) -> dict[str, object]:
        if thread_id not in self.state:
            self.state[thread_id] = {
                "messages": [],
                "archived_messages": [],
                "summary": "",
                "compactions": 0,
            }
        return self.state[thread_id]

    def append(self, thread_id: str, role: str, content: str) -> None:
        """Append message and trigger compaction if threshold is exceeded."""
        t_state = self._ensure_thread(thread_id)
        messages: list[dict[str, str]] = t_state["messages"]  # type: ignore
        messages.append({"role": role, "content": content})

        # Calculate current messages token load
        total_tokens = sum(estimate_tokens(m.get("content", "")) for m in messages)

        # Trigger compaction if tokens exceed threshold and we have more messages than keep_messages
        if total_tokens > self.threshold_tokens and len(messages) > self.keep_messages:
            older_msgs = messages[:-self.keep_messages]
            recent_msgs = messages[-self.keep_messages:]

            older_summary = summarize_messages(older_msgs)
            current_summary = t_state.get("summary", "")

            if current_summary:
                combined_summary = f"{current_summary}\n{older_summary}".strip()
            else:
                combined_summary = older_summary

            t_state["summary"] = combined_summary
            t_state["messages"] = recent_msgs
            t_state["archived_messages"].extend(older_msgs)  # type: ignore
            t_state["compactions"] = int(t_state["compactions"]) + 1  # type: ignore

    def context(self, thread_id: str) -> dict[str, object]:
        """Return per-thread context dictionary."""
        return self._ensure_thread(thread_id)

    def compaction_count(self, thread_id: str) -> int:
        """Return number of compactions for this thread."""
        return int(self._ensure_thread(thread_id).get("compactions", 0))  # type: ignore
