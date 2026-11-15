# PetMóvel Itajubá MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Construir o MVP web de agendamento e gestão do pet shop híbrido PetMóvel Itajubá, executável com `pip install -r requirements.txt` e `python app.py`.

**Architecture:** App Flask único renderizado no servidor (Jinja2 + Tailwind via CDN + JS sem framework). As regras de negócio (preço, disponibilidade, máquina de estados, notificações) ficam em `services.py`, sem dependência de `request`, e as rotas em `app.py` apenas as chamam. SQLite via Flask-SQLAlchemy, com tabelas e seed criados na primeira execução.

**Tech Stack:** Python 3.10+, Flask 3, Flask-SQLAlchemy 3, Werkzeug (hash de senha), pytest, Tailwind CSS (CDN).

**Spec:** `docs/superpowers/specs/2026-11-15-petmovel-mvp-design.md` (mais a especificação original do autor, seções 1–6, resumida nela).

## Global Constraints

- Código compatível com Python 3.10 (nada exclusivo de 3.11+).
- Dependências: apenas `Flask`, `Flask-SQLAlchemy`, `pytest`. Sem Node.js, sem etapa de build, sem Flask-Login/Flask-WTF.
- Banco: arquivo `petshop.db` na raiz do projeto (caminho absoluto a partir de `app.py`, não a pasta `instance/`).
- Interface, mensagens e identificadores de domínio em português do Brasil.
- Valores literais do domínio, exatamente: perfis `CLIENTE`, `PRESTADOR`; espécies `Cão`, `Gato`; portes `Pequeno`, `Medio`, `Grande`; tipos `PRESENCIAL_LOJA`, `DOMICILIO_MOVEL`; pagamentos `Dinheiro`, `Cartao`, `PIX`; status `Pendente`, `Confirmado`, `Em Deslocamento`, `Em Atendimento`, `Concluído`, `Cancelado`.
- Multiplicadores: Pequeno 1.0, Medio 1.25, Grande 1.5. Valores monetários arredondados a 2 casas.
- Horários: slots de hora cheia, 08:00 a 17:00 (10 slots), todos os dias.
- Toda alteração de estado é feita por `POST` com token CSRF; nenhuma por `GET`.
- Datas e horas são locais e sem fuso (`datetime.now()`).
- `python app.py` sobe em `http://127.0.0.1:5000`, com `debug` desligado salvo `FLASK_DEBUG=1`.
- Cada tarefa termina com `pytest -q` verde e um commit.

## Review Focus

Entradas que a especificação implica mas não descreve; cada uma tem teste na tarefa indicada.

1. **Acesso a dados de outro cliente** (editar/excluir pet, cancelar agendamento, ler notificações de outro usuário trocando o id na URL) → resposta 404, nada alterado. Tarefas 6 e 7.
2. **Requisição forjada de transição** (cliente enviando `confirmar`, prestador enviando `concluir` em agendamento Pendente, ação em estado final) → recusada, status inalterado. Tarefas 3, 7 e 8.
3. **Formulário de agendamento adulterado** (`valor_total` enviado, data passada, hora `10:30` ou `03:00`, data malformada, pet de outro cliente, nenhum serviço, id de serviço inexistente) → mensagem de erro, nada criado, nunca erro 500. Tarefas 3 e 7.
4. **Recurso some entre agendar e confirmar** (bairro desativado, van ou baia desativada, último slot tomado por outro cliente) → confirmação recusada com mensagem, agendamento continua Pendente. Tarefa 3.
5. **Cadastro e login hostis** (e-mail duplicado com maiúsculas diferentes, `perfil=PRESTADOR` no formulário de cadastro, `next=https://evil.example` ou `next=//evil.example` no login) → sem conta duplicada, sem prestador criado, sem redirecionamento externo. Tarefa 5.

---

## Estrutura de arquivos

| Arquivo | Responsabilidade |
|---|---|
| `requirements.txt` | dependências |
| `.gitignore` | `petshop.db`, `__pycache__/`, `.pytest_cache/`, `.venv/`, `instance/` |
| `models.py` | `db`, constantes de domínio, as 9 tabelas |
| `services.py` | regras de negócio puras (recebem objetos e `agora`, não tocam em `request`) |
| `seed.py` | dados iniciais |
| `app.py` | `create_app`, autenticação, CSRF, todas as rotas |
| `templates/base.html` | navbar, sino, toasts, rodapé |
| `templates/_macros.html` | badge de status, campo de formulário |
| `templates/index.html`, `login.html`, `cadastro.html` | área pública |
| `templates/perfil.html`, `pets.html`, `pet_form.html`, `agendar.html`, `meus_agendamentos.html`, `notificacoes.html` | área do cliente |
| `templates/painel.html`, `gestao.html` | área do prestador |
| `static/app.js` | formulário reativo de agendamento, abas, toasts |
| `tests/conftest.py` | fixtures `app`, `client`, `dados`, helper `login` |
| `tests/test_*.py` | um arquivo por tarefa |
| `README.md` | documentação da entrega |

---

### Task 1: Fundação — modelos e fábrica do app

**Files:**
- Create: `requirements.txt`, `.gitignore`, `models.py`, `app.py`, `tests/conftest.py`, `tests/test_models.py`

**Interfaces:**
- Produces (em `models.py`):
  - `db = SQLAlchemy()`
  - Constantes: `PERFIL_CLIENTE`, `PERFIL_PRESTADOR`, `ESPECIES`, `PORTES`, `TIPO_LOJA`, `TIPO_MOVEL`, `TIPOS`, `FORMAS_PAGAMENTO`, `PENDENTE`, `CONFIRMADO`, `EM_DESLOCAMENTO`, `EM_ATENDIMENTO`, `CONCLUIDO`, `CANCELADO`, `STATUS_ATIVOS = (PENDENTE, CONFIRMADO, EM_DESLOCAMENTO, EM_ATENDIMENTO)`, `STATUS_FINAIS = (CONCLUIDO, CANCELADO)`, `MULTIPLICADORES = {"Pequeno": 1.0, "Medio": 1.25, "Grande": 1.5}`, `HORAS_ATENDIMENTO = range(8, 18)`.
  - Classes com os campos da seção 4 da especificação: `Usuario`, `Pet`, `Servico`, `BairroCobertura`, `UnidadeMovel`, `PostoFixo`, `Agendamento`, `AgendamentoServico`, `Notificacao`.
  - Relacionamentos: `Usuario.pets`, `Usuario.notificacoes`, `Pet.cliente`, `Pet.agendamentos`, `Agendamento.cliente`, `Agendamento.pet`, `Agendamento.itens` (lista de `AgendamentoServico`, `cascade="all, delete-orphan"`), `Agendamento.unidade_movel`, `Agendamento.posto_fixo`, `AgendamentoServico.servico`.
  - `Usuario.set_senha(senha: str) -> None`, `Usuario.check_senha(senha: str) -> bool` (Werkzeug).
  - `Agendamento.duracao_total -> int` (soma de `servico.duracao_minutos` dos itens).
