"""Login and bearer authentication without a database."""

import os
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import jwt
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from angebotfinder.api.app import app
from angebotfinder.security import create_access_token, decode_access_token, hash_password


class LoginTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, JWT_SECRET_KEY="test-secret-" * 5)
        self.env.start()
        self.addCleanup(self.env.stop)
        self.client = TestClient(app)
        self.password = "Learning-Postgres-2026!"
        self.user = {
            "id": uuid4(), "name": "Shimanto", "email": "learner@example.com",
            "created_at": datetime.now(timezone.utc),
        }

    def test_login_returns_signed_token_and_me_returns_user(self):
        credentials = {"id": self.user["id"], "password_hash": hash_password(self.password)}
        with patch("angebotfinder.api.routes.auth.get_user_by_email", return_value=credentials) as lookup:
            response = self.client.post("/auth/login", json={
                "email": "Learner@EXAMPLE.COM", "password": self.password,
            })
        self.assertEqual(response.status_code, 200)
        lookup.assert_called_once_with("learner@example.com")
        data = response.json()
        self.assertEqual(set(data), {"access_token", "token_type", "expires_in"})
        self.assertEqual(data["expires_in"], 1800)
        payload = decode_access_token(data["access_token"])
        self.assertEqual(payload["sub"], str(self.user["id"]))
        with patch("angebotfinder.api.dependencies.get_user_by_id", return_value=self.user):
            me = self.client.get("/auth/me", headers={"Authorization": f"Bearer {data['access_token']}"})
        self.assertEqual(me.status_code, 200)
        self.assertEqual(set(me.json()), {"id", "name", "email", "created_at"})

    def test_missing_user_and_wrong_password_have_same_error(self):
        responses = []
        for user in [None, {"id": self.user["id"], "password_hash": hash_password("another-password")}]:
            with patch("angebotfinder.api.routes.auth.get_user_by_email", return_value=user):
                response = self.client.post("/auth/login", json={
                    "email": self.user["email"], "password": self.password,
                })
                self.assertEqual(response.status_code, 401)
                responses.append(response.json())
        self.assertEqual(responses[0], responses[1])

    def test_missing_invalid_expired_and_wrong_signature_tokens_rejected(self):
        expired = jwt.encode({"sub": str(self.user["id"]), "iat": 0, "exp": 1}, os.environ["JWT_SECRET_KEY"], algorithm="HS256")
        wrong_signature = jwt.encode({"sub": str(self.user["id"]), "iat": datetime.now(timezone.utc), "exp": datetime.now(timezone.utc)+timedelta(minutes=5)}, "different-secret-" * 4, algorithm="HS256")
        missing_exp = jwt.encode({"sub": str(self.user["id"]), "iat": 0}, os.environ["JWT_SECRET_KEY"], algorithm="HS256")
        for token in [None, "invalid", expired, wrong_signature, missing_exp]:
            headers = {"Authorization": f"Bearer {token}"} if token else {}
            with patch("angebotfinder.api.dependencies.get_user_by_id") as lookup:
                self.assertEqual(self.client.get("/auth/me", headers=headers).status_code, 401)
                lookup.assert_not_called()

    def test_deleted_user_token_is_rejected(self):
        token = create_access_token(self.user["id"])
        with patch("angebotfinder.api.dependencies.get_user_by_id", return_value=None):
            response = self.client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(response.status_code, 401)
