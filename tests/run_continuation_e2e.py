#!/usr/bin/env python3
"""
Teste E2E da continuação pós-diagnóstico via REST API.

Uso (com Rasa rodando em localhost:5005):
    python tests/run_continuation_e2e.py

Variável opcional:
    RASA_WEBHOOK_URL=http://localhost:5005/webhooks/rest/webhook
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path

# Permite importar módulos locais ao rodar como script
sys.path.insert(0, str(Path(__file__).resolve().parent))

from e2e_client import RasaRestClient, all_text, find_custom, has_text_containing
from test_data import CROSS_TOPIC_HELP_CASES, DIAGNOSTIC_CORRECT_ANSWERS


class CheckResult:
    def __init__(self) -> None:
        self.passed = 0
        self.failed = 0
        self.details: list[str] = []

    def check(self, name: str, ok: bool, detail: str = "") -> None:
        status = "OK" if ok else "FALHOU"
        line = f"[{status}] {name}"
        if detail:
            line += f" — {detail}"
        print(line)
        if ok:
            self.passed += 1
        else:
            self.failed += 1
            self.details.append(line)

    @property
    def ok(self) -> bool:
        return self.failed == 0


def complete_diagnostic(client: RasaRestClient, sender: str, results: CheckResult) -> None:
    print("\n=== FASE 1: Diagnóstico (10 perguntas) ===\n")

    msgs = client.send(sender, "oi")
    results.check(
        "Saudação convida ao diagnóstico",
        has_text_containing(msgs, "questionário") or has_text_containing(msgs, "10 perguntas"),
        all_text(msgs)[:120] + "...",
    )

    msgs = client.send(sender, "sim")
    diagnostic = find_custom(msgs, "diagnostic")
    results.check(
        "Primeira pergunta diagnóstica (JSON)",
        diagnostic is not None and diagnostic.get("index") == 1,
        f"index={diagnostic.get('index') if diagnostic else None}",
    )
    results.check(
        "Primeira pergunta com 4 opções",
        diagnostic is not None and len(diagnostic.get("options", [])) == 4,
        f"opções={len(diagnostic.get('options', [])) if diagnostic else 0}",
    )
    results.check(
        "Primeira pergunta diagnóstica (texto)",
        has_text_containing(msgs, "Pergunta 1/10") and has_text_containing(msgs, "A)"),
        "",
    )

    last_msgs: list = []
    for i, answer in enumerate(DIAGNOSTIC_CORRECT_ANSWERS, start=1):
        last_msgs = client.send(sender, answer)
        if i < len(DIAGNOSTIC_CORRECT_ANSWERS):
            diag = find_custom(last_msgs, "diagnostic")
            expected_index = i + 1
            results.check(
                f"Resposta {i} avança para pergunta {expected_index}",
                diag is not None and diag.get("index") == expected_index,
                f"recebido index={diag.get('index') if diag else None}",
            )
            if diag is not None:
                results.check(
                    f"Pergunta {expected_index} tem 4 opções",
                    len(diag.get("options", [])) == 4,
                    f"opções={len(diag.get('options', []))}",
                )

    cog = find_custom(last_msgs, "cognitive_state")
    results.check(
        "Diagnóstico concluído — cognitive_state",
        cog is not None and "mastery" in cog,
        f"event={cog.get('event') if cog else None}",
    )
    results.check(
        "Menu de continuação após 10ª resposta",
        has_text_containing(last_msgs, "Recomendo")
        or has_text_containing(last_msgs, "tópicos"),
        all_text(last_msgs)[:120] + "...",
    )


def test_post_diagnostic_continuation(
    client: RasaRestClient, sender: str, results: CheckResult
) -> None:
    print("\n=== FASE 2: Continuação após diagnóstico ===\n")

    msgs = client.send(sender, "o que preciso fazer agora")
    results.check(
        "Explica próximos passos",
        has_text_containing(msgs, "questionário diagnóstico")
        or has_text_containing(msgs, "Próximo passo"),
        all_text(msgs)[:150] + "...",
    )
    cog = find_custom(msgs, "cognitive_state")
    results.check(
        "Payload cognitive_state na orientação",
        cog is not None and "mastery" in cog,
        f"event={cog.get('event') if cog else None}",
    )

    msgs = client.send(sender, "sim")
    study = find_custom(msgs, "study")
    results.check(
        "Aceitar tema inicia estudo (JSON study)",
        study is not None and "prompt" in study and "topic" in study,
        f"topic={study.get('topic') if study else None}",
    )
    results.check(
        "Lição reflexiva no texto",
        has_text_containing(msgs, "Reflexão"),
        "",
    )


def test_cross_topic_help_cases(
    client: RasaRestClient, sender: str, results: CheckResult
) -> None:
    print("\n=== FASE 3: Ajuda contextual entre tópicos ===\n")

    for case in CROSS_TOPIC_HELP_CASES:
        msgs = client.send(sender, case["study_message"])
        study = find_custom(msgs, "study")
        results.check(
            f"Inicia estudo — {case['name']}",
            study is not None and study.get("topic") == case["study_topic"],
            f"topic={study.get('topic') if study else None}",
        )

        msgs = client.send(sender, case["reflection"])
        results.check(
            f"Reflexão APT — {case['name']}",
            has_text_containing(msgs, "Explicação")
            or has_text_containing(msgs, "explicação"),
            all_text(msgs)[:100] + "...",
        )

        msgs = client.send(sender, case["help_message"])
        labels = case["expected_labels"]
        results.check(
            f"Ajuda sem resposta pronta — {case['name']}",
            any(has_text_containing(msgs, label) for label in labels)
            and has_text_containing(msgs, "Em vez de dar a resposta direta"),
            all_text(msgs)[:150] + "...",
        )


def test_mid_diagnostic_help(client: RasaRestClient, results: CheckResult) -> None:
    print("\n=== FASE 4: Dúvida durante o diagnóstico ===\n")

    sender = f"e2e-mid-{uuid.uuid4().hex[:8]}"
    client.send(sender, "oi")
    client.send(sender, "sim")
    client.send(sender, DIAGNOSTIC_CORRECT_ANSWERS[0])

    msgs = client.send(sender, "o que preciso fazer agora")
    results.check(
        "Durante diagnóstico, orienta a responder pergunta atual",
        has_text_containing(msgs, "questionário diagnóstico")
        or has_text_containing(msgs, "responda"),
        all_text(msgs)[:150] + "...",
    )
    diag = find_custom(msgs, "diagnostic")
    results.check(
        "Não pula para menu de estudo no meio do form",
        find_custom(msgs, "study") is None,
        f"ainda em diagnóstico={diag is not None}",
    )


def main() -> int:
    sender = f"e2e-full-{uuid.uuid4().hex[:8]}"
    client = RasaRestClient()
    results = CheckResult()

    print(f"Sender de teste: {sender}")
    print(f"Webhook: {client.webhook_url}\n")

    try:
        complete_diagnostic(client, sender, results)
        test_post_diagnostic_continuation(client, sender, results)
        test_cross_topic_help_cases(client, sender, results)
        test_mid_diagnostic_help(client, results)
    except ConnectionError as exc:
        print(f"\nERRO: {exc}")
        return 1

    print(f"\n{'=' * 50}")
    print(f"Resultado: {results.passed} OK, {results.failed} falha(s)")
    if not results.ok:
        print("\nFalhas:")
        for line in results.details:
            print(f"  {line}")
        return 1

    print("\nTodos os testes de continuação passaram.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
