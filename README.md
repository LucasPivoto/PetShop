# PetMóvel Itajubá — Sistema de Gestão e Agendamento Híbrido

**Autor:** Lucas Pires Pivoto — **Matrícula:** 2024014435
**Disciplina:** ECOT11A – Laboratório de Engenharia de Software I (UNIFEI)
**Entrega 2:** MVP testável via repositório GitHub

---

## 1. Proposta

O PetMóvel Itajubá é um sistema web que conecta tutores de animais de estimação a
um pet shop de Itajubá-MG que atende em duas modalidades ao mesmo tempo:

- **Loja física (presencial):** o tutor leva o pet até uma das baias do estabelecimento.
- **Domicílio (unidade móvel):** uma van equipada vai até o endereço do cliente,
  desde que o bairro esteja dentro da área de cobertura ativa.

O tutor cadastra os seus pets, monta o atendimento escolhendo um ou mais serviços e
vê o valor total na hora, calculado conforme o porte do animal. A equipe do pet shop
aprova a solicitação, aloca automaticamente uma van ou baia livre e conduz o
atendimento por uma máquina de estados, com o cliente notificado a cada etapa.

## 2. Como executar

Pré-requisito: **Python 3.10 ou superior**. Não é necessário Node.js nem etapa de build.

```bash
git clone https://github.com/LucasPivoto/PetShop.git
cd PetShop
```

