from pathlib import Path

from agent_advanced import AdvancedAgent
from agent_baseline import BaselineAgent
from config import LabConfig, load_config
from memory_store import CompactMemoryManager, UserProfileStore


def make_config(tmp_path: Path) -> LabConfig:
    """Build an isolated config for tests with a lower compact threshold."""
    base_cfg = load_config()
    state_dir = tmp_path / "state"
    (state_dir / "profiles").mkdir(parents=True, exist_ok=True)
    return LabConfig(
        base_dir=base_cfg.base_dir,
        data_dir=base_cfg.data_dir,
        state_dir=state_dir,
        compact_threshold_tokens=50,  # Small threshold to trigger compaction in tests
        compact_keep_messages=2,
        model=base_cfg.model,
        judge_model=base_cfg.judge_model,
    )


def test_user_markdown_read_write_edit(tmp_path: Path) -> None:
    """Verify `User.md` can be created, read, edited, and monitored for size."""
    profiles_dir = tmp_path / "profiles"
    store = UserProfileStore(profiles_dir)

    # 1. Write text
    p = store.write_text("user_test", "# User Profile\n- Name: Alice\n- Location: Hanoi\n")
    assert p.exists()
    assert store.file_size("user_test") > 0

    # 2. Read text
    content = store.read_text("user_test")
    assert "- Name: Alice" in content
    assert "- Location: Hanoi" in content

    # 3. Edit text
    edited = store.edit_text("user_test", "Hanoi", "Hue")
    assert edited is True
    assert "- Location: Hue" in store.read_text("user_test")

    # 4. Update structured facts
    store.update_facts("user_test", {"profession": "MLOps engineer"})
    facts = store.get_facts("user_test")
    assert facts.get("profession") == "MLOps engineer"


def test_compact_trigger(tmp_path: Path) -> None:
    """Verify long threads trigger compaction when token threshold is exceeded."""
    cm = CompactMemoryManager(threshold_tokens=40, keep_messages=2)

    # Append 4 substantial messages to exceed threshold
    cm.append("t-1", "user", "Tin nhắn đầu tiên thảo luận về kiến trúc memory systems cho AI Agent.")
    cm.append("t-1", "assistant", "Phản hồi giải thích chi tiết về short-term và persistent memory.")
    cm.append("t-1", "user", "Tin nhắn thứ ba tiếp tục mở rộng về compact rolling summary.")
    cm.append("t-1", "assistant", "Phản hồi xác nhận và phân tích chi phí prompt tokens.")

    # Compaction should have fired
    assert cm.compaction_count("t-1") >= 1
    ctx = cm.context("t-1")
    assert len(ctx["messages"]) == 2  # Only kept messages remain active
    assert len(ctx["summary"]) > 0  # Summary generated from older turns


def test_cross_session_recall(tmp_path: Path) -> None:
    """Verify advanced remembers across sessions and baseline does not."""
    cfg = make_config(tmp_path)
    baseline = BaselineAgent(cfg, force_offline=True)
    advanced = AdvancedAgent(cfg, force_offline=True)

    # Session 1: User introduces themselves
    intro = "Chào bạn, mình tên là DũngCT. Nơi ở hiện tại là Huế và đồ uống yêu thích là cà phê sữa đá."
    baseline.reply("dungct", "session_1", intro)
    advanced.reply("dungct", "session_1", intro)

    # Session 2: Recall in a completely fresh thread
    query = "Mình tên gì, hiện ở đâu và thích uống gì?"
    resp_b = baseline.reply("dungct", "session_2", query)
    resp_a = advanced.reply("dungct", "session_2", query)

    # Baseline forgets across threads
    assert "DũngCT" not in resp_b["response"]
    assert "cà phê sữa đá" not in resp_b["response"]
    assert "chưa có thông tin" in resp_b["response"]

    # Advanced recalls perfectly across threads
    assert "DũngCT" in resp_a["response"]
    assert "Huế" in resp_a["response"]
    assert "cà phê sữa đá" in resp_a["response"]


def test_compact_reduces_prompt_load_on_long_thread(tmp_path: Path) -> None:
    """Compare prompt load of baseline vs advanced on a long thread."""
    cfg = make_config(tmp_path)
    cfg.compact_threshold_tokens = 250
    cfg.compact_keep_messages = 3

    baseline = BaselineAgent(cfg, force_offline=True)
    advanced = AdvancedAgent(cfg, force_offline=True)

    thread_id = "stress_test_thread"
    stress_file = cfg.data_dir / "advanced_long_context.json"
    if stress_file.exists():
        import json
        with open(stress_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            turns = data[0]["turns"]
    else:
        turns = [
            f"Turn {i}: Đoạn hội thoại dài thảo luận về kỹ thuật tối ưu bộ nhớ cho AI agent với nhiều chi tiết phức tạp. " * 6
            for i in range(16)
        ]

    for turn in turns:
        baseline.reply("dungct_stress", thread_id, turn)
        advanced.reply("dungct_stress", thread_id, turn)

    # Advanced should have triggered compactions and carried significantly fewer prompt tokens
    assert advanced.compaction_count(thread_id) > 0
    baseline_prompt_tokens = baseline.prompt_token_usage(thread_id)
    advanced_prompt_tokens = advanced.prompt_token_usage(thread_id)

    assert advanced_prompt_tokens < baseline_prompt_tokens, (
        f"Advanced prompt tokens ({advanced_prompt_tokens}) must be less than baseline ({baseline_prompt_tokens})"
    )


def test_conflict_handling_in_profile(tmp_path: Path) -> None:
    """Verify correction updates overwrite obsolete facts in User.md (Bonus)."""
    cfg = make_config(tmp_path)
    agent = AdvancedAgent(cfg, force_offline=True)

    # Initial facts
    agent.reply("dungct", "t-1", "Chào bạn, mình tên là DũngCT. Mình ở Đà Nẵng và làm backend engineer.")
    facts_1 = agent.profile_store.get_facts("dungct")
    assert facts_1["location"] == "Đà Nẵng"
    assert facts_1["profession"] == "backend engineer"

    # Correction turn
    agent.reply("dungct", "t-2", "À, mình đính chính: giờ mình đang ở Huế chứ không còn ở Đà Nẵng nữa. Và mình chuyển sang MLOps engineer.")
    facts_2 = agent.profile_store.get_facts("dungct")
    assert facts_2["location"] == "Huế"
    assert facts_2["profession"] == "MLOps engineer"


def test_confidence_filtering_ignores_noise(tmp_path: Path) -> None:
    """Verify questions, rhetorical jokes, and temporary meetings do not corrupt User.md (Bonus)."""
    cfg = make_config(tmp_path)
    agent = AdvancedAgent(cfg, force_offline=True)

    # Setup base facts
    agent.reply("dungct", "t-1", "Chào bạn, mình tên là DũngCT. Nơi ở hiện tại là Đà Nẵng, nghề MLOps engineer.")

    # Noise message containing jokes and meeting trips
    noise_msg = (
        "Có lúc mình đùa chuyển sang product manager, nhưng chỉ là câu đùa thôi. "
        "Hà Nội chỉ là nơi mình vừa bay ra họp 2 ngày chứ không phải nơi ở."
    )
    agent.reply("dungct", "t-2", noise_msg)

    facts = agent.profile_store.get_facts("dungct")
    assert facts["profession"] == "MLOps engineer"
    assert facts["location"] == "Đà Nẵng"
    assert "product manager" not in facts.get("profession", "")
    assert "Hà Nội" not in facts.get("location", "")
