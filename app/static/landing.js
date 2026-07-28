const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];

const plans = {
  essencial: { name: 'Essencial', price: 'R$ 29,90/mês' },
  profissional: { name: 'Profissional', price: 'R$ 44,90/mês' },
  premium: { name: 'Premium', price: 'R$ 64,90/mês' }
};

const authModes = ['login', 'register', 'verification', 'forgot', 'reset', 'checkout'];
const modeElements = {
  login: '#login-form',
  register: '#register-form',
  verification: '#verification-step',
  forgot: '#forgot-form',
  reset: '#reset-form',
  checkout: '#checkout-step'
};
const modeHeadings = {
  login: 'auth-title',
  register: 'register-title',
  verification: 'verification-title',
  forgot: 'forgot-title',
  reset: 'reset-title',
  checkout: 'checkout-title'
};
const modeFocus = {
  login: '#email',
  register: '#register-name',
  verification: '#verification-resend',
  forgot: '#forgot-email',
  reset: '#reset-password',
  checkout: '.auth-panel'
};
const contextContent = {
  login: {
    eyebrow: 'ACESSO À OPERAÇÃO',
    title: 'Tudo o que acontece na sua barbearia, em um só painel.',
    description: 'Agenda, equipe, clientes e resultados protegidos pelo seu acesso.'
  },
  register: {
    eyebrow: 'SUA OPERAÇÃO COMEÇA AQUI',
    title: 'Uma base profissional para crescer com controle.',
    description: 'Escolha o plano, confirme seu e-mail e conclua o pagamento com segurança.'
  },
  verification: {
    eyebrow: 'ETAPA 2 DE 3',
    title: 'Seu acesso começa com um e-mail confirmado.',
    description: 'Essa verificação protege a conta e libera a próxima etapa do cadastro.'
  },
  forgot: {
    eyebrow: 'RECUPERAÇÃO SEGURA',
    title: 'Volte ao painel sem perder seus dados.',
    description: 'Enviaremos um link de uso único para o e-mail cadastrado.'
  },
  reset: {
    eyebrow: 'PROTEÇÃO DA CONTA',
    title: 'Uma senha longa é a melhor linha de defesa.',
    description: 'Use uma frase fácil para você lembrar e difícil para outras pessoas adivinharem.'
  },
  checkout: {
    eyebrow: 'ÚLTIMA ETAPA',
    title: 'Pagamento protegido, acesso liberado.',
    description: 'A Stripe processa sua assinatura. Os dados do cartão não passam pelo CortaFlow.'
  }
};

let toastTimer;
let pendingVerificationEmail = '';
let resetToken = '';
let lastFocusedElement = null;
let activeAuthMode = 'login';
let checkoutRetry = null;
let googleOAuthConfigured = false;

function announce(message) {
  $('#auth-live').textContent = '';
  window.setTimeout(() => {
    $('#auth-live').textContent = message;
  }, 20);
}

function toast(message) {
  const element = $('#toast');
  element.textContent = message;
  element.classList.add('show');
  clearTimeout(toastTimer);
  toastTimer = window.setTimeout(() => element.classList.remove('show'), 4600);
}

function setButtonLoading(button, loading, loadingLabel = 'Aguarde...') {
  if (!button) return;
  const label = $('.button-label', button);
  if (!button.dataset.idleLabel && label) button.dataset.idleLabel = label.textContent;
  button.disabled = loading;
  button.classList.toggle('is-loading', loading);
  button.setAttribute('aria-busy', String(loading));
  if (label) label.textContent = loading ? loadingLabel : button.dataset.idleLabel;
}

function setButtonLabel(button, label) {
  if (!button) return;
  const labelElement = $('.button-label', button);
  if (labelElement) labelElement.textContent = label;
  else button.textContent = label;
  button.dataset.idleLabel = label;
}

function clearMessage(selector) {
  const element = $(selector);
  element.textContent = '';
  element.classList.add('hidden');
}

