from functools import lru_cache
import os
from pydantic import BaseModel, Field, ValidationError


class Settings(BaseModel):
    """Application settings loaded from environment variables."""
    jwt_secret: str = Field(..., description="Secret key for signing JWT tokens")
    jwt_algorithm: str = Field(default="HS256", description="JWT algorithm")
    jwt_expires_minutes: int = Field(default=120, description="JWT expiration in minutes")
    cors_allow_origins: str = Field(default="*", description="CORS allowed origins, comma-separated")

    postgres_url: str | None = Field(default=None, description="Full Postgres URL, optional")
    postgres_user: str | None = None
    postgres_password: str | None = None
    postgres_db: str | None = None
    postgres_port: int | None = 5432
    postgres_host: str | None = Field(default="localhost", description="Postgres host if URL is not provided")

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
            cors_allow_origins=os.getenv("CORS_ALLOW_ORIGINS", "*"),
            postgres_url=os.getenv("POSTGRES_URL"),
            postgres_user=os.getenv("POSTGRES_USER"),
            postgres_password=os.getenv("POSTGRES_PASSWORD"),
            postgres_db=os.getenv("POSTGRES_DB"),
            postgres_port=int(os.getenv("POSTGRES_PORT", "5432")) if os.getenv("POSTGRES_PORT") else 5432,
            postgres_host=os.getenv("POSTGRES_HOST", os.getenv("POSTGRES_HOSTNAME", "localhost")),
        )
    except ValidationError as e:
        raise RuntimeError(f"Invalid environment configuration: {e}") from e
