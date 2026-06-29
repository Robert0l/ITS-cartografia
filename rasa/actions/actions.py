"""Custom Actions do ITS Cartografia — integração Rasa + Rede Bayesiana."""

from __future__ import annotations

import json
import logging
import random
import re
from typing import Any, Dict, List, Text, Tuple

from rasa_sdk import Action, Tracker
from rasa_sdk.events import ActiveLoop, SlotSet
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.forms import FormValidationAction

from actions.bayesian_network import (
    CartographyKnowledgeTracer,
    DIAGNOSTIC_QUESTION_TOPICS,
    TOPIC_LABELS,
    TOPICS,
)

logger = logging.getLogger(__name__)

SLOT_TRACER_STATE = "tracer_state"
SLOT_DIAGNOSTIC_INDEX = "diagnostic_index"
SLOT_LAST_TOPIC = "last_topic"
SLOT_PENDING_CORRECT = "pending_correct"
SLOT_DIAGNOSTIC_INVITATION_PENDING = "diagnostic_invitation_pending"
SLOT_SCALE_REFLECTION_PENDING = "scale_reflection_pending"
SLOT_STUDY_SUGGESTION_PENDING = "study_suggestion_pending"
SLOT_ACTIVE_STUDY_TOPIC = "active_study_topic"
SLOT_DIAGNOSTIC_LAYOUT = "diagnostic_layout"
SLOT_STUDY_FOLLOWUP_PENDING = "study_followup_pending"
SLOT_STUDY_FOLLOWUP_QUESTION = "study_followup_question"

DIAGNOSTIC_QUESTIONS: List[Dict[str, str]] = [
    {
        "text": "O que é um mapa?",
        "options": (
            "Representação reduzida e simplificada da superfície terrestre"
            " | Imagem de satélite sem qualquer edição"
            " | Modelo tridimensional em tamanho real"
            " | Lista apenas com nomes de cidades"
        ),
        "correct": "Representação reduzida e simplificada da superfície terrestre",
    },
    {
        "text": "Qual é a função principal da cartografia?",
        "options": (
            "Representar e comunicar fenômenos espaciais"
            " | Prever o tempo em cada cidade"
            " | Medir a gravidade no Equador"
            " | Registrar somente fronteiras políticas"
        ),
        "correct": "Representar e comunicar fenômenos espaciais",
    },
    {
        "text": "O que são coordenadas geográficas?",
        "options": (
            "Sistema de localização por latitude e longitude"
            " | Medida da altitude acima do nível do mar"
            " | Tipo de projeção cartográfica"
            " | Escala numérica impressa no mapa"
        ),
        "correct": "Sistema de localização por latitude e longitude",
    },
    {
        "text": "A latitude mede a distância em relação a qual referência?",
        "options": (
            "Equador"
            " | Meridiano de Greenwich"
            " | Polo Norte"
            " | Trópico de Capricórnio"
        ),
        "correct": "Equador",
    },
    {
        "text": "Qual elemento do mapa explica o significado dos símbolos?",
        "options": (
            "Legenda"
            " | Escala gráfica"
            " | Título do mapa"
            " | Rosa dos ventos"
        ),
        "correct": "Legenda",
    },
    {
        "text": "O que é escala gráfica?",
        "options": (
            "Segmento de reta que relaciona distâncias no mapa e na realidade"
            " | Número que indica a população da região"
            " | Ângulo de inclinação do terreno"
            " | Direção do norte magnético"
        ),
        "correct": "Segmento de reta que relaciona distâncias no mapa e na realidade",
    },
    {
        "text": "Na escala 1:50.000, 1 cm no mapa equivale a quanto na realidade?",
        "options": (
            "500 metros"
            " | 50 metros"
            " | 5 km"
            " | 50 km"
        ),
        "correct": "500 metros",
    },
    {
        "text": "Se a distância real é 10 km e no mapa mede 2 cm, qual é a escala numérica?",
        "options": (
            "1:500.000"
            " | 1:50.000"
            " | 1:5.000"
            " | 1:500"
        ),
        "correct": "1:500.000",
    },
    {
        "text": "Por que usamos projeções cartográficas?",
        "options": (
            "Representar a superfície curva da Terra em um plano"
            " | Aumentar a resolução das fotos aéreas"
            " | Calcular a latitude de um ponto"
            " | Colorir automaticamente os países"
        ),
        "correct": "Representar a superfície curva da Terra em um plano",
    },
    {
        "text": "Em um mapa topográfico, o que a densidade de curvas de nível indica?",
        "options": (
            "Inclinação do relevo"
            " | Temperatura média da região"
            " | Densidade populacional"
            " | Tipo de clima predominante"
        ),
        "correct": "Inclinação do relevo",
    },
]

for _i, _q in enumerate(DIAGNOSTIC_QUESTIONS):
    _opts = [o.strip() for o in _q["options"].split(" | ")]
    if len(_opts) != 4:
        raise ValueError(f"Pergunta diagnóstica {_i + 1} deve ter 4 opções, tem {len(_opts)}")
    if _q["correct"] not in _opts:
        raise ValueError(f"Pergunta diagnóstica {_i + 1}: resposta correta não está entre as opções")


TOPIC_LESSONS: Dict[str, Dict[str, str]] = {
    "introducao": {
        "intro": "Cartografia é a ciência que representa fenômenos espaciais. Antes de calcular escalas, vale fixar o que um mapa faz e o que ele não faz.",
        "prompt": "Na sua opinião, qual a diferença entre um mapa e uma fotografia aérea da mesma região? O que o mapa precisa simplificar ou destacar?",
    },
    "coordenadas_geograficas": {
        "intro": "Coordenadas localizam pontos na superfície terrestre usando latitude e longitude.",
        "prompt": "Se você está no hemisfério sul, a latitude é positiva ou negativa? Por que o Equador é a referência para latitude?",
    },
    "elementos_mapa": {
        "intro": "Título, legenda, escala e orientação ajudam a ler qualquer mapa.",
        "prompt": "Abra um mapa mental que você conheça: onde estaria a legenda e por que ela é indispensável para interpretar símbolos?",
    },
    "escala_grafica": {
        "intro": "A escala gráfica relaciona distâncias no mapa com distâncias reais por meio de um segmento de reta.",
        "prompt": "Se um segmento de 2 cm no mapa representa 1 km na realidade, como você explicaria essa relação para um colega sem dar só a fórmula?",
    },
    "escala_numerica": {
        "intro": "Na escala numérica (ex.: 1:50.000), cada unidade no mapa multiplica por 50.000 na realidade.",
        "prompt": "Em 1:50.000, 1 cm no mapa equivale a quantos centímetros na realidade? Que passos você usaria para converter?",
    },
    "calculo_escala": {
        "intro": "Calcular escala exige alinhar unidades (cm, m, km) e comparar distância no mapa com distância real.",
        "prompt": "Uma distância real de 10 km aparece como 2 cm no mapa. Como você montaria a razão antes de simplificar para 1:n?",
    },
    "projecoes": {
        "intro": "Projeções cartográficas levam a superfície curva da Terra para um plano, com distorções controladas.",
        "prompt": "Por que não dá para representar a Terra em um plano sem distorcer área, forma ou distância? Qual tipo de mapa você usaria para comparar tamanhos de países?",
    },
    "orientacao": {
        "intro": "Orientação e rosa dos ventos indicam onde está o norte e ajudam a situar-se no espaço.",
        "prompt": "Se a bússola aponta para o norte magnético e o mapa usa norte verdadeiro, o que pode mudar na leitura de uma rota?",
    },
    "interpretacao_mapa": {
        "intro": "Interpretar mapas integra escala, relevo, símbolos e contexto geográfico.",
        "prompt": "Curvas de nível muito próximas num mapa topográfico indicam o quê sobre o relevo? Como você justificaria isso?",
    },
}

