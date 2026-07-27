const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => document.querySelectorAll(selector);
let toastTimer;
let pendingVerificationEmail = '';
const planLabels = {
  essencial: 'Essencial — R$ 29,90/mês',
  profissional: 'Profissional — R$ 44,90/mês',
  premium: 'Premium — R$ 64,90/mês'
};

function toast(message) {
  const element = $('#toast');
  element.textContent = message;
  element.classList.add('show');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => element.classList.remove('show'), 4200);
}

async function api(path, options = {}) {
  const accessToken = localStorage.getItem('token');
  const response = await fetch('/api' + path, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
      ...(options.headers || {})
    }
  });
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = Array.isArray(data?.detail)
      ? String(data.detail[0]?.msg || '').replace(/^Value error,\s*/i, '')
      : data?.detail;
    throw new Error(detail || 'Não foi possível concluir agora.');
  }
  return data;
}

function updateSelectedPlan() {
  const plan = localStorage.getItem('selectedPlan');
  const input = plan && $(`#register-form input[name="plano"][value="${plan}"]`);
  if (input) input.checked = true;
}

function showAuth(mode = 'login') {
  const login = $('#login-form');
  const register = $('#register-form');
  const verification = $('#verification-step');
  login.classList.toggle('hidden', mode !== 'login');
  register.classList.toggle('hidden', mode !== 'register');
  verification.classList.toggle('hidden', mode !== 'verification');
  $('#auth-modal').classList.remove('hidden');
  document.body.classList.add('modal-open');
  if (mode === 'register') updateSelectedPlan();
  setTimeout(() => {
    if (mode === 'login') $('#email').focus();
    if (mode === 'register') $('#register-name').focus();
  }, 50);
}

function closeAuth() {
  $('#auth-modal').classList.add('hidden');
  document.body.classList.remove('modal-open');
}

function showVerification(email, sent = true) {
  pendingVerificationEmail = email;
  $('#verification-email').textContent = email;
  const status = $('#email-sent-status');
  status.classList.toggle('failed', !sent);
  status.querySelector('span').textContent = sent ? '✓' : '!';
  status.querySelector('b').textContent = sent ? 'E-mail enviado' : 'Não conseguimos enviar agora';
  status.querySelector('small').textContent = sent
    ? 'O link é válido por 24 horas'
    : 'Use o botão abaixo para tentar novamente';
  showAuth('verification');
}

function showPaymentNext(plan, verified = false) {
  const summary = planLabels[plan];
  if (!summary) return;
  $('#login-payment-next').classList.remove('hidden');
  $('#login-payment-next > span').textContent = verified ? '✓ E-mail confirmado' : '✓ Conta localizada';
  $('#login-plan-summary').textContent = summary;
  $('#login-form .form-submit').textContent = 'Entrar e ir para o pagamento';
}

function bindSiteNavigation() {
  const closeMenu = () => {
    $('#site-nav').classList.remove('open');
    document.body.classList.remove('menu-open');
    $('#menu-toggle').setAttribute('aria-expanded', 'false');
    $('#menu-toggle').setAttribute('aria-label', 'Abrir menu');
    $('#menu-toggle').textContent = '☰';
  };
  window.addEventListener('scroll', () => $('.site-header').classList.toggle('scrolled', scrollY > 24), { passive: true });
  $('#menu-toggle').onclick = () => {
    const open = $('#site-nav').classList.toggle('open');
    document.body.classList.toggle('menu-open', open);
    $('#menu-toggle').setAttribute('aria-expanded', String(open));
    $('#menu-toggle').setAttribute('aria-label', open ? 'Fechar menu' : 'Abrir menu');
    $('#menu-toggle').textContent = open ? '×' : '☰';
  };
  $$('#site-nav a').forEach((link) => {
    link.onclick = closeMenu;
  });
  $$('[data-auth]').forEach((button) => {
    button.onclick = () => {
      closeMenu();
      showAuth(button.dataset.auth);
    };
  });
  $('#modal-close').onclick = closeAuth;
  $('#modal-backdrop').onclick = closeAuth;
  document.addEventListener('keydown', (event) => {
    if (event.key !== 'Escape') return;
    closeAuth();
    closeMenu();
  });
}

async function bindAuth() {
  const params = new URLSearchParams(location.search);
  const confirmation = params.get('email_confirmado');
  const confirmedEmail = params.get('email');
  const confirmedPlan = params.get('plan');
  const verificationCode = params.get('code');
  const checkout = params.get('checkout');
  if (checkout === 'sucesso') toast('Assinatura confirmada. Bem-vindo ao CortaFlow!');
  if (checkout === 'cancelado') toast('Checkout cancelado. Nenhuma cobrança foi feita.');
  if (confirmation) {
    showAuth('login');
    if (confirmedEmail) $('#email').value = confirmedEmail;
    if (confirmedPlan && planLabels[confirmedPlan]) {
      localStorage.setItem('selectedPlan', confirmedPlan);
      showPaymentNext(confirmedPlan, confirmation === 'sucesso');
    }
    const notice = $('#verification-notice');
    notice.classList.remove('hidden');
    notice.textContent = confirmation === 'sucesso'
      ? 'E-mail confirmado com sucesso. Digite sua senha para seguir ao pagamento.'
      : 'Este link é inválido ou expirou. Solicite um novo link.';
    if (confirmation === 'sucesso') {
      $('#auth-title').textContent = 'E-mail confirmado!';
      $('#login-description').textContent = verificationCode
        ? 'Tudo certo. Estamos abrindo o pagamento seguro do seu plano.'
        : 'Entre para continuar com o plano escolhido e concluir o pagamento.';
    }
    if (confirmation !== 'sucesso') $('#resend-verification').classList.remove('hidden');
  }
  if (confirmation || checkout) history.replaceState({}, '', '/');

  if (confirmation === 'sucesso' && verificationCode) {
    const submit = $('#login-form .form-submit');
    submit.disabled = true;
    submit.textContent = 'Abrindo pagamento seguro...';
    try {
      const result = await api('/auth/confirmar-sessao', {
        method: 'POST',
        body: JSON.stringify({ code: verificationCode })
      });
      localStorage.setItem('token', result.access_token);
      localStorage.setItem('name', result.nome || 'gestor');
      const plan = confirmedPlan || result.subscription_plan;
      if (result.subscription_required && plan) {
        localStorage.setItem('selectedPlan', plan);
        await startCheckout(plan);
        return;
      }
      location.href = '/painel';
      return;
    } catch (error) {
      submit.disabled = false;
      submit.textContent = 'Entrar e ir para o pagamento';
      $('#verification-notice').textContent = `${error.message} Entre com sua senha para continuar.`;
      $('#verification-notice').classList.remove('hidden');
    }
  }

  $('#toggle-password').onclick = () => {
    const input = $('#password');
    input.type = input.type === 'password' ? 'text' : 'password';
    $('#toggle-password').textContent = input.type === 'password' ? 'Mostrar' : 'Ocultar';
  };
  $('#forgot-password').onclick = () => toast('A recuperação por e-mail será ativada com o Resend.');
  $('#show-register').onclick = () => showAuth('register');
  $('#show-login').onclick = () => showAuth('login');
  $$('[data-google-login]').forEach((button) => {
    button.onclick = () => toast(button.dataset.googleMode === 'register'
      ? 'Cadastro com Google será conectado em breve.'
      : 'Login com Google será conectado em breve.');
  });
  $('#verification-login').onclick = () => {
    $('#email').value = pendingVerificationEmail;
    showAuth('login');
    $('#verification-notice').textContent = 'Depois de confirmar pelo Gmail, entre para continuar ao pagamento.';
    $('#verification-notice').classList.remove('hidden');
  };

  $('#login-form').onsubmit = async (event) => {
    event.preventDefault();
    const button = event.currentTarget.querySelector('[type="submit"]');
    button.disabled = true;
    $('#login-error').textContent = '';
    try {
      const result = await api('/auth/login', {
        method: 'POST',
        body: JSON.stringify({ email: $('#email').value.trim(), senha: $('#password').value })
      });
      localStorage.setItem('token', result.access_token);
      localStorage.setItem('name', result.nome || 'gestor');
      if (result.subscription_required) {
        const plan = localStorage.getItem('selectedPlan') || result.subscription_plan;
        if (plan) await startCheckout(plan);
        else {
          closeAuth();
          document.querySelector('#planos').scrollIntoView({ behavior: 'smooth' });
          toast('Escolha um plano para liberar seu painel.');
        }
      } else {
        location.href = '/painel';
      }
    } catch (error) {
      $('#login-error').textContent = error.message;
      if (/Confirme seu e-mail/i.test(error.message)) $('#resend-verification').classList.remove('hidden');
    } finally {
      button.disabled = false;
    }
  };

  $('#register-form').onsubmit = async (event) => {
    event.preventDefault();
    if (!event.currentTarget.checkValidity()) return event.currentTarget.reportValidity();
    const button = event.currentTarget.querySelector('[type="submit"]');
    const data = Object.fromEntries(new FormData(event.currentTarget));
    localStorage.setItem('selectedPlan', data.plano);
    button.disabled = true;
    $('#register-error').textContent = '';
    try {
      const result = await api('/auth/register', { method: 'POST', body: JSON.stringify(data) });
      event.currentTarget.reset();
      showVerification(data.email, result.email_sent);
    } catch (error) {
      if (/já possui uma conta confirmada/i.test(error.message)) {
        $('#email').value = data.email;
        $('#auth-title').textContent = 'Sua conta já existe.';
        $('#login-description').textContent = 'Entre com sua senha para continuar com o plano escolhido.';
        $('#verification-notice').textContent = 'Não é necessário criar outra conta. Seu e-mail já está confirmado.';
        $('#verification-notice').classList.remove('hidden');
        showPaymentNext(data.plano);
        showAuth('login');
      } else {
        $('#register-error').textContent = error.message;
      }
    } finally {
      button.disabled = false;
    }
  };

  const resendVerification = async (email, button) => {
    if (!email) return void toast('Informe seu Gmail para reenviar.');
    button.disabled = true;
    try {
      const result = await api('/auth/reenviar-confirmacao', { method: 'POST', body: JSON.stringify({ email }) });
      toast(result.message);
      if (!$('#verification-step').classList.contains('hidden')) {
        const status = $('#email-sent-status');
        status.classList.remove('failed');
        status.querySelector('span').textContent = '✓';
        status.querySelector('b').textContent = 'Solicitação processada';
        status.querySelector('small').textContent = 'Confira sua caixa de entrada e a pasta de spam';
      }
    } catch (error) {
      toast(error.message);
    } finally {
      button.disabled = false;
    }
  };
  $('#resend-verification').onclick = () => resendVerification(
    $('#email').value.trim(), $('#resend-verification')
  );
  $('#verification-resend').onclick = () => resendVerification(
    pendingVerificationEmail, $('#verification-resend')
  );
}

function bindPricing() {
  $$('[data-plan]').forEach((button) => {
    button.onclick = () => {
      const plan = button.dataset.plan;
      localStorage.setItem('selectedPlan', plan);
      if (localStorage.getItem('token')) startCheckout(plan, button);
      else {
        updateSelectedPlan();
        showAuth('register');
      }
    };
  });
  $$('#register-form input[name="plano"]').forEach((input) => {
    input.onchange = () => localStorage.setItem('selectedPlan', input.value);
  });
}

async function startCheckout(plan, button = null) {
  const original = button?.innerHTML;
  if (button) {
    button.disabled = true;
    button.textContent = 'Abrindo checkout...';
  }
  try {
    const result = await api('/billing/checkout', {
      method: 'POST',
      body: JSON.stringify({ plan })
    });
    location.href = result.url;
  } catch (error) {
    if (/Autenticação necessária|Token inválido|expirado/i.test(error.message)) {
      localStorage.removeItem('token');
      showAuth('login');
      toast('Entre na sua conta para continuar a assinatura.');
    } else {
      toast(error.message);
    }
    if (button) {
      button.disabled = false;
      button.innerHTML = original;
    }
  }
}

bindSiteNavigation();
bindAuth();
bindPricing();
