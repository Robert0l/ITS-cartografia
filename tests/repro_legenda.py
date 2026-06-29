"""Reproduz o fluxo elementos_mapa + resposta legenda."""
from __future__ import annotations

import json
import sys
import uuid

sys.path.insert(0, "tests")
from e2e_client import RasaRestClient, find_custom, has_text_containing
from test_data import DIAGNOSTIC_CORRECT_ANSWERS


def main() -> None:
    client = RasaRestClient()
    sender = f"repro-legenda-{uuid.uuid4().hex[:8]}"

    client.send(sender, "oi")
    client.send(sender, "sim")
    for answer in DIAGNOSTIC_CORRECT_ANSWERS:
        client.send(sender, answer)

    client.send(sender, "quero começar por elementos do mapa")
    msgs = client.send(
        sender,
        "estaria na parte de baixo do mapa e a legenda serviria para explicar os elementos do mapa",
    )
    fb = find_custom(msgs, "study_feedback")
    print("After reflection feedback kind:", fb.get("kind") if fb else None)
    print("After reflection followUp set:", bool(fb.get("followUp")) if fb else None)

    msgs = client.send(sender, "Legenda")
    fb = find_custom(msgs, "study_feedback")
    assert fb is not None, "expected study_feedback for Legenda"
    assert fb.get("kind") == "followup", f"expected followup, got {fb.get('kind')}"
    assert fb.get("correct") is True, "Legenda should be accepted"
    assert has_text_containing(msgs, "concluiu o estudo"), "expected topic completion message"
    assert has_text_containing(msgs, "Recomendo estudar"), "expected next topic suggestion"
    assert not has_text_containing(msgs, "organizar"), "should not restart reflection loop"
    assert not has_text_containing(msgs, "palavra ou frase curta"), "should not show follow-up hint"
    print("OK: legenda follow-up advances correctly")

    msgs = client.send(sender, "não sei")
    assert has_text_containing(msgs, "Próximo passo") or has_text_containing(
        msgs, "Recomendo estudar"
    ), "expected navigation help after nao sei, not reflection loop"
    assert not has_text_containing(msgs, "Para fixar"), "should not re-ask follow-up question"
    print("OK: nao sei after completion suggests next topic")


if __name__ == "__main__":
    main()
