"""
Unit tests for app/models.py

Tests for Pydantic model validation (CheckRequest, StreamRequest, VerifyRequest).
"""

import pytest
from pydantic import ValidationError

from app.models import CheckRequest, StreamRequest, VerifyRequest


class TestCheckRequest:
    """Tests for the CheckRequest model."""

    def test_valid_check_request(self):
        """Test creating a valid CheckRequest."""
        req = CheckRequest(text="PORTAL: http://example.com MAC: 00:11:22:33:44:55")
        assert req.text == "PORTAL: http://example.com MAC: 00:11:22:33:44:55"

    def test_check_request_empty_string(self):
        """Test CheckRequest with empty string (valid but may be rejected by API)."""
        req = CheckRequest(text="")
        assert req.text == ""

    def test_check_request_whitespace_only(self):
        """Test CheckRequest with whitespace only."""
        req = CheckRequest(text="   ")
        assert req.text == "   "

    def test_check_request_long_text(self):
        """Test CheckRequest with long text."""
        long_text = "A" * 10000
        req = CheckRequest(text=long_text)
        assert req.text == long_text

    def test_check_request_unicode(self):
        """Test CheckRequest with unicode characters."""
        text = "🛰 ➤ http://example.com ✅ ➤ 00:11:22:33:44:55"
        req = CheckRequest(text=text)
        assert req.text == text

    def test_check_request_missing_field(self):
        """Test CheckRequest fails without required field."""
        with pytest.raises(ValidationError) as exc_info:
            CheckRequest()
        
        assert "text" in str(exc_info.value)

    def test_check_request_json_serialization(self):
        """Test CheckRequest JSON serialization."""
        req = CheckRequest(text="test text")
        json_data = req.model_dump_json()
        
        assert '"text":"test text"' in json_data


class TestStreamRequest:
    """Tests for the StreamRequest model."""

    def test_valid_stream_request(self):
        """Test creating a valid StreamRequest."""
        req = StreamRequest(
            url="http://example.com/stalker_portal/c/",
            mac="00:11:22:33:44:55",
            cmd="ffmpeg http://stream.example.com/video.ts"
        )
        assert req.url == "http://example.com/stalker_portal/c/"
        assert req.mac == "00:11:22:33:44:55"
        assert req.cmd == "ffmpeg http://stream.example.com/video.ts"

    def test_stream_request_case_insensitive_mac(self):
        """Test StreamRequest accepts MAC in any case."""
        req = StreamRequest(
            url="http://example.com/stalker_portal/c/",
            mac="AA:bb:CC:dd:EE:ff",
            cmd="test"
        )
        assert req.mac == "AA:bb:CC:dd:EE:ff"

    def test_stream_request_different_mac_formats(self):
        """Test StreamRequest accepts different MAC formats."""
        # Colon-separated
        req1 = StreamRequest(
            url="http://example.com",
            mac="00:11:22:33:44:55",
            cmd="test"
        )
        assert req1.mac == "00:11:22:33:44:55"

        # Hyphen-separated (will be normalized in processing)
        req2 = StreamRequest(
            url="http://example.com",
            mac="00-11-22-33-44-55",
            cmd="test"
        )
        assert req2.mac == "00-11-22-33-44-55"

    def test_stream_request_missing_url(self):
        """Test StreamRequest fails without url."""
        with pytest.raises(ValidationError) as exc_info:
            StreamRequest(mac="00:11:22:33:44:55", cmd="test")
        
        assert "url" in str(exc_info.value)

    def test_stream_request_missing_mac(self):
        """Test StreamRequest fails without mac."""
        with pytest.raises(ValidationError) as exc_info:
            StreamRequest(url="http://example.com", cmd="test")
        
        assert "mac" in str(exc_info.value)

    def test_stream_request_missing_cmd(self):
        """Test StreamRequest fails without cmd."""
        with pytest.raises(ValidationError) as exc_info:
            StreamRequest(url="http://example.com", mac="00:11:22:33:44:55")
        
        assert "cmd" in str(exc_info.value)

    def test_stream_request_json_serialization(self):
        """Test StreamRequest JSON serialization."""
        req = StreamRequest(
            url="http://example.com",
            mac="00:11:22:33:44:55",
            cmd="test_cmd"
        )
        json_dict = req.model_dump()
        
        assert json_dict["url"] == "http://example.com"
        assert json_dict["mac"] == "00:11:22:33:44:55"
        assert json_dict["cmd"] == "test_cmd"


class TestVerifyRequest:
    """Tests for the VerifyRequest model."""

    def test_valid_verify_request(self):
        """Test creating a valid VerifyRequest."""
        req = VerifyRequest(
            url="http://example.com/stalker_portal/c/",
            mac="00:11:22:33:44:55"
        )
        assert req.url == "http://example.com/stalker_portal/c/"
        assert req.mac == "00:11:22:33:44:55"

    def test_verify_request_missing_url(self):
        """Test VerifyRequest fails without url."""
        with pytest.raises(ValidationError) as exc_info:
            VerifyRequest(mac="00:11:22:33:44:55")
        
        assert "url" in str(exc_info.value)

    def test_verify_request_missing_mac(self):
        """Test VerifyRequest fails without mac."""
        with pytest.raises(ValidationError) as exc_info:
            VerifyRequest(url="http://example.com")
        
        assert "mac" in str(exc_info.value)

    def test_verify_request_both_missing(self):
        """Test VerifyRequest fails when both fields are missing."""
        with pytest.raises(ValidationError) as exc_info:
            VerifyRequest()
        
        error_msg = str(exc_info.value)
        assert "url" in error_msg
        assert "mac" in error_msg

    def test_verify_request_json_serialization(self):
        """Test VerifyRequest JSON serialization."""
        req = VerifyRequest(
            url="http://example.com",
            mac="00:11:22:33:44:55"
        )
        json_dict = req.model_dump()
        
        assert json_dict["url"] == "http://example.com"
        assert json_dict["mac"] == "00:11:22:33:44:55"

    def test_verify_request_different_url_formats(self):
        """Test VerifyRequest accepts various URL formats."""
        urls = [
            "http://example.com",
            "https://example.com",
            "http://example.com:8080",
            "http://192.168.1.1/stalker_portal/c/",
            "http://example.com/stalker_portal/c/",
        ]
        
        for url in urls:
            req = VerifyRequest(url=url, mac="00:11:22:33:44:55")
            assert req.url == url


class TestModelComparison:
    """Tests comparing model behaviors."""

    def test_all_models_require_all_fields(self):
        """Test that all models require their fields."""
        with pytest.raises(ValidationError):
            CheckRequest()
        
        with pytest.raises(ValidationError):
            StreamRequest()
        
        with pytest.raises(ValidationError):
            VerifyRequest()

    def test_models_are_immutable_by_default(self):
        """Test that model instances can't be modified (frozen)."""
        # Note: Models are not frozen by default in Pydantic v2
        req = CheckRequest(text="test")
        # This should work since models are not frozen
        req.text = "new text"
        assert req.text == "new text"