TOPIC_ALIASES: Dict[str, str] = {
    "introdução": "introducao",
    "introducao": "introducao",
    "cartografia": "introducao",
    "coordenadas geográficas": "coordenadas_geograficas",
    "coordenadas": "coordenadas_geograficas",
    "latitude": "coordenadas_geograficas",
    "longitude": "coordenadas_geograficas",
    "elementos do mapa": "elementos_mapa",
    "elementos": "elementos_mapa",
    "legenda": "elementos_mapa",
    "escala gráfica": "escala_grafica",
    "escala grafica": "escala_grafica",
    "escala numérica": "escala_numerica",
    "escala numerica": "escala_numerica",
    "cálculo de escala": "calculo_escala",
    "calculo de escala": "calculo_escala",
    "calcular escala": "calculo_escala",
    "escala": "escala_grafica",
    "projeções": "projecoes",
    "projeção": "projecoes",
    "projeções cartográficas": "projecoes",
    "projeção cartográfica": "projecoes",
    "projecoes": "projecoes",
    "orientação": "orientacao",
    "orientacao": "orientacao",
    "norte magnético": "orientacao",
    "norte magnetico": "orientacao",
    "rosa dos ventos": "orientacao",
    "interpretação": "interpretacao_mapa",
    "interpretação de mapas": "interpretacao_mapa",
    "interpretacao de mapas": "interpretacao_mapa",
    "interpretacao": "interpretacao_mapa",
    "interpretar mapa": "interpretacao_mapa",
    "tema recomendado": "introducao",
    "tema sugerido": "introducao",
}


UNCERTAINTY_PHRASES = (
    "não sei",
    "nao sei",
    "não entendi",
    "nao entendi",
    "sem ideia",
    "difícil",
    "dificil",
    "não faço ideia",
    "nao faco ideia",
)

TOPIC_TEACHING: Dict[str, Dict[str, Any]] = {
    "introducao": {
        "explanation": (
            "Um **mapa** é uma representação **reduzida, simplificada e seletiva** do espaço: "
            "o cartógrafo escolhe o que mostrar (rios, cidades, relevo) e usa **símbolos** para "
            "padronizar a leitura. Uma **fotografia aérea** registra a aparência real da superfície "
            "no momento do voo — tem detalhe visual, mas não traz, por si só, legenda, escala "
            "nem generalização didática."
        ),
        "signals_strong": ("mapa", "foto", "fotografia", "simplif", "selecion", "símbol", "simbol", "generaliz"),
        "signals_partial": ("imagem", "região", "regiao", "mostrar", "diferen"),
        "follow_up": "Se você removesse a legenda de um mapa temático, o que ficaria difícil de interpretar?",
    },
    "coordenadas_geograficas": {
        "explanation": (
            "**Latitude** mede a distância angular em relação ao **Equador** (0°): "
            "valores ao **norte** são positivos e ao **sul**, negativos. "
            "**Longitude** mede em relação ao **Meridiano de Greenwich** (0°), "
            "para leste ou oeste. Juntas, latitude e longitude localizam qualquer ponto na Terra."
        ),
        "signals_strong": ("equador", "latitude", "longitude", "hemisf", "norte", "sul", "meridiano", "positiv", "negativ"),
        "signals_partial": ("coordenad", "localiz", "graus"),
        "follow_up": "Um ponto em 23°S está no hemisfério norte ou sul? Por quê?",
        "follow_up_checks": [
            {
                "match": "23",
                "accept_keywords": ("hemisferio sul", "hemisfério sul", "sul", "ao sul"),
                "reject_keywords": ("norte", "hemisferio norte", "hemisfério norte"),
                "correct_msg": (
                    "Correto: **23°S** está ao **sul** do Equador, no **hemisfério sul**."
                ),
                "wrong_msg": (
                    "O **S** em 23°S indica latitude **sul** do Equador — portanto, hemisfério **sul**."
                ),
            },
        ],
    },
    "elementos_mapa": {
        "explanation": (
            "Os elementos básicos de leitura são: **título** (tema do mapa), **legenda** "
            "(significado dos símbolos e cores), **escala** (relação mapa–terreno) e "
            "**orientação** (direção do norte). Sem a **legenda**, símbolos como estradas, "
            "rios ou áreas urbanas perdem significado."
        ),
        "signals_strong": ("legenda", "título", "titulo", "escala", "orient", "rosa", "símbol", "simbol", "norte"),
        "signals_partial": ("elemento", "mapa", "ler", "interpret"),
        "follow_up": "Qual elemento você consultaria primeiro para saber o que uma cor representa?",
        "follow_up_checks": [
            {
                "match": "cor representa",
                "accept_keywords": ("legenda",),
                "reject_keywords": (
                    "titulo", "título", "escala", "orientacao", "orientação",
                    "rosa dos ventos", "bússola", "bussola",
                ),
                "correct_msg": (
                    "Exato: a **legenda** explica o significado das **cores** e **símbolos** do mapa."
                ),
                "wrong_msg": (
                    "Para saber o que uma **cor** representa, consulte a **legenda** — "
                    "é ela que traduz símbolos e cores."
                ),
            },
        ],
    },
    "escala_grafica": {
        "explanation": (
            "A **escala gráfica** é um **segmento de reta** no mapa acompanhado do valor real "
            "que ele representa (ex.: 2 cm = 1 km). Você mede uma distância no mapa com régua "
            "e compara com o segmento para estimar a distância no terreno. "
            "A **razão** entre mapa e realidade permanece a mesma em qualquer parte do mapa."
        ),
        "signals_strong": ("segmento", "reta", "propor", "distân", "distanc", "razão", "razao", "equival"),
        "signals_partial": ("escala", "mapa", "real", "medir", "cm", "metro", "quilô", "quilo"),
        "follow_up": "Se 2 cm no mapa equivalem a 1 km, quantos metros reais correspondem a 4 cm?",
        "follow_up_checks": [
            {
                "match": "4 cm",
                "accept": [
                    {"value": 2000, "units": ("m", "metro", "metros")},
                    {"value": 2, "units": ("km", "quilomet", "quilôm")},
                ],
                "correct_msg": "4 cm correspondem ao dobro de 2 cm: **2 km** ou **2000 m**.",
                "wrong_msg": (
                    "Se 2 cm = 1 km, então 4 cm = 2 × 1 km = **2000 m**. "
                    "Dobre a medida no mapa e a distância real também dobra."
                ),
            },
        ],
    },
    "escala_numerica": {
        "explanation": (
            "Na escala **numérica** (ex.: **1:50.000**), cada unidade no mapa vale 50.000 "
            "no terreno. Assim, **1 cm no mapa = 50.000 cm na realidade**, ou seja, **500 m**. "
            "Para converter: multiplique a medida do mapa pelo denominador, sempre com as "
            "**mesmas unidades**."
        ),
        "signals_strong": (
            "50.000", "50000", "1:50", "multiplic", "denominador", "propor",
            "500 m", "500m", "500 metros", "50000 cm", "50 mil",
        ),
        "signals_partial": ("escala", "numéric", "numeric", "converter", "cm", "razão", "razao"),
        "follow_up": "Em 1:50.000, quantos metros reais correspondem a 3 cm no mapa?",
        "follow_up_checks": [
            {
                "match": "3 cm",
                "accept": [
                    {"value": 1500, "units": ("m", "metro", "metros")},
                    {"value": 1.5, "units": ("km", "quilomet", "quilôm")},
                ],
                "correct_msg": (
                    "3 cm no mapa × 500 m por cm = **1500 m** (ou **1,5 km**) na escala 1:50.000."
                ),
                "wrong_msg": (
                    "Revise: em 1:50.000 cada **1 cm** vale **500 m** no terreno. "
                    "Para **3 cm**, multiplique: 3 × 500 = **1500 m**."
                ),
            },
        ],
    },
    "calculo_escala": {
        "explanation": (
            "Para calcular a escala, alinhe as **unidades**: por exemplo, 2 cm no mapa e "
            "10 km no terreno → 2 cm e 1.000.000 cm. A razão é **2 : 1.000.000**, "
            "que simplificada vira **1:500.000**. Só depois de igualar unidades é seguro "
            "escrever a escala no formato 1:n."
        ),
        "signals_strong": ("cm", "km", "unidad", "razão", "razao", "simplif", "1:", "500.000", "500000", "converter"),
        "signals_partial": ("calcular", "escala", "distân", "distanc", "mapa", "real"),
        "follow_up": "Por que não podemos comparar 2 cm diretamente com 10 km sem converter antes?",
    },
    "projecoes": {
        "explanation": (
            "A Terra tem forma aproximada de **esfera (geoide)**. Ao representá-la em um **plano**, "
            "é impossível manter ao mesmo tempo **área, forma, distância e direção** sem alguma "
            "**distorção** — por isso existem vários tipos de **projeção cartográfica**, cada um "
            "priorizando uma propriedade. Para **comparar tamanhos de países**, usamos projeções "
            "**equidistantes em área** (como Peters ou equivalentes), que preservam proporções de superfície."
        ),
        "signals_strong": ("esfera", "curv", "plano", "distor", "geoide", "bidimensional", "duas dim", "2 d", "2d", "achat"),
        "signals_partial": ("terra", "mapa mundi", "mapa", "represent"),
        "follow_up": "Por que uma projeção boa para navegação pode distorcer o tamanho aparente dos continentes?",
    },
    "orientacao": {
        "explanation": (
            "A **orientação** indica onde está o **norte** no mapa, muitas vezes com **rosa dos ventos**. "
            "O **norte verdadeiro (geográfico)** segue o eixo de rotação da Terra. "
            "O **norte magnético** é onde a bússola aponta — fica perto do norte geográfico, "
            "mas **não é o sul** e pode **desviar** alguns graus (declinação magnética). "
            "O **sul verdadeiro** é o oposto do eixo, no hemisfério sul — conceito diferente do norte magnético."
        ),
        "signals_strong": ("bússola", "bussola", "declinação", "declinacao", "desvio", "geográf", "geograf", "rosa", "vento", "rumo"),
        "signals_partial": ("norte", "magnét", "magnet", "verdadeir", "orient", "direção", "direcao", "rota"),
        "signals_incorrect": (
            "magnético é o sul",
            "magnetico e o sul",
            "magnético e o sul",
            "norte magnético é o sul",
            "norte magnetico e o sul",
            "sul verdadeiro",
            "magnético é o verdadeiro sul",
        ),
        "follow_up": "Se a bússola aponta para o norte magnético, o que muda na rota quando o mapa usa norte verdadeiro?",
    },
    "interpretacao_mapa": {
        "explanation": (
            "**Curvas de nível** ligam pontos com a mesma altitude. Quando estão **muito próximas**, "
            "o relevo é **íngreme**; quando estão **afastadas**, o terreno é mais **suave**. "
            "Interpretar um mapa topográfico combina escala, legenda, orientação e esse padrão "
            "do relevo para entender o espaço."
        ),
        "signals_strong": ("curva", "nível", "nivel", "relevo", "íngrem", "ingrem", "inclin", "denso", "próxim", "proxim", "altitude"),
        "signals_partial": ("topográf", "topograf", "mapa", "terreno", "montan"),
        "follow_up": "Além do relevo, o que as curvas de nível ajudam a inferir sobre drenagem e vales?",
    },
}


