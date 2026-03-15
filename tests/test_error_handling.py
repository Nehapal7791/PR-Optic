"""Tests for error handling and structured logging."""

import pytest
from fastapi.testclient import TestClient
from fastapi import FastAPI
from src.middleware.error_handler import add_error_handlers, GitHubAPIError, AIServiceError
from src.api.routes import reviews, webhook, health


@pytest.fixture
def app():
    """Create test FastAPI app with error handlers."""
    app = FastAPI()
    add_error_handlers(app)
    app.include_router(health.router)
    app.include_router(reviews.router, prefix="/api")
    app.include_router(webhook.router)
    return app


@pytest.fixture
def client(app):
    """Create test client."""
    return TestClient(app, raise_server_exceptions=False)


class TestJSONErrorResponses:
    """Test that all errors return JSON, not HTML."""
    
    def test_404_returns_json_not_html(self, client):
        """Test /api/nonexistent returns JSON error, not HTML 404."""
        response = client.get("/api/nonexistent")
        
        assert response.status_code == 404
        assert response.headers["content-type"] == "application/json"
        
        data = response.json()
        assert "error" in data
        assert "status_code" in data
        assert data["status_code"] == 404
        assert "path" in data
        assert "timestamp" in data
        
        # Ensure no HTML in response
        response_text = response.text
        assert "<html>" not in response_text.lower()
        assert "<!doctype" not in response_text.lower()
    
    def test_405_method_not_allowed_returns_json(self, client):
        """Test wrong HTTP method returns JSON."""
        response = client.get("/api/reviews")  # Should be POST
        
        assert response.status_code == 405
        assert response.headers["content-type"] == "application/json"
        
        data = response.json()
        assert "error" in data
        assert "status_code" in data
    
    def test_500_internal_error_returns_json_no_traceback(self, app):
        """Test internal errors return JSON without raw traceback."""
        
        # Add a route that raises an exception
        @app.get("/test/error")
        async def error_route():
            raise ValueError("Test error")
        
        # Create new client with updated app
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/test/error")
        
        assert response.status_code == 500
        assert response.headers["content-type"] == "application/json"
        
        data = response.json()
        assert "error" in data
        assert data["error"] == "Internal server error"
        assert "status_code" in data
        assert data["status_code"] == 500
        assert "error_type" in data
        assert data["error_type"] == "ValueError"
        assert "timestamp" in data
        
        # CRITICAL: No raw traceback in response
        response_text = response.text
        assert "Traceback" not in response_text
        assert "File \"" not in response_text
        assert "line " not in response_text.lower() or "line" in data.get("error", "").lower()


class TestValidationErrors:
    """Test validation error responses include failing field names."""
    
    def test_missing_required_field_shows_field_name(self, client):
        """Test invalid request body returns JSON with failing field name."""
        response = client.post(
            "/api/reviews",
            json={"owner": "test", "repo": "test"}  # Missing pull_number
        )
        
        assert response.status_code == 422
        assert response.headers["content-type"] == "application/json"
        
        data = response.json()
        assert "error" in data
        assert data["error"] == "Validation failed"
        assert "failing_fields" in data
        assert len(data["failing_fields"]) > 0
        
        # Check that field name is included
        field_names = [f["field"] for f in data["failing_fields"]]
        assert any("pull_number" in field for field in field_names)
        
        # Check field details
        for field in data["failing_fields"]:
            assert "field" in field
            assert "message" in field
            assert "type" in field
    
    def test_invalid_field_type_shows_details(self, client):
        """Test invalid field type shows clear error."""
        response = client.post(
            "/api/reviews",
            json={
                "owner": "test",
                "repo": "test",
                "pull_number": "not_a_number"  # Should be int
            }
        )
        
        assert response.status_code == 422
        
        data = response.json()
        assert "failing_fields" in data
        
        # Should mention pull_number
        field_names = [f["field"] for f in data["failing_fields"]]
        assert any("pull_number" in field for field in field_names)
    
    def test_empty_string_validation(self, client):
        """Test empty string validation."""
        response = client.post(
            "/api/reviews",
            json={
                "owner": "",  # Empty string
                "repo": "test",
                "pull_number": 1
            }
        )
        
        assert response.status_code == 422
        
        data = response.json()
        assert "failing_fields" in data
        
        # Should mention owner
        field_names = [f["field"] for f in data["failing_fields"]]
        assert any("owner" in field for field in field_names)