- Produces (em `app.py`): `create_app(config: dict | None = None) -> Flask`. Padrões: `SECRET_KEY` de `os.environ` ou `"petmovel-dev-secret"`, `SQLALCHEMY_DATABASE_URI` absoluto para `petshop.db`, `SEED_ON_START=True`, `CSRF_ENABLED=True`. Chama `db.create_all()` dentro do contexto do app. Bloco `if __name__ == "__main__"` roda o servidor.
- Produces (em `tests/conftest.py`):
  - fixture `app`: `create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path}/t.db", "SEED_ON_START": False, "CSRF_ENABLED": False})`, entregue dentro de `app.app_context()`.
  - fixture `client`: `app.test_client()`.
  - fixture `dados` → `SimpleNamespace` de **ids** criados no banco: `cliente` (cliente@teste.com, bairro BPS), `maria` (maria@teste.com, Centro), `prestador` (admin@petmovel.com), todos com senha `123456`; `thor` (Cão, Grande, de `cliente`, restrição "Alergia a shampoo perfumado"), `luna` (Gato, Pequeno, de `maria`); `banho` (50.0, 45 min), `unhas` (20.0, 15 min); bairros Centro e BPS ativos, Cruzeiro inativo; `van`, `baia1`, `baia2` ativos.
  - constantes `AGORA = datetime(2026, 3, 2, 7, 0)` e `DIA = date(2026, 3, 3)`.
  - `login(client, email, senha="123456")` → faz `POST /login`.

- [ ] **Step 1: Escrever `requirements.txt` e `.gitignore`**

`requirements.txt`: `Flask>=3.0,<4`, `Flask-SQLAlchemy>=3.1,<4`, `pytest>=8.0`.

- [ ] **Step 2: Instalar dependências**

Run: `pip install -r requirements.txt`
Expected: instalação sem erro.

- [ ] **Step 3: Escrever os testes que falham em `tests/test_models.py`**

```python
def test_tabelas_criadas(app):
    nomes = set(db.inspect(db.engine).get_table_names())
    assert {"usuario", "pet", "servico", "bairro_cobertura", "unidade_movel",
            "posto_fixo", "agendamento", "agendamento_servico", "notificacao"} <= nomes

def test_senha_e_hash(app):
    u = Usuario(nome="A", email="a@a.com", perfil=PERFIL_CLIENTE)
    u.set_senha("123456")
    assert u.senha_hash != "123456"
    assert u.check_senha("123456") and not u.check_senha("errada")

def test_email_unico(app, dados):
    # inserir outro Usuario com email "cliente@teste.com" levanta IntegrityError

def test_banco_padrao_na_raiz_do_projeto():
    # create_app com SEED_ON_START False e sem URI: a URI termina em "petshop.db"
    # e aponta para o diretório de app.py, não para "instance/"

def test_fixture_dados(app, dados):
    assert db.session.get(Pet, dados.thor).cliente_id == dados.cliente
    assert Usuario.query.count() == 3
```

- [ ] **Step 4: Rodar e ver falhar**

Run: `pytest tests/test_models.py -q`
Expected: FAIL (módulos `models`/`app` inexistentes).

- [ ] **Step 5: Implementar `models.py`, `app.py` (só `create_app`) e `tests/conftest.py`**

Nomes de tabela via `__tablename__` conforme o teste. `Usuario.email` com `unique=True, nullable=False`. `Agendamento.unidade_movel_id` e `posto_fixo_id` anuláveis. `Notificacao.criada_em` com `default=datetime.now`.

- [ ] **Step 6: Rodar e ver passar**

Run: `pytest -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add -A && git commit -m "feat: modelos de dados e fábrica do app"
```

---

### Task 2: Regras de preço, cobertura e disponibilidade

**Files:**
- Create: `services.py`, `tests/test_precos_disponibilidade.py`

**Interfaces:**
- Consumes: modelos, constantes e fixtures da Task 1.
- Produces (em `services.py`):
  - `class RegraNegocioError(Exception)` — a mensagem é o texto mostrado ao usuário.
  - `calcular_preco(preco_base: float, porte: str) -> float`
  - `calcular_total(servicos: list[Servico], porte: str) -> float`
  - `bairro_coberto(nome: str | None) -> bool` — ignora maiúsculas e espaços nas pontas.
  - `capacidade(tipo: str) -> int` — unidades móveis ativas (`TIPO_MOVEL`) ou postos fixos ativos (`TIPO_LOJA`).
  - `ocupados(tipo: str, data_hora: datetime, ignorar_id: int | None = None) -> int` — agendamentos do tipo com status em `STATUS_ATIVOS` e `|data_hora − outro| < 1 hora`.
  - `horarios_disponiveis(tipo: str, dia: date, agora: datetime | None = None) -> list[dict]` — 10 itens `{"hora": "08:00", "livre": bool}`; `livre` é falso se o slot já passou (`<= agora`) ou se `ocupados >= capacidade`.

- [ ] **Step 1: Escrever os testes que falham**

```python
@pytest.mark.parametrize("base,porte,esperado", [
    (50, "Pequeno", 50.0), (50, "Medio", 62.5), (35, "Medio", 43.75), (50, "Grande", 75.0)])
def test_calcular_preco(base, porte, esperado): ...

def test_porte_invalido_levanta():           # calcular_preco(50, "Gigante") -> RegraNegocioError
def test_calcular_total(app, dados):         # [banho, unhas], "Grande" == 105.0

@pytest.mark.parametrize("nome,ok", [("Centro", True), ("  centro ", True), ("BPS", True),
    ("Cruzeiro", False), ("Inexistente", False), ("", False), (None, False)])
def test_bairro_coberto(app, dados, nome, ok): ...

def test_capacidade(app, dados):             # LOJA == 2, MOVEL == 1; desativar baia1 -> LOJA == 1
def test_horarios_lista_dez_slots(app, dados):
    hs = horarios_disponiveis(TIPO_MOVEL, DIA, AGORA)
    assert [h["hora"] for h in hs] == [f"{h:02d}:00" for h in range(8, 18)]
    assert all(h["livre"] for h in hs)
def test_van_ocupada_bloqueia_slot(app, dados):    # 1 Pendente MOVEL às 10:00 -> "10:00" livre False, "11:00" True
def test_cancelado_nao_ocupa(app, dados):          # o mesmo com status Cancelado -> "10:00" livre True
def test_loja_tem_duas_vagas(app, dados):          # 1 LOJA às 10:00 -> True; 2 -> False
def test_tipos_nao_competem(app, dados):           # 1 MOVEL às 10:00 não afeta LOJA às 10:00
def test_slots_passados_indisponiveis(app, dados): # agora = DIA 12:30 -> 08..12 False, 13:00 True
def test_sem_recurso_ativo_nada_livre(app, dados): # van desativada -> todos False para MOVEL
```

