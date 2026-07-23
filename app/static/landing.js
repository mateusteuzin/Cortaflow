const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => document.querySelectorAll(selector);
let toastTimer;

function toast(message) {
  const element = $('#toast');
  element.textContent = message;
  element.classList.add('show');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => element.classList.remove('show'), 4200);
}

async function api(path, options = {}) {
  const response = await fetch('/api' + path, {
    ...options,
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) }
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

function showAuth(mode = 'login') {
  const login = $('#login-form');
  const register = $('#register-form');
  login.classList.toggle('hidden', mode !== 'login');
  register.classList.toggle('hidden', mode !== 'register');
  $('#auth-modal').classList.remove('hidden');
  document.body.classList.add('modal-open');
  setTimeout(() => (mode === 'login' ? $('#email') : $('#register-name')).focus(), 50);
}

function closeAuth() {
  $('#auth-modal').classList.add('hidden');
  document.body.classList.remove('modal-open');
}

function bindSiteNavigation() {
  const closeMenu = () => {
    $('#site-nav').classList.remove('open');
    $('#menu-toggle').setAttribute('aria-expanded', 'false');
    $('#menu-toggle').textContent = '☰';
  };
  window.addEventListener('scroll', () => $('.site-header').classList.toggle('scrolled', scrollY > 24), { passive: true });
  $('#menu-toggle').onclick = () => {
    const open = $('#site-nav').classList.toggle('open');
    $('#menu-toggle').setAttribute('aria-expanded', String(open));
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
  document.addEventListener('keydown', (event) => { if (event.key === 'Escape') closeAuth(); });
}

function bindAuth() {
  const params = new URLSearchParams(location.search);
  const confirmation = params.get('email_confirmado');
  const checkout = params.get('checkout');
  if (checkout === 'sucesso') toast('Assinatura confirmada. Bem-vindo ao CortaFlow!');
  if (checkout === 'cancelado') toast('Checkout cancelado. Nenhuma cobrança foi feita.');
  if (confirmation) {
    showAuth('login');
    const notice = $('#verification-notice');
    notice.classList.remove('hidden');
    notice.textContent = confirmation === 'sucesso'
      ? 'E-mail confirmado. Agora você já pode entrar.'
      : 'Este link é inválido ou expirou. Solicite um novo link.';
    if (confirmation !== 'sucesso') $('#resend-verification').classList.remove('hidden');
  }
  if (confirmation || checkout) history.replaceState({}, '', '/');

  $('#toggle-password').onclick = () => {
    const input = $('#password');
    input.type = input.type === 'password' ? 'text' : 'password';
    $('#toggle-password').textContent = input.type === 'password' ? 'Mostrar' : 'Ocultar';
  };
  $('#show-register').onclick = () => showAuth('register');
  $('#show-login').onclick = () => showAuth('login');

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
      location.href = '/painel';
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
    button.disabled = true;
    try {
      const result = await api('/auth/register', { method: 'POST', body: JSON.stringify(data) });
      event.currentTarget.reset();
      showAuth('login');
      $('#email').value = data.email;
      $('#verification-notice').textContent = result.message;
      $('#verification-notice').classList.remove('hidden');
      $('#resend-verification').classList.remove('hidden');
    } catch (error) {
      toast(error.message);
    } finally {
      button.disabled = false;
    }
  };

  $('#resend-verification').onclick = async () => {
    const email = $('#email').value.trim();
    if (!email) return void ($('#login-error').textContent = 'Informe seu Gmail acima.');
    const button = $('#resend-verification');
    button.disabled = true;
    try {
      const result = await api('/auth/reenviar-confirmacao', { method: 'POST', body: JSON.stringify({ email }) });
      $('#verification-notice').textContent = result.message;
      $('#verification-notice').classList.remove('hidden');
    } catch (error) {
      $('#login-error').textContent = error.message;
    } finally {
      button.disabled = false;
    }
  };
}

function bindPricing() {
  $$('[data-plan]').forEach((button) => {
    button.onclick = async () => {
      const original = button.innerHTML;
      button.disabled = true;
      button.textContent = 'Abrindo checkout...';
      try {
        const result = await api('/billing/checkout', {
          method: 'POST',
          body: JSON.stringify({ plan: button.dataset.plan })
        });
        location.href = result.url;
      } catch (error) {
        toast(error.message);
        button.disabled = false;
        button.innerHTML = original;
      }
    };
  });
}

bindSiteNavigation();
bindAuth();
bindPricing();