function showMessage(selector, message) {
  const element = $(selector);
  element.textContent = message;
  element.classList.remove('hidden');
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
    throw new Error(detail || 'Não foi possível concluir agora. Tente novamente.');
  }
  return data;
}

async function loadPublicConfiguration() {
  try {
    const status = await api('/config/status');
    googleOAuthConfigured = Boolean(status?.google_oauth?.configured);
  } catch {
    googleOAuthConfigured = false;
  }
  $$('[data-google-login], [data-google-register]').forEach((button) => {
    button.setAttribute('aria-disabled', String(!googleOAuthConfigured));
  });
  updateGoogleRegisterButton();
  $$('[data-google-login]').forEach((button) => {
    const helper = $('small', button);
    if (helper) helper.textContent = googleOAuthConfigured ? 'Seguro' : 'Configurar';
  });
}

function selectedPlan() {
  return localStorage.getItem('selectedPlan') || 'profissional';
}

function planSummary(plan) {
  const item = plans[plan];
  return item ? `${item.name} · ${item.price}` : '';
}

function updateSelectedPlan(plan = selectedPlan()) {
  if (!plans[plan]) plan = 'profissional';
  const input = $(`#register-form input[name="plano"][value="${plan}"]`);
  if (input) input.checked = true;
  localStorage.setItem('selectedPlan', plan);
  updateGoogleRegisterButton(plan);
}

function updateGoogleRegisterButton(plan = selectedPlan()) {
  const button = $('[data-google-register]');
  if (!button) return;
  const selected = plans[plan] || plans.profissional;
  const helper = $('small', button);
  if (helper) helper.textContent = googleOAuthConfigured ? `Plano ${selected.name}` : 'Configurar Google';
}

function updateAuthContext(mode) {
  const content = contextContent[mode] || contextContent.login;
  $('#auth-context-eyebrow').textContent = content.eyebrow;
  $('#auth-context-title').textContent = content.title;
  $('#auth-context-description').textContent = content.description;
}

function showAuth(mode = 'login', { focus = true } = {}) {
  if (!authModes.includes(mode)) mode = 'login';
  const modal = $('#auth-modal');
  const wasClosed = modal.classList.contains('hidden');
  if (wasClosed) lastFocusedElement = document.activeElement;

  authModes.forEach((name) => {
    $(modeElements[name]).classList.toggle('hidden', name !== mode);
  });

  activeAuthMode = mode;
  $('.auth-panel').dataset.mode = mode;
  modal.setAttribute('aria-labelledby', modeHeadings[mode]);
  modal.classList.remove('hidden');
  document.body.classList.add('modal-open');
  $('.auth-content').scrollTop = 0;
  updateAuthContext(mode);
  if (mode === 'register') updateSelectedPlan();

  if (focus) {
    window.setTimeout(() => {
      const target = $(modeFocus[mode]);
      target?.focus({ preventScroll: true });
    }, 70);
  }
}

function closeAuth() {
  $('#auth-modal').classList.add('hidden');
  document.body.classList.remove('modal-open');
  if (lastFocusedElement instanceof HTMLElement) lastFocusedElement.focus({ preventScroll: true });
}

function showVerification(email, sent = true) {
  pendingVerificationEmail = email;
  $('#verification-email').textContent = email;
  const status = $('#email-sent-status');
  status.classList.toggle('failed', !sent);
  $('span', status).textContent = sent ? '✓' : '!';
  $('b', status).textContent = sent ? 'E-mail de confirmação enviado' : 'Não conseguimos enviar agora';
  $('small', status).textContent = sent
    ? 'Abra a mensagem para liberar o pagamento'
    : 'Use o botão abaixo para tentar novamente';
  setButtonLabel($('#verification-resend'), sent ? 'Reenviar e-mail' : 'Tentar enviar novamente');
  showAuth('verification');
  announce(sent ? 'E-mail de confirmação enviado.' : 'O e-mail não foi enviado. Tente novamente.');
}