class TestGitHubAPIErrors:
    """Test GitHub API errors return 502 with readable message."""
    
    def test_github_api_error_returns_502(self, app):
        """Test GitHub API errors return 502 Bad Gateway."""
        
        @app.get("/test/github-error")
        async def github_error_route():
            raise GitHubAPIError("GitHub API rate limit exceeded")
        
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/test/github-error")
        
        assert response.status_code == 502
        assert response.headers["content-type"] == "application/json"
        
        data = response.json()
        assert "error" in data
        assert data["error"] == "GitHub API communication failed"
        assert "message" in data
        assert "rate limit" in data["message"].lower()
        assert "hint" in data
        assert "status_code" in data
        assert data["status_code"] == 502
        assert "timestamp" in data
        
        # Should have helpful hint
        assert "try again" in data["hint"].lower()


class TestAIServiceErrors:
    """Test AI service errors return 503 with retry hint."""
    
    def test_ai_service_error_returns_503(self, app):
        """Test AI service errors return 503 Service Unavailable."""
        
        @app.get("/test/ai-error")
        async def ai_error_route():
            raise AIServiceError("Claude API timeout")
        
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/test/ai-error")
        
        assert response.status_code == 503
        assert response.headers["content-type"] == "application/json"
        
        data = response.json()
        assert "error" in data
        assert data["error"] == "AI service temporarily unavailable"
        assert "message" in data
        assert "timeout" in data["message"].lower()
        assert "hint" in data
        assert "retry" in data["hint"].lower()
        assert "retry_after" in data
        assert data["retry_after"] == 60
        assert "status_code" in data
        assert data["status_code"] == 503
        assert "timestamp" in data


class TestNoRawTracebacks:
    """Test that no raw Python tracebacks appear in HTTP responses."""
    
    def test_exception_no_traceback_in_response(self, app):
        """Test exceptions don't expose tracebacks."""
        
        @app.get("/test/complex-error")
        async def complex_error():
            try:
                # Nested error to create complex traceback
                _ = 1 / 0
            except ZeroDivisionError:
                raise RuntimeError("Complex error with nested cause")
        
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/test/complex-error")
        
        assert response.status_code == 500
        
        response_text = response.text
        
        # No traceback indicators
        assert "Traceback (most recent call last)" not in response_text
        assert "File \"" not in response_text
        assert "raise RuntimeError" not in response_text
        assert "ZeroDivisionError" not in response_text
        
        # Should have clean error message
        data = response.json()
        assert data["error"] == "Internal server error"
        assert "contact support" in data["message"].lower()
    
    def test_import_error_no_traceback(self, app):
        """Test import errors don't expose file paths."""
        
        @app.get("/test/import-error")
        async def import_error():
            raise ImportError("No module named 'nonexistent_module'")
        
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/test/import-error")
        
        assert response.status_code == 500
        
        response_text = response.text
        
        # No file system paths
        assert "/Users/" not in response_text
        assert "/home/" not in response_text
        assert "C:\\" not in response_text
        assert ".py\"" not in response_text


class TestStructuredErrorFormat:
    """Test all errors follow consistent JSON structure."""
    
    def test_error_response_structure(self, client):
        """Test all error responses have consistent structure."""
        
        # Test 404
        response = client.get("/api/nonexistent")
        data = response.json()
        
        required_fields = ["error", "status_code", "path", "timestamp"]
        for field in required_fields:
            assert field in data, f"Missing field: {field}"
        
        # Verify timestamp format (ISO 8601)
        assert "T" in data["timestamp"]
        assert ":" in data["timestamp"]
    
    def test_validation_error_structure(self, client):
        """Test validation errors have consistent structure."""
        response = client.post("/api/reviews", json={})
        data = response.json()
        
        required_fields = ["error", "status_code", "failing_fields", "path", "timestamp"]
        for field in required_fields:
            assert field in data
        
        # Verify failing_fields structure
        assert isinstance(data["failing_fields"], list)
        if data["failing_fields"]:
            field = data["failing_fields"][0]
            assert "field" in field
            assert "message" in field
            assert "type" in field


class TestHealthEndpoint:
    """Test health endpoint always works."""
    
    def test_health_check_returns_200(self, client):
        """Test health endpoint returns 200."""
        response = client.get("/health")
        
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/json"
        
        data = response.json()
        assert "ok" in data
        assert data["ok"] is True
