"""Cliente REST para testes E2E contra o Rasa."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional

DEFAULT_WEBHOOK = os.environ.get(
    "RASA_WEBHOOK_URL", "http://localhost:5005/webhooks/rest/webhook"
)


class RasaRestClient:
    def __init__(self, webhook_url: str = DEFAULT_WEBHOOK) -> None:
        self.webhook_url = webhook_url

    def send(self, sender: str, message: str) -> List[Dict[str, Any]]:
        payload = json.dumps({"sender": sender, "message": message}).encode("utf-8")
        request = urllib.request.Request(
            self.webhook_url,
            data=payload,
            headers={"Content-Type": "application/json; charset=utf-8"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                body = response.read().decode("utf-8")
        except urllib.error.URLError as exc:
            raise ConnectionError(
                f"Não foi possível conectar ao Rasa em {self.webhook_url}. "
                "Suba os serviços com: docker compose up -d"
            ) from exc

        data = json.loads(body)
        if not isinstance(data, list):
            raise ValueError(f"Resposta inesperada do Rasa: {body[:500]}")
        return data


def all_text(messages: List[Dict[str, Any]]) -> str:
    return "\n".join(m.get("text", "") for m in messages if m.get("text"))


def custom_blocks(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [m["custom"] for m in messages if m.get("custom")]


def find_custom(messages: List[Dict[str, Any]], key: str) -> Optional[Dict[str, Any]]:
    """Retorna o último bloco custom com a chave (resposta mais recente do turno)."""
    found: Optional[Dict[str, Any]] = None
    for block in custom_blocks(messages):
        if key in block:
            found = block[key]
    return found


def all_custom(messages: List[Dict[str, Any]], key: str) -> List[Dict[str, Any]]:
    return [block[key] for block in custom_blocks(messages) if key in block]


def has_text_containing(messages: List[Dict[str, Any]], snippet: str) -> bool:
    snippet_lower = snippet.lower()
    return snippet_lower in all_text(messages).lower()