Os testes criam `Agendamento` direto no banco com um helper local `_ag(dados, tipo, hora, status=PENDENTE)`.

- [ ] **Step 2: Rodar e ver falhar**

Run: `pytest tests/test_precos_disponibilidade.py -q`
Expected: FAIL (`services` inexistente).

- [ ] **Step 3: Implementar as funções em `services.py`**

- [ ] **Step 4: Rodar e ver passar**

Run: `pytest -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: regras de preço, cobertura e disponibilidade"
```

---

### Task 3: Criação de agendamento, máquina de estados e notificações

**Files:**
- Modify: `services.py`
- Create: `tests/test_agendamento_estados.py`

**Interfaces:**
- Consumes: tudo da Task 2.
- Produces (em `services.py`):
  - `notificar(usuario_id: int, mensagem: str) -> Notificacao` (adiciona à sessão, sem commit).
  - `criar_agendamento(cliente: Usuario, pet_id, servico_ids: list, tipo: str, data_hora: datetime, forma_pagamento: str, bairro: str = "", endereco: str = "", agora: datetime | None = None) -> Agendamento` — valida, grava com status `Pendente`, cria os `AgendamentoServico` com `preco_aplicado`, notifica o cliente e faz commit. Em qualquer falha levanta `RegraNegocioError` sem gravar nada. Para `TIPO_LOJA`, `bairro_atendimento` e `endereco_atendimento` ficam `None`. Para `TIPO_MOVEL`, grava o nome canônico do bairro (o de `BairroCobertura`).
  - `executar_acao(ag: Agendamento, acao: str, usuario: Usuario) -> Agendamento` — aplica a transição, notifica o cliente com mensagem que contém o novo status, faz commit. Transição inválida ou sem permissão levanta `RegraNegocioError` e não altera nada.
  - `acoes_disponiveis(ag: Agendamento, usuario: Usuario) -> list[tuple[str, str]]` — pares `(acao, rótulo)` que `executar_acao` aceitaria.
  - `resumo_do_dia(dia: date) -> dict` com chaves `total`, `pendentes`, `loja`, `movel` (`total`, `loja` e `movel` ignoram Cancelado).
  - `agenda_do_dia(dia: date, tipo: str | None = None) -> list[Agendamento]` ordenada por `data_hora`.

Tabela de ações (única fonte da verdade; qualquer par fora dela é recusado):

| `acao` | Rótulo | De → Para | Quem | Tipo |
|---|---|---|---|---|
| `confirmar` | Confirmar (validar rota e escala) | Pendente → Confirmado | prestador | ambos |
| `recusar` | Recusar atendimento | Pendente → Cancelado | prestador | ambos |
| `cancelar` | Cancelar | Pendente → Cancelado | cliente dono | ambos |
| `cancelar` | Cancelar | Confirmado → Cancelado | cliente dono ou prestador | ambos |
| `iniciar_deslocamento` | Iniciar deslocamento | Confirmado → Em Deslocamento | prestador | só `DOMICILIO_MOVEL` |
| `iniciar_atendimento` | Chegada no local | Em Deslocamento → Em Atendimento | prestador | só `DOMICILIO_MOVEL` |
| `iniciar_atendimento` | Iniciar atendimento | Confirmado → Em Atendimento | prestador | só `PRESENCIAL_LOJA` |
| `concluir` | Finalizar procedimentos | Em Atendimento → Concluído | prestador | ambos |

`confirmar` valida `bairro_coberto` (se domicílio) e aloca o primeiro recurso ativo do tipo (menor id) que não esteja em outro agendamento Confirmado/Em Deslocamento/Em Atendimento a menos de 1 hora; sem recurso livre, levanta `RegraNegocioError`.

Validações de `criar_agendamento`, na ordem: pet existe e é do cliente; ao menos um serviço e todos existem; tipo em `TIPOS`; forma em `FORMAS_PAGAMENTO`; `data_hora` com minuto e segundo zero e hora em `HORAS_ATENDIMENTO`; `data_hora > agora`; se domicílio, endereço não vazio e `bairro_coberto`; `ocupados < capacidade`.

- [ ] **Step 1: Escrever os testes que falham**

