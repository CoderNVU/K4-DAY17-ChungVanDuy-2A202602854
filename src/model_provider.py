from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ProviderConfig:
    """Configuration for chat model providers shared by the agents.

    Required providers for this lab:
    - openai
    - custom (OpenAI-compatible base URL)
    - gemini
    - anthropic
    - ollama
    - openrouter
    """

    provider: str
    model_name: str
    temperature: float = 0.0
    api_key: str | None = None
    base_url: str | None = None


def normalize_provider(value: str) -> str:
    """Map provider names and common aliases to canonical provider names."""
    val = value.strip().lower().replace("_", "-")
    aliases = {
        "anthorpic": "anthropic",
        "claude": "anthropic",
        "google": "gemini",
        "google-genai": "gemini",
        "gemini-api": "gemini",
        "chatgpt": "openai",
        "gpt": "openai",
        "vllm": "custom",
        "sglang": "custom",
        "openai-compatible": "custom",
        "local": "ollama",
        "open-router": "openrouter",
    }
    return aliases.get(val, val)


def build_chat_model(config: ProviderConfig):
    """Instantiate the chat model for the selected provider with graceful import error handling."""
    provider = normalize_provider(config.provider)

    if provider == "openai":
        try:
            from langchain_openai import ChatOpenAI
            return ChatOpenAI(
                model=config.model_name,
                temperature=config.temperature,
                api_key=config.api_key,
            )
        except ImportError as e:
            raise ImportError(
                "langchain-openai is required for the 'openai' provider. "
                "Install it with `pip install langchain-openai`."
            ) from e

    elif provider == "custom":
        try:
            from langchain_openai import ChatOpenAI
            return ChatOpenAI(
                model=config.model_name,
                temperature=config.temperature,
                base_url=config.base_url,
                api_key=config.api_key or "EMPTY",
            )
        except ImportError as e:
            raise ImportError(
                "langchain-openai is required for the 'custom' provider. "
                "Install it with `pip install langchain-openai`."
            ) from e

    elif provider == "gemini":
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI
            return ChatGoogleGenerativeAI(
                model=config.model_name,
                temperature=config.temperature,
                google_api_key=config.api_key,
            )
        except ImportError as e:
            raise ImportError(
                "langchain-google-genai is required for the 'gemini' provider. "
                "Install it with `pip install langchain-google-genai`."
            ) from e

    elif provider == "anthropic":
        try:
            from langchain_anthropic import ChatAnthropic
            return ChatAnthropic(
                model=config.model_name,
                temperature=config.temperature,
                api_key=config.api_key,
            )
        except ImportError as e:
            raise ImportError(
                "langchain-anthropic is required for the 'anthropic' provider. "
                "Install it with `pip install langchain-anthropic`."
            ) from e

    elif provider == "ollama":
        try:
            from langchain_ollama import ChatOllama
            return ChatOllama(
                model=config.model_name,
                temperature=config.temperature,
                base_url=config.base_url or "http://localhost:11434",
            )
        except ImportError as e:
            raise ImportError(
                "langchain-ollama is required for the 'ollama' provider. "
                "Install it with `pip install langchain-ollama`."
            ) from e

    elif provider == "openrouter":
        try:
            from langchain_openai import ChatOpenAI
            return ChatOpenAI(
                model=config.model_name,
                temperature=config.temperature,
                base_url=config.base_url or "https://openrouter.ai/api/v1",
                api_key=config.api_key,
            )
        except ImportError as e:
            raise ImportError(
                "langchain-openai is required for the 'openrouter' provider. "
                "Install it with `pip install langchain-openai`."
            ) from e

    else:
        raise ValueError(
            f"Unsupported provider: '{config.provider}'. "
            f"Supported providers: openai, custom, gemini, anthropic, ollama, openrouter."
        )
