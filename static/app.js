/* PetMóvel Itajubá — interatividade do front-end (JavaScript sem framework). */
(function () {
  'use strict';

  // --- Toasts: somem sozinhos e podem ser fechados -------------------------
  function fecharToast(toast) {
    toast.classList.add('opacity-0', '-translate-y-2');
    setTimeout(function () { toast.remove(); }, 300);
  }
  document.querySelectorAll('[data-toast]').forEach(function (toast) {
    setTimeout(function () { fecharToast(toast); }, 6000);
    var botao = toast.querySelector('[data-fechar-toast]');
    if (botao) botao.addEventListener('click', function () { fecharToast(toast); });
  });

  // --- Menu em telas pequenas ----------------------------------------------
  var alternarMenu = document.querySelector('[data-alternar-menu]');
  var menu = document.querySelector('[data-menu]');
  if (alternarMenu && menu) {
    alternarMenu.addEventListener('click', function () {
      var aberto = menu.classList.toggle('flex');
      menu.classList.toggle('hidden', !aberto);
      alternarMenu.setAttribute('aria-expanded', String(aberto));
    });
  }

  // --- Login: preencher com uma conta de demonstração ----------------------
  document.querySelectorAll('[data-preencher-login]').forEach(function (botao) {
    botao.addEventListener('click', function () {
      document.getElementById('email').value = botao.dataset.preencherLogin;
      document.getElementById('senha').value = '123456';
      document.getElementById('senha').focus();
    });
  });
})();

/* Formulários com data-confirmar pedem confirmação antes de enviar. */
document.addEventListener('submit', function (evento) {
  var mensagem = evento.target.dataset && evento.target.dataset.confirmar;
  if (mensagem && !window.confirm(mensagem)) evento.preventDefault();
});

/* Abas simples: botões [data-aba] mostram o painel [data-painel] de mesmo nome. */
document.querySelectorAll('[data-abas]').forEach(function (grupo) {
  var botoes = grupo.querySelectorAll('[data-aba]');
  function ativar(nome) {
    botoes.forEach(function (botao) {
      var ativo = botao.dataset.aba === nome;
      botao.setAttribute('aria-selected', String(ativo));
      botao.classList.toggle('bg-white', ativo);
      botao.classList.toggle('shadow-sm', ativo);
      botao.classList.toggle('text-marca-800', ativo);
      botao.classList.toggle('text-stone-500', !ativo);
    });
    document.querySelectorAll('[data-painel]').forEach(function (painel) {
      painel.classList.toggle('hidden', painel.dataset.painel !== nome);
    });
  }
  botoes.forEach(function (botao) {
    botao.addEventListener('click', function () { ativar(botao.dataset.aba); });
  });
  ativar(botoes[0].dataset.aba);
});