def _normalize_text(value: Text) -> Text:
    return str(value).strip().lower()


def _close_stale_diagnostic_loop(tracker: Tracker) -> List[Any]:
    """Encerra o form diagnóstico se o cold start já foi concluído."""
    if not tracker.get_slot("diagnostic_completed"):
        return []
    loop_name = tracker.active_loop.get("name") if tracker.active_loop else None
    if loop_name == "diagnostic_form":
        return [ActiveLoop(None)]
    return []


def _resolve_topic_from_tracker(tracker: Tracker, tracer: CartographyKnowledgeTracer) -> Text | None:
    for ent in tracker.latest_message.get("entities") or []:
        if ent.get("entity") == "topic":
            value = ent.get("value")
            if value in TOPICS:
                return value

    text = _normalize_text(tracker.latest_message.get("text") or "")
    if "tema recomendado" in text or "tema sugerido" in text:
        return tracer.focused_topic

    for alias, topic_id in sorted(TOPIC_ALIASES.items(), key=lambda x: -len(x[0])):
        if alias in text:
            return topic_id

    topic = tracker.get_slot("topic") or tracker.get_slot(SLOT_ACTIVE_STUDY_TOPIC)
    if topic and topic in TOPICS:
        return topic

    return None


def _format_topic_menu(tracer: CartographyKnowledgeTracer) -> Text:
    mastery = tracer.get_mastery()
    lines = []
    for topic_id in TOPICS:
        label = TOPIC_LABELS.get(topic_id, topic_id)
        pct = mastery.get(topic_id, 0.0)
        marker = " ← recomendado" if topic_id == tracer.focused_topic else ""
        lines.append(f"• {label} ({pct:.0f}%){marker}")
    return "\n".join(lines)


def _emit_study_lesson(
    dispatcher: CollectingDispatcher,
    tracer: CartographyKnowledgeTracer,
    topic: Text,
) -> None:
    lesson = TOPIC_LESSONS[topic]
    label = TOPIC_LABELS.get(topic, topic)
    mastery_pct = tracer.get_mastery().get(topic, 0.0)

    dispatcher.utter_message(
        json_message={
            "study": {
                "topic": topic,
                "topicLabel": label,
                "mastery": mastery_pct,
                "intro": lesson["intro"],
                "prompt": lesson["prompt"],
            }
        }
    )
    dispatcher.utter_message(
        text=(
            f"**{label}** (domínio estimado: {mastery_pct:.0f}%)\n\n"
            f"{lesson['intro']}\n\n"
            f"**Reflexão:** {lesson['prompt']}"
        )
    )
    dispatcher.utter_message(response="utter_study_topic_hint")


def _load_tracer(tracker: Tracker) -> CartographyKnowledgeTracer:
    raw = tracker.get_slot(SLOT_TRACER_STATE)
    if raw:
        try:
            data = json.loads(raw) if isinstance(raw, str) else raw
            return CartographyKnowledgeTracer.from_dict(data)
        except (json.JSONDecodeError, TypeError):
            logger.warning("Estado do tracer inválido; reiniciando.")
    return CartographyKnowledgeTracer()


def _save_tracer(tracer: CartographyKnowledgeTracer) -> SlotSet:
    return SlotSet(SLOT_TRACER_STATE, json.dumps(tracer.to_dict()))


def _emit_cognitive_payload(
    dispatcher: CollectingDispatcher,
    tracer: CartographyKnowledgeTracer,
    extra: Dict[str, Any] | None = None,
) -> None:
    payload = tracer.get_payload()
    if extra:
        payload.update(extra)
    dispatcher.utter_message(json_message={"cognitive_state": payload})


def _format_diagnostic_options(options: List[str]) -> Text:
    letters = "ABCD"
    return "\n".join(f"  {letters[i]}) {opt}" for i, opt in enumerate(options))


def _emit_diagnostic_question(
    dispatcher: CollectingDispatcher,
    index: int,
    options: List[str],
) -> Text:
    """Emite payload JSON e texto da pergunta diagnóstica no índice dado."""
    q = DIAGNOSTIC_QUESTIONS[index]
    topic = DIAGNOSTIC_QUESTION_TOPICS[index]
    topic_label = TOPIC_LABELS.get(topic, topic)

    dispatcher.utter_message(
        json_message={
            "diagnostic": {
                "index": index + 1,
                "total": len(DIAGNOSTIC_QUESTIONS),
                "question": q["text"],
                "options": options,
                "topic": topic,
                "topicLabel": topic_label,
            }
        }
    )
    dispatcher.utter_message(
        text=(
            f"**Pergunta {index + 1}/10** ({topic_label}): {q['text']}\n\n"
            f"{_format_diagnostic_options(options)}\n\n"
            "Escolha uma letra ou digite a resposta completa."
        )
    )
    return topic


