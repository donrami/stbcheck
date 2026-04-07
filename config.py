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
        default=30,
        description="Timeout for streaming operations (proxy, concurrent checks)",
        alias="STREAM_TIMEOUT",
    )
    logo_fetch_timeout: int = Field(
        default=15,
        description="Timeout for fetching logo images",
        alias="LOGO_FETCH_TIMEOUT",
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
        default="*",
        description="Comma-separated list of allowed CORS origins, or '*' for all",
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
        default=8000,
        description="Port number for the server",
        alias="SERVER_PORT",
    )

    # =============================================================================
    # Application Settings
    # =============================================================================
    app_version: str = Field(
        default="1.1.0 - Organization & Refactoring",
        description="Application version string",
        alias="APP_VERSION",
    )

    # =============================================================================
    # Stalker Portal Detection
    # =============================================================================
    stalker_check_timeout: int = Field(
        default=10,
        description="Timeout for Stalker portal checks (seconds)",
        alias="STALKER_CHECK_TIMEOUT",
    )
    stalker_cache_ttl: int = Field(
        default=300,
        description="Cache TTL for Stalker portal results (seconds)",
        alias="STALKER_CACHE_TTL",
    )
    stalker_detection_enabled: bool = Field(
        default=True,
        description="Enable Stalker portal detection and specialized handling",
        alias="STALKER_DETECTION_ENABLED",
    )

    # =============================================================================
    # Expiry Detection Configuration
    # =============================================================================
    expiry_field_priority: List[str] = Field(
        default=[
            "expire_billing_date",  # Stalker priority
            "expire_date",
            "exp_date",
            "max_view_date",
            "end_date",
            "end_date_time",
            "date_end",
            "valid_until",
            "access_end",
            "end",
            "to",
            "active_until",
            "subscription_end",
            "billing_end",
            "plan_expires",
            "expires",
            "expiry_date",
            "expired",
        ],
        description="Ordered list of field names to check for expiry dates",
        alias="EXPIRY_FIELD_PRIORITY",
    )

    date_parsing_timezone: str = Field(
        default="UTC",
        description="Default timezone for date parsing",
        alias="DATE_PARSING_TIMEZONE",
    )

    max_redirects: int = Field(
        default=10,
        description="Maximum number of redirects to follow when proxying streams",
        alias="MAX_REDIRECTS",
    )


# Global settings instance - imported by other modules
settings = Settings()
