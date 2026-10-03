import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agent_advanced import AdvancedAgent
from agent_baseline import BaselineAgent
from config import load_config


@dataclass
class BenchmarkRow:
    agent_name: str
    agent_tokens_only: int
    prompt_tokens_processed: int
    recall_score: float
    response_quality: float
    memory_growth_bytes: int
    compactions: int


def load_conversations(path: Path) -> list[dict[str, Any]]:
    """Read JSON conversations from disk."""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def recall_points(answer: str, expected: list[str]) -> float:
    """Return fraction of expected facts present in the answer (0.0 to 1.0)."""
    if not expected:
        return 1.0
    ans_lower = answer.lower()
    matches = sum(1 for exp in expected if exp.lower() in ans_lower)
    return matches / len(expected)


def heuristic_quality(answer: str, expected: list[str]) -> float:
    """Add a lightweight quality score evaluating structure, recall, and conciseness."""
    if not answer or len(answer.strip()) < 10:
        return 0.0

    score = 0.5
    # Structured response bonus (bullets or clean lines)
    if "-" in answer or "\n" in answer:
        score += 0.2
    # Fact accuracy bonus
    rec = recall_points(answer, expected)
    score += 0.3 * rec

    return min(1.0, round(score, 2))


def run_agent_benchmark(
    agent_name: str,
    agent: BaselineAgent | AdvancedAgent,
    conversations: list[dict[str, Any]],
    config: Any,
) -> BenchmarkRow:
    """Evaluate one agent over conversations and compute benchmark metrics."""
    user_ids = {c["user_id"] for c in conversations}
    initial_memory = sum(agent.memory_file_size(u) for u in user_ids) if hasattr(agent, "memory_file_size") else 0

    recall_scores: list[float] = []
    quality_scores: list[float] = []
    total_compactions = 0

    for conv in conversations:
        user_id = conv["user_id"]
        conv_id = conv["id"]

        # 1. Process conversation turns in thread
        for turn in conv["turns"]:
            agent.reply(user_id=user_id, thread_id=conv_id, message=turn)

        if hasattr(agent, "compaction_count"):
            total_compactions += agent.compaction_count(conv_id)

        # 2. Ask recall questions in fresh threads to measure cross-session memory
        for q_idx, q in enumerate(conv.get("recall_questions", [])):
            fresh_thread_id = f"{conv_id}_recall_{q_idx}"
            reply = agent.reply(user_id=user_id, thread_id=fresh_thread_id, message=q["question"])
            ans = reply["response"]
            expected = q.get("expected_contains", [])

            recall_scores.append(recall_points(ans, expected))
            quality_scores.append(heuristic_quality(ans, expected))

    agent_tokens = agent.total_token_usage()
    prompt_tokens = agent.total_prompt_token_usage()
    final_memory = sum(agent.memory_file_size(u) for u in user_ids) if hasattr(agent, "memory_file_size") else 0
    memory_growth = max(0, final_memory - initial_memory)

    avg_recall = (sum(recall_scores) / len(recall_scores) * 100) if recall_scores else 0.0
    avg_quality = (sum(quality_scores) / len(quality_scores) * 100) if quality_scores else 0.0

    return BenchmarkRow(
        agent_name=agent_name,
        agent_tokens_only=agent_tokens,
        prompt_tokens_processed=prompt_tokens,
        recall_score=round(avg_recall, 1),
        response_quality=round(avg_quality, 1),
        memory_growth_bytes=memory_growth,
        compactions=total_compactions,
    )


def format_rows(rows: list[BenchmarkRow]) -> str:
    """Format benchmark rows into a clean Markdown table."""
    try:
        from tabulate import tabulate
        table_data = [
            [
                r.agent_name,
                f"{r.agent_tokens_only:,}",
                f"{r.prompt_tokens_processed:,}",
                f"{r.recall_score}%",
                f"{r.response_quality}%",
                f"{r.memory_growth_bytes:,}",
                r.compactions,
            ]
            for r in rows
        ]
        headers = [
            "Agent",
            "Agent tokens only",
            "Prompt tokens processed",
            "Cross-session recall",
            "Response quality",
            "Memory growth (bytes)",
            "Compactions",
        ]
        return tabulate(table_data, headers=headers, tablefmt="github")
    except ImportError:
        # Fallback to pure string Markdown formatting if tabulate is absent
        header_line = "| Agent | Agent tokens only | Prompt tokens processed | Cross-session recall | Response quality | Memory growth (bytes) | Compactions |"
        sep_line = "|:---|---:|---:|---:|---:|---:|---:|"
        row_lines = [
            f"| {r.agent_name} | {r.agent_tokens_only:,} | {r.prompt_tokens_processed:,} | {r.recall_score}% | {r.response_quality}% | {r.memory_growth_bytes:,} | {r.compactions} |"
            for r in rows
        ]
        return "\n".join([header_line, sep_line] + row_lines)


def main() -> None:
    """Run both Standard Benchmark and Long-Context Stress Benchmark."""
    repo_root = Path(__file__).resolve().parent.parent
    config = load_config(repo_root)

    standard_path = config.data_dir / "conversations.json"
    stress_path = config.data_dir / "advanced_long_context.json"

    print("=" * 80)
    print("MEMORY SYSTEMS BENCHMARK: BASELINE vs ADVANCED")
    print("=" * 80)

    # 1. Standard Benchmark Suite
    if standard_path.exists():
        print("\n### 1. Standard Benchmark (data/conversations.json)")
        standard_convs = load_conversations(standard_path)

        # Baseline Agent
        baseline_std = BaselineAgent(config, force_offline=True)
        row_baseline_std = run_agent_benchmark("Baseline", baseline_std, standard_convs, config)

        # Advanced Agent (clean state for fresh benchmark)
        profile_dir = config.state_dir / "profiles" / "dungct"
        if (profile_dir / "User.md").exists():
            (profile_dir / "User.md").unlink()

        advanced_std = AdvancedAgent(config, force_offline=True)
        row_advanced_std = run_agent_benchmark("Advanced", advanced_std, standard_convs, config)

        print(format_rows([row_baseline_std, row_advanced_std]))

    # 2. Long-Context Stress Benchmark Suite
    if stress_path.exists():
        print("\n### 2. Long-Context Stress Benchmark (data/advanced_long_context.json)")
        stress_convs = load_conversations(stress_path)

        # Baseline Agent
        baseline_stress = BaselineAgent(config, force_offline=True)
        row_baseline_stress = run_agent_benchmark("Baseline", baseline_stress, stress_convs, config)

        # Advanced Agent (clean state for stress benchmark)
        stress_profile_dir = config.state_dir / "profiles" / "dungct_stress"
        if (stress_profile_dir / "User.md").exists():
            (stress_profile_dir / "User.md").unlink()

        advanced_stress = AdvancedAgent(config, force_offline=True)
        row_advanced_stress = run_agent_benchmark("Advanced", advanced_stress, stress_convs, config)

        print(format_rows([row_baseline_stress, row_advanced_stress]))

    print("\n" + "=" * 80)
    print("Benchmark completed successfully.")


if __name__ == "__main__":
    main()
