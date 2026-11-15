# PetMóvel Itajubá — Desenho do MVP (Entrega 2, ECOT11A)

Data: 2026-11-15 · Status: aprovado pelo autor

## Intenção

Entregar o MVP testável do sistema de agendamento e gestão de um pet shop
híbrido de Itajubá-MG (loja física + unidade móvel). O avaliador da disciplina
ECOT11A (UNIFEI) clona o repositório, roda `pip install -r requirements.txt` e
`python app.py`, e encontra o sistema já populado e utilizável.

## Objetivos

- Home pública: serviços, preços base, bairros atendidos, depoimentos.
- Cadastro/login com sessão e dois perfis: CLIENTE e PRESTADOR.
- Cliente: perfil, CRUD de pets, novo agendamento reativo, agendamentos ativos e
  histórico, central de notificações.
- Prestador: dashboard do dia, agenda filtrável por data e modalidade, botões da
  máquina de estados, gestão de serviços, bairros, unidades móveis e postos fixos.
- Preço calculado no front-end em tempo real e recalculado no back-end.
- Validação de cobertura de bairro e de conflito de horário.
- Notificação gravada no banco a cada mudança de status.
- Seed automático na primeira execução.

## Fora de escopo

Pagamento online, rastreamento GPS, folha de pagamento ou contabilidade.

## O que tornaria a entrega um fracasso

- Não rodar de primeira com apenas Python instalado.
- Exigir Node.js/npm ou qualquer etapa de build.
- Permitir uma transição de status inválida.
- Abrir vazio, sem dados para o avaliador navegar.

## Restrições

- Python 3.10+, Flask, Jinja2, Tailwind via CDN, JavaScript sem framework.
- SQLite (`petshop.db`) com SQLAlchemy; tabelas criadas automaticamente.
- Interface em português do Brasil.
- Tailwind via CDN exige internet na máquina do avaliador (aceito pelo autor).

## Abordagens consideradas

1. **App Flask único com Jinja2 (escolhida).** Sessão, flash e formulários já
   vêm prontos; poucos arquivos, fáceis de ler e avaliar.
2. **FastAPI com Jinja2.** Exigiria peças extras para sessão, formulários e
   mensagens flash, sem ganho para um app renderizado no servidor.
3. **Flask em pacote com blueprints.** Organização melhor para projetos grandes,
   mas excesso de estrutura para este tamanho.

## Estrutura

```
app.py        rotas, criação das tabelas, chamada do seed
models.py     as 9 tabelas
services.py   preço, disponibilidade, máquina de estados, notificações
seed.py       dados iniciais
templates/    home, login/cadastro, perfil, pets, agendar,
              meus agendamentos, notificações, painel, gestão
static/app.js formulário reativo
tests/        pytest: preço, transições, conflitos
README.md, requirements.txt, .gitignore
```

## Modelo de dados

As nove tabelas da especificação, com os campos nela descritos: Usuario, Pet,
Servico, BairroCobertura, UnidadeMovel, PostoFixo, Agendamento,
AgendamentoServico, Notificacao.

## Regras de negócio

**Preço.** `preco_base` × multiplicador do porte (Pequeno 1,0; Medio 1,25;
Grande 1,5), somado sobre os serviços escolhidos. O back-end recalcula e ignora
qualquer valor vindo do formulário. `preco_aplicado` guarda o valor por serviço.

**Máquina de estados.**

| De | Para | Quem | Condição |
|---|---|---|---|
| — | Pendente | Cliente | ao solicitar |
| Pendente | Confirmado | Prestador | bairro coberto (se domicílio) e recurso livre; aloca van ou baia |
| Pendente | Cancelado | Prestador ou Cliente | — |
| Confirmado | Em Deslocamento | Prestador | só DOMICILIO_MOVEL |
| Confirmado | Em Atendimento | Prestador | só PRESENCIAL_LOJA |
| Confirmado | Cancelado | Prestador ou Cliente | — |
| Em Deslocamento | Em Atendimento | Prestador | — |
| Em Atendimento | Concluído | Prestador | — |

Concluído e Cancelado são finais. Qualquer outra transição é recusada no
servidor, mesmo que a requisição seja forjada.

**Cobertura.** Agendamento em domicílio exige bairro ativo em BairroCobertura,
validado ao agendar e de novo ao confirmar.

## Decisões do construtor (não vieram da especificação)

1. **Horários em slots fixos de hora em hora, 08h–17h.** Cada slot comporta
   tantos atendimentos ativos (Pendente, Confirmado, Em Deslocamento, Em
   Atendimento) quantos recursos ativos da modalidade existirem. Um combo longo
   ocupa um slot só, conforme a "janela de 1 hora". O formulário consulta um
   endpoint JSON e mostra apenas os horários livres.
2. **Cadastro público cria apenas CLIENTE.** O prestador vem do seed.
3. **Exclusão protegida.** Pet ou serviço com agendamentos não pode ser apagado.
4. **Testes com pytest** para preço, transições e conflitos; `pytest` entra no
   `requirements.txt`.
5. **Autenticação sem Flask-Login:** sessão do Flask e decoradores próprios,
   com senha em hash do Werkzeug.
6. **`services.py`** além dos arquivos listados na especificação, para manter as
   regras de negócio fora das rotas e testáveis.
7. **Matrícula** fica como `[INSIRA SUA MATRÍCULA]` no README.

## Seed

Conforme a seção 6 da especificação: 1 prestador, 2 clientes, 3 pets, 5
serviços, 6 bairros (Cruzeiro inativo), 1 van, 2 baias e 4 agendamentos em
Pendente, Confirmado, Em Atendimento e Concluído. As datas dos agendamentos são
relativas ao dia da primeira execução, para a agenda do dia nunca abrir vazia.

## Deixado ao construtor

Visual (paleta, ícones, textos dos depoimentos), nomes das rotas, organização
interna dos templates e redação das mensagens.
