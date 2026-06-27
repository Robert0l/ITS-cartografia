# Prompt: Desenvolvimento do Backend ITS (Rasa + Redes Bayesianas)

**Atue como um Engenheiro de Software Full-Stack especialista em IA Educacional, Arquitetura de Chatbots e Modelagem Probabilística (Redes Bayesianas/Python).**

Seu objetivo é construir e configurar do zero o backend de um Sistema Tutor Inteligente (ITS) utilizando o Rasa Open Source (https://github.com/RasaHQ/rasa). O sistema ensinará Cartografia e já deve ser construído com rotas e troca de payloads preparadas para integração futura com um frontend visual em React.

## 1. Inspiração Teórica e Escopo de Domínio
* **Base Didática:** O progresso segue o capítulo 5 da obra "Conexões: Estudos de Geografia Geral e do Brasil" (Terra, Araújo e Guimarães, 2015).
* **Agente Conversacional:** O chatbot usará *Academically Productive Talk*, engajando o aluno em reflexões para chegar à resposta, sem entregá-la de imediato.

## 2. Motor Cognitivo e Rastreamento (Knowledge Tracing)
* **Cold Start:** O fluxo inicial deve aplicar um questionário diagnóstico de 10 perguntas.
* **Rede Bayesiana:** O rastreamento contínuo utiliza um Grafo Direcionado Acíclico (DAG). Nós incluem: Introdução, Coordenadas Geográficas, Escala (Gráfica/Numérica), Projeções, etc.
* **Atualização (CPT):** As interações (acertos, erros, tempo) atualizam a probabilidade de domínio na Rede Bayesiana.

## 3. Stack Tecnológica e Integração (Future-Proofing)
* **Framework Core:** Rasa Open Source. É mandatório o uso da REST API (`rest` channel em `credentials.yml`).
* **Backend (Action Server):** Python com `pgmpy` (ou similar) para gerenciar o DAG.
* **Infraestrutura:** Docker e Docker Compose para orquestrar os serviços.
* **Comunicação Frontend-Backend:** O Action Server precisa devolver o estado cognitivo em formato JSON usando `dispatcher.utter_message(json_message=...)`. O payload deve conter o objeto `mastery` (dicionário com as porcentagens de domínio de cada conceito) e o `focusedTopic` para alimentar o futuro frontend visual.

## 4. Entregáveis Esperados
Forneça o código e a explicação divididos nestas 4 etapas lógicas:

**1. Configuração e Ambiente (Rasa + Docker):**
* Um `docker-compose.yml` e um `Dockerfile` para o Action Server (incluindo pacotes como `rasa-sdk` e `pgmpy`).
* Configurações vitais do Rasa: `endpoints.yml` (para conectar as Custom Actions) e `credentials.yml` habilitando o canal REST.

**2. Arquitetura do Motor Cognitivo (Action Server):**
* Um script em Python mostrando como montar o DAG de Cartografia (as dependências entre os assuntos).
* Uma *Custom Action* (`ActionUpdateMastery`) que recebe um acerto/erro, atualiza a probabilidade na rede e **retorna o JSON payload** com o objeto `mastery` atualizado para consumo via API.

**3. Lógica do Cold Start (Rasa NLU e Core):**
* Como configurar um *Form* ou regra no Rasa para fazer as 10 perguntas iniciais e capturar as respostas para calibrar as probabilidades da Rede Bayesiana.

**4. Stories e Academically Productive Talk:**
* Crie um exemplo de intenção e história onde o aluno erra o cálculo de "Escala", e o bot faz uma pergunta reflexiva em vez de dar a resposta, acionando a *Custom Action* para penalizar levemente a probabilidade de domínio daquele tópico.