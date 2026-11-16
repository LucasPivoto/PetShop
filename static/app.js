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