```python
# helper: _novo(dados, tipo=TIPO_MOVEL, hora=10, **kw) chama criar_agendamento com thor,
# [banho, unhas], DIA às `hora`, "PIX", bairro "BPS", endereco "Rua A, 10", agora=AGORA

def test_cria_pendente_com_total_e_itens(app, dados):
    ag = _novo(dados)
    assert ag.status == PENDENTE and ag.valor_total == 105.0
    assert sorted(i.preco_aplicado for i in ag.itens) == [30.0, 75.0]
    assert ag.unidade_movel_id is None and ag.posto_fixo_id is None
    assert Notificacao.query.filter_by(usuario_id=dados.cliente).count() == 1

def test_loja_ignora_endereco(app, dados):         # bairro/endereco gravados como None

@pytest.mark.parametrize("kw", [
    {"pet_id": "luna"},                 # pet de outro cliente
    {"pet_id": 9999},
    {"servico_ids": []},
    {"servico_ids": [9999]},
    {"tipo": "OUTRO"},
    {"forma_pagamento": "Cheque"},
    {"data_hora": datetime(2026, 3, 1, 10, 0)},    # passado em relação a AGORA
    {"data_hora": datetime(2026, 3, 3, 10, 30)},
    {"data_hora": datetime(2026, 3, 3, 7, 0)},
    {"data_hora": datetime(2026, 3, 3, 18, 0)},
    {"bairro": "Cruzeiro"},
    {"bairro": "Inexistente"},
    {"endereco": "   "},
])
def test_criacao_invalida_nao_grava(app, dados, kw):
    # levanta RegraNegocioError; Agendamento.query.count() == 0; nenhuma Notificacao

def test_van_cheia_recusa_segundo(app, dados)      # 2º MOVEL no mesmo slot levanta
def test_loja_recusa_terceiro(app, dados)          # 3º LOJA no mesmo slot levanta
def test_cancelado_libera_slot(app, dados)         # cancelar o 1º permite novo no mesmo slot

def test_fluxo_completo_domicilio(app, dados):
    # confirmar -> Confirmado e unidade_movel_id == dados.van
    # iniciar_deslocamento -> Em Deslocamento; iniciar_atendimento -> Em Atendimento
    # concluir -> Concluído; a cada passo a última Notificacao do cliente contém o novo status

def test_fluxo_completo_loja(app, dados):
    # dois agendamentos LOJA no mesmo slot: confirmar aloca baia1 e depois baia2
    # iniciar_atendimento direto de Confirmado; concluir

def test_loja_nao_desloca(app, dados)              # iniciar_deslocamento em LOJA levanta
def test_domicilio_nao_pula_deslocamento(app, dados)  # Confirmado MOVEL + iniciar_atendimento levanta

@pytest.mark.parametrize("status", [PENDENTE, CONFIRMADO, EM_DESLOCAMENTO, EM_ATENDIMENTO, CONCLUIDO, CANCELADO])
@pytest.mark.parametrize("acao", ["confirmar", "recusar", "cancelar", "iniciar_deslocamento",
                                  "iniciar_atendimento", "concluir", "inexistente"])
def test_matriz_de_transicoes_prestador_domicilio(app, dados, status, acao):
    # permitido somente nos pares da tabela; nos demais levanta e ag.status permanece igual

def test_estados_finais_imutaveis(app, dados)      # Concluído e Cancelado recusam todas as ações
def test_cliente_cancela_pendente_e_confirmado(app, dados)
def test_cliente_nao_cancela_em_atendimento(app, dados)
def test_outro_cliente_nao_cancela(app, dados)     # maria em agendamento de cliente levanta
def test_cliente_nao_confirma(app, dados)
def test_prestador_nao_usa_cancelar_em_pendente(app, dados)  # deve usar recusar

def test_confirmar_falha_se_bairro_desativado(app, dados)    # continua Pendente, sem recurso
def test_confirmar_falha_se_van_desativada(app, dados)       # continua Pendente
def test_confirmar_falha_se_recurso_ja_alocado(app, dados):
    # um Confirmado MOVEL com a van às 10:00 inserido direto no banco + um Pendente às 10:00:
    # confirmar o Pendente levanta e ele continua Pendente

def test_acoes_disponiveis(app, dados):
    # comparando só os nomes: [a for a, _ in acoes_disponiveis(ag, usuario)]
    # Pendente/prestador -> ["confirmar", "recusar"]; Pendente/cliente dono -> ["cancelar"]
    # Confirmado MOVEL/prestador -> ["iniciar_deslocamento", "cancelar"]
    # Confirmado LOJA/prestador -> ["iniciar_atendimento", "cancelar"]
    # Concluído -> []; maria em agendamento de cliente -> []

def test_resumo_e_agenda_do_dia(app, dados):
    # 1 MOVEL Pendente, 1 LOJA Confirmado, 1 LOJA Cancelado em DIA; 1 em outro dia
    # resumo == {"total": 2, "pendentes": 1, "loja": 1, "movel": 1}
    # agenda_do_dia(DIA) tem 3 itens em ordem de horário; com tipo=TIPO_LOJA, 2
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `pytest tests/test_agendamento_estados.py -q`
Expected: FAIL (funções inexistentes).

- [ ] **Step 3: Implementar em `services.py`**

A tabela de ações vira uma estrutura de dados única consultada por `executar_acao` e `acoes_disponiveis`.

- [ ] **Step 4: Rodar e ver passar**

Run: `pytest -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: criação de agendamento, máquina de estados e notificações"
```

---

### Task 4: Seed automático

**Files:**
- Create: `seed.py`, `tests/test_seed.py`
- Modify: `app.py` (chamar o seed em `create_app` quando `SEED_ON_START`)

**Interfaces:**
- Consumes: modelos; `calcular_preco` da Task 2.
- Produces: `seed.popular(agora: datetime | None = None) -> None`; `seed.popular_se_vazio() -> bool` (verdadeiro se populou; decide por `Usuario.query.count() == 0`).

Dados (os da seção 6 da especificação, mais estas escolhas):

- Usuários, senha `123456`: `admin@petmovel.com` "Equipe PetMóvel" PRESTADOR; `cliente@teste.com` "Carlos Cliente", "Rua Coronel Rennó, 120 — BPS, Itajubá-MG", bairro BPS; `maria@teste.com` "Maria Souza", "Praça Theodomiro Santiago, 45 — Centro, Itajubá-MG", bairro Centro.
- Pets: Thor (Cão, Grande, "Alergia a shampoo perfumado") e Bob (Cão, Medio) de Carlos; Luna (Gato, Pequeno) de Maria.
- Serviços, bairros e recursos exatamente como na especificação; van com responsável "João Ferreira", baias com "Ana Lima" e "Pedro Santos".
- Agendamentos (inseridos direto, sem `criar_agendamento`, pois alguns ficam no passado):

| Status | Pet | Serviços | Tipo | Quando | Pagamento | Recurso | Total |
|---|---|---|---|---|---|---|---|
| Pendente | Thor | Banho Completo, Corte de Unhas | DOMICILIO_MOVEL, BPS | hoje 16:00 | PIX | — | 105.00 |
| Confirmado | Bob | Tosa Higiênica | PRESENCIAL_LOJA | hoje 15:00 | Cartao | Baia 01 | 43.75 |
| Em Atendimento | Luna | Banho Completo, Hidratação de Pelos | DOMICILIO_MOVEL, Centro | hoje 10:00 | Dinheiro | Van 01 | 90.00 |
| Concluído | Thor | Tosa Completa | PRESENCIAL_LOJA | ontem 14:00 | Dinheiro | Baia 02 | 105.00 |

- Uma notificação não lida por agendamento, para o respectivo cliente, citando o status.

- [ ] **Step 1: Escrever os testes que falham**

```python
def test_seed_contagens(app):
    seed.popular()
    assert Usuario.query.count() == 3 and Pet.query.count() == 3
    assert Servico.query.count() == 5 and BairroCobertura.query.count() == 6
    assert UnidadeMovel.query.count() == 1 and PostoFixo.query.count() == 2
    assert {a.status for a in Agendamento.query} == {PENDENTE, CONFIRMADO, EM_ATENDIMENTO, CONCLUIDO}

