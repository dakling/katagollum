"""Configuration loader for KataGo LLM.

Reads configuration from ~/.config/katagollum.yaml
Falls back to config.yaml.default in the project root if user config doesn't exist.
"""

import os
from pathlib import Path
from typing import Any

import yaml


def get_config() -> dict[str, Any]:
    """Load configuration from YAML file.

    Priority:
    1. ~/.config/katagollum.yaml (user config)
    2. config.yaml.default in project root (default config)

    Returns:
        Dictionary containing configuration values
    """
    # Try user config first
    user_config_path = Path.home() / ".config" / "katagollum.yaml"

    # Fall back to default config in project root
    project_root = Path(__file__).parent.parent.parent
    default_config_path = project_root / "config.yaml.default"

    config_path = user_config_path if user_config_path.exists() else default_config_path

    try:
        with open(config_path) as f:
            config = yaml.safe_load(f)
        return config or {}
    except Exception as e:
        print(f"Warning: Could not load config from {config_path}: {e}")
        return {}


def get_katago_model() -> str:
    """Get KataGo model path from config."""
    config = get_config()
    model_path = config.get("katago", {}).get(
        "model", "~/Go/katago-networks/kata1-b28c512nbt-s9584861952-d4960414494.bin.gz"
    )
    return os.path.expanduser(model_path)


def get_katago_config() -> str:
    """Get KataGo config path from config."""
    config = get_config()
    config_path = config.get("katago", {}).get("config", "~/.config/katago/minimal_fast.cfg")
    return os.path.expanduser(config_path)


def get_llm_model() -> str:
    """Get LLM model name from config."""
    config = get_config()
    return config.get("llm", {}).get("model", "llama3.2")


def get_llm_base_url() -> str:
    """Get LLM base URL from config."""
    config = get_config()
    return config.get("llm", {}).get("base_url", "http://localhost:11434/v1")