function showPaymentNext(plan, verified = false) {
  const summary = planSummary(plan);
  if (!summary) return;
  $('#login-payment-next').classList.remove('hidden');
  $('#login-payment-next small').textContent = verified ? 'E-MAIL CONFIRMADO' : 'CONTA LOCALIZADA';
  $('#login-plan-summary').textContent = summary;
  setButtonLabel($('#login-form .form-submit'), 'Entrar e concluir assinatura');
}

function showCheckoutState(state, options = {}) {
  const defaults = {
    loading: {
      kicker: 'PAGAMENTO SEGURO',
      title: 'Preparando seu checkout.',
      description: 'Estamos conectando sua assinatura à Stripe.'
    },
    success: {
      kicker: 'PAGAMENTO CONFIRMADO',
      title: 'Sua assinatura está ativa.',
      description: 'Tudo certo. Estamos preparando seu painel.'
    },
    cancelled: {
      kicker: 'PAGAMENTO NÃO CONCLUÍDO',
      title: 'Você não foi cobrado.',
      description: 'O checkout foi fechado antes da confirmação. Seu plano continua reservado.'
    },
    error: {
      kicker: 'NÃO FOI POSSÍVEL CONCLUIR',
      title: 'Vamos tentar novamente.',
      description: 'Sua cobrança não foi confirmada. Revise a tentativa ou entre novamente.'
    }
  };
  const content = { ...defaults[state], ...options };
  const illustration = $('#checkout-illustration');
  illustration.dataset.state = state;
  $('#checkout-kicker').textContent = content.kicker;
  $('#checkout-title').textContent = content.title;
  $('#checkout-description').textContent = content.description;
  $('#checkout-error').textContent = content.error || '';

  const plan = content.plan || selectedPlan();
  const summary = planSummary(plan);
  $('#checkout-plan-summary').classList.toggle('hidden', !summary);
  $('#checkout-plan-summary strong').textContent = summary;

  const primary = $('#checkout-primary');
  primary.classList.toggle('hidden', !content.primaryLabel);
  if (content.primaryLabel) setButtonLabel(primary, content.primaryLabel);
  $('#checkout-login').classList.toggle('hidden', !content.showLogin);
  checkoutRetry = content.onPrimary || null;
  showAuth('checkout', { focus: state !== 'loading' });
  announce(`${content.title} ${content.description}`);
}

function cleanReturnUrl() {
  if (location.search) history.replaceState({}, '', location.pathname);
}

function closeMenu() {
  $('#site-nav').classList.remove('open');
  document.body.classList.remove('menu-open');
  $('#menu-toggle').setAttribute('aria-expanded', 'false');
  $('#menu-toggle').setAttribute('aria-label', 'Abrir menu');
  $('#menu-toggle').textContent = '☰';
}

function bindSiteNavigation() {
  window.addEventListener(
    'scroll',
    () => $('.site-header').classList.toggle('scrolled', scrollY > 24),
    { passive: true }
  );

  $('#menu-toggle').addEventListener('click', () => {
    const open = $('#site-nav').classList.toggle('open');
    document.body.classList.toggle('menu-open', open);
    $('#menu-toggle').setAttribute('aria-expanded', String(open));
    $('#menu-toggle').setAttribute('aria-label', open ? 'Fechar menu' : 'Abrir menu');
    $('#menu-toggle').textContent = open ? '×' : '☰';
  });

  $$('#site-nav a').forEach((link) => link.addEventListener('click', closeMenu));
  $$('[data-auth]').forEach((button) => {
    button.addEventListener('click', () => {
      closeMenu();
      showAuth(button.dataset.auth);
    });
  });
  $('#modal-close').addEventListener('click', closeAuth);
  $('#modal-backdrop').addEventListener('click', closeAuth);

  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') {
      if (!$('#auth-modal').classList.contains('hidden')) closeAuth();
      closeMenu();
      return;
    }
    if (event.key !== 'Tab' || $('#auth-modal').classList.contains('hidden')) return;
    const focusable = $$(
      'button:not([disabled]):not(.hidden), a[href], input:not([disabled]), [tabindex]:not([tabindex="-1"])',
      $(modeElements[activeAuthMode])
    ).filter((element) => element.offsetParent !== null);
    focusable.unshift($('#modal-close'));
    if (!focusable.length) return;
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  });
}

