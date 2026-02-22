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
    # For model reference
    use_model: Optional[str] = None


@dataclass
class ModelProfile:
    name: str
    provider: str = "openai"
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    model_name: Optional[str] = None
    max_tokens: Optional[int] = None
    description: Optional[str] = None


@dataclass
class Config:
    role_configs: dict[str, RoleConfig] = field(default_factory=dict)
    models: dict[str, ModelProfile] = field(default_factory=dict)
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
            
        # If using a model reference, look it up
        if config.use_model:
            model = self.models.get(config.use_model)
            if model:
                return (
                    model.api_key, 
                    model.base_url, 
                    model.model_name, 
                    model.provider, 
                    config.max_tokens or model.max_tokens # Role specific max_tokens overrides model default
                )
            # If model not found, fallback or return incomplete
            return None, None, None, None, None

        return config.api_key, config.base_url, config.model_name, config.provider, config.max_tokens

    def has_role_configured(self, role: str) -> bool:
        config = self.role_configs.get(role.lower())
        if not config:
            return False
            
        if config.use_model:
            model = self.models.get(config.use_model)
            return bool(model and model.api_key and model.base_url and model.model_name)
            
        return bool(config.api_key and config.base_url and config.model_name)

    def get_configured_roles(self) -> list[str]:
        return [role for role in self.role_configs.keys() if self.has_role_configured(role)]


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
    models = {}
    if "models" in data:
        for name, model_data in data["models"].items():
            models[name] = ModelProfile(
                name=name,
                provider=model_data.get("provider", "openai"),
                api_key=model_data.get("api_key"),
                base_url=model_data.get("base_url"),
                model_name=model_data.get("model_name"),
                max_tokens=model_data.get("max_tokens"),
                description=model_data.get("description"),
            )

    role_configs = {}
    
    if "roles" in data:
        for role_name, role_data in data["roles"].items():
            if isinstance(role_data, str):
                # Format: role: model_name
                role_configs[role_name.lower()] = RoleConfig(
                    role=role_name.lower(),
                    use_model=role_data
                )
            else:
                # Format: role: { ... }
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
        models=models,
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

    if config.models:
        data["models"] = {}
        for name, model in config.models.items():
            model_data = {
                "provider": model.provider,
                "api_key": model.api_key,
                "base_url": model.base_url,
                "model_name": model.model_name,
            }
            if model.max_tokens:
                model_data["max_tokens"] = model.max_tokens
            if model.description:
                model_data["description"] = model.description
            data["models"][name] = model_data

    for role_name, role_config in config.role_configs.items():
        if role_config.use_model:
            # Save as reference
            data["roles"][role_name] = role_config.use_model
        else:
            # Save as full config
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
# Can be direct configuration or reference to a model in 'models'
roles:
  fast: "deepseek-v3" # References model defined below
  pro: "gpt-4" 
  sonnet: "claude-3-5-sonnet"
  opus:
    # Inline configuration (legacy style)
    provider: "openai"
    api_key: "your-api-key"
    base_url: "https://api.example.com/v1"
    model_name: "model-name"

# Define reusable model profiles here
models:
  deepseek-v3:
    provider: "deepseek"
    api_key: "sk-..."
    base_url: "https://api.deepseek.com"
    model_name: "deepseek-chat"
    description: "Official DeepSeek API"
    max_tokens: 4096
  
  deepseek-azure:
    provider: "azure"
    api_key: "..."
    base_url: "https://my-resource.openai.azure.com"
    model_name: "deepseek-v3"
    description: "Azure hosted DeepSeek"
    max_tokens: 4096

  gpt-4:
    provider: "openai"
    api_key: "sk-..."
    base_url: "https://api.openai.com/v1"
    model_name: "gpt-4"
    description: "Standard OpenAI GPT-4"
    max_tokens: 4096

  claude-3-5-sonnet:
    provider: "anthropic"
    api_key: "sk-ant-..."
    base_url: "https://api.anthropic.com/v1"
    model_name: "claude-3-5-sonnet-20240620"
    description: "Anthropic Claude 3.5 Sonnet"
    max_tokens: 4096
"""

    with open(config_path, "w", encoding="utf-8") as f:
        f.write(sample_config)
