"""Testes pytest E2E — requer Rasa em localhost:5005."""

from __future__ import annotations

import uuid

import pytest

from e2e_client import RasaRestClient, find_custom, has_text_containing
from test_data import CROSS_TOPIC_HELP_CASES, DIAGNOSTIC_CORRECT_ANSWERS


@pytest.fixture(scope="module")
def client() -> RasaRestClient:
    return RasaRestClient()


def _unique_sender(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def _run_diagnostic(client: RasaRestClient, sender: str) -> None:
    client.send(sender, "oi")
    client.send(sender, "sim")
    for answer in DIAGNOSTIC_CORRECT_ANSWERS:
        client.send(sender, answer)


@pytest.fixture
def sender_after_diagnostic(client: RasaRestClient) -> str:
    sender = _unique_sender("pytest-diag")
    _run_diagnostic(client, sender)
    return sender


def test_greet_invites_diagnostic(client: RasaRestClient) -> None:
    sender = _unique_sender("pytest-greet")
    msgs = client.send(sender, "oi")
    assert has_text_containing(msgs, "10 perguntas") or has_text_containing(
        msgs, "questionário"
    )


def test_first_diagnostic_question(client: RasaRestClient) -> None:
    sender = _unique_sender("pytest-q1")
    client.send(sender, "oi")
    msgs = client.send(sender, "sim")
    diagnostic = find_custom(msgs, "diagnostic")
    assert diagnostic is not None
    assert diagnostic["index"] == 1
    assert diagnostic["total"] == 10
    assert len(diagnostic["options"]) == 4


def test_post_diagnostic_menu(client: RasaRestClient, sender_after_diagnostic: str) -> None:
    msgs = client.send(sender_after_diagnostic, "o que preciso fazer agora")
    cog = find_custom(msgs, "cognitive_state")
    assert cog is not None
    assert "mastery" in cog
    assert "focusedTopic" in cog
    assert has_text_containing(msgs, "Próximo passo") or has_text_containing(
        msgs, "questionário diagnóstico"
    )


def test_start_study_with_affirm(
    client: RasaRestClient, sender_after_diagnostic: str
) -> None:
    client.send(sender_after_diagnostic, "o que preciso fazer agora")
    msgs = client.send(sender_after_diagnostic, "sim")
    study = find_custom(msgs, "study")
    assert study is not None
    assert study.get("topic")
    assert study.get("prompt")
    assert has_text_containing(msgs, "Reflexão")


def test_choose_topic(client: RasaRestClient, sender_after_diagnostic: str) -> None:
    msgs = client.send(sender_after_diagnostic, "quero estudar elementos do mapa")
    study = find_custom(msgs, "study")
    assert study is not None
    assert study["topic"] == "elementos_mapa"


def test_study_reflection(client: RasaRestClient, sender_after_diagnostic: str) -> None:
    client.send(sender_after_diagnostic, "quero estudar escala gráfica")
    msgs = client.send(
        sender_after_diagnostic,
        "tentaria explicar usando 1 cm para representar 500 metros",
    )
    assert has_text_containing(msgs, "Explicação") or has_text_containing(msgs, "explicação")
    assert find_custom(msgs, "study") is None or find_custom(msgs, "cognitive_state") is not None
    assert not has_text_containing(msgs, "questionário diagnóstico de 10 perguntas")


def test_topic_help(client: RasaRestClient, sender_after_diagnostic: str) -> None:
    msgs = client.send(sender_after_diagnostic, "tenho dúvida sobre escala gráfica")
    assert has_text_containing(msgs, "Escala Gráfica") or has_text_containing(
        msgs, "escala gráfica"
    )


@pytest.mark.parametrize("case", CROSS_TOPIC_HELP_CASES, ids=lambda c: c["name"])
def test_cross_topic_help(
    client: RasaRestClient, sender_after_diagnostic: str, case: dict
) -> None:
    msgs = client.send(sender_after_diagnostic, case["study_message"])
    study = find_custom(msgs, "study")
    assert study is not None
    assert study["topic"] == case["study_topic"]

    client.send(sender_after_diagnostic, case["reflection"])
    msgs = client.send(sender_after_diagnostic, case["help_message"])
    assert any(has_text_containing(msgs, label) for label in case["expected_labels"])
    assert has_text_containing(msgs, "Em vez de dar a resposta direta")


def test_help_during_diagnostic_does_not_skip(client: RasaRestClient) -> None:
    sender = _unique_sender("pytest-mid")
    client.send(sender, "oi")
    client.send(sender, "sim")
    client.send(sender, DIAGNOSTIC_CORRECT_ANSWERS[0])
    msgs = client.send(sender, "o que preciso fazer agora")
    assert find_custom(msgs, "study") is None
    assert has_text_containing(msgs, "diagnóstico") or has_text_containing(
        msgs, "responda"
    )