function passwordFeedback(value) {
  const length = value.length;
  if (!length) return { score: 0, color: '#b06a44', text: 'Use uma frase com 12 caracteres ou mais. Você pode colar do gerenciador.' };
  if (length < 12) {
    const missing = 12 - length;
    return { score: 24, color: '#a84c42', text: `Continue: faltam ${missing} ${missing === 1 ? 'caractere' : 'caracteres'}.` };
  }
  if (length < 16) return { score: 52, color: '#a87924', text: 'Boa. Uma frase mais longa fica ainda mais resistente.' };
  if (length < 24) return { score: 78, color: '#527a5c', text: 'Senha forte.' };
  return { score: 100, color: '#356b46', text: 'Senha muito forte.' };
}

function updatePasswordFeedback(input) {
  const feedback = $(`[data-password-strength="${input.id}"]`);
  if (!feedback) return;
  const result = passwordFeedback(input.value);
  feedback.style.setProperty('--strength', `${result.score}%`);
  feedback.style.setProperty('--strength-color', result.color);
  $('span', feedback).textContent = result.text;
}

function bindPasswordFields() {
  $$('[data-password-toggle]').forEach((button) => {
    button.addEventListener('click', () => {
      const input = document.getElementById(button.dataset.passwordToggle);
      const visible = input.type === 'text';
      input.type = visible ? 'password' : 'text';
      button.setAttribute('aria-pressed', String(!visible));
      button.setAttribute('aria-label', visible ? 'Mostrar senha' : 'Ocultar senha');
      $('span', button).textContent = visible ? 'Mostrar' : 'Ocultar';
      input.focus({ preventScroll: true });
    });
  });
  $$('[data-password-strength]').forEach((feedback) => {
    const input = document.getElementById(feedback.dataset.passwordStrength);
    input.addEventListener('input', () => updatePasswordFeedback(input));
  });
}

function bindPhoneFormatting() {
  $('#register-phone').addEventListener('input', (event) => {
    const digits = event.currentTarget.value.replace(/\D/g, '').slice(0, 11);
    if (digits.length <= 2) event.currentTarget.value = digits;
    else if (digits.length <= 6) event.currentTarget.value = `(${digits.slice(0, 2)}) ${digits.slice(2)}`;
    else if (digits.length <= 10) {
      event.currentTarget.value = `(${digits.slice(0, 2)}) ${digits.slice(2, 6)}-${digits.slice(6)}`;
    } else {
      event.currentTarget.value = `(${digits.slice(0, 2)}) ${digits.slice(2, 7)}-${digits.slice(7)}`;
    }
  });
}

async function resendVerification(email, button) {
  if (!email) {
    toast('Informe seu e-mail para reenviar.');
    return;
  }
  setButtonLoading(button, true, 'Enviando...');
  try {
    const result = await api('/auth/reenviar-confirmacao', {
      method: 'POST',
      body: JSON.stringify({ email })
    });
    toast(result.message);
    if (!$('#verification-step').classList.contains('hidden')) {
      const status = $('#email-sent-status');
      status.classList.remove('failed');
      $('span', status).textContent = '✓';
      $('b', status).textContent = 'Novo e-mail solicitado';
      $('small', status).textContent = 'Confira a caixa de entrada e a pasta de spam';
      announce('Novo e-mail de confirmação solicitado.');
    }
  } catch (error) {
    toast(error.message);
  } finally {
    setButtonLoading(button, false);
  }
}

