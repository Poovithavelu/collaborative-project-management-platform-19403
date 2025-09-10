from functools import lru_cache
import os
from pydantic import BaseModel, Field, ValidationError
from typing import Optional


class Settings(BaseModel):
    """Application settings loaded from environment variables."""
    jwt_secret: str = Field(..., description="Secret key for signing JWT tokens")
    jwt_algorithm: str = Field(default="HS256", description="JWT algorithm")
    jwt_expires_minutes: int = Field(default=120, description="JWT expiration in minutes")

    # CORS and security-related settings
    cors_allow_origins: str = Field(
        default="http://localhost:3000",
        description="CORS allowed origins, comma-separated. Example: https://app.collabtask.com,https://www.app.collabtask.com,http://localhost:3000"
    )
    cors_allow_credentials: bool = Field(
        default=True,
        description="Whether to allow credentials (cookies/authorization headers). Should be True only if required by the frontend."
    )
    cors_allow_methods: str = Field(
        default="GET,POST,PUT,PATCH,DELETE,OPTIONS",
        description="Comma-separated list of allowed CORS methods."
    )
    cors_allow_headers: str = Field(
        default="Authorization,Content-Type,Accept,Origin,User-Agent,Accept-Language,Accept-Encoding",
        description="Comma-separated list of allowed CORS headers. Avoid '*' in production."
    )

    postgres_url: str | None = Field(default=None, description="Full Postgres URL, optional")
    postgres_user: str | None = None
    postgres_password: str | None = None
    postgres_db: str | None = None
    postgres_port: int | None = 5432
    postgres_host: str | None = Field(default="localhost", description="Postgres host if URL is not provided")

    # Stripe configuration
    stripe_api_key: Optional[str] = Field(default=None, description="Stripe secret API key")
    stripe_webhook_secret: Optional[str] = Field(default=None, description="Stripe webhook signing secret")
    stripe_billing_portal_config_id: Optional[str] = Field(default=None, description="Optional Billing Portal configuration id")

    # PUBLIC_INTERFACE
    def build_database_dsn(self) -> str:
        """Build a PostgreSQL DSN from either POSTGRES_URL or discrete parts."""
        if self.postgres_url:
            return self.postgres_url
        if not all([self.postgres_user, self.postgres_password, self.postgres_db, self.postgres_host, self.postgres_port]):
            raise ValueError("Database configuration is incomplete: provide POSTGRES_URL or all discrete parts.")
        return f"postgresql://{self.postgres_user}:{self.postgres_password}@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"


@lru_cache
# PUBLIC_INTERFACE
def get_settings() -> Settings:
    """Load settings from environment variables with caching."""
    try:
        return Settings(
            jwt_secret=os.getenv("JWT_SECRET", ""),
            jwt_algorithm=os.getenv("JWT_ALGORITHM", "HS256"),
            jwt_expires_minutes=int(os.getenv("JWT_EXPIRES_MINUTES", "120")),
            cors_allow_origins=os.getenv("CORS_ALLOW_ORIGINS", "http://localhost:3000"),
            cors_allow_credentials=os.getenv("CORS_ALLOW_CREDENTIALS", "true").lower() in ("1", "true", "yes"),
            cors_allow_methods=os.getenv("CORS_ALLOW_METHODS", "GET,POST,PUT,PATCH,DELETE,OPTIONS"),
            cors_allow_headers=os.getenv(
                "CORS_ALLOW_HEADERS",
                "Authorization,Content-Type,Accept,Origin,User-Agent,Accept-Language,Accept-Encoding"
            ),
            postgres_url=os.getenv("POSTGRES_URL"),
            postgres_user=os.getenv("POSTGRES_USER"),
            postgres_password=os.getenv("POSTGRES_PASSWORD"),
            postgres_db=os.getenv("POSTGRES_DB"),
            postgres_port=int(os.getenv("POSTGRES_PORT", "5432")) if os.getenv("POSTGRES_PORT") else 5432,
            postgres_host=os.getenv("POSTGRES_HOST", os.getenv("POSTGRES_HOSTNAME", "localhost")),
            stripe_api_key=os.getenv("STRIPE_API_KEY"),
            stripe_webhook_secret=os.getenv("STRIPE_WEBHOOK_SECRET"),
            stripe_billing_portal_config_id=os.getenv("STRIPE_BILLING_PORTAL_CONFIG_ID"),
        )
    except ValidationError as e:
        raise RuntimeError(f"Invalid environment configuration: {e}") from e