/* Formulário reativo de agendamento. `dados` vem do servidor (ver agendar.html). */
window.initAgendar = function (dados) {
  'use strict';
  var $ = function (id) { return document.getElementById(id); };
  var form = $('form-agendar');
  var selectPet = $('pet_id');
  var selectBairro = $('bairro');
  var campoEndereco = $('endereco');
  var campoData = $('data');
  var campoHora = $('hora');
  var botao = $('btn-confirmar');
  var caixasServico = Array.prototype.slice.call(form.querySelectorAll('input[name="servicos"]'));
  var radiosTipo = Array.prototype.slice.call(form.querySelectorAll('input[name="tipo"]'));
  var nomesPorte = { Pequeno: 'Pequeno', Medio: 'Médio', Grande: 'Grande' };
  var consultaAtual = 0;

  function moeda(valor) { return 'R$ ' + valor.toFixed(2).replace('.', ','); }
  function petAtual() {
    return dados.pets.find(function (p) { return String(p.id) === selectPet.value; });
  }
  function tipoAtual() {
    var marcado = radiosTipo.find(function (r) { return r.checked; });
    return marcado ? marcado.value : '';
  }
  // Mesmo cálculo do servidor: preço base × multiplicador do porte, 2 casas.
  function precoDe(servico, porte) {
    return Math.round(servico.preco_base * dados.multiplicadores[porte] * 100) / 100;
  }
  function bairroInativo() {
    var bairro = dados.bairros.find(function (b) { return b.nome === selectBairro.value; });
    return Boolean(bairro && !bairro.ativo);
  }

  function atualizarPrecos() {
    var pet = petAtual();
    if (!pet) return;
    var mult = dados.multiplicadores[pet.porte];
    $('porte-pet').textContent = nomesPorte[pet.porte];
    $('multiplicador-pet').textContent =
      mult === 1 ? 'preço base' : '+' + Math.round((mult - 1) * 100) + '% sobre o preço base';
    dados.servicos.forEach(function (servico) {
      var alvo = form.querySelector('[data-preco-servico="' + servico.id + '"]');
      if (alvo) alvo.textContent = moeda(precoDe(servico, pet.porte));
    });
  }

  function atualizarResumo() {
    var pet = petAtual();
    var tipo = tipoAtual();
    var total = 0;
    var duracao = 0;
    var selecionados = 0;
    var lista = $('resumo-servicos');
    lista.innerHTML = '';
    caixasServico.filter(function (c) { return c.checked; }).forEach(function (caixa) {
      var servico = dados.servicos.find(function (s) { return String(s.id) === caixa.value; });
      if (!servico || !pet) return;
      var preco = precoDe(servico, pet.porte);
      total += preco;
      duracao += servico.duracao;
      selecionados += 1;
      var item = document.createElement('li');
      item.className = 'flex justify-between gap-3';
      var nome = document.createElement('span');
      nome.textContent = servico.nome;
      var valor = document.createElement('span');
      valor.className = 'font-bold';
      valor.textContent = moeda(preco);
      item.appendChild(nome);
      item.appendChild(valor);
      lista.appendChild(item);
    });
    if (!selecionados) {
      lista.innerHTML = '<li class="text-stone-400">Nenhum serviço selecionado.</li>';
    }
    $('resumo-total').textContent = moeda(Math.round(total * 100) / 100);
    $('resumo-duracao').textContent = duracao + ' min';
    $('resumo-pet').textContent = pet ? pet.nome + ' · ' + nomesPorte[pet.porte] : '—';
    $('resumo-tipo').textContent =
      tipo === dados.tipoMovel ? 'Domicílio' : tipo === dados.tipoLoja ? 'Loja física' : '—';
    var partes = campoData.value ? campoData.value.split('-') : null;
    $('resumo-quando').textContent = partes && campoHora.value
      ? partes[2] + '/' + partes[1] + ' às ' + campoHora.value : '—';

    // O botão só libera quando não falta nada; a pendência é dita em texto.
    var pendencia = '';
    if (!selecionados) pendencia = 'Selecione ao menos um serviço.';
    else if (!tipo) pendencia = 'Escolha a modalidade.';
    else if (tipo === dados.tipoMovel && bairroInativo()) pendencia = 'Bairro fora da área de cobertura.';
    else if (!campoHora.value) pendencia = 'Escolha um horário disponível.';
    botao.disabled = Boolean(pendencia);
    $('resumo-pendencia').textContent = pendencia;
  }

  function atualizarModalidade() {
    var domicilio = tipoAtual() === dados.tipoMovel;
    $('bloco-domicilio').classList.toggle('hidden', !domicilio);
    selectBairro.required = domicilio;
    campoEndereco.required = domicilio;
    var inativo = domicilio && bairroInativo();
    $('alerta-bairro').classList.toggle('hidden', !inativo);
    $('alerta-bairro-nome').textContent = selectBairro.value;
  }

  function desenharHorarios(horarios) {
    var area = $('slots');
    area.innerHTML = '';
    var selecionadoAindaLivre = false;
    horarios.forEach(function (h) {
      var b = document.createElement('button');
      b.type = 'button';
      b.textContent = h.hora;
      b.disabled = !h.livre;
      b.dataset.hora = h.hora;
      b.className = 'rounded-xl border px-2 py-2 text-sm font-extrabold transition ' +
        (h.livre ? 'border-stone-300 bg-white text-stone-800 hover:border-marca-500'
                 : 'cursor-not-allowed border-stone-200 bg-stone-100 text-stone-400 line-through');
      if (h.livre && h.hora === campoHora.value) selecionadoAindaLivre = true;
      b.addEventListener('click', function () {
        campoHora.value = h.hora;
        marcarHorario();
        atualizarResumo();
      });
      area.appendChild(b);
    });
    if (!selecionadoAindaLivre) campoHora.value = '';
    marcarHorario();
    var algumLivre = horarios.some(function (h) { return h.livre; });
    $('slots-aviso').textContent = algumLivre
      ? 'Horários riscados já estão ocupados ou já passaram.'
      : 'Não há horários livres nesta data. Tente outro dia ou outra modalidade.';
    atualizarResumo();
  }

  function marcarHorario() {
    $('slots').querySelectorAll('button').forEach(function (b) {
      var ativo = b.dataset.hora === campoHora.value;
      b.classList.toggle('!border-marca-600', ativo);
      b.classList.toggle('!bg-marca-600', ativo);
      b.classList.toggle('!text-white', ativo);
      b.setAttribute('aria-pressed', String(ativo));
    });
  }

  function buscarHorarios() {
    var tipo = tipoAtual();
    if (!tipo || !campoData.value) {
      $('slots').innerHTML = '';
      campoHora.value = '';
      $('slots-aviso').textContent = 'Escolha a modalidade e a data para ver os horários.';
      atualizarResumo();
      return;
    }
    var consulta = ++consultaAtual;
    $('slots-aviso').textContent = 'Consultando disponibilidade…';
    fetch('/api/horarios?tipo=' + encodeURIComponent(tipo) + '&data=' + encodeURIComponent(campoData.value))
      .then(function (r) { return r.json(); })
      .then(function (json) {
        if (consulta !== consultaAtual) return;  // resposta de uma consulta antiga
        desenharHorarios(json.horarios || []);
      })
      .catch(function () {
        if (consulta !== consultaAtual) return;
        $('slots').innerHTML = '';
        campoHora.value = '';
        $('slots-aviso').textContent = 'Não foi possível consultar os horários. Tente novamente.';
        atualizarResumo();
      });
  }

  selectPet.addEventListener('change', function () { atualizarPrecos(); atualizarResumo(); });
  caixasServico.forEach(function (c) { c.addEventListener('change', atualizarResumo); });
  radiosTipo.forEach(function (r) {
    r.addEventListener('change', function () { atualizarModalidade(); buscarHorarios(); });
  });
  selectBairro.addEventListener('change', function () { atualizarModalidade(); atualizarResumo(); });
  campoData.addEventListener('change', buscarHorarios);

  atualizarPrecos();
  atualizarModalidade();
  buscarHorarios();
};
