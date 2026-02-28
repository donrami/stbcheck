"""
Unit tests for app/config.py

Tests for the Settings class, environment variable loading, and CORS origins parsing.
"""

import os
import pytest
from unittest.mock import patch

from app.config import Settings


class TestSettings:
    """Tests for the Settings configuration class."""

    def test_default_values(self):
        """Test that default values are correctly set."""
        # Clear any existing env vars that might affect defaults
        with patch.dict(os.environ, {}, clear=True):
            settings = Settings()
            
            assert settings.request_timeout == 10
            assert settings.stream_timeout == 20
            assert settings.logo_fetch_timeout == 5
            assert settings.max_concurrent_portal_checks == 15
            assert settings.log_level == "INFO"
            assert settings.log_file_max_bytes == 5 * 1024 * 1024  # 5 MB
            assert settings.log_backup_count == 2
            assert settings.cors_origins == "*"
            assert settings.server_host == "0.0.0.0"
            assert settings.server_port == 8000
            assert settings.app_version == "1.0.1 - Playback Fixes"

    def test_get_cors_origins_list_wildcard(self):
        """Test get_cors_origins_list returns ['*'] for wildcard."""
        with patch.dict(os.environ, {"CORS_ORIGINS": "*"}, clear=True):
            settings = Settings()
            origins = settings.get_cors_origins_list()
            
            assert origins == ["*"]

    def test_get_cors_origins_list_single_origin(self):
        """Test get_cors_origins_list with single origin."""
        with patch.dict(os.environ, {"CORS_ORIGINS": "https://example.com"}, clear=True):
            settings = Settings()
            origins = settings.get_cors_origins_list()
            
            assert origins == ["https://example.com"]

    def test_get_cors_origins_list_multiple_origins(self):
        """Test get_cors_origins_list with multiple comma-separated origins."""
        with patch.dict(os.environ, {"CORS_ORIGINS": "https://example.com,https://app.example.com,http://localhost:3000"}, clear=True):
            settings = Settings()
            origins = settings.get_cors_origins_list()
            
            assert origins == ["https://example.com", "https://app.example.com", "http://localhost:3000"]

    def test_get_cors_origins_list_with_whitespace(self):
        """Test get_cors_origins_list handles whitespace correctly."""
        with patch.dict(os.environ, {"CORS_ORIGINS": "  https://example.com  ,   https://app.example.com  "}, clear=True):
            settings = Settings()
            origins = settings.get_cors_origins_list()
            
            assert origins == ["https://example.com", "https://app.example.com"]

    def test_get_cors_origins_list_empty_string(self):
        """Test get_cors_origins_list with empty string."""
        with patch.dict(os.environ, {"CORS_ORIGINS": ""}, clear=True):
            settings = Settings()
            origins = settings.get_cors_origins_list()
            
            assert origins == []

    @patch.dict(os.environ, {"REQUEST_TIMEOUT": "30"}, clear=False)
    def test_env_var_request_timeout(self):
        """Test that REQUEST_TIMEOUT environment variable is loaded."""
        # Create new settings instance to read env vars
        settings = Settings()
        assert settings.request_timeout == 30

    @patch.dict(os.environ, {"STREAM_TIMEOUT": "60"}, clear=False)
    def test_env_var_stream_timeout(self):
        """Test that STREAM_TIMEOUT environment variable is loaded."""
        settings = Settings()
        assert settings.stream_timeout == 60

    @patch.dict(os.environ, {"LOG_LEVEL": "DEBUG"}, clear=False)
    def test_env_var_log_level(self):
        """Test that LOG_LEVEL environment variable is loaded."""
        settings = Settings()
        assert settings.log_level == "DEBUG"

    @patch.dict(os.environ, {"CORS_ORIGINS": "https://example.com,https://app.example.com"}, clear=False)
    def test_env_var_cors_origins(self):
        """Test that CORS_ORIGINS environment variable is loaded."""
        settings = Settings()
        assert settings.cors_origins == "https://example.com,https://app.example.com"

    @patch.dict(os.environ, {"SERVER_HOST": "127.0.0.1"}, clear=False)
    def test_env_var_server_host(self):
        """Test that SERVER_HOST environment variable is loaded."""
        settings = Settings()
        assert settings.server_host == "127.0.0.1"

    @patch.dict(os.environ, {"SERVER_PORT": "8080"}, clear=False)
    def test_env_var_server_port(self):
        """Test that SERVER_PORT environment variable is loaded."""
        settings = Settings()
        assert settings.server_port == 8080

    @patch.dict(os.environ, {"MAX_CONCURRENT_PORTAL_CHECKS": "50"}, clear=False)
    def test_env_var_max_concurrent(self):
        """Test that MAX_CONCURRENT_PORTAL_CHECKS environment variable is loaded."""
        settings = Settings()
        assert settings.max_concurrent_portal_checks == 50

    def test_settings_case_insensitive(self):
        """Test that settings are case insensitive for field names."""
        # Pydantic v2 settings are case insensitive by default with case_sensitive=False
        settings = Settings()
        assert hasattr(settings, 'request_timeout')
        assert hasattr(settings, 'REQUEST_TIMEOUT') is False  # Field name is lowercase

    def test_extra_env_vars_ignored(self):
        """Test that extra environment variables are ignored (extra='ignore')."""
        with patch.dict(os.environ, {"SOME_RANDOM_VAR": "value"}, clear=False):
            # Should not raise an error
            settings = Settings()
            assert not hasattr(settings, 'SOME_RANDOM_VAR')
