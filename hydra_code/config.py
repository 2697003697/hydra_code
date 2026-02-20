"""
Configuration management for Hydra Code.
Supports ~/.hydra-code config file for API keys and role mappings.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml


@dataclass
class RoleConfig:
    role: str
    provider: str = "openai"
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    model_name: Optional[str] = None
    max_tokens: Optional[int] = None


@dataclass
class Config:
    role_configs: dict[str, RoleConfig] = field(default_factory=dict)
    default_role: str = "fast"
    language: str = "zh"
    max_tokens: int = 4096
    temperature: float = 0.0
    working_directory: Optional[str] = None
    auto_approve: bool = False
    verbose: bool = False
    single_model_mode: bool = True

    def __post_init__(self):
        if not self.role_configs:
            self.role_configs = self._get_default_role_configs()

    def _get_default_role_configs(self) -> dict[str, RoleConfig]:
        return {
            "fast": RoleConfig(role="fast"),
            "pro": RoleConfig(role="pro"),
            "sonnet": RoleConfig(role="sonnet"),
            "opus": RoleConfig(role="opus"),
        }

    def get_role_config(self, role: str) -> tuple[Optional[str], Optional[str], Optional[str], Optional[str], Optional[int]]:
        role_key = role.lower()
        config = self.role_configs.get(role_key)
        
        if not config:
            return None, None, None, None, None
        return config.api_key, config.base_url, config.model_name, config.provider, config.max_tokens

    def has_role_configured(self, role: str) -> bool:
        config = self.role_configs.get(role.lower())
        return bool(config and config.api_key and config.base_url and config.model_name)

    def get_configured_roles(self) -> list[str]:
        return [
            role for role, config in self.role_configs.items()
            if config.api_key and config.base_url and config.model_name
        ]


CONFIG_FILE_NAME = ".hydra-code"


def get_config_path() -> Path:
    # 1. Try default .hydra-code
    default_path = Path.home() / CONFIG_FILE_NAME
    if default_path.exists():
        return default_path
    
    # 2. Try legacy .aicli
    legacy_path = Path.home() / ".aicli"
    if legacy_path.exists():
        return legacy_path
        
    # 3. Default to .hydra-code for new configs
    return default_path


def load_config() -> Config:
    config_path = get_config_path()
    if not config_path.exists():
        return Config()

    with open(config_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    return parse_config(data)


def parse_config(data: dict) -> Config:
    role_configs = {}
    
    if "roles" in data:
        for role_name, role_data in data["roles"].items():
            role_configs[role_name.lower()] = RoleConfig(
                role=role_name.lower(),
                provider=role_data.get("provider", "openai"),
                api_key=role_data.get("api_key"),
                base_url=role_data.get("base_url"),
                model_name=role_data.get("model_name"),
                max_tokens=role_data.get("max_tokens"),
            )

    default_role = data.get("default_role", "fast")

    return Config(
        default_role=default_role,
        role_configs=role_configs,
        language=data.get("language", "zh"),
        max_tokens=data.get("max_tokens", 4096),
        temperature=data.get("temperature", 0.0),
        working_directory=data.get("working_directory"),
        auto_approve=data.get("auto_approve", False),
        verbose=data.get("verbose", False),
        single_model_mode=data.get("single_model_mode", False),
    )


def save_config(config: Config) -> None:
    config_path = get_config_path()

    data = {
        "default_role": config.default_role,
        "language": config.language,
        "max_tokens": config.max_tokens,
        "temperature": config.temperature,
        "auto_approve": config.auto_approve,
        "verbose": config.verbose,
        "single_model_mode": config.single_model_mode,
        "roles": {},
    }

    if config.working_directory:
        data["working_directory"] = config.working_directory

    for role_name, role_config in config.role_configs.items():
        role_data = {}
        if role_config.provider != "openai":
            role_data["provider"] = role_config.provider
        if role_config.api_key:
            role_data["api_key"] = role_config.api_key
        if role_config.base_url:
            role_data["base_url"] = role_config.base_url
        if role_config.model_name:
            role_data["model_name"] = role_config.model_name
        if role_config.max_tokens:
            role_data["max_tokens"] = role_config.max_tokens
        if role_data:
            data["roles"][role_name] = role_data

    with open(config_path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True)


def create_sample_config() -> None:
    config_path = get_config_path()
    if config_path.exists():
        return

    sample_config = """# Hydra Code Configuration
# Copy this file to ~/.hydra-code and fill in your API keys

default_role: fast
language: zh

max_tokens: 4096
temperature: 0.0
auto_approve: false
verbose: false

# Single model mode: use only one model for all tasks (faster, simpler)
single_model_mode: false

# Role configurations
# Each role needs: api_key, base_url, model_name
# Optional: provider (default: openai), max_tokens
roles:
  fast:
    provider: "openai" # or azure, deepseek, etc.
    api_key: "your-api-key"
    base_url: "https://api.example.com/v1"
    model_name: "model-name"
    max_tokens: 4096

  pro:
    provider: "openai" # or azure, deepseek, etc.
    api_key: "your-api-key"
    base_url: "https://api.example.com/v1"
    model_name: "model-name"
    max_tokens: 4096

  sonnet:
    provider: "openai" # or azure, deepseek, etc.
    api_key: "your-api-key"
    base_url: "https://api.example.com/v1"
    model_name: "model-name"
    max_tokens: 4096

  opus:
    provider: "openai" # or azure, deepseek, etc.
    api_key: "your-api-key"
    base_url: "https://api.example.com/v1"
    model_name: "model-name"
    max_tokens: 4096
"""

    with open(config_path, "w", encoding="utf-8") as f:
        f.write(sample_config)