TOPIC_FOLLOW_UPS: Dict[str, str] = {
    "escala_grafica": (
        "Se você mudar a escala do mapa, o segmento gráfico muda também? "
        "O que permanece constante na relação mapa–realidade?"
    ),
    "escala_numerica": (
        "Na escala 1:50.000, o que acontece com a distância real se você "
        "medir 3 cm no mapa em vez de 1 cm?"
    ),
    "calculo_escala": (
        "Antes de simplificar para 1:n, por que é importante usar as mesmas unidades "
        "para mapa e terreno?"
    ),
    "introducao": (
        "Que tipo de informação um mapa precisa omitir ou generalizar "
        "que uma foto aérea não omitiria?"
    ),
    "coordenadas_geograficas": (
        "Como você explicaria a diferença entre latitude e longitude para alguém "
        "que nunca viu um globo?"
    ),
    "elementos_mapa": (
        "Se você removesse a legenda do mapa, qual informação se tornaria "
        "impossível de interpretar?"
    ),
    "projecoes": (
        "Por que a mesma projeção não serve igualmente bem para comparar "
        "áreas e para navegar em alta latitude?"
    ),
    "orientacao": (
        "O que muda na leitura de uma rota se o norte do mapa não estiver "
        "alinhado com o topo da página?"
    ),
    "interpretacao_mapa": (
        "Além do relevo, que outro fenômeno espacial as curvas de nível "
        "ajudam a inferir?"
    ),
}


def _signal_matches(normalized: Text, signal: Text) -> bool:
    """Evita falso positivo (ex.: '500' dentro de '1500')."""
    if re.fullmatch(r"[\d.:]+", signal):
        return re.search(rf"(?<!\d){re.escape(signal)}(?!\d)", normalized) is not None
    return signal in normalized


def _is_uncertainty_message(text: Text) -> bool:
    normalized = _normalize_text(text)
    return any(phrase in normalized for phrase in UNCERTAINTY_PHRASES)


def _reflection_quality(topic: Text, user_text: Text) -> Text:
    teaching = TOPIC_TEACHING.get(topic, {})
    normalized = _normalize_text(user_text)
    if any(_signal_matches(normalized, signal) for signal in teaching.get("signals_incorrect", ())):
        return "misconception"
    if len(normalized) < 12:
        return "weak"
    strong_hits = sum(
        1 for signal in teaching.get("signals_strong", ())
        if _signal_matches(normalized, signal)
    )
    partial_hits = sum(
        1 for signal in teaching.get("signals_partial", ())
        if _signal_matches(normalized, signal)
    )
    if strong_hits >= 2 or (strong_hits >= 1 and len(normalized.split()) >= 10):
        return "strong"
    if strong_hits >= 1 or partial_hits >= 2:
        return "partial"
    if partial_hits >= 1:
        return "partial"
    return "weak"


def _reflection_opener(label: Text, quality: Text) -> Text:
    if quality == "strong":
        return f"Boa leitura do conceito em **{label}**!"
    if quality == "partial":
        return f"Você tocou em pontos importantes de **{label}**."
    if quality == "misconception":
        return f"Boa tentativa em **{label}** — vamos corrigir um detalhe importante."
    return f"Vamos organizar o raciocínio sobre **{label}**."


def _build_reflection_bridge(topic: Text, user_text: Text, quality: Text) -> Text:
    snippet = user_text[:200] + ("…" if len(user_text) > 200 else "")
    if quality == "misconception":
        return (
            f"Você disse: _{snippet}_\n\n"
            "Vale ajustar um ponto: sua ideia mistura **norte magnético** com **sul verdadeiro**, "
            "que são referências diferentes. Veja a explicação abaixo."
        )
    if quality == "strong":
        return (
            f"Você disse: _{snippet}_\n\n"
            "Seu raciocínio vai na direção certa — especialmente ao relacionar as ideias centrais do tema."
        )
    if quality == "partial":
        return (
            f"Você disse: _{snippet}_\n\n"
            "Há boas pistas no que você escreveu; vamos completar o quadro com a explicação abaixo."
        )
    return (
        f"Você compartilhou: _{snippet}_\n\n"
        "Obrigado por tentar — a seguir organizo o conceito de forma didática."
    )


def _extract_numeric_answers(text: Text) -> List[Tuple[float, Text | None]]:
    normalized = _normalize_text(text)
    found: List[Tuple[float, Text | None]] = []
    pattern = re.compile(
        r"(\d+(?:[.,]\d+)?)\s*(km|quilomet\w*|m\b|metros?|cm|centimet\w*)?",
        re.IGNORECASE,
    )
    for match in pattern.finditer(normalized):
        raw_val = match.group(1).replace(",", ".")
        try:
            value = float(raw_val)
        except ValueError:
            continue
        unit = (match.group(2) or "").strip().lower() or None
        found.append((value, unit))
    return found


def _numeric_answer_matches(
    value: float,
    unit: Text | None,
    spec: Dict[str, Any],
) -> bool:
    expected = spec["value"]
    units = spec.get("units", ())
    if unit:
        if not any(u in unit for u in units):
            return False
    return abs(value - expected) <= max(0.01 * expected, 0.5)


def _evaluate_text_followup(normalized: Text, check: Dict[str, Any]) -> bool | None:
    """Avalia resposta textual. True=correta, False=incorreta, None=não aplicável."""
    accept = check.get("accept_keywords", ())
    reject = check.get("reject_keywords", ())
    if not accept:
        return None

    has_accept = any(keyword in normalized for keyword in accept)
    has_reject = bool(reject) and any(keyword in normalized for keyword in reject)

    if has_accept and not has_reject:
        return True
    if has_reject and not has_accept:
        return False
    if has_accept and has_reject:
        return None
    if reject and has_reject:
        return False
    return False


def _evaluate_followup_answer(topic: Text, follow_up: Text, user_text: Text) -> Dict[str, Any]:
    teaching = TOPIC_TEACHING.get(topic, {})
    checks = teaching.get("follow_up_checks", [])
    normalized = _normalize_text(user_text)
    numbers = _extract_numeric_answers(user_text)

    for check in checks:
        if check.get("match", "").lower() not in follow_up.lower():
            continue

        if check.get("accept_keywords"):
            text_result = _evaluate_text_followup(normalized, check)
            if text_result is True:
                return {
                    "correct": True,
                    "message": check.get("correct_msg", "Resposta correta."),
                    "quality": "followup_correct",
                }
            if text_result is False:
                return {
                    "correct": False,
                    "message": check.get(
                        "wrong_msg",
                        "Revise com calma — repense o conceito central do tema.",
                    ),
                    "quality": "followup_wrong",
                }

        if check.get("accept"):
            for spec in check.get("accept", ()):
                for value, unit in numbers:
                    if _numeric_answer_matches(value, unit, spec):
                        return {
                            "correct": True,
                            "message": check.get("correct_msg", "Seu cálculo está certo."),
                            "quality": "followup_correct",
                        }
            if numbers or not check.get("accept_keywords"):
                return {
                    "correct": False,
                    "message": check.get(
                        "wrong_msg",
                        "Revise o cálculo com calma — compare mapa e terreno usando a mesma escala.",
                    ),
                    "quality": "followup_wrong",
                }

    return {
        "correct": None,
        "message": "Registrei sua resposta.",
        "quality": "followup_neutral",
    }


def _emit_followup_feedback(
    dispatcher: CollectingDispatcher,
    tracer: CartographyKnowledgeTracer,
    topic: Text,
    user_text: Text,
    follow_up: Text,
) -> Dict[str, Any]:
    label = TOPIC_LABELS.get(topic, topic)
    evaluation = _evaluate_followup_answer(topic, follow_up, user_text)
    is_correct = evaluation["correct"]

    if is_correct is True:
        opener = f"**Correto!** {evaluation['message']}"
        closing = (
            "Quer **aprofundar neste tema** com outra pergunta ou **estudar outro tópico**? "
            "Diga por exemplo: *quero estudar coordenadas*."
        )
    elif is_correct is False:
        opener = f"**Ainda não é isso.** {evaluation['message']}"
        closing = (
            "Tente responder de novo com suas palavras ou diga **entendi** se preferir seguir adiante."
        )
    else:
        opener = f"Entendi sua resposta sobre **{label}**."
        closing = "Quer **estudar outro tópico** ou continuar neste?"

    dispatcher.utter_message(text=f"{opener}\n\n{closing}")

    dispatcher.utter_message(
        json_message={
            "study_feedback": {
                "kind": "followup",
                "topic": topic,
                "topicLabel": label,
                "userAnswer": user_text,
                "quality": evaluation["quality"],
                "correct": is_correct,
                "followUpQuestion": follow_up,
            }
        }
    )

    return evaluation


