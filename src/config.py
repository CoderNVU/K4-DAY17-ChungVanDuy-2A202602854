from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

from model_provider import ProviderConfig, normalize_provider


@dataclass
class LabConfig:
    """Shared configuration for the lab."""

    base_dir: Path
    data_dir: Path
    state_dir: Path
    compact_threshold_tokens: int = 600
    compact_keep_messages: int = 4
    model: ProviderConfig = field(
        default_factory=lambda: ProviderConfig(
            provider="openai",
            model_name="gpt-4o-mini",
            temperature=0.0,
        )
    )
    judge_model: ProviderConfig = field(
        default_factory=lambda: ProviderConfig(
            provider="openai",
            model_name="gpt-4o-mini",
            temperature=0.0,
        )
    )


def load_config(base_dir: Path | None = None) -> LabConfig:
    """Load configuration from environment variables or defaults and return a LabConfig.

    Steps:
    1. Resolve the repo root or default to the parent of src/.
    2. Load values from .env if present.
    3. Ensure state/ and state/profiles/ exist.
    4. Populate and return a LabConfig instance.
    """
    root = (base_dir or Path(__file__).resolve().parent.parent).resolve()
    data_dir = root / "data"
    state_dir = root / "state"

    # Load .env if present
    env_file = root / ".env"
    if env_file.exists():
        load_dotenv(dotenv_path=env_file)
    else:
        load_dotenv()

    # Ensure state/profiles directory exists
    profiles_dir = state_dir / "profiles"
    profiles_dir.mkdir(parents=True, exist_ok=True)

    # Provider and model resolution
    provider = normalize_provider(os.getenv("LLM_PROVIDER", "openai"))
    model_name = os.getenv("LLM_MODEL", "gpt-4o-mini")
    temperature = float(os.getenv("LLM_TEMPERATURE", "0.0"))

    # API keys and base URLs
    api_key: str | None = None
    base_url: str | None = None

    if provider == "openai":
        api_key = os.getenv("OPENAI_API_KEY")
    elif provider == "custom":
        api_key = os.getenv("CUSTOM_API_KEY") or os.getenv("OPENAI_API_KEY")
        base_url = os.getenv("CUSTOM_BASE_URL", "http://localhost:8000/v1")
    elif provider == "gemini":
        api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    elif provider == "anthropic":
        api_key = os.getenv("ANTHROPIC_API_KEY")
    elif provider == "ollama":
        base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    elif provider == "openrouter":
        api_key = os.getenv("OPENROUTER_API_KEY")
        base_url = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")

    # Thresholds
    threshold_tokens = int(os.getenv("COMPACT_THRESHOLD_TOKENS", "600"))
    keep_messages = int(os.getenv("COMPACT_KEEP_MESSAGES", "4"))

    model_config = ProviderConfig(
        provider=provider,
        model_name=model_name,
        temperature=temperature,
        api_key=api_key,
        base_url=base_url,
    )

    # Judge model config
    judge_provider = normalize_provider(os.getenv("JUDGE_LLM_PROVIDER", provider))
    judge_model_name = os.getenv("JUDGE_LLM_MODEL", model_name)
    judge_model_config = ProviderConfig(
        provider=judge_provider,
        model_name=judge_model_name,
        temperature=0.0,
        api_key=api_key,
        base_url=base_url,
    )

    return LabConfig(
        base_dir=root,
        data_dir=data_dir,
        state_dir=state_dir,
        compact_threshold_tokens=threshold_tokens,
        compact_keep_messages=keep_messages,
        model=model_config,
        judge_model=judge_model_config,
    )
