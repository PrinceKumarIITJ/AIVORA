import os
from dataclasses import dataclass
from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    database_url: str = "sqlite:///./data/aivora.db"
    origin: str = "http://127.0.0.1:8090"
    environment: str = "development"
    allow_signup: bool = True
    cookie_secure: bool = False
    provider: str = "extractive"
    model: str = ""
    groq_key: str = ""
    google_key: str = ""
    daily_limit: int = 100
    semantic_model: str = ""

    @classmethod
    def from_env(cls):
        load_dotenv()
        settings = cls(
            database_url=os.getenv("AIVORA_DATABASE_URL", cls.database_url),
            origin=os.getenv("AIVORA_ORIGIN", cls.origin).rstrip("/"),
            environment=os.getenv("AIVORA_ENV", "development"),
            allow_signup=os.getenv("AIVORA_ALLOW_SIGNUP", "true").lower() == "true",
            cookie_secure=os.getenv("AIVORA_COOKIE_SECURE", "false").lower() == "true",
            provider=os.getenv("AIVORA_PROVIDER", "extractive"),
            model=os.getenv("AIVORA_MODEL", ""),
            groq_key=os.getenv("GROQ_API_KEY", ""),
            google_key=os.getenv("GOOGLE_API_KEY", ""),
            daily_limit=int(os.getenv("AIVORA_DAILY_REQUEST_LIMIT", "100")),
            semantic_model=os.getenv("AIVORA_SEMANTIC_MODEL", ""),
        )
        if settings.provider not in {"extractive", "groq", "gemini"}:
            raise ValueError("Unsupported AIVORA_PROVIDER")
        if settings.daily_limit < 1:
            raise ValueError("Daily request limit must be positive")
        if settings.environment == "production":
            if not settings.cookie_secure or not settings.origin.startswith("https://"):
                raise ValueError("Production requires HTTPS origin and secure cookies")
            if settings.allow_signup:
                raise ValueError("Disable public organization signup for production")
            # SQLite has no database-level tenant isolation; do not imply otherwise.
            raise ValueError("v0.1 is a local pilot; production requires the hardening gates in docs/OPERATIONS.md")
        return settings