def test_seed_credenciais(app):       # os 3 e-mails existem, check_senha("123456"), perfis e bairros corretos
def test_seed_servicos(app):          # {(nome, preco, duracao)} == os 5 da especificação
def test_seed_cruzeiro_inativo(app):  # só Cruzeiro tem ativo False
def test_seed_van(app):               # placa "ABC-1D23", modelo "Van PetMóvel 01"
def test_seed_totais_coerentes(app):  # para cada agendamento: valor_total == soma dos preco_aplicado
                                      # == calcular_total(serviços, pet.porte)
def test_seed_recursos_alocados(app): # Confirmado tem posto_fixo_id; Em Atendimento tem unidade_movel_id; Pendente nenhum
def test_seed_datas_relativas(app):   # popular(agora=datetime(2026,3,2,9,0)): 3 agendamentos em 2026-03-02, 1 em 2026-03-01
def test_popular_se_vazio_idempotente(app):  # 1ª chamada True, 2ª False, contagens iguais
def test_create_app_popula(tmp_path):        # create_app com SEED_ON_START True e banco novo -> 3 usuários
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `pytest tests/test_seed.py -q`
Expected: FAIL.

- [ ] **Step 3: Implementar `seed.py` e ligar em `create_app`**

- [ ] **Step 4: Rodar e ver passar**

Run: `pytest -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: seed automático na primeira execução"
```

---

### Task 5: Autenticação, layout base e home pública

**Files:**
- Modify: `app.py`
- Create: `templates/base.html`, `templates/_macros.html`, `templates/index.html`, `templates/login.html`, `templates/cadastro.html`, `static/app.js`, `tests/test_auth_home.py`

**Interfaces:**
- Consumes: modelos, `seed`.
- Produces (em `app.py`):
  - Sessão: `session["usuario_id"]`; `g.usuario` preenchido em `before_request` (ou `None`).
  - Decoradores `login_required`, `cliente_required`, `prestador_required`. Sem login: redireciona para `/login?next=<caminho>`. Perfil errado: flash `erro` "Acesso restrito." e redireciona para `/`.
  - CSRF: token em `session["_csrf"]`, global Jinja `csrf_token()`, campo oculto `_csrf` em todo `<form method="post">`; `before_request` responde 400 a `POST` sem token válido quando `CSRF_ENABLED`.
  - Context processor: `usuario`, `nao_lidas` (int), `TIPO_LOJA`, `TIPO_MOVEL`.
  - Filtros Jinja: `brl` (`105.0` → `R$ 105,00`), `datahora` (`dd/mm/aaaa HH:MM`).
  - Categorias de flash: `sucesso`, `erro`, `info`.
  - Rotas: `GET /`, `GET|POST /login`, `GET|POST /cadastro`, `POST /logout`.
- Produces (em `templates/_macros.html`): `badge_status(status)` — cores: Pendente âmbar, Confirmado azul, Em Deslocamento roxo, Em Atendimento índigo, Concluído verde, Cancelado cinza.
- Produces (em `templates/base.html`): blocos `title` e `content`; navbar com logo "PetMóvel Itajubá", links por perfil (cliente: Agendar, Meus Agendamentos, Meus Pets, sino com `nao_lidas`, Perfil, Sair; prestador: Painel, Gestão, Sair; visitante: Meus Agendamentos, Entrar, Cadastrar); toasts a partir das mensagens flash, que somem sozinhos.

Regras:
- Os links da navbar usam caminhos literais (`/agendar`, `/pets`, `/painel`…), porque as rotas chegam em tarefas posteriores.
- Cadastro: campos nome, email, senha (mínimo 6), telefone, endereco_completo, bairro (texto livre). Sempre cria `CLIENTE`. E-mail gravado em minúsculas e sem espaços. Após cadastrar, já entra logado e vai para `/pets`.
- Login: e-mail comparado em minúsculas. Erro: "E-mail ou senha inválidos." Destino: `next` se for caminho local (começa com `/` e não com `//`), senão `/painel` para prestador e `/meus-agendamentos` para cliente.
- Home: hero com botão "Agendar agora" (`/agendar`); seção de cobertura com os bairros **ativos**; cards dos serviços com descrição, duração, preço base e a nota "Médio +25% · Grande +50%"; seção das duas modalidades; três depoimentos fixos (lista em `app.py`, tutores fictícios de Itajubá, identificados por primeiro nome e bairro).

- [ ] **Step 1: Escrever os testes que falham**

```python
def test_home_publica(client, dados):
    html = client.get("/").get_data(as_text=True)
    assert "PetMóvel Itajubá" in html and "Banho Completo" in html
    assert "Centro" in html and "BPS" in html and "Cruzeiro" not in html

def test_cadastro_cria_cliente_e_loga(client, app)     # 302 para /pets; perfil CLIENTE; sessão ativa
def test_cadastro_ignora_perfil_prestador(client, app) # perfil=PRESTADOR no form -> gravado CLIENTE
def test_cadastro_email_duplicado(client, dados)       # "CLIENTE@teste.com" -> erro, Usuario.count() == 3
def test_cadastro_senha_curta(client, app)             # "123" -> erro, nada criado
def test_cadastro_campos_obrigatorios(client, app)     # nome vazio -> erro

def test_login_cliente(client, dados)                  # 302 Location termina em /meus-agendamentos
def test_login_prestador(client, dados)                # 302 Location termina em /painel
def test_login_email_maiusculo(client, dados)          # "Cliente@Teste.com" entra
def test_login_invalido(client, dados)                 # 200 com "E-mail ou senha inválidos"
def test_login_next_local(client, dados)               # /login?next=/pets -> Location /pets
@pytest.mark.parametrize("alvo", ["https://evil.example", "//evil.example"])
def test_login_next_externo_ignorado(client, dados, alvo)  # Location termina em /meus-agendamentos
def test_logout(client, dados)                         # POST /logout limpa a sessão; GET /logout -> 405
def test_navbar_por_perfil(client, dados)              # visitante vê "Entrar"; cliente vê "Meus Pets"; prestador vê "Painel"
def test_csrf_exigido(tmp_path)                        # app com CSRF_ENABLED True: POST /login sem token -> 400;
                                                       # com o token extraído do GET /login -> não é 400
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `pytest tests/test_auth_home.py -q`
Expected: FAIL.

- [ ] **Step 3: Implementar rotas, helpers e templates**

`static/app.js` nesta tarefa contém só o sumiço automático dos toasts.

- [ ] **Step 4: Rodar e ver passar**

Run: `pytest -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: autenticação, layout base e home pública"
```

---

### Task 6: Área do cliente — perfil e pets

**Files:**
- Modify: `app.py`
- Create: `templates/perfil.html`, `templates/pets.html`, `templates/pet_form.html`, `tests/test_perfil_pets.py`

**Interfaces:**
- Consumes: decoradores e base da Task 5.
- Produces: rotas `GET|POST /perfil`; `GET /pets`; `GET|POST /pets/novo`; `GET|POST /pets/<int:id>/editar`; `POST /pets/<int:id>/excluir`. Todas com `cliente_required`.

Regras:
- Perfil edita nome, telefone, endereco_completo e bairro; e-mail aparece só para leitura.
- Pet: nome obrigatório; espécie em `ESPECIES`; porte em `PORTES`; restrições opcionais. Formulário inválido re-renderiza com status 400 e a mensagem.
- Pet de outro cliente (ou inexistente): 404.
- Excluir pet com qualquer agendamento: bloqueado, flash `erro` "Este pet possui agendamentos e não pode ser excluído."
- A lista mostra as restrições em destaque e, por pet, o número de atendimentos concluídos.

- [ ] **Step 1: Escrever os testes que falham**

```python
def test_pets_exige_login(client, dados)          # GET /pets -> 302 para /login?next=/pets
def test_prestador_nao_acessa_pets(client, dados) # 302 para /
def test_lista_so_os_proprios(client, dados)      # cliente vê "Thor", não vê "Luna"
def test_cria_pet(client, dados)                  # POST válido -> 302; pet no banco com cliente_id certo
@pytest.mark.parametrize("campo,valor", [("nome", ""), ("especie", "Peixe"), ("porte", "Gigante")])
def test_pet_invalido(client, dados, campo, valor)  # 400; Pet.count() inalterado
def test_edita_pet(client, dados)                 # muda porte para "Medio"
def test_nao_edita_pet_alheio(client, dados)      # GET e POST /pets/<luna>/editar -> 404; Luna intacta
def test_nao_exclui_pet_alheio(client, dados)     # 404; Luna continua
def test_exclui_pet_sem_agendamento(client, dados)
def test_nao_exclui_pet_com_agendamento(client, dados)  # Thor com 1 agendamento continua no banco
def test_edita_perfil(client, dados)              # telefone e bairro alterados; e-mail enviado no form é ignorado
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `pytest tests/test_perfil_pets.py -q`
Expected: FAIL.

