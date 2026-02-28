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
        default=20,
        description="Timeout for streaming operations (proxy, concurrent checks)",
        alias="STREAM_TIMEOUT",
    )
    logo_fetch_timeout: int = Field(
        default=5,
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
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]
    
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
        default="1.0.1 - Playback Fixes",
        description="Application version string",
        alias="APP_VERSION",
    )


# Global settings instance - imported by other modules
settings = Settings()
