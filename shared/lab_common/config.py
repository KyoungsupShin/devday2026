"""Configuration that is safe to import from a Jupyter notebook."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:  # Allows the local-only workflow/tests to run before pip install.
    def load_dotenv(path: Path, override: bool = False) -> bool:
        if not path.exists():
            return False
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                if override or key.strip() not in os.environ:
                    os.environ[key.strip()] = value.strip()
        return True

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def load_settings(env_file: Path | None = None) -> "Settings":
    """Load the repository-level .env without overriding shell variables."""
    selected_env = env_file or REPOSITORY_ROOT / ".env"
    load_dotenv(selected_env, override=False)
    return Settings(
        base_url=os.getenv("AICORE_BASE_URL", "").rstrip("/"),
        auth_url=os.getenv("AICORE_AUTH_URL", "").rstrip("/"),
        client_id=os.getenv("AICORE_CLIENT_ID", ""),
        client_secret=os.getenv("AICORE_CLIENT_SECRET", ""),
        resource_group=os.getenv("AICORE_RESOURCE_GROUP", "default"),
        llm_model=os.getenv("LLM_MODEL", "gpt-5.6-luna"),
        rerank_endpoint=os.getenv("RERANK_ENDPOINT", "").rstrip("/"),
        rerank_api_key=os.getenv("RERANK_API_KEY", ""),
        rerank_model=os.getenv("RERANK_MODEL", "cohere-rerank-pro"),
        allow_write_tools=os.getenv("ALLOW_WRITE_TOOLS", "false").lower() == "true",
    )


@dataclass(frozen=True)
class Settings:
    base_url: str
    auth_url: str
    client_id: str
    client_secret: str
    resource_group: str
    llm_model: str
    rerank_endpoint: str
    rerank_api_key: str
    rerank_model: str
    allow_write_tools: bool

    def missing_ai_core_fields(self) -> list[str]:
        values = {
            "AICORE_BASE_URL": self.base_url,
            "AICORE_AUTH_URL": self.auth_url,
            "AICORE_CLIENT_ID": self.client_id,
            "AICORE_CLIENT_SECRET": self.client_secret,
        }
        return [name for name, value in values.items() if not value]

    def require_ai_core(self) -> None:
        missing = self.missing_ai_core_fields()
        if missing:
            raise RuntimeError(
                "AI Core 설정이 없습니다: " + ", ".join(missing) +
                ". 루트 .env를 .env.example을 참고해 작성하세요."
            )