def _emit_study_deepening(
    dispatcher: CollectingDispatcher,
    tracer: CartographyKnowledgeTracer,
    topic: Text,
    user_text: Text,
    *,
    needs_help: bool = False,
) -> Dict[str, Any]:
    """Responde à opinião do aluno com explicação didática conectada ao que ele disse."""
    teaching = TOPIC_TEACHING.get(topic, {})
    lesson = TOPIC_LESSONS.get(topic, {})
    label = TOPIC_LABELS.get(topic, topic)
    explanation = teaching.get("explanation", lesson.get("intro", ""))
    follow_up = teaching.get("follow_up", TOPIC_FOLLOW_UPS.get(topic, ""))

    if needs_help:
        quality = "needs_help"
        opener = f"Sem problema — em **{label}**, vou explicar passo a passo."
        bridge = "Não precisa ter respondido certo antes; o importante é compreender o conceito."
    else:
        quality = _reflection_quality(topic, user_text)
        opener = _reflection_opener(label, quality)
        bridge = _build_reflection_bridge(topic, user_text, quality)

    dispatcher.utter_message(text=f"{opener}\n\n{bridge}")
    dispatcher.utter_message(text=f"**Explicação:** {explanation}")
    if follow_up:
        dispatcher.utter_message(
            text=(
                f"**Para fixar:** {follow_up}\n\n"
                f"{_followup_prompt_hint(topic)}"
            )
        )
    else:
        dispatcher.utter_message(
            text="Quando quiser seguir, diga **entendi** ou **quero estudar outro tema**."
        )

    dispatcher.utter_message(
        json_message={
            "study_feedback": {
                "kind": "reflection",
                "topic": topic,
                "topicLabel": label,
                "userReflection": user_text if not needs_help else None,
                "quality": quality,
                "explanation": explanation,
                "followUp": follow_up,
            }
        }
    )

    return {"quality": quality, "follow_up": follow_up if follow_up else None}


def _load_diagnostic_layout(tracker: Tracker) -> Dict[str, List[str]]:
    raw = tracker.get_slot(SLOT_DIAGNOSTIC_LAYOUT)
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {}


def _shuffle_diagnostic_options(index: int, sender_id: Text) -> List[str]:
    options = [o.strip() for o in DIAGNOSTIC_QUESTIONS[index]["options"].split(" | ")]
    rng = random.Random(hash(f"{sender_id}:{index}") & 0xFFFFFFFF)
    shuffled = options[:]
    rng.shuffle(shuffled)
    return shuffled


def _diagnostic_options_for_index(
    tracker: Tracker,
    index: int,
) -> Tuple[List[str], Dict[str, List[str]]]:
    layout = _load_diagnostic_layout(tracker)
    key = str(index)
    if key not in layout:
        layout[key] = _shuffle_diagnostic_options(index, tracker.sender_id or "")
    return layout[key], layout


def _parse_diagnostic_selection(
    slot_value: Any,
    index: int,
    options: List[str] | None = None,
) -> Text | None:
    """Resolve letra (A–D), formato 'A) texto' ou texto da opção."""
    if index >= len(DIAGNOSTIC_QUESTIONS):
        return None
    if options is None:
        options = [o.strip() for o in DIAGNOSTIC_QUESTIONS[index]["options"].split(" | ")]
    raw = str(slot_value).strip()
    normalized = raw.lower()

    for opt in options:
        if normalized == opt.lower():
            return opt

    letter_match = re.match(r"^([a-dA-D])\)\s*(.*)$", raw)
    if letter_match:
        letter_index = ord(letter_match.group(1).lower()) - ord("a")
        rest = letter_match.group(2).strip().lower()
        if 0 <= letter_index < len(options):
            if not rest or rest == options[letter_index].lower():
                return options[letter_index]
            for opt in options:
                if rest == opt.lower():
                    return opt

    if len(normalized) == 1 and normalized in "abcd":
        letter_index = ord(normalized) - ord("a")
        if letter_index < len(options):
            return options[letter_index]

    return None


def _is_diagnostic_correct(
    slot_value: Any,
    index: int,
    options: List[str] | None = None,
) -> bool:
    selected = _parse_diagnostic_selection(slot_value, index, options)
    if not selected:
        return False
    return selected == DIAGNOSTIC_QUESTIONS[index]["correct"]


def _matches_diagnostic_answer(
    slot_value: Any,
    index: int,
    options: List[str] | None = None,
) -> bool:
    """Verifica se o texto corresponde à resposta, letra ou opção da pergunta atual."""
    return _parse_diagnostic_selection(slot_value, index, options) is not None


def _wants_to_start_study(text: Text) -> bool:
    normalized = _normalize_text(text)
    return any(
        phrase in normalized
        for phrase in (
            "vamos começar",
            "começar por",
            "comece por",
            "quero estudar",
            "vamos estudar",
            "quero aprender",
            "iniciar estudo",
            "começar a estudar",
        )
    )


def _resolve_study_topic(tracker: Tracker, tracer: CartographyKnowledgeTracer) -> Text | None:
    topic = (
        tracker.get_slot(SLOT_ACTIVE_STUDY_TOPIC)
        or _resolve_topic_from_tracker(tracker, tracer)
        or tracker.get_slot(SLOT_LAST_TOPIC)
    )
    if topic and topic in TOPICS:
        return topic
    return None


NAVIGATION_INTENTS = frozenset({
    "ask_cartography_help",
    "ask_what_to_do",
    "greet",
    "goodbye",
    "start_diagnostic",
})


def _clear_followup_slots() -> List[SlotSet]:
    return [
        SlotSet(SLOT_STUDY_FOLLOWUP_PENDING, False),
        SlotSet(SLOT_STUDY_FOLLOWUP_QUESTION, None),
    ]


def _get_active_followup(tracker: Tracker, topic: Text) -> Text | None:
    """Pergunta de fixação pendente — usa o texto salvo como fonte principal."""
    question = tracker.get_slot(SLOT_STUDY_FOLLOWUP_QUESTION)
    if question:
        return question
    if tracker.get_slot(SLOT_STUDY_FOLLOWUP_PENDING):
        teaching = TOPIC_TEACHING.get(topic, {})
        return teaching.get("follow_up") or TOPIC_FOLLOW_UPS.get(topic)
    return None


def _study_reflection_already_ran_after_last_user(tracker: Tracker) -> bool:
    """Evita segunda execução no mesmo turno (RulePolicy + TEDPolicy)."""
    for event in reversed(tracker.events):
        if event.get("event") == "user":
            break
        if (
            event.get("event") == "action"
            and event.get("name") == "action_handle_study_reflection"
        ):
            return True
    return False


def _followup_prompt_hint(topic: Text) -> Text:
    checks = TOPIC_TEACHING.get(topic, {}).get("follow_up_checks", ())
    if any(check.get("accept_keywords") for check in checks):
        return "Responda com uma palavra ou frase curta."
    return "Responda com o resultado (número + unidade, se souber)."


def _process_followup_response(
    events: List[Any],
    dispatcher: CollectingDispatcher,
    tracer: CartographyKnowledgeTracer,
    tracker: Tracker,
    topic: Text,
    user_text: Text,
    follow_up: Text,
) -> List[Any]:
    evaluation = _emit_followup_feedback(dispatcher, tracer, topic, user_text, follow_up)
    is_correct = evaluation.get("correct")
    if is_correct is True:
        tracer.update_from_interaction(topic=topic, correct=True)
    elif is_correct is False:
        tracer.update_from_interaction(topic=topic, correct=False)
    _emit_cognitive_payload(
        dispatcher,
        tracer,
        extra={
            "event": "study_followup",
            "topic": topic,
            "correct": is_correct,
            "quality": evaluation.get("quality"),
        },
    )
    followup_events = [
        _save_tracer(tracer),
        SlotSet(SLOT_LAST_TOPIC, topic),
        SlotSet(SLOT_PENDING_CORRECT, is_correct if is_correct is not None else None),
        SlotSet(SLOT_STUDY_FOLLOWUP_PENDING, is_correct is not True),
        SlotSet(
            SLOT_STUDY_FOLLOWUP_QUESTION,
            follow_up if is_correct is not True else None,
        ),
    ]
    return events + followup_events


