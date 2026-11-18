"""Registration API checks without a running database."""

import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient
from psycopg.errors import UniqueViolation

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from angebotfinder.api.app import app
from angebotfinder.security import password_hasher


class DuplicateEmail(UniqueViolation):
    @property
    def diag(self):
        return SimpleNamespace(constraint_name="users_email_unique")


class RegistrationTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.password = "Learning-Postgres-2026!"
        self.user = {
            "id": uuid4(),
            "name": "Shimanto",
            "email": "learner@example.com",
            "created_at": datetime.now(timezone.utc),
        }

    def test_registration_hashes_password_and_returns_public_fields(self):
        with patch(
            "angebotfinder.api.routes.auth.create_user", return_value=self.user
        ) as create_user:
            response = self.client.post("/auth/register", json={
                "name": "  Shimanto  ", "email": "Learner@EXAMPLE.COM", "password": self.password,
            })

        self.assertEqual(response.status_code, 201)
        self.assertEqual(set(response.json()), {"id", "name", "email", "created_at"})
        values = create_user.call_args.kwargs
        hashed = values["password_hash"]
        self.assertEqual(values["email"], "learner@example.com")
        self.assertEqual(values["name"], "Shimanto")
        self.assertNotEqual(hashed, self.password)
        self.assertTrue(hashed.startswith("$argon2id$"))
        self.assertTrue(password_hasher.verify(self.password, hashed))

    def test_invalid_input_does_not_call_database(self):
        with patch("angebotfinder.api.routes.auth.create_user") as create_user:
            for invalid in [
                {"email": "invalid", "password": self.password},
                {"email": self.user["email"], "password": "short"},
                {"email": self.user["email"], "password": "x" * 129},
                {"email": self.user["email"]},
            ]:
                payload = {"name": "Shimanto", **invalid}
                with self.subTest(payload_keys=list(payload)):
                    self.assertEqual(
                        self.client.post("/auth/register", json=payload).status_code,
                        422,
                    )
            create_user.assert_not_called()

    def test_duplicate_email_returns_conflict(self):
        with patch(
            "angebotfinder.api.routes.auth.create_user",
            side_effect=DuplicateEmail(),
        ):
            response = self.client.post("/auth/register", json={
                "name": "Shimanto", "email": self.user["email"], "password": self.password,
            })
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"], "Email is already registered.")

    def test_other_unique_violation_is_not_reported_as_duplicate_email(self):
        with patch(
            "angebotfinder.api.routes.auth.create_user", side_effect=UniqueViolation()
        ):
            with self.assertRaises(UniqueViolation):
                self.client.post("/auth/register", json={
                    "name": "Shimanto", "email": self.user["email"], "password": self.password,
                })

    def test_name_is_required_and_cannot_be_blank_or_too_long(self):
        with patch("angebotfinder.api.routes.auth.create_user") as create_user:
            for extra in [{}, {"name": "   "}, {"name": "x" * 101}]:
                payload = {"email": self.user["email"], "password": self.password, **extra}
                self.assertEqual(self.client.post("/auth/register", json=payload).status_code, 422)
            create_user.assert_not_called()