async function startCheckout(plan, sourceButton = null) {
  if (!plans[plan]) {
    toast('Escolha um plano válido para continuar.');
    return;
  }
  updateSelectedPlan(plan);
  if (sourceButton) sourceButton.disabled = true;
  showCheckoutState('loading', {
    title: 'Abrindo o pagamento seguro.',
    description: 'Você será direcionado à Stripe para concluir sua assinatura.',
    plan
  });
  try {
    const result = await api('/billing/checkout', {
      method: 'POST',
      body: JSON.stringify({ plan })
    });
    location.assign(result.url);
  } catch (error) {
    if (/Autenticação necessária|Token inválido|expirado/i.test(error.message)) {
      localStorage.removeItem('token');
      showAuth('login');
      showMessage('#verification-notice', 'Entre novamente para continuar com o plano escolhido.');
      showPaymentNext(plan);
    } else {
      showCheckoutState('error', {
        error: error.message,
        plan,
        primaryLabel: 'Tentar abrir a Stripe novamente',
        onPrimary: () => startCheckout(plan),
        showLogin: true
      });
    }
  } finally {
    if (sourceButton) sourceButton.disabled = false;
  }
}

async function completeCheckout(sessionId) {
  showCheckoutState('loading', {
    title: 'Confirmando sua assinatura.',
    description: 'A Stripe aprovou o retorno. Estamos liberando seu painel.'
  });
  try {
    const result = await api('/auth/concluir-pagamento', {
      method: 'POST',
      body: JSON.stringify({ session_id: sessionId })
    });
    localStorage.setItem('token', result.access_token);
    localStorage.setItem('name', result.nome || 'gestor');
    showCheckoutState('success', {
      title: 'Pagamento confirmado.',
      description: 'Sua conta está pronta. Abrindo o painel agora.'
    });
    window.setTimeout(() => location.assign('/painel?checkout=sucesso'), 900);
  } catch (error) {
    showCheckoutState('error', {
      error: error.message,
      primaryLabel: 'Confirmar pagamento novamente',
      onPrimary: () => completeCheckout(sessionId),
      showLogin: true
    });
  }
}

async function continueVerifiedSession(code, confirmedPlan, confirmedEmail) {
  showCheckoutState('loading', {
    kicker: 'E-MAIL CONFIRMADO',
    title: 'Preparando a última etapa.',
    description: 'Estamos abrindo o pagamento seguro do seu plano.',
    plan: confirmedPlan
  });
  try {
    const result = await api('/auth/confirmar-sessao', {
      method: 'POST',
      body: JSON.stringify({ code })
    });
    if (result.checkout_url) {
      location.assign(result.checkout_url);
      return;
    }
    localStorage.setItem('token', result.access_token);
    localStorage.setItem('name', result.nome || 'gestor');
    const plan = confirmedPlan || result.subscription_plan;
    if (result.subscription_required && plan) {
      await startCheckout(plan);
      return;
    }
    location.assign('/painel');
  } catch (error) {
    showAuth('login');
    if (confirmedEmail) $('#email').value = confirmedEmail;
    showMessage('#verification-notice', `${error.message} Entre com sua senha para continuar.`);
    if (confirmedPlan) showPaymentNext(confirmedPlan, true);
  }
}

