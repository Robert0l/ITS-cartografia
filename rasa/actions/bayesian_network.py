"""Motor cognitivo: Rede Bayesiana de domínio em Cartografia."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from pgmpy.factors.discrete import TabularCPD
from pgmpy.inference import VariableElimination
from pgmpy.models import DiscreteBayesianNetwork

# Nós alinhados ao cap. 5 — Cartografia (Terra, Araújo e Guimarães, 2015)
TOPICS: List[str] = [
    "introducao",
    "coordenadas_geograficas",
    "elementos_mapa",
    "escala_grafica",
    "escala_numerica",
    "calculo_escala",
    "projecoes",
    "orientacao",
    "interpretacao_mapa",
]

# DAG: conceitos fundamentais alimentam tópicos derivados
EDGES = [
    ("introducao", "coordenadas_geograficas"),
    ("introducao", "elementos_mapa"),
    ("introducao", "escala_grafica"),
    ("escala_grafica", "escala_numerica"),
    ("escala_numerica", "calculo_escala"),
    ("coordenadas_geograficas", "projecoes"),
    ("elementos_mapa", "orientacao"),
    ("projecoes", "interpretacao_mapa"),
    ("orientacao", "interpretacao_mapa"),
    ("calculo_escala", "interpretacao_mapa"),
]

TOPIC_LABELS: Dict[str, str] = {
    "introducao": "Introdução à Cartografia",
    "coordenadas_geograficas": "Coordenadas Geográficas",
    "elementos_mapa": "Elementos do Mapa",
    "escala_grafica": "Escala Gráfica",
    "escala_numerica": "Escala Numérica",
    "calculo_escala": "Cálculo de Escala",
    "projecoes": "Projeções Cartográficas",
    "orientacao": "Orientação e Rosa dos Ventos",
    "interpretacao_mapa": "Interpretação de Mapas",
}

# Mapeamento das 10 perguntas do cold start para tópicos
DIAGNOSTIC_QUESTION_TOPICS: List[str] = [
    "introducao",
    "introducao",
    "coordenadas_geograficas",
    "coordenadas_geograficas",
    "elementos_mapa",
    "escala_grafica",
    "escala_numerica",
    "calculo_escala",
    "projecoes",
    "interpretacao_mapa",
]


def _cpd_prior(topic: str, p_mastered: float = 0.35) -> TabularCPD:
    """CPD para nó raiz (sem pais): estados 0=não domina, 1=domina."""
    p_not = 1.0 - p_mastered
    return TabularCPD(
        variable=topic,
        variable_card=2,
        values=[[p_not], [p_mastered]],
    )


def _cpd_with_parent(topic: str, parent: str, parent_strength: float = 0.75) -> TabularCPD:
    """
    P(filho | pai): se pai domina (1), alta chance do filho dominar;
    se pai não domina (0), chance reduzida.
    """
    # P(filho=0 | pai=0), P(filho=0 | pai=1)
    # P(filho=1 | pai=0), P(filho=1 | pai=1)
    p_not_given_not = 0.75
    p_not_given_yes = 1.0 - parent_strength
    return TabularCPD(
        variable=topic,
        variable_card=2,
        values=[
            [p_not_given_not, p_not_given_yes],
            [1.0 - p_not_given_not, parent_strength],
        ],
        evidence=[parent],
        evidence_card=[2],
    )


def _cpd_multi_parent(topic: str, parents: List[str]) -> TabularCPD:
    """CPD para nó com vários pais: mais pais dominados → maior P(dominar)."""
    n_combos = 2 ** len(parents)
    p_not_row: List[float] = []
    for combo in range(n_combos):
        mastered_parents = sum((combo >> i) & 1 for i in range(len(parents)))
        ratio = mastered_parents / len(parents)
        p_not_row.append(round(0.85 - 0.55 * ratio, 2))

    p_yes_row = [round(1.0 - p, 2) for p in p_not_row]
    return TabularCPD(
        variable=topic,
        variable_card=2,
        values=[p_not_row, p_yes_row],
        evidence=parents,
        evidence_card=[2] * len(parents),
    )


def build_cartography_dag() -> DiscreteBayesianNetwork:
    """Monta o DAG de Cartografia com CPTs condicionais."""
    model = DiscreteBayesianNetwork(EDGES)
    cpds: List[TabularCPD] = []

    parents_map: Dict[str, List[str]] = {t: [] for t in TOPICS}
    for parent, child in EDGES:
        parents_map[child].append(parent)

    for topic in TOPICS:
        parents = parents_map[topic]
        if not parents:
            cpds.append(_cpd_prior(topic))
        elif len(parents) == 1:
            cpds.append(_cpd_with_parent(topic, parents[0], parent_strength=0.72))
        else:
            cpds.append(_cpd_multi_parent(topic, parents))

    model.add_cpds(*cpds)
    assert model.check_model(), "CPTs inconsistentes no DAG de Cartografia"
    return model


@dataclass
class CartographyKnowledgeTracer:
    """Rastreador de domínio baseado em inferência bayesiana."""

    model: DiscreteBayesianNetwork = field(default_factory=build_cartography_dag)
    focused_topic: str = "introducao"
    _evidence: Dict[str, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self._infer = VariableElimination(self.model)

    def get_mastery(self) -> Dict[str, float]:
        """Retorna porcentagens de domínio (0–100) para cada conceito."""
        mastery: Dict[str, float] = {}
        for topic in TOPICS:
            if topic in self._evidence:
                mastery[topic] = float(self._evidence[topic]) * 100.0
            else:
                result = self._infer.query(
                    variables=[topic],
                    evidence=self._evidence,
                )
                prob_mastered = float(result.values[1])
                mastery[topic] = round(prob_mastered * 100.0, 1)
        return mastery

    def get_payload(self) -> dict:
        return {
            "mastery": self.get_mastery(),
            "focusedTopic": self.focused_topic,
            "topicLabels": TOPIC_LABELS,
        }

    def set_focus(self, topic: str) -> None:
        if topic in TOPICS:
            self.focused_topic = topic

    def apply_evidence(self, topic: str, mastered: bool) -> None:
        if topic in TOPICS:
            self._evidence[topic] = 1 if mastered else 0

    def update_from_interaction(
        self,
        topic: str,
        correct: bool,
        response_time_sec: Optional[float] = None,
        penalty_only: bool = False,
    ) -> Dict[str, float]:
        """
        Atualiza crenças após uma interação.

        penalty_only: usado em APT quando o aluno erra — penaliza levemente
        sem marcar evidência dura de 'não domina'.
        """
        if topic not in TOPICS:
            return self.get_mastery()

        self.set_focus(topic)

        if penalty_only and not correct:
            current = self.get_mastery().get(topic, 50.0) / 100.0
            adjusted = max(0.05, current - 0.08)
            self._evidence[topic] = 1 if adjusted >= 0.5 else 0
            return self.get_mastery()

        if response_time_sec is not None and response_time_sec > 120:
            correct = False

        self.apply_evidence(topic, mastered=correct)
        return self.get_mastery()

    def calibrate_from_diagnostic(self, answers: List[bool]) -> Dict[str, float]:
        """Calibra probabilidades iniciais a partir do questionário de 10 itens."""
        topic_results: Dict[str, List[bool]] = {t: [] for t in TOPICS}

        for idx, correct in enumerate(answers[:10]):
            topic = DIAGNOSTIC_QUESTION_TOPICS[idx]
            topic_results[topic].append(correct)

        for topic, results in topic_results.items():
            if results:
                mastered_ratio = sum(results) / len(results)
                self._evidence[topic] = 1 if mastered_ratio >= 0.5 else 0

        if not any(self._evidence.values()):
            weakest = min(TOPICS, key=lambda t: self.get_mastery()[t])
            self.set_focus(weakest)
        else:
            mastery = self.get_mastery()
            self.set_focus(min(mastery, key=mastery.get))

        return self.get_mastery()

    def to_dict(self) -> dict:
        return {
            "evidence": self._evidence.copy(),
            "focused_topic": self.focused_topic,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "CartographyKnowledgeTracer":
        tracer = cls()
        tracer._evidence = {k: int(v) for k, v in data.get("evidence", {}).items()}
        tracer.focused_topic = data.get("focused_topic", "introducao")
        return tracer
