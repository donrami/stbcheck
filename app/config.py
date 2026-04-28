"""
Configuration management for STBcheck app using Pydantic Settings.
All configuration values can be set via environment variables.
"""

from typing import List
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings with environment variable support.

    All fields can be configured via environment variables.
    Default values match the original hardcoded values for backward compatibility.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",  # Allow extra env variables without errors
    )

    # =============================================================================
    # Timeouts (in seconds)
    # =============================================================================
    request_timeout: int = Field(
        default=10,
        description="Timeout for HTTP requests to portals",
        alias="REQUEST_TIMEOUT",
    )
    stream_timeout: int = Field(
        default=60,
        description="Timeout for streaming operations (proxy, concurrent checks)",
        alias="STREAM_TIMEOUT",
    )
    logo_fetch_timeout: int = Field(
        default=15,
        description="Timeout for fetching logo images",
        alias="LOGO_FETCH_TIMEOUT",
    )

    # =============================================================================
    # Deployment Mode (Vercel/Serverless vs VPS)
    # =============================================================================
    vercel_compatible_mode: bool = Field(
        default=False,
        description="Enable Vercel-compatible mode with reduced timeouts (10s stream timeout). For long-lived streams, use VPS deployment instead.",
        alias="VERCEL_COMPATIBLE_MODE",
    )

    # =============================================================================
    # Concurrency Limits
    # =============================================================================
    max_concurrent_portal_checks: int = Field(
        default=15,
        description="Maximum number of concurrent portal checks (semaphore limit)",
        alias="MAX_CONCURRENT_PORTAL_CHECKS",
    )

    # =============================================================================
    # Logging Configuration
    # =============================================================================
    log_level: str = Field(
        default="INFO",
        description="Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)",
        alias="LOG_LEVEL",
    )
    log_file_max_bytes: int = Field(
        default=5 * 1024 * 1024,  # 5 MB
        description="Maximum size of log file before rotation (bytes)",
        alias="LOG_FILE_MAX_BYTES",
    )
    log_backup_count: int = Field(
        default=2,
        description="Number of backup log files to keep",
        alias="LOG_BACKUP_COUNT",
    )

    # =============================================================================
    # CORS Configuration
    # =============================================================================
    cors_origins: str = Field(
        default="http://localhost:6767,http://127.0.0.1:6767",
        description="Comma-separated list of allowed CORS origins. Default is development only. Use '*' with caution.",
        alias="CORS_ORIGINS",
    )

    def get_cors_origins_list(self) -> List[str]:
        """Parse CORS_ORIGINS string into a list of origins.

        Returns:
            List of allowed origins, or ["*"] if set to wildcard.
        """
        if self.cors_origins == "*":
            return ["*"]
        return [
            origin.strip() for origin in self.cors_origins.split(",") if origin.strip()
        ]

    # =============================================================================
    # Server Configuration
    # =============================================================================
    server_host: str = Field(
        default="0.0.0.0",
        description="Host address to bind the server to",
        alias="SERVER_HOST",
    )
    server_port: int = Field(
        default=6767,
        description="Port number for the server",
        alias="SERVER_PORT",
    )

    # =============================================================================
    # Application Settings
    # =============================================================================
    app_version: str = Field(
        default="1.0.1 - Playback Fixes",
        description="Application version string",
        alias="APP_VERSION",
    )

    # =============================================================================
    # Security Settings
    # =============================================================================
    verify_ssl: bool = Field(
        default=True,
        description="Verify SSL certificates for outbound HTTP requests (set to false only for testing with self-signed certs)",
        alias="VERIFY_SSL",
    )

    # =============================================================================
    # Date Parsing Configuration
    # =============================================================================
    date_parsing_timezone: str = Field(
        default="UTC",
        description="Timezone for parsing expiry dates from portal responses",
        alias="DATE_PARSING_TIMEZONE",
    )

    # =============================================================================
    # Stalker Detection Configuration
    # =============================================================================
    stalker_detection_enabled: bool = Field(
        default=True,
        description="Enable Stalker portal detection features",
        alias="STALKER_DETECTION_ENABLED",
    )

    # =============================================================================
    # Redis Configuration (Optional - for shared logo cache across workers)
    # =============================================================================
    redis_url: str = Field(
        default="",
        description="Redis URL for shared logo cache (e.g., redis://localhost:6379/0). If empty, uses in-memory cache.",
        alias="REDIS_URL",
    )

    # =============================================================================
    # Cache Configuration
    # =============================================================================
    logo_cache_maxsize: int = Field(
        default=1000,
        description="Maximum number of entries in the logo cache",
        alias="LOGO_CACHE_MAXSIZE",
    )
    logo_cache_ttl: int = Field(
        default=300,
        description="Time-to-live for logo cache entries (seconds)",
        alias="LOGO_CACHE_TTL",
    )

    # =============================================================================
    # Rate Limiting Configuration
    # =============================================================================
    rate_limit_portal_check: str = Field(
        default="5/minute",
        description="Rate limit for portal checking endpoint (e.g., '5/minute')",
        alias="RATE_LIMIT_PORTAL_CHECK",
    )
    rate_limit_proxy_logo: str = Field(
        default="2000/minute",
        description="Rate limit for logo proxy endpoint",
        alias="RATE_LIMIT_PROXY_LOGO",
    )
    rate_limit_stream_ops: str = Field(
        default="60/minute",
        description="Rate limit for streaming operations",
        alias="RATE_LIMIT_STREAM_OPS",
    )

    # =============================================================================
    # Streaming Configuration
    # =============================================================================
    stream_chunk_size: int = Field(
        default=128 * 1024,
        description="Chunk size for streaming responses (bytes)",
        alias="STREAM_CHUNK_SIZE",
    )
    logo_chunk_size: int = Field(
        default=4096,
        description="Chunk size for logo image transfers (bytes)",
        alias="LOGO_CHUNK_SIZE",
    )

    max_redirects: int = Field(
        default=10,
        description="Maximum number of redirects to follow when proxying streams",
        alias="MAX_REDIRECTS",
    )

    stream_auth_cache_ttl: int = Field(
        default=180,
        description="Session auth cache TTL in seconds (3 min - aligned with WAF token expiration)",
        alias="STREAM_AUTH_CACHE_TTL",
    )

    # =============================================================================
    # Circuit Breaker Configuration
    # =============================================================================
    circuit_breaker_threshold: int = Field(
        default=10,
        description="Number of consecutive failures before circuit breaker opens",
        alias="CIRCUIT_BREAKER_THRESHOLD",
    )
    circuit_breaker_duration: int = Field(
        default=30,
        description="Duration in seconds to keep circuit breaker open before allowing retry",
        alias="CIRCUIT_BREAKER_DURATION",
    )


# Global settings instance - imported by other modules
settings = Settings()