async function handleReturnRoute() {
  const params = new URLSearchParams(location.search);
  const confirmation = params.get('email_confirmado');
  const confirmedEmail = params.get('email');
  const confirmedPlan = params.get('plan');
  const verificationCode = params.get('code');
  const checkout = params.get('checkout');
  const checkoutSessionId = params.get('session_id');
  const google = params.get('google');
  resetToken = params.get('reset_password') || '';

  if (confirmedPlan && plans[confirmedPlan]) updateSelectedPlan(confirmedPlan);

  if (google === 'conta_nao_encontrada') {
    cleanReturnUrl();
    showAuth('login');
    showMessage(
      '#verification-notice',
      'Este Google ainda não possui uma assinatura CortaFlow. Crie sua conta e conclua o pagamento primeiro.'
    );
    return;
  }

  if (google === 'checkout_cancelado') {
    cleanReturnUrl();
    showAuth('register');
    showMessage(
      '#register-error',
      'O cadastro com Google foi interrompido antes do pagamento. Seu plano continua selecionado e nenhuma cobranca foi feita.'
    );
    announce('Cadastro interrompido. Nenhuma cobranca foi feita.');
    return;
  }

  if (google === 'conta_existente') {
    cleanReturnUrl();
    showAuth('login');
    showMessage(
      '#verification-notice',
      'Este e-mail Google ja possui uma conta CortaFlow. Entre com o Google para acessar seu painel.'
    );
    announce('Conta existente encontrada. Entre com o Google.');
    return;
  }

  if (google === 'login_cancelado') {
    cleanReturnUrl();
    showAuth('login');
    showMessage('#verification-notice', 'O acesso com Google foi cancelado. Nenhuma alteracao foi feita.');
    announce('Acesso com Google cancelado.');
    return;
  }

  if (google) {
    const googleRegisterErrors = {
      plano_invalido: 'Nao foi possivel identificar o plano escolhido. Selecione um plano e tente novamente.',
      email_indisponivel: 'Este e-mail Google nao esta disponivel para um novo cadastro.',
      cadastro_cancelado: 'O cadastro com Google foi cancelado. Voce pode tentar novamente quando quiser.',
      cadastro_erro: 'Nao foi possivel iniciar seu cadastro com Google. Revise o plano e tente novamente.',
      erro_cadastro: 'Nao foi possivel concluir seu cadastro com Google. Tente novamente em instantes.',
      erro: 'O Google nao conseguiu concluir o cadastro. Tente novamente em instantes.'
    };
    cleanReturnUrl();
    showAuth('register');
    showMessage(
      '#register-error',
      googleRegisterErrors[google] || 'Nao foi possivel concluir o cadastro com Google. Tente novamente.'
    );
    announce('Nao foi possivel concluir o cadastro com Google.');
    return;
  }

  if (resetToken) {
    cleanReturnUrl();
    showAuth('reset');
    return;
  }

  if (checkout === 'sucesso' && checkoutSessionId) {
    cleanReturnUrl();
    await completeCheckout(checkoutSessionId);
    return;
  }

  if (checkout === 'sucesso') {
    cleanReturnUrl();
    showCheckoutState('success', {
      title: 'Assinatura confirmada.',
      description: 'Seu acesso está pronto.',
      primaryLabel: 'Abrir meu painel',
      onPrimary: () => location.assign('/painel')
    });
    return;
  }

  if (checkout === 'cancelado') {
    cleanReturnUrl();
    const plan = selectedPlan();
    showCheckoutState('cancelled', {
      plan,
      primaryLabel: 'Retomar pagamento',
      onPrimary: () => {
        if (localStorage.getItem('token')) startCheckout(plan);
        else {
          showAuth('login');
          showPaymentNext(plan);
        }
      },
      showLogin: true
    });
    return;
  }

  if (!confirmation) return;
  cleanReturnUrl();

  if (confirmation === 'sucesso' && verificationCode) {
    await continueVerifiedSession(verificationCode, confirmedPlan, confirmedEmail);
    return;
  }

  showAuth('login');
  if (confirmedEmail) $('#email').value = confirmedEmail;
  if (confirmation === 'sucesso') {
    showMessage('#verification-notice', 'E-mail confirmado. Entre para concluir sua assinatura.');
    $('#auth-title').textContent = 'E-mail confirmado.';
    $('#login-description').textContent = 'Falta apenas concluir o pagamento do plano escolhido.';
    if (confirmedPlan) showPaymentNext(confirmedPlan, true);
  } else {
    showMessage('#verification-notice', 'Este link é inválido ou expirou. Solicite uma nova confirmação.');
    $('#resend-verification').classList.remove('hidden');
  }
}

