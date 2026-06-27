"""Dados fixos para testes E2E — espelham rasa/actions/actions.py."""

DIAGNOSTIC_CORRECT_ANSWERS = [
    "Representação reduzida e simplificada da superfície terrestre",
    "Representar e comunicar fenômenos espaciais",
    "Sistema de localização por latitude e longitude",
    "Equador",
    "Legenda",
    "Segmento de reta que relaciona distâncias no mapa e na realidade",
    "500 metros",
    "1:500.000",
    "Representar a superfície curva da Terra em um plano",
    "Inclinação do relevo",
]

# Estudo ativo → pergunta sobre outro tópico (ajuda contextual APT)
CROSS_TOPIC_HELP_CASES = [
    {
        "name": "Coordenadas ativo -> duvida sobre escala grafica",
        "study_message": "quero estudar coordenadas",
        "study_topic": "coordenadas_geograficas",
        "reflection": "a latitude mede a distância do equador",
        "help_message": "tenho dúvida sobre escala gráfica",
        "expected_labels": ("Escala Gráfica", "escala gráfica"),
    },
    {
        "name": "Escala grafica ativo -> duvida sobre projecoes",
        "study_message": "quero estudar escala gráfica",
        "study_topic": "escala_grafica",
        "reflection": "usaria um segmento de reta para mostrar a relação",
        "help_message": "tenho dúvida sobre projeções cartográficas",
        "expected_labels": ("Projeções", "projeções"),
    },
    {
        "name": "Elementos do mapa ativo -> duvida sobre coordenadas",
        "study_message": "quero estudar elementos do mapa",
        "study_topic": "elementos_mapa",
        "reflection": "a legenda ajuda a entender os símbolos do mapa",
        "help_message": "tenho dúvida sobre coordenadas geográficas",
        "expected_labels": ("Coordenadas Geográficas", "coordenadas"),
    },
    {
        "name": "Projecoes ativo -> duvida sobre interpretacao de mapas",
        "study_message": "quero estudar projeções",
        "study_topic": "projecoes",
        "reflection": "penso que não dá representar a Terra sem distorcer",
        "help_message": "tenho dúvida sobre interpretação de mapas",
        "expected_labels": ("Interpretação de Mapas", "interpretação"),
    },
]