class ActionGreet(Action):
    """Saudação com convite ao diagnóstico ou retomada conforme o estado."""

    def name(self) -> Text:
        return "action_greet"

    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> List[Any]:
        dispatcher.utter_message(response="utter_greet")

        if tracker.get_slot("diagnostic_completed"):
            tracer = _load_tracer(tracker)
            _emit_cognitive_payload(dispatcher, tracer)
            dispatcher.utter_message(
                text=(
                    "Bem-vindo de volta! Seu diagnóstico já foi concluído.\n\n"
                    "Diga **o que preciso fazer agora** para ver os próximos passos, "
                    "ou **quero estudar escala** (ou outro tema) para começar."
                )
            )
            return []

        dispatcher.utter_message(response="utter_ask_start_diagnostic")
        return [SlotSet(SLOT_DIAGNOSTIC_INVITATION_PENDING, True)]


class ActionSendCognitiveState(Action):
    """Envia o estado cognitivo atual para o frontend via JSON."""

    def name(self) -> Text:
        return "action_send_cognitive_state"

    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> List[Any]:
        tracer = _load_tracer(tracker)
        _emit_cognitive_payload(dispatcher, tracer)
        return []


class ActionUpdateMastery(Action):
    """
    Recebe acerto/erro (via slots ou entidades), atualiza a Rede Bayesiana
    e retorna o payload JSON com mastery atualizado.
    """

    def name(self) -> Text:
        return "action_update_mastery"

    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> List[Any]:
        tracer = _load_tracer(tracker)

        topic = tracker.get_slot(SLOT_LAST_TOPIC) or tracker.get_slot("topic")
        if not topic and tracker.latest_message.get("entities"):
            for ent in tracker.latest_message["entities"]:
                if ent.get("entity") == "topic":
                    topic = ent.get("value")
                    break

        intent = tracker.latest_message.get("intent", {}).get("name", "")
        penalty_only = intent == "inform_wrong_scale_calculation"

        correct_slot = tracker.get_slot(SLOT_PENDING_CORRECT)
        if correct_slot is not None:
            correct = str(correct_slot).lower() in ("true", "1", "sim", "yes", "correct")
        else:
            correct = intent in (
                "affirm",
                "inform_correct_answer",
                "diagnostic_answer",
            ) and not penalty_only

        response_time = tracker.get_slot("response_time_sec")
        try:
            response_time_f = float(response_time) if response_time else None
        except (TypeError, ValueError):
            response_time_f = None

        if topic and topic in TOPICS:
            tracer.update_from_interaction(
                topic=topic,
                correct=correct,
                response_time_sec=response_time_f,
                penalty_only=penalty_only,
            )
        elif penalty_only:
            tracer.update_from_interaction(
                topic="calculo_escala",
                correct=False,
                penalty_only=True,
            )

        _emit_cognitive_payload(
            dispatcher,
            tracer,
            extra={
                "event": "mastery_updated",
                "topic": topic or tracer.focused_topic,
                "correct": correct if not penalty_only else False,
            },
        )

        events: List[Any] = [
            _save_tracer(tracer),
            SlotSet(SLOT_PENDING_CORRECT, None),
        ]
        if tracker.get_slot(SLOT_SCALE_REFLECTION_PENDING):
            events.append(SlotSet(SLOT_SCALE_REFLECTION_PENDING, False))
        return events


class ActionAskDiagnosticAnswer(Action):
    """Emite a pergunta diagnóstica ao solicitar o slot diagnostic_answer (convenção Rasa)."""

    def name(self) -> Text:
        return "action_ask_diagnostic_answer"

    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> List[Any]:
        index = tracker.get_slot(SLOT_DIAGNOSTIC_INDEX)
        index = int(index) if index is not None else 0

        events: List[Any] = []
        if tracker.get_slot(SLOT_DIAGNOSTIC_INVITATION_PENDING):
            events.append(SlotSet(SLOT_DIAGNOSTIC_INVITATION_PENDING, False))

        if index >= len(DIAGNOSTIC_QUESTIONS):
            dispatcher.utter_message(response="utter_diagnostic_complete")
            return events

        options, layout = _diagnostic_options_for_index(tracker, index)
        topic = _emit_diagnostic_question(dispatcher, index, options)
        return events + [
            SlotSet(SLOT_LAST_TOPIC, topic),
            SlotSet(SLOT_DIAGNOSTIC_LAYOUT, json.dumps(layout)),
        ]


class ActionStartDiagnostic(Action):
    """Ativa o formulário diagnóstico (a pergunta é emitida por action_ask_diagnostic_answer)."""

    def name(self) -> Text:
        return "action_start_diagnostic"

    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> List[Any]:
        if tracker.get_slot("diagnostic_completed"):
            dispatcher.utter_message(
                text=(
                    "Você já concluiu o questionário diagnóstico. "
                    "Diga **quero estudar** + um tema para continuar."
                )
            )
            return [ActiveLoop(None)]

        return [
            SlotSet(SLOT_DIAGNOSTIC_INVITATION_PENDING, False),
            SlotSet(SLOT_DIAGNOSTIC_INDEX, 0),
            SlotSet("diagnostic_answers", "[]"),
            SlotSet(SLOT_DIAGNOSTIC_LAYOUT, "{}"),
            ActiveLoop("diagnostic_form"),
        ]


class ActionCalibrateFromDiagnostic(Action):
    """Calibra a Rede Bayesiana após as 10 respostas do cold start."""

    def name(self) -> Text:
        return "action_calibrate_from_diagnostic"

    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> List[Any]:
        tracer = _load_tracer(tracker)
        answers_raw = tracker.get_slot("diagnostic_answers") or "[]"

        try:
            answers = json.loads(answers_raw) if isinstance(answers_raw, str) else answers_raw
        except json.JSONDecodeError:
            answers = []

        bool_answers = [bool(a) for a in answers]
        tracer.calibrate_from_diagnostic(bool_answers)

        _emit_cognitive_payload(
            dispatcher,
            tracer,
            extra={"event": "diagnostic_calibrated", "answers_count": len(bool_answers)},
        )

        dispatcher.utter_message(response="utter_diagnostic_complete")

        return [
            _save_tracer(tracer),
            SlotSet("diagnostic_completed", True),
            SlotSet(SLOT_DIAGNOSTIC_INDEX, len(DIAGNOSTIC_QUESTIONS)),
        ]


