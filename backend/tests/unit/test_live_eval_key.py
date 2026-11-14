"""The live evaluation finds the Anthropic key like the app (024, T066): the environment first,
then `backend/.env` through the settings; otherwise the Anthropic cases are skipped."""

from __future__ import annotations

import pytest

from tests.agent_evals.test_golden_live import anthropic_key


@pytest.fixture
def in_tmp(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # Settings reads `.env` from the working directory
    monkeypatch.delenv("AGENT_ANTHROPIC_API_KEY", raising=False)
    return tmp_path


def test_the_environment_comes_first(in_tmp, monkeypatch):
    (in_tmp / ".env").write_text("AGENT_ANTHROPIC_API_KEY=from-dotenv\n")
    monkeypatch.setenv("AGENT_ANTHROPIC_API_KEY", "from-env")
    assert anthropic_key() == "from-env"


def test_then_the_dotenv_file(in_tmp):
    (in_tmp / ".env").write_text("AGENT_ANTHROPIC_API_KEY=from-dotenv\n")
    assert anthropic_key() == "from-dotenv"


def test_none_when_neither_has_it(in_tmp):
    assert anthropic_key() is None