- [ ] **Step 3: Implementar rotas e templates**

- [ ] **Step 4: Rodar e ver passar**

Run: `pytest -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: perfil do cliente e CRUD de pets"
```

---

### Task 7: Agendamento, meus agendamentos e notificações

**Files:**
- Modify: `app.py`, `static/app.js`
- Create: `templates/agendar.html`, `templates/meus_agendamentos.html`, `templates/notificacoes.html`, `tests/test_agendar.py`

**Interfaces:**
- Consumes: `criar_agendamento`, `executar_acao`, `acoes_disponiveis`, `horarios_disponiveis`, `RegraNegocioError`.
- Produces (rotas):
  - `GET|POST /agendar` (`cliente_required`). Campos do POST: `pet_id`, `servicos` (múltiplo), `tipo`, `data` (`AAAA-MM-DD`), `hora` (`HH:MM`), `bairro`, `endereco`, `forma_pagamento`.
  - `GET /api/horarios?tipo=<tipo>&data=<AAAA-MM-DD>` → `{"horarios": [{"hora", "livre"}]}`; sem login 401 `{"erro": ...}`; parâmetro inválido 400 `{"erro": ...}`.
  - `GET /meus-agendamentos` (`cliente_required`).
  - `POST /agendamentos/<int:id>/acao` (`login_required`), campos `acao` e `next` opcional (caminho local). Cliente só nos próprios (senão 404). Redireciona para `next`, ou `/painel` (prestador), ou `/meus-agendamentos`.
  - `GET /notificacoes`, `POST /notificacoes/ler` (`login_required`).
- Produces (em `static/app.js`): `initAgendar(dados)`, chamada pelo template com `dados = {pets: [{id, nome, especie, porte}], servicos: [{id, nome, preco_base, duracao}], multiplicadores, bairros: [{nome, ativo}], tipoMovel, tipoLoja}`.

Regras:
- `GET /agendar` de cliente sem pets: flash `info` e redireciona para `/pets/novo`.
- `POST /agendar`: monta `data_hora`; data ou hora malformada vira mensagem "Data ou horário inválido."; chama `criar_agendamento`; em `RegraNegocioError`, re-renderiza com status 400, a mensagem e os valores preenchidos. Sucesso: flash `sucesso` e redireciona para `/meus-agendamentos`. Qualquer `valor_total` vindo do formulário é ignorado.
- O `<select>` de bairro lista **todos** os bairros cadastrados; os inativos aparecem com o sufixo "(fora da área de cobertura)". Endereço e bairro vêm pré-preenchidos com os do perfil.
- `initAgendar`: ao trocar o pet, mostra o porte e reescreve o preço de cada serviço; ao marcar serviços, atualiza total (R$) e duração total (min); ao escolher Domicílio, mostra bairro e endereço e os torna obrigatórios; bairro inativo mostra alerta vermelho e desabilita o botão de confirmar; ao mudar tipo ou data, busca `/api/horarios` e desenha os slots como botões (ocupados desabilitados), limpando a hora escolhida; o campo de data tem `min` igual a hoje.
- Meus Agendamentos: duas abas no cliente (`static/app.js`), "Agendamentos Ativos" (status em `STATUS_ATIVOS`, ordem crescente de data) e "Histórico de Atendimentos" (finais, ordem decrescente). Cada item mostra pet, serviços com `preco_aplicado`, modalidade, endereço se domicílio, data/hora, pagamento, total, `badge_status` e o recurso alocado quando houver. O botão Cancelar aparece só quando `acoes_disponiveis` o inclui e pede confirmação.
- Notificações: lista decrescente por `criada_em`, não lidas destacadas, botão "Marcar todas como lidas".

- [ ] **Step 1: Escrever os testes que falham**