function bindAuthActions() {
  $('#forgot-password').addEventListener('click', () => {
    $('#forgot-email').value = $('#email').value.trim();
    clearMessage('#forgot-error');
    clearMessage('#forgot-notice');
    showAuth('forgot');
  });
  $('#forgot-back').addEventListener('click', () => showAuth('login'));
  $('#reset-back').addEventListener('click', () => showAuth('login'));
  $('#show-register').addEventListener('click', () => showAuth('register'));
  $('#show-login').addEventListener('click', () => showAuth('login'));
  $('#verification-login').addEventListener('click', () => {
    $('#email').value = pendingVerificationEmail;
    showAuth('login');
    showMessage('#verification-notice', 'Depois de confirmar pelo e-mail, entre para continuar ao pagamento.');
  });

  $$('[data-google-login]').forEach((button) => {
    button.addEventListener('click', () => {
      if (googleOAuthConfigured) {
        location.assign('/api/auth/google/iniciar');
        return;
      }
      toast('Login Google pronto. Falta configurar as credenciais no ambiente.');
    });
  });

  $$('[data-google-register]').forEach((button) => {
    button.addEventListener('click', () => {
      const plan = selectedPlan();
      clearMessage('#register-error');
      if (!googleOAuthConfigured) {
        toast('Cadastro com Google indisponivel enquanto as credenciais nao estiverem configuradas.');
        return;
      }
      const query = new URLSearchParams({ mode: 'register', plan });
      location.assign(`/api/auth/google/iniciar?${query.toString()}`);
    });
  });

  $('#checkout-primary').addEventListener('click', () => checkoutRetry?.());
  $('#checkout-login').addEventListener('click', () => showAuth('login'));

  $('#forgot-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    if (!form.checkValidity()) {
      form.reportValidity();
      return;
    }
    const button = $('[type="submit"]', form);
    clearMessage('#forgot-error');
    clearMessage('#forgot-notice');
    setButtonLoading(button, true, 'Enviando link...');
    try {
      const result = await api('/auth/esqueci-senha', {
        method: 'POST',
        body: JSON.stringify({ email: $('#forgot-email').value.trim() })
      });
      showMessage('#forgot-notice', result.message);
      setButtonLabel(button, 'Reenviar link');
      announce('Solicitação concluída. Confira seu e-mail.');
    } catch (error) {
      showMessage('#forgot-error', error.message);
    } finally {
      setButtonLoading(button, false);
    }
  });

  $('#reset-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    if (!form.checkValidity()) {
      form.reportValidity();
      return;
    }
    const button = $('[type="submit"]', form);
    const password = $('#reset-password').value;
    clearMessage('#reset-error');
    clearMessage('#reset-notice');
    if (password !== $('#reset-password-confirmation').value) {
      showMessage('#reset-error', 'As senhas não são iguais.');
      $('#reset-password-confirmation').focus();
      return;
    }
    if (!resetToken) {
      showMessage('#reset-error', 'Este link não é válido. Solicite uma nova recuperação de senha.');
      return;
    }
    setButtonLoading(button, true, 'Atualizando senha...');
    try {
      const result = await api('/auth/redefinir-senha', {
        method: 'POST',
        body: JSON.stringify({ token: resetToken, senha: password })
      });
      form.reset();
      updatePasswordFeedback($('#reset-password'));
      showMessage('#reset-notice', result.message);
      button.classList.add('hidden');
      $('#reset-back').textContent = 'Entrar com a nova senha';
      announce('Senha atualizada com sucesso.');
    } catch (error) {
      showMessage('#reset-error', error.message);
    } finally {
      setButtonLoading(button, false);
    }
  });

  $('#login-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    if (!form.checkValidity()) {
      form.reportValidity();
      return;
    }
    const button = $('[type="submit"]', form);
    clearMessage('#login-error');
    setButtonLoading(button, true, 'Entrando...');
    try {
      const result = await api('/auth/login', {
        method: 'POST',
        body: JSON.stringify({
          email: $('#email').value.trim(),
          senha: $('#password').value
        })
      });
      localStorage.setItem('token', result.access_token);
      localStorage.setItem('name', result.nome || 'gestor');
      if (result.subscription_required) {
        const plan = localStorage.getItem('selectedPlan') || result.subscription_plan;
        if (plan) await startCheckout(plan);
        else {
          closeAuth();
          $('#planos').scrollIntoView({ behavior: 'smooth' });
          toast('Escolha um plano para liberar seu painel.');
        }
      } else {
        location.assign('/painel');
      }
    } catch (error) {
      showMessage('#login-error', error.message);
      if (/Confirme seu e-mail/i.test(error.message)) {
        $('#resend-verification').classList.remove('hidden');
      }
    } finally {
      setButtonLoading(button, false);
    }
  });

  $('#register-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    if (!form.checkValidity()) {
      form.reportValidity();
      return;
    }
    const button = $('[type="submit"]', form);
    const data = Object.fromEntries(new FormData(form));
    data.nome = data.nome.trim();
    data.barbearia_nome = data.barbearia_nome.trim();
    data.email = data.email.trim();
    data.telefone = data.telefone.trim();
    updateSelectedPlan(data.plano);
    clearMessage('#register-error');
    setButtonLoading(button, true, 'Reservando seus dados...');
    try {
      const result = await api('/auth/register', {
        method: 'POST',
        body: JSON.stringify(data)
      });
      form.reset();
      showVerification(data.email, result.email_sent);
    } catch (error) {
      if (/já possui uma conta confirmada/i.test(error.message)) {
        $('#email').value = data.email;
        $('#auth-title').textContent = 'Sua conta já existe.';
        $('#login-description').textContent = 'Entre para continuar com o plano escolhido.';
        showMessage('#verification-notice', 'Seu e-mail já está confirmado. Não é necessário criar outra conta.');
        showPaymentNext(data.plano);
        showAuth('login');
      } else {
        showMessage('#register-error', error.message);
      }
    } finally {
      setButtonLoading(button, false);
    }
  });

  $('#resend-verification').addEventListener('click', () => {
    resendVerification($('#email').value.trim(), $('#resend-verification'));
  });
  $('#verification-resend').addEventListener('click', () => {
    resendVerification(pendingVerificationEmail, $('#verification-resend'));
  });
}