Crie um ambiente virtual (recomendado; em distribuições Linux recentes é
necessário, porque o `pip` do sistema recusa instalações globais):

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
```

Instalar e rodar:

```bash
pip install -r requirements.txt
python app.py
```

Abra no navegador o endereço que aparece no terminal — normalmente
**http://127.0.0.1:5000**.

> **Porta 5000 bloqueada?** Em algumas máquinas, sobretudo no Windows, a porta 5000
> é reservada pelo sistema ou usada por outro programa (erro "Foi feita uma tentativa
> de acesso a um soquete de uma maneira que é proibida pelas permissões de acesso").
> O sistema detecta isso sozinho e sobe na próxima porta livre (8000, 8080 ou 5050),
> avisando no terminal qual endereço abrir. Para escolher a porta, defina a variável
> `PORT` antes de rodar — por exemplo, no PowerShell: `$env:PORT = "8123"`.

Na primeira execução o sistema cria o banco `petshop.db` e o popula sozinho com os
dados de demonstração. É preciso conexão com a internet, porque o Tailwind CSS e a
fonte são carregados via CDN.

## 3. Credenciais de teste

A senha de todas as contas é **`123456`**. Na tela de login, basta clicar em um dos
e-mails da caixa "Contas de demonstração" para preencher o formulário.

| Perfil | E-mail | Senha | Observação |
|---|---|---|---|
| Prestador (equipe) | `admin@petmovel.com` | `123456` | Acessa o painel e a gestão |
| Cliente (tutor) | `cliente@teste.com` | `123456` | Bairro BPS · pets Thor (Cão, Grande, com alergia) e Bob (Cão, Médio) |
| Cliente (tutor) | `maria@teste.com` | `123456` | Bairro Centro · pet Luna (Gato, Pequeno) |

## 4. Roteiro de teste sugerido

1. **Home pública:** veja serviços, preços, bairros atendidos e depoimentos sem login.
   Clique em "Agendar agora" e note o redirecionamento para o login.
2. **Entre como `cliente@teste.com`** e abra **Agendar**.
3. Escolha o pet **Thor** e marque **Banho Completo** e **Corte de Unhas**: o total
   mostra **R$ 105,00** (porte Grande, +50%). Troque para **Bob** e o total cai para
   R$ 87,50 (porte Médio, +25%).
4. Escolha **Domicílio** e o bairro **Cruzeiro**: aparece o alerta de área fora de
   cobertura e o botão de confirmar fica bloqueado. Troque para **BPS**.
5. Escolha data e um horário livre (os ocupados aparecem riscados), a forma de
   pagamento, e confirme. O agendamento nasce **Pendente** em "Meus Agendamentos".
6. **Saia e entre como `admin@petmovel.com`.** O painel mostra o resumo e a agenda
   do dia; use "Próximo dia" para chegar ao agendamento recém-criado.
7. Clique em **Confirmar (validar rota e escala)** — a van é alocada —, depois
   **Iniciar deslocamento**, **Chegada no local** e **Finalizar procedimentos**.
8. Em **Gestão → Bairros de Cobertura**, ative o Cruzeiro e veja que ele passa a
   aparecer na home e a ser aceito no agendamento.
9. **Volte como cliente:** o atendimento está no **Histórico** e o sino mostra as
   notificações de cada mudança de status.

## 5. Funcionalidades implementadas

**Área pública**
- Página inicial com catálogo de serviços (descrição, duração, preço base e
  multiplicador por porte), bairros atendidos pela unidade móvel e depoimentos.
- Cadastro e login com sessão; "Agendar" e "Meus Agendamentos" exigem autenticação.

**Cliente (tutor)**
- Edição do perfil e CRUD completo de pets (espécie, porte, restrições médicas).
- Agendamento reativo: preços por porte, soma de valor e duração em tempo real,
  validação de bairro, horários livres consultados no servidor, forma de pagamento.
- "Meus Agendamentos" com abas de ativos e histórico, badge de status e cancelamento
  enquanto o agendamento está Pendente ou Confirmado.
- Central de notificações com contador de não lidas no sino.

**Prestador (equipe)**
- Dashboard do dia: total de atendimentos, pendentes de aprovação, em loja física e
  em unidade móvel.
- Agenda e roteiro com filtro por data e modalidade, mostrando horário, endereço,
  tutor, pet (com alerta visual de restrições), serviços e pagamento.
- Botões de ação contextuais que só oferecem as transições válidas de cada estado.
- Gestão de serviços, bairros de cobertura, unidades móveis e postos fixos.

## 6. Arquitetura

Aplicação Flask única, renderizada no servidor com Jinja2, Tailwind CSS via CDN e
JavaScript sem framework. O banco é SQLite acessado por SQLAlchemy.

| Arquivo | Responsabilidade |
|---|---|
| `app.py` | Fábrica do app, autenticação, proteção CSRF e todas as rotas |
| `models.py` | As 9 tabelas e as constantes de domínio |
| `services.py` | Regras de negócio: preço, cobertura, disponibilidade, máquina de estados, notificações |
| `seed.py` | Dados iniciais, criados na primeira execução |
| `templates/` | Páginas Jinja2 (`base.html` traz navbar, sino e avisos) |
| `static/app.js` | Formulário reativo de agendamento, abas e avisos |
| `tests/` | Testes automatizados (pytest) |

As regras ficam em `services.py` e não dependem da requisição HTTP, o que permite
testá-las isoladamente; as rotas apenas as chamam.

### Entidades

`Usuario`, `Pet`, `Servico`, `BairroCobertura`, `UnidadeMovel`, `PostoFixo`,
`Agendamento`, `AgendamentoServico` (associação N:N que guarda o preço aplicado) e
`Notificacao`.

### Máquina de estados do agendamento

| De | Para | Quem | Condição |
|---|---|---|---|
| — | Pendente | Cliente | ao solicitar o agendamento |
| Pendente | Confirmado | Prestador | bairro coberto (se domicílio) e van ou baia livre, alocada automaticamente |
| Pendente | Cancelado | Prestador (recusa) ou Cliente | — |
| Confirmado | Em Deslocamento | Prestador | apenas domicílio |
| Confirmado | Em Atendimento | Prestador | apenas loja física |
| Confirmado | Cancelado | Cliente ou Prestador | — |
| Em Deslocamento | Em Atendimento | Prestador | chegada no local |
| Em Atendimento | Concluído | Prestador | — |

**Concluído** e **Cancelado** são estados finais. As transições vêm de uma única
tabela em `services.py`; qualquer combinação fora dela é recusada no servidor,
mesmo que a requisição seja forjada.

### Regras de cálculo e de conflito

- **Preço:** `preço base × multiplicador do porte` — Pequeno 1,0 · Médio 1,25 ·
  Grande 1,5 — somado sobre os serviços escolhidos. O navegador mostra o total em
  tempo real e o servidor sempre o recalcula, ignorando qualquer valor enviado.
  A conta é feita em centavos inteiros (meio centavo arredonda para cima) nos dois
  lados, para a tela e o banco nunca divergirem.
- **Horários:** slots de hora cheia, das 08:00 às 17:00. Cada slot comporta tantos
  atendimentos ativos (Pendente, Confirmado, Em Deslocamento, Em Atendimento)
  quantos recursos ativos da modalidade existirem — 1 van e 2 baias no seed. A
  janela de conflito é de 1 hora, independentemente da duração dos serviços.
- **Cobertura:** o bairro do atendimento em domicílio precisa estar ativo, o que é
  verificado ao agendar e novamente ao confirmar.
- **Antecedência:** o agendamento precisa ser para um horário futuro, com no máximo
  um ano de antecedência.

## 7. Testes

```bash
pytest -q
```

A suíte cobre o cálculo de preço (inclusive a igualdade entre o valor mostrado na
tela e o gravado pelo servidor), a disponibilidade, a matriz de status × ação da
máquina de estados, as permissões por perfil, o seed, as rotas e entradas inválidas
ou maliciosas. Um dos testes compara o cálculo do JavaScript com o do Python e só
roda se houver Node.js instalado; sem ele, é pulado.

Para **zerar os dados** e voltar ao estado inicial, apague o arquivo `petshop.db` e
rode `python app.py` de novo. Os agendamentos de exemplo são criados com datas
relativas ao dia dessa primeira execução; se o banco for reaproveitado em outro
dia, o painel de "hoje" abrirá vazio — use o filtro de data ou zere os dados.

## 8. Fora de escopo e decisões de projeto

**Fora de escopo:** pagamento online (o sistema apenas registra a opção escolhida —
Dinheiro, Cartão ou PIX — e o pagamento ocorre presencialmente), rastreamento GPS do
veículo e folha de pagamento ou contabilidade.

**Decisões:**
- O cadastro público cria apenas clientes; a conta da equipe vem do seed.
- Pet, serviço, van ou baia já usados em agendamentos não podem ser excluídos, para
  preservar o histórico; vans, baias e bairros podem ser desativados.
- Autenticação com a sessão do Flask e senha em hash (Werkzeug); formulários
  protegidos por token CSRF.
- Os depoimentos da página inicial são ilustrativos.
- A chave de sessão padrão serve apenas para execução local; em outro ambiente,
  defina a variável `SECRET_KEY`.