```python
# helper: _form(dados, **kw) -> dict válido: thor, [banho, unhas], DOMICILIO_MOVEL,
# data = amanhã, hora "10:00", bairro "BPS", endereco "Rua A, 10", forma "PIX"

def test_agendar_exige_login(client, dados)          # 302 /login?next=/agendar
def test_meus_agendamentos_exige_login(client, dados)
def test_agendar_sem_pets_redireciona(client, app)   # cliente recém-cadastrado -> /pets/novo
def test_tela_agendar_lista_dados(client, dados)     # contém "Thor", "Banho Completo", "Cruzeiro"; não contém "Luna"

def test_agendar_sucesso(client, dados):
    r = client.post("/agendar", data=_form(dados))
    assert r.status_code == 302
    ag = Agendamento.query.one()
    assert ag.status == PENDENTE and ag.valor_total == 105.0

def test_valor_enviado_e_ignorado(client, dados)     # valor_total=1 no form -> gravado 105.0

@pytest.mark.parametrize("kw,trecho", [
    ({"bairro": "Cruzeiro"}, "fora da área de cobertura"),
    ({"servicos": []}, "serviço"),
    ({"hora": "10:30"}, "horário"),
    ({"hora": "03:00"}, "horário"),
    ({"data": "2020-01-01"}, ""),
    ({"data": "amanhã"}, "inválido"),
    ({"pet_id": "luna"}, ""),
    ({"endereco": ""}, "endereço"),
    ({"forma_pagamento": "Cheque"}, ""),
])
def test_agendar_invalido(client, dados, kw, trecho):
    # status 400, `trecho` aparece no HTML (sem distinguir maiúsculas), Agendamento.count() == 0

def test_slot_cheio(client, dados)                   # 2º POST igual -> 400, count == 1
def test_api_horarios(client, dados)                 # 10 itens; após agendar às 10:00, "10:00" livre False
def test_api_horarios_sem_login(client, dados)       # 401
@pytest.mark.parametrize("qs", ["tipo=X&data=2026-03-03", "tipo=DOMICILIO_MOVEL&data=ontem", ""])
def test_api_horarios_invalido(client, dados, qs)    # 400

def test_abas_ativos_e_historico(client, dados)      # 1 Pendente e 1 Concluído no banco: ambos na página,
                                                     # "Cancelar" aparece uma única vez
def test_nao_ve_agendamento_alheio(client, dados)    # agendamento de maria não aparece para cliente
def test_cliente_cancela(client, dados)              # POST acao=cancelar -> Cancelado
def test_cliente_nao_cancela_alheio(client, dados)   # 404; status inalterado
def test_cliente_nao_confirma_por_post(client, dados)  # acao=confirmar -> status continua Pendente
def test_next_externo_ignorado(client, dados)        # next=https://evil.example -> Location /meus-agendamentos

def test_sino_e_notificacoes(client, dados):
    # após agendar: GET / mostra contador 1; GET /notificacoes mostra a mensagem
    # POST /notificacoes/ler -> todas lidas; contador some
def test_notificacoes_sao_do_usuario(client, dados)  # notificação de maria não aparece para cliente
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `pytest tests/test_agendar.py -q`
Expected: FAIL.

- [ ] **Step 3: Implementar rotas, templates e `initAgendar`**

- [ ] **Step 4: Rodar e ver passar**

Run: `pytest -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: agendamento reativo, meus agendamentos e notificações"
```

---

### Task 8: Painel do prestador

**Files:**
- Modify: `app.py`
- Create: `templates/painel.html`, `tests/test_painel.py`

**Interfaces:**
- Consumes: `resumo_do_dia`, `agenda_do_dia`, `acoes_disponiveis`, rota `POST /agendamentos/<id>/acao` da Task 7.
- Produces: `GET /painel?data=<AAAA-MM-DD>&tipo=<todos|movel|loja>` (`prestador_required`).

Regras:
- `data` ausente ou inválida vira hoje; `tipo` ausente ou inválido vira `todos`.
- Quatro cards: Total de Atendimentos, Pendentes de Aprovação, Em Loja Física, Em Unidade Móvel (de `resumo_do_dia`, sempre do dia inteiro, independentes do filtro de modalidade).
- Filtros: campo de data, botões dia anterior / hoje / próximo dia, seletor de modalidade (Todos, Unidade Móvel / Veículo, Loja Física).
- Cada agendamento mostra: horário, modalidade, `badge_status`, endereço e bairro (se domicílio), tutor (nome e telefone), pet (nome, espécie, porte), bloco de alerta vermelho com as restrições quando houver, serviços, duração total, forma de pagamento, valor total, recurso alocado, e um formulário `POST` por ação de `acoes_disponiveis`, com `next` apontando para a URL atual do painel.
- Ações que levam a Cancelado pedem confirmação no navegador.
- Dia sem agendamentos mostra uma mensagem de lista vazia.

- [ ] **Step 1: Escrever os testes que falham**

```python
def test_painel_exige_prestador(client, dados)       # visitante -> /login; cliente -> /
def test_cards_do_dia(client, dados)                 # 1 MOVEL Pendente + 1 LOJA Confirmado hoje:
                                                     # atributos data-card="total">2, "pendentes">1, "loja">1, "movel">1
def test_mostra_alerta_de_restricao(client, dados)   # "Alergia a shampoo perfumado" presente
def test_filtro_modalidade(client, dados)            # ?tipo=loja esconde "Rua A, 10"; ?tipo=movel mostra
def test_filtro_data(client, dados)                  # ?data=<outro dia> não lista os de hoje
def test_data_invalida_vira_hoje(client, dados)      # ?data=xyz -> 200
def test_botoes_contextuais(client, dados):
    # Pendente: value="confirmar" e value="recusar" presentes; value="concluir" ausente
def test_fluxo_completo_por_post(client, dados):
    # confirmar, iniciar_deslocamento, iniciar_atendimento, concluir via POST -> Concluído;
    # cliente recebeu ao menos 4 notificações
def test_transicao_forjada_nao_altera(client, dados) # acao=concluir em Pendente -> continua Pendente;
                                                     # a página seguinte contém a mensagem de erro
