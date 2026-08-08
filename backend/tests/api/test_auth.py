"""Unit tests for OpenShift OAuth authentication dependency."""

import os
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.auth import AuthenticationError, UserInfo, get_current_user, handle_authentication_error

pytestmark = pytest.mark.unit


def _create_test_app():
    """Create a minimal FastAPI app with an authenticated endpoint and error handler."""
    app = FastAPI()
    app.add_exception_handler(AuthenticationError, handle_authentication_error)

    @app.get("/test")
    async def test_endpoint(user: UserInfo = pytest.importorskip("fastapi").Depends(get_current_user)):
        return {"username": user.username, "groups": user.groups}

    return app


class TestAuthDisabled:
    def test_returns_stub_user_when_disabled(self):
        with patch.dict(os.environ, {"AUTH_DISABLED": "true"}):
            from fastapi import Depends

            app = FastAPI()
            app.add_exception_handler(AuthenticationError, handle_authentication_error)

            @app.get("/test")
            async def endpoint(user: UserInfo = Depends(get_current_user)):
                return {"username": user.username, "groups": user.groups}

            client = TestClient(app)
            resp = client.get("/test")
            assert resp.status_code == 200
            data = resp.json()
            assert data["username"] == "dev-user"
            assert "system:authenticated" in data["groups"]


class TestAuthEnabled:
    def test_missing_token_returns_401(self):
        with patch.dict(os.environ, {"AUTH_DISABLED": ""}, clear=False):
            from fastapi import Depends

            app = FastAPI()
            app.add_exception_handler(AuthenticationError, handle_authentication_error)

            @app.get("/test")
            async def endpoint(user: UserInfo = Depends(get_current_user)):
                return {"username": user.username}

            client = TestClient(app)
            resp = client.get("/test")
            assert resp.status_code == 401
            assert resp.headers.get("www-authenticate") == "Bearer"
            body = resp.json()
            assert body["code"] == "UNAUTHORIZED"
            assert "error" in body

    def test_invalid_bearer_format_returns_401(self):
        with patch.dict(os.environ, {"AUTH_DISABLED": ""}, clear=False):
            from fastapi import Depends

            app = FastAPI()
            app.add_exception_handler(AuthenticationError, handle_authentication_error)

            @app.get("/test")
            async def endpoint(user: UserInfo = Depends(get_current_user)):
                return {"username": user.username}

            client = TestClient(app)
            resp = client.get("/test", headers={"Authorization": "Basic abc"})
            assert resp.status_code == 401
            body = resp.json()
            assert body["code"] == "UNAUTHORIZED"

    @patch("src.api.auth._validate_token_via_review")
    def test_valid_token_returns_user(self, mock_validate):
        mock_validate.return_value = UserInfo(username="test-user", groups=["admins"])

        with patch.dict(os.environ, {"AUTH_DISABLED": ""}, clear=False):
            from fastapi import Depends

            app = FastAPI()
            app.add_exception_handler(AuthenticationError, handle_authentication_error)

            @app.get("/test")
            async def endpoint(user: UserInfo = Depends(get_current_user)):
                return {"username": user.username, "groups": user.groups}

            client = TestClient(app)
            resp = client.get(
                "/test", headers={"Authorization": "Bearer valid-token-123"}
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["username"] == "test-user"
            assert "admins" in data["groups"]
