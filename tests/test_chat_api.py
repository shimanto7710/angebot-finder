"""Chat ownership, history handoff and saving without loading LLMs."""

import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock, patch
from uuid import uuid4

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from angebotfinder.api.app import app
from angebotfinder.api.dependencies import get_current_user


class ChatAPITests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.user = {"id": uuid4()}
        app.dependency_overrides[get_current_user] = lambda: self.user
        self.addCleanup(app.dependency_overrides.clear)
        self.history = [
            {"id": i, "question": f"Question {i}", "answer": f"Answer {i}",
             "created_at": datetime.now(timezone.utc)}
            for i in [1, 2, 3]
        ]
        self.result = {
            "question": "And at Lidl?", "search_question": "Tea offers at Lidl?",
            "answer": "Saved offer answer.", "status": "generated", "sources": [],
        }

    def test_ask_passes_history_then_saves_original_question_and_answer(self):
        pipeline = Mock()
        events = []
        def generate(question, history):
            events.append("generate")
            self.assertEqual(history, self.history)
            return self.result
        pipeline.ask_question.side_effect = generate
        with patch("angebotfinder.api.routes.chats.get_chat_history", return_value=self.history) as history, patch(
            "angebotfinder.api.routes.chats.get_rag_pipeline", return_value=pipeline
        ), patch("angebotfinder.api.routes.chats.save_chat_turn", side_effect=lambda *args: events.append("save")) as save:
            response = self.client.post("/chat", json={"user_id": str(self.user["id"]), "question": "  And at Lidl?  "})
        self.assertEqual(response.status_code, 200)
        history.assert_called_once_with(self.user["id"], limit=3)
        save.assert_called_once_with(self.user["id"], "And at Lidl?", self.result["answer"])
        self.assertEqual(events, ["generate", "save"])

    def test_other_user_cannot_read_or_write_history(self):
        other = str(uuid4())
        with patch("angebotfinder.api.routes.chats.get_chat_history") as history, patch(
            "angebotfinder.api.routes.chats.get_rag_pipeline"
        ) as pipeline:
            self.assertEqual(self.client.post("/chat", json={"user_id": other, "question": "Hello"}).status_code, 403)
            self.assertEqual(self.client.get("/chat/history", params={"user_id": other}).status_code, 403)
            history.assert_not_called()
            pipeline.assert_not_called()

    def test_history_defaults_to_last_three(self):
        with patch("angebotfinder.api.routes.chats.get_chat_history", return_value=self.history) as history:
            response = self.client.get("/chat/history", params={"user_id": str(self.user["id"])})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()), 3)
        history.assert_called_once_with(self.user["id"], limit=3)

    def test_invalid_questions_rejected_before_loading_models(self):
        with patch("angebotfinder.api.routes.chats.get_rag_pipeline") as pipeline:
            for question in ["", "  ", "x" * 2001]:
                self.assertEqual(self.client.post("/chat", json={"user_id": str(self.user["id"]), "question": question}).status_code, 422)
            pipeline.assert_not_called()

    def test_generation_failure_does_not_save_a_turn(self):
        pipeline = Mock()
        pipeline.ask_question.side_effect = RuntimeError("Generation failed")
        with patch("angebotfinder.api.routes.chats.get_chat_history", return_value=[]), patch(
            "angebotfinder.api.routes.chats.get_rag_pipeline", return_value=pipeline
        ), patch("angebotfinder.api.routes.chats.save_chat_turn") as save:
            with self.assertRaises(RuntimeError):
                self.client.post("/chat", json={"user_id": str(self.user["id"]), "question": "Tea?"})
            save.assert_not_called()

    def test_chat_requires_authentication(self):
        app.dependency_overrides.clear()
        response = self.client.post("/chat", json={"user_id": str(self.user["id"]), "question": "Tea?"})
        self.assertEqual(response.status_code, 401)