def test_acao_volta_para_o_filtro(client, dados)     # next=/painel?tipo=loja -> Location igual
```

Os cards levam um atributo `data-card="<chave>"` para o teste localizar o número.

- [ ] **Step 2: Rodar e ver falhar**

Run: `pytest tests/test_painel.py -q`
Expected: FAIL.

- [ ] **Step 3: Implementar rota e template**

- [ ] **Step 4: Rodar e ver passar**

Run: `pytest -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: painel do prestador com agenda e máquina de estados"
```

---

### Task 9: Gestão básica (CRUD auxiliar)

**Files:**
- Modify: `app.py`
- Create: `templates/gestao.html`, `tests/test_gestao.py`

**Interfaces:**
- Consumes: modelos; `prestador_required`.
- Produces (todas `prestador_required`):
  - `GET /gestao?aba=<servicos|bairros|unidades|postos>` (padrão `servicos`)
  - `POST /gestao/<recurso>/novo`
  - `POST /gestao/<recurso>/<int:id>/editar`
  - `POST /gestao/<recurso>/<int:id>/alternar` (inverte `ativo`; 404 para `servicos`)
  - `POST /gestao/<recurso>/<int:id>/excluir`
  - `recurso` fora da lista ou id inexistente: 404. Todas redirecionam para `/gestao?aba=<recurso>`.

Campos por recurso (todos obrigatórios, sem espaços nas pontas):

| `recurso` | Modelo | Campos |
|---|---|---|
| `servicos` | `Servico` | `nome_servico`, `descricao`, `preco_base` (> 0, aceita vírgula decimal), `duracao_minutos` (inteiro > 0) |
| `bairros` | `BairroCobertura` | `nome_bairro` (único, sem distinguir maiúsculas); novo bairro nasce ativo |
| `unidades` | `UnidadeMovel` | `modelo`, `placa`, `profissional_responsavel`; nasce ativa |
| `postos` | `PostoFixo` | `identificacao_mesa`, `responsavel_setor`; nasce ativo |

Regras:
- As quatro rotas são uma implementação só, dirigida por um dicionário de configuração por recurso (modelo, campos, validadores).
- Dado inválido: flash `erro` com o motivo e nada é gravado.
- Excluir serviço presente em `AgendamentoServico`, ou unidade/posto referenciado por `Agendamento`: bloqueado com flash `erro` sugerindo desativar. Bairro pode ser excluído sempre.
- Tela: abas por link (`?aba=`); cada aba tem a tabela dos registros com edição na própria linha, botão de ativar/desativar (com selo Ativo/Inativo), excluir com confirmação, e um formulário de novo registro.

- [ ] **Step 1: Escrever os testes que falham**

```python
def test_gestao_exige_prestador(client, dados)        # cliente: GET -> 302 /; POST novo -> nada criado
@pytest.mark.parametrize("aba", ["servicos", "bairros", "unidades", "postos"])
def test_abas_renderizam(client, dados, aba)          # 200
def test_recurso_desconhecido(client, dados)          # POST /gestao/usuarios/novo -> 404
def test_cria_servico_aparece_na_home(client, dados)  # "Escovação Dental" 30,00 20 min -> listado em /
@pytest.mark.parametrize("preco,duracao", [("0", "30"), ("-5", "30"), ("abc", "30"), ("30", "0"), ("30", "x")])
def test_servico_invalido(client, dados, preco, duracao)  # Servico.count() inalterado
def test_preco_com_virgula(client, dados)             # "45,50" -> 45.5
def test_edita_servico(client, dados)                 # banho passa a 55.0
def test_exclui_servico_sem_uso(client, dados)
def test_nao_exclui_servico_em_uso(client, dados)     # banho usado em agendamento continua
def test_alternar_servico_404(client, dados)
def test_ativar_bairro_libera_cobertura(client, dados)  # alternar Cruzeiro -> bairro_coberto("Cruzeiro") e aparece em /
def test_bairro_duplicado(client, dados)              # "centro" -> recusado
def test_desativar_van_fecha_horarios(client, dados)  # alternar van -> horarios_disponiveis(TIPO_MOVEL, ...) todos False
def test_cria_e_alterna_posto(client, dados)          # "Baia 03" criada ativa; capacidade(TIPO_LOJA) == 3; alternar -> 2
def test_nao_exclui_van_em_uso(client, dados)         # van alocada em agendamento continua
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `pytest tests/test_gestao.py -q`
Expected: FAIL.

- [ ] **Step 3: Implementar rotas e template**

- [ ] **Step 4: Rodar e ver passar**

Run: `pytest -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: gestão de serviços, bairros, unidades móveis e postos fixos"
```

---

### Task 10: README e verificação ponta a ponta

**Files:**
- Create: `README.md`

**Interfaces:**
- Consumes: o sistema completo.

Conteúdo do `README.md`, nesta ordem:
1. Título "PetMóvel Itajubá — Sistema de Gestão e Agendamento Híbrido".
2. Autor: Lucas Pires Pivoto — Matrícula: `[INSIRA SUA MATRÍCULA]`. Disciplina: ECOT11A – Laboratório de Engenharia de Software I (UNIFEI). Entrega 2 — MVP testável.
3. Descrição da proposta (as duas modalidades, Itajubá-MG).
4. Funcionalidades implementadas, agrupadas em público, cliente e prestador.
5. Como executar: `git clone`, `cd`, ambiente virtual opcional, `pip install -r requirements.txt`, `python app.py`, abrir `http://127.0.0.1:5000`. Nota: requer internet para o Tailwind via CDN.
6. Tabela de credenciais de teste (perfil, e-mail, senha, observação).
7. Roteiro de teste sugerido em passos numerados: agendar como cliente, tentar o bairro Cruzeiro, confirmar e conduzir até Concluído como prestador, ver as notificações do cliente.
8. Arquitetura: tabela de arquivos, as 9 entidades, tabela da máquina de estados, regra de preço e regra de conflito.
9. Como rodar os testes (`pytest -q`) e como zerar os dados (apagar `petshop.db`).
10. Fora de escopo e decisões de projeto (as do documento de desenho).

- [ ] **Step 1: Escrever o `README.md`**

- [ ] **Step 2: Verificar a execução do zero**

Run: `rm -f petshop.db && python app.py` (em segundo plano), depois `curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:5000/`
Expected: `200`, e `petshop.db` criado na raiz.

- [ ] **Step 3: Percorrer o sistema num navegador real**

Com Playwright (já instalado no ambiente), num script fora do repositório: abrir a home; entrar como `cliente@teste.com`; em `/agendar`, escolher Thor, marcar dois serviços e conferir que o total exibido é `R$ 105,00`; escolher Domicílio + Cruzeiro e conferir o alerta e o botão desabilitado; trocar para BPS, escolher data de amanhã e um horário livre, confirmar; sair; entrar como `admin@petmovel.com`; no painel do dia de amanhã, clicar nas quatro ações até Concluído; voltar como cliente e conferir o histórico e o contador do sino. Capturar telas da home, do formulário de agendamento, de Meus Agendamentos, do painel e da gestão, e também da home em largura de celular (390 px).
Expected: nenhum erro no console do navegador, nenhum 500 no log do servidor, telas legíveis e sem quebra de layout. Corrigir o que aparecer, com teste quando for defeito de comportamento.

- [ ] **Step 4: Suíte completa**

Run: `pytest -q`
Expected: PASS, sem avisos de depreciação do SQLAlchemy vindos do código do projeto.

- [ ] **Step 5: Commit e push**

```bash
git add -A && git commit -m "docs: README da entrega e ajustes da verificação ponta a ponta"
git push -u origin claude/zen-brahmagupta-8dxe7c
```