function bindPricing() {
  $$('[data-plan]').forEach((button) => {
    button.addEventListener('click', () => {
      const plan = button.dataset.plan;
      updateSelectedPlan(plan);
      if (localStorage.getItem('token')) startCheckout(plan, button);
      else showAuth('register');
    });
  });
  $$('#register-form input[name="plano"]').forEach((input) => {
    input.addEventListener('change', () => updateSelectedPlan(input.value));
  });
}

function initializeMotion() {
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
  const targets = $$('[data-reveal], .transform-grid article, .feature-card, .price-card, .proof-grid article, .security-list article');
  if (!targets.length) return;
  document.documentElement.classList.add('motion-ready');
  if (!('IntersectionObserver' in window)) {
    targets.forEach((target) => target.classList.add('is-visible'));
    return;
  }
  const observer = new IntersectionObserver((entries) => {
    entries.forEach((entry) => {
      if (!entry.isIntersecting) return;
      entry.target.classList.add('is-visible');
      observer.unobserve(entry.target);
    });
  }, { threshold: .14, rootMargin: '0px 0px -7% 0px' });
  requestAnimationFrame(() => targets.forEach((target) => observer.observe(target)));
}

async function initialize() {
  initializeMotion();
  bindSiteNavigation();
  bindPasswordFields();
  bindPhoneFormatting();
  bindAuthActions();
  bindPricing();
  await loadPublicConfiguration();
  await handleReturnRoute();
}

initialize();