class ValidateDiagnosticForm(FormValidationAction):
    """Valida respostas do formulário diagnóstico e acumula acertos."""

    def name(self) -> Text:
        return "validate_diagnostic_form"

    def validate_diagnostic_answer(
        self,
        slot_value: Any,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> Dict[Text, Any]:
        if tracker.get_slot("diagnostic_completed"):
            dispatcher.utter_message(
                text=(
                    "Você já concluiu o questionário diagnóstico. "
                    "Para estudar um tema, diga por exemplo: **quero estudar orientação**."
                )
            )
            return {"diagnostic_answer": None}

        intent = tracker.latest_message.get("intent", {}).get("name", "")

        index = tracker.get_slot(SLOT_DIAGNOSTIC_INDEX)
        index = int(index) if index is not None else 0
        slot_text = slot_value if slot_value is not None else ""

        if index >= len(DIAGNOSTIC_QUESTIONS):
            return {"diagnostic_answer": slot_value}

        options, layout = _diagnostic_options_for_index(tracker, index)

        if intent in (
            "ask_what_to_do",
            "choose_topic",
            "greet",
            "goodbye",
            "start_diagnostic",
        ) and not _matches_diagnostic_answer(slot_text, index, options):
            dispatcher.utter_message(
                text=(
                    "Estamos no questionário diagnóstico — responda à pergunta acima "
                    "escolhendo uma das opções ou digitando a resposta."
                )
            )
            return {"diagnostic_answer": None, SLOT_DIAGNOSTIC_LAYOUT: json.dumps(layout)}

        # "sim" / start_diagnostic ativam o form — não são respostas à pergunta 1.
        if tracker.get_slot(SLOT_DIAGNOSTIC_INVITATION_PENDING) or intent in (
            "affirm",
            "start_diagnostic",
        ):
            return {
                SLOT_DIAGNOSTIC_INVITATION_PENDING: False,
                "diagnostic_answer": None,
                SLOT_DIAGNOSTIC_LAYOUT: json.dumps(layout),
            }

        is_correct = _is_diagnostic_correct(slot_value, index, options)

        answers_raw = tracker.get_slot("diagnostic_answers") or "[]"
        try:
            answers = json.loads(answers_raw)
        except json.JSONDecodeError:
            answers = []
        answers.append(is_correct)
        next_index = index + 1

        dispatcher.utter_message(
            text="Ótimo!" if is_correct else "Vamos registrar isso para personalizar seu estudo."
        )

        result: Dict[Text, Any] = {
            "diagnostic_answers": json.dumps(answers),
            SLOT_DIAGNOSTIC_INDEX: next_index,
            SLOT_PENDING_CORRECT: is_correct,
            SLOT_DIAGNOSTIC_LAYOUT: json.dumps(layout),
        }

        if next_index < len(DIAGNOSTIC_QUESTIONS):
            result["diagnostic_answer"] = None
            if next_index < len(DIAGNOSTIC_QUESTION_TOPICS):
                result[SLOT_LAST_TOPIC] = DIAGNOSTIC_QUESTION_TOPICS[next_index]
        else:
            result["diagnostic_answer"] = slot_value

        return result


class ActionReflectiveScalePrompt(Action):
    """Academically Productive Talk: pergunta reflexiva sobre escala."""

    def name(self) -> Text:
        return "action_reflective_scale_prompt"

    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> List[Any]:
        dispatcher.utter_message(response="utter_reflective_scale_question")
        return [
            SlotSet(SLOT_LAST_TOPIC, "calculo_escala"),
            SlotSet(SLOT_PENDING_CORRECT, False),
        ]


class ActionScaleHintAfterReflection(Action):
    """Dica reflexiva de escala e marca contexto para confirmação do aluno."""

    def name(self) -> Text:
        return "action_scale_hint_after_reflection"

    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> List[Any]:
        dispatcher.utter_message(response="utter_scale_hint_after_reflection")
        return [SlotSet(SLOT_SCALE_REFLECTION_PENDING, True)]


class ActionSuggestNextSteps(Action):
    """Após o diagnóstico, apresenta menu de tópicos e sugere por onde começar."""

    def name(self) -> Text:
        return "action_suggest_next_steps"

    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> List[Any]:
        tracer = _load_tracer(tracker)
        focused = tracer.focused_topic
        focused_label = TOPIC_LABELS.get(focused, focused)

        _emit_cognitive_payload(
            dispatcher,
            tracer,
            extra={"event": "study_menu", "recommendedTopic": focused},
        )

        dispatcher.utter_message(
            text=(
                "Com base no diagnóstico, estes são seus tópicos e domínio estimado:\n\n"
                f"{_format_topic_menu(tracer)}\n\n"
                f"Recomendo começar por **{focused_label}**.\n\n"
                "Para continuar, você pode:\n"
                f"• Dizer **sim** ou **começar pelo tema recomendado**\n"
                f"• Dizer **quero estudar {focused_label}** ou outro tema da lista\n"
                "• Perguntar **o que preciso fazer agora** se ainda tiver dúvidas"
            )
        )

        return [
            SlotSet(SLOT_STUDY_SUGGESTION_PENDING, True),
            SlotSet("diagnostic_completed", True),
            ActiveLoop(None),
        ]


class ActionHandleFallback(Action):
    """Encaminha fallback para estudo/fixação em vez de resposta genérica."""

    def name(self) -> Text:
        return "action_handle_fallback"

    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> List[Any]:
        if (
            tracker.get_slot(SLOT_STUDY_FOLLOWUP_PENDING)
            or tracker.get_slot(SLOT_STUDY_FOLLOWUP_QUESTION)
            or tracker.get_slot(SLOT_ACTIVE_STUDY_TOPIC)
        ):
            return ActionHandleStudyReflection().run(dispatcher, tracker, domain)

        if tracker.get_slot("diagnostic_completed"):
            return ActionExplainWhatToDo().run(dispatcher, tracker, domain)

        dispatcher.utter_message(response="utter_default")
        return []


class ActionExplainWhatToDo(Action):
    """Explica como usar o tutor após o diagnóstico (dúvidas de navegação)."""

    def name(self) -> Text:
        return "action_explain_what_to_do"

    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> List[Any]:
        if (
            tracker.get_slot(SLOT_ACTIVE_STUDY_TOPIC)
            or tracker.get_slot(SLOT_STUDY_FOLLOWUP_PENDING)
            or tracker.get_slot(SLOT_STUDY_FOLLOWUP_QUESTION)
        ):
            return ActionHandleStudyReflection().run(dispatcher, tracker, domain)

        tracer = _load_tracer(tracker)
        user_text = (tracker.latest_message.get("text") or "").strip()
        resolved = _resolve_topic_from_tracker(tracker, tracer)
        if resolved and _wants_to_start_study(user_text):
            return ActionStartTopicStudy().run(dispatcher, tracker, domain)
        if resolved:
            return ActionHandleStudyReflection().run(dispatcher, tracker, domain)

        if not tracker.get_slot("diagnostic_completed"):
            dispatcher.utter_message(
                text=(
                    "Ainda não fizemos o diagnóstico inicial.\n\n"
                    "O primeiro passo é um questionário rápido de **10 perguntas** "
                    "para calibrar seu perfil. Posso iniciar?"
                )
            )
            return [SlotSet(SLOT_DIAGNOSTIC_INVITATION_PENDING, True)]

        focused_label = TOPIC_LABELS.get(tracer.focused_topic, tracer.focused_topic)

        dispatcher.utter_message(
            text=(
                "Sem problema — vou explicar!\n\n"
                "1. Você já fez o **questionário diagnóstico** de 10 perguntas.\n"
                "2. Calibrei seu **perfil de domínio** (veja as porcentagens no painel).\n"
                "3. Agora o tutor guia seu estudo **por tópicos**, com perguntas reflexivas "
                "(não entrego a resposta pronta de imediato).\n\n"
                f"**Próximo passo sugerido:** estudar **{focused_label}**.\n\n"
                "Diga **sim** para começar por esse tema, ou **quero estudar** + nome do tema. "
                "Se tiver dúvida sobre um conceito, pergunte por exemplo: "
                "*não entendi escala gráfica*."
            )
        )

        _emit_cognitive_payload(dispatcher, tracer, extra={"event": "navigation_help"})
        return [SlotSet(SLOT_STUDY_SUGGESTION_PENDING, True)]


class ActionStartTopicStudy(Action):
    """Inicia estudo reflexivo de um tópico escolhido ou recomendado."""

    def name(self) -> Text:
        return "action_start_topic_study"

    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> List[Any]:
        if tracker.get_slot(SLOT_STUDY_FOLLOWUP_QUESTION) or tracker.get_slot(
            SLOT_STUDY_FOLLOWUP_PENDING
        ):
            user_text = (tracker.latest_message.get("text") or "").strip()
            if not _wants_to_start_study(user_text):
                return ActionHandleStudyReflection().run(dispatcher, tracker, domain)

        if not tracker.get_slot("diagnostic_completed"):
            dispatcher.utter_message(
                text=(
                    "Primeiro vamos concluir o **questionário diagnóstico** (10 perguntas). "
                    "Diga **sim** se ainda não começamos, ou **quero fazer o diagnóstico**."
                )
            )
            return []

        tracer = _load_tracer(tracker)
        topic = _resolve_topic_from_tracker(tracker, tracer)

        if not topic:
            intent = tracker.latest_message.get("intent", {}).get("name", "")
            if intent == "affirm" or tracker.get_slot(SLOT_STUDY_SUGGESTION_PENDING):
                topic = tracer.focused_topic

        if not topic or topic not in TOPICS:
            dispatcher.utter_message(
                text=(
                    "Não identifiquei o tema. Escolha um destes, por exemplo:\n"
                    "• quero estudar escala gráfica\n"
                    "• vamos para coordenadas\n"
                    "• começar pelo tema recomendado"
                )
            )
            return []

        tracer.set_focus(topic)
        _emit_study_lesson(dispatcher, tracer, topic)

        events = [
            _save_tracer(tracer),
            SlotSet(SLOT_LAST_TOPIC, topic),
            SlotSet(SLOT_ACTIVE_STUDY_TOPIC, topic),
            SlotSet(SLOT_STUDY_SUGGESTION_PENDING, False),
            SlotSet(SLOT_STUDY_FOLLOWUP_PENDING, False),
            SlotSet(SLOT_STUDY_FOLLOWUP_QUESTION, None),
            ActiveLoop(None),
        ]
        return events


class ActionTopicHelp(Action):
    """Ajuda contextual sobre um tópico durante o estudo (APT)."""

    def name(self) -> Text:
        return "action_topic_help"

    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> List[Any]:
        user_text = (tracker.latest_message.get("text") or "").strip()
        if _wants_to_start_study(user_text):
            return ActionStartTopicStudy().run(dispatcher, tracker, domain)

        tracer = _load_tracer(tracker)
        topic = (
            _resolve_topic_from_tracker(tracker, tracer)
            or tracker.get_slot(SLOT_ACTIVE_STUDY_TOPIC)
            or tracer.focused_topic
        )

        if topic not in TOPIC_LESSONS:
            dispatcher.utter_message(
                text="Sobre qual tema você quer ajuda? Por exemplo: escala, coordenadas ou legenda."
            )
            return []

        lesson = TOPIC_LESSONS[topic]
        label = TOPIC_LABELS.get(topic, topic)

        dispatcher.utter_message(
            text=(
                f"Sobre **{label}**: {lesson['intro']}\n\n"
                f"Em vez de dar a resposta direta, pense nesta pergunta: {lesson['prompt']}"
            )
        )

        return [
            SlotSet(SLOT_LAST_TOPIC, topic),
            SlotSet(SLOT_ACTIVE_STUDY_TOPIC, topic),
            SlotSet(SLOT_STUDY_FOLLOWUP_PENDING, False),
            SlotSet(SLOT_STUDY_FOLLOWUP_QUESTION, None),
        ]


class ActionHandleStudyReflection(Action):
    """APT: acolhe a opinião do aluno e aprofunda com explicação didática."""

    def name(self) -> Text:
        return "action_handle_study_reflection"

    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> List[Any]:
        events = _close_stale_diagnostic_loop(tracker)
        if _study_reflection_already_ran_after_last_user(tracker):
            return events

        tracer = _load_tracer(tracker)
        topic = _resolve_study_topic(tracker, tracer)
        if not topic:
            dispatcher.utter_message(
                text="Não identifiquei em qual tema estamos. Diga **quero estudar** + o tema."
            )
            return events

        if not tracker.get_slot(SLOT_ACTIVE_STUDY_TOPIC):
            events.append(SlotSet(SLOT_ACTIVE_STUDY_TOPIC, topic))

        intent = tracker.latest_message.get("intent", {}).get("name", "")
        user_text = (tracker.latest_message.get("text") or "").strip()
        label = TOPIC_LABELS.get(topic, topic)

        follow_up_q = _get_active_followup(tracker, topic)
        explicit_topic_change = _wants_to_start_study(user_text)

        if follow_up_q:
            if intent == "ask_cartography_help":
                return events + _clear_followup_slots() + ActionTopicHelp().run(
                    dispatcher, tracker, domain
                )
            if intent == "choose_topic" and explicit_topic_change:
                return events + _clear_followup_slots() + ActionStartTopicStudy().run(
                    dispatcher, tracker, domain
                )
            if intent in NAVIGATION_INTENTS or intent == "ask_what_to_do":
                return events + _clear_followup_slots() + ActionExplainWhatToDo().run(
                    dispatcher, tracker, domain
                )
            return _process_followup_response(
                events, dispatcher, tracer, tracker, topic, user_text, follow_up_q
            )

        if intent in ("affirm", "inform_correct_answer"):
            tracer.update_from_interaction(topic=topic, correct=True)
            mastery_pct = tracer.get_mastery().get(topic, 0.0)
            dispatcher.utter_message(
                text=(
                    f"Ótimo! Seu raciocínio em **{label}** está evoluindo "
                    f"(domínio estimado: {mastery_pct:.0f}%).\n\n"
                    "Quer **aprofundar neste tema** com outra reflexão, ou "
                    "**estudar outro tópico**? Diga por exemplo: "
                    "*quero estudar coordenadas*."
                )
            )
            _emit_cognitive_payload(
                dispatcher,
                tracer,
                extra={"event": "study_progress", "topic": topic, "correct": True},
            )
            return events + [
                _save_tracer(tracer),
                SlotSet(SLOT_LAST_TOPIC, topic),
                SlotSet(SLOT_PENDING_CORRECT, None),
            ] + _clear_followup_slots()

        if intent == "deny":
            mentioned = _resolve_topic_from_tracker(tracker, tracer)
            if mentioned and mentioned in TOPIC_LESSONS and mentioned != topic:
                return ActionTopicHelp().run(dispatcher, tracker, domain)

            if _is_uncertainty_message(user_text):
                deepening = _emit_study_deepening(
                    dispatcher, tracer, topic, user_text, needs_help=True
                )
                quality = deepening["quality"]
                tracer.update_from_interaction(topic=topic, correct=False)
                _emit_cognitive_payload(
                    dispatcher,
                    tracer,
                    extra={
                        "event": "study_explanation",
                        "topic": topic,
                        "quality": quality,
                    },
                )
                follow_up = deepening.get("follow_up")
                return events + [
                    _save_tracer(tracer),
                    SlotSet(SLOT_LAST_TOPIC, topic),
                    SlotSet(SLOT_PENDING_CORRECT, None),
                    SlotSet(SLOT_STUDY_FOLLOWUP_PENDING, bool(follow_up)),
                    SlotSet(SLOT_STUDY_FOLLOWUP_QUESTION, follow_up),
                ]

            lesson = TOPIC_LESSONS.get(topic, {})
            dispatcher.utter_message(
                text=(
                    f"Sem problema — em **{label}**, vamos por partes.\n\n"
                    f"{lesson.get('intro', '')}\n\n"
                    f"Pense neste ângulo: {lesson.get('prompt', '')}\n\n"
                    "Tente responder com suas palavras; não precisa ser perfeito."
                )
            )
            return events + [SlotSet(SLOT_LAST_TOPIC, topic)]

        deepening = _emit_study_deepening(dispatcher, tracer, topic, user_text)
        quality = deepening["quality"]
        follow_up = deepening.get("follow_up")
        learned_well = quality in ("strong", "partial")
        tracer.update_from_interaction(topic=topic, correct=learned_well)
        _emit_cognitive_payload(
            dispatcher,
            tracer,
            extra={
                "event": "study_explanation",
                "topic": topic,
                "quality": quality,
                "correct": learned_well,
            },
        )

        return events + [
            _save_tracer(tracer),
            SlotSet(SLOT_LAST_TOPIC, topic),
            SlotSet(SLOT_PENDING_CORRECT, learned_well),
            SlotSet(SLOT_STUDY_FOLLOWUP_PENDING, bool(follow_up)),
            SlotSet(SLOT_STUDY_FOLLOWUP_QUESTION, follow_up),
        ]
