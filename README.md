# Backend ITS — Cartografia (Rasa + Redes Bayesianas)

Sistema Tutor Inteligente para ensino de Cartografia, baseado no capítulo 5 de *Conexões: Estudos de Geografia Geral e do Brasil* (Terra, Araújo e Guimarães, 2015).

**Documentação completa do projeto** (domínio, grafo, modelo do aluno, inspirações teóricas e guia de instalação no Windows): [DOCUMENTACAO.md](DOCUMENTACAO.md)

## Arquitetura

```
┌─────────────┐     REST API      ┌──────────────┐     webhook     ┌─────────────────┐
│  Frontend   │ ◄──────────────► │  Rasa Server │ ◄──────────────► │  Action Server  │
│  (React)    │   :5005/webhooks │   (NLU+Core) │                  │  (pgmpy + SDK)  │
└─────────────┘   /rest/webhook  └──────────────┘                  └─────────────────┘
```

## Pré-requisitos

- Docker e Docker Compose
- ~4 GB RAM livres (treino do modelo)

## Início rápido

```bash
# 1. Treinar o modelo NLU/Core
docker compose --profile train run --rm rasa-train

# 2. Subir serviços
docker compose up --build

# 3. Testar via REST API
curl -X POST http://localhost:5005/webhooks/rest/webhook \
  -H "Content-Type: application/json" \
  -d '{"sender": "aluno1", "message": "olá"}'
```

## Payload cognitivo (frontend)

Toda atualização de domínio retorna JSON via `json_message`:

```json
{
  "cognitive_state": {
    "mastery": {
      "introducao": 72.5,
      "coordenadas_geograficas": 45.0,
      "escala_grafica": 38.2,
      "calculo_escala": 25.0
    },
    "focusedTopic": "calculo_escala",
    "topicLabels": { "calculo_escala": "Cálculo de Escala" },
    "event": "mastery_updated"
  }
}
```

## Estrutura do projeto

| Caminho | Descrição |
|---------|-----------|
| `docker-compose.yml` | Orquestra Rasa + Action Server |
| `Dockerfile.action-server` | Imagem Python com rasa-sdk e pgmpy |
| `rasa/config.yml` | Pipeline NLU e políticas de diálogo |
| `rasa/endpoints.yml` | URL do Action Server |
| `rasa/credentials.yml` | Canal REST habilitado |
| `rasa/actions/bayesian_network.py` | DAG e inferência bayesiana |
| `rasa/actions/actions.py` | Custom Actions (mastery, diagnóstico, APT) |
| `rasa/data/` | NLU, stories e rules |

## Fluxos principais

1. **Cold start:** Form `diagnostic_form` aplica 10 perguntas → `action_calibrate_from_diagnostic` calibra a rede.
2. **APT (Escala):** Intent `inform_wrong_scale_calculation` → pergunta reflexiva → penalidade leve em `calculo_escala`.
3. **Acerto:** Intent `inform_correct_answer` → evidência positiva no tópico → payload `mastery` atualizado.

## Testes automatizados

### Pré-requisito

Rasa e Action Server rodando (`docker compose up -d`).

### E2E via REST (recomendado para validar continuação)

Script com relatório legível no terminal:

```powershell
cd D:\ITS
python tests/run_continuation_e2e.py
```

Com pytest (opcional):

```powershell
pip install -r tests/requirements.txt
pytest tests/test_continuation_e2e.py -v
```

O que é validado:

| Fase | Cenário |
|------|---------|
| 1 | Saudação → diagnóstico → 10 perguntas com avanço correto |
| 2 | Menu pós-diagnóstico, `o que preciso fazer agora`, `sim` → lição `study` |
| 3 | Escolher tópico, ajuda contextual, dúvida **durante** o diagnóstico |

Cada execução usa um `sender` único (não reutilize `aluno1` nos testes).

### Testes de diálogo Rasa (rules/policies)

```powershell
docker compose --profile test run --rm rasa-test
```

## Desenvolvimento local (Action Server)

```bash
cd rasa/actions
pip install -r requirements.txt
python -m rasa_sdk --actions actions --port 5055
```
