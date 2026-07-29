const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => document.querySelectorAll(selector);
if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => navigator.serviceWorker.register('/sw.js').catch(() => {}));
}
const money = (value) => Number(value || 0).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });
const localDate = () => {
  const now = new Date();
  const offset = now.getTimezoneOffset() * 60000;
  return new Date(now.getTime() - offset).toISOString().slice(0, 10);
};
const escapeHTML = (value) => String(value ?? '').replace(/[&<>"']/g, (char) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;' }[char]));
const statusLabel = { agendado: 'Agendado', confirmado: 'Confirmado', em_andamento: 'Em andamento', concluido: 'Concluído', realizado: 'Concluído', cancelado: 'Cancelado', nao_compareceu: 'Não compareceu' };

let token = localStorage.getItem('token');
let barbers = [];
let products = [];
let services = [];
let shopProfile = null;
let businessHours = [];
let subscription = null;
let customerClients = [];
let financeExpenses = [];
let sessionContext = null;
let toastTimer;
let agendaWeekAnchor = null;
let agendaWeekDays = [];
let agendaWeekAppointments = [];
let appointmentCache = new Map();
let deferredInstallPrompt = null;

window.addEventListener('beforeinstallprompt', (event) => {
  event.preventDefault();
  deferredInstallPrompt = event;
  $$('[data-install-app]').forEach((button) => button.classList.add('install-ready'));
});

window.addEventListener('appinstalled', () => {
  deferredInstallPrompt = null;
  $$('[data-install-app]').forEach((button) => {
    button.classList.remove('install-ready');
    button.classList.add('is-installed');
    button.querySelector('span').textContent = 'Aplicativo instalado';
  });
  toast('CortaFlow instalado com sucesso.');
});

function setTheme(theme) {
  const dark = theme === 'dark';
  document.documentElement.dataset.theme = dark ? 'dark' : 'light';
  localStorage.setItem('cortaflow-theme', dark ? 'dark' : 'light');
  const button = $('#theme-toggle');
  if (!button) return;
  button.setAttribute('aria-pressed', String(dark));
  button.setAttribute('aria-label', dark ? 'Ativar modo claro' : 'Ativar modo escuro');
  button.querySelector('b').textContent = dark ? 'Claro' : 'Escuro';
}

function bindTheme() {
  const saved = localStorage.getItem('cortaflow-theme');
  const preferred = window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  setTheme(saved || preferred);
  $('#theme-toggle').onclick = () => setTheme(document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark');
}

async function api(path, options = {}) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 30000);
  try {
    const response = await fetch('/api' + path, {
      ...options,
      signal: controller.signal,
      headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}), ...(options.headers || {}) }
    });
    const contentType = response.headers.get('content-type') || '';
    const data = contentType.includes('application/json') ? await response.json() : null;
    if (response.status === 401 && path !== '/auth/login') {
      logout();
      throw new Error('Sessão expirada. Entre novamente.');
    }
    if (!response.ok) {
      const detail = Array.isArray(data?.detail)
        ? String(data.detail[0]?.msg || '').replace(/^Value error,\s*/i, '')
        : data?.detail;
      throw new Error(detail || 'Não foi possível concluir a operação.');
    }
    return data;
  } catch (error) {
    if (error.name === 'AbortError') throw new Error('A conexão demorou demais. Tente novamente.');
    if (error instanceof SyntaxError) throw new Error('A resposta do servidor não pôde ser lida.');
    throw error;
  } finally {
    clearTimeout(timer);
  }
}

async function uploadImage(file) {
  if (!(file instanceof File) || !file.size) return '';
  const body = new FormData();
  body.append('arquivo', file);
  const response = await fetch('/api/uploads/imagem', {
    method: 'POST',
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    body
  });
  const data = await response.json().catch(() => null);
  if (response.status === 401) logout();
  if (!response.ok) throw new Error(data?.detail || 'Não foi possível enviar a imagem.');
  return data.url;
}

function imageUploadField(name, current = '', label = 'Foto') {
  const preview = current ? `<img src="${escapeHTML(current)}" alt="Prévia da imagem">` : '<span>Escolher imagem</span>';
  return `<div class="upload-field">
    <span class="upload-label">${escapeHTML(label)}</span>
    <label class="upload-picker">
      <span class="upload-preview">${preview}</span>
      <span class="upload-copy"><b>Carregar da galeria</b><small>JPG, PNG ou WebP · máximo 5 MB</small></span>
      <input name="${name}_arquivo" type="file" accept="image/jpeg,image/png,image/webp">
    </label>
    <input name="${name}" type="hidden" value="${escapeHTML(current)}">
  </div>`;
}

function bindImagePreview() {
  const input = $('#modal-fields input[type="file"]');
  if (!input) return;
  input.onchange = () => {
    const file = input.files?.[0];
    if (!file) return;
    const preview = input.closest('.upload-picker').querySelector('.upload-preview');
    preview.innerHTML = `<img src="${URL.createObjectURL(file)}" alt="Prévia da imagem selecionada">`;
  };
}

function toast(message) {
  const element = $('#toast');
  element.textContent = message;
  element.classList.add('show');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => element.classList.remove('show'), 2800);
}

function logout() {
  localStorage.removeItem('token');
  localStorage.removeItem('name');
  token = null;
  location.replace('/');
}

function show(view) {
  $$('.view').forEach((element) => element.classList.toggle('hidden', element.id !== view));
  $$('nav button[data-view]').forEach((button) => button.classList.toggle('active', button.dataset.view === view));
  const label = { dashboard: 'Resumo do dia', agenda: 'Agenda', clientes: 'Clientes', barbeiros: 'Barbeiros', servicos: 'Serviços', produtos: 'Produtos', financeiro: 'Financeiro', relatorios: 'Relatórios', assinatura: 'Minha assinatura', conta: 'Minha conta' }[view] || 'Painel';
  $('#title').textContent = label;
  const breadcrumb = $('#breadcrumb-current');
  if (breadcrumb) breadcrumb.textContent = label;
  closeSidebar();
  const loaders = { agenda: loadAppointments, clientes: loadClients, servicos: loadServices, produtos: loadProducts, financeiro: loadFinance, relatorios: loadReports, assinatura: loadSubscription, conta: loadProfile };
  if (loaders[view]) loaders[view]().catch((error) => toast(error.message));
}

function closeSidebar() {
  $('.sidebar').classList.remove('open');
  $('#overlay').classList.remove('open');
  $('#menu').setAttribute('aria-expanded', 'false');
  document.body.classList.remove('sidebar-open');
}

function openSidebar() {
  $('.sidebar').classList.add('open');
  $('#overlay').classList.add('open');
  $('#menu').setAttribute('aria-expanded', 'true');
  document.body.classList.add('sidebar-open');
}

function bindAuth() {
  const confirmation = new URLSearchParams(location.search).get('email_confirmado');
  if (confirmation) {
    const notice = $('#verification-notice');
    notice.classList.remove('hidden');
    notice.textContent = confirmation === 'sucesso'
      ? 'E-mail confirmado! Agora você já pode entrar no painel.'
      : 'Este link é inválido ou expirou. Informe seu e-mail e solicite um novo link.';
    if (confirmation !== 'sucesso') $('#resend-verification').classList.remove('hidden');
    history.replaceState({}, '', '/');
  }
  $('#toggle-password').onclick = () => {
    const password = $('#password');
    const showing = password.type === 'text';
    password.type = showing ? 'password' : 'text';
    $('#toggle-password').textContent = showing ? 'Mostrar' : 'Ocultar';
    $('#toggle-password').setAttribute('aria-label', showing ? 'Mostrar senha' : 'Ocultar senha');
  };
  $('#forgot-password').onclick = () => toast('A recuperação por e-mail será ativada com o Resend.');
  $('#show-register').onclick = (event) => { event.preventDefault(); location.href = '/#planos'; };
  $('#show-login').onclick = (event) => { event.preventDefault(); $('#register-form').classList.add('hidden'); $('#login-form').classList.remove('hidden'); };
  $$('[data-google-login]').forEach((button) => {
    button.onclick = () => toast(button.dataset.googleMode === 'register'
      ? 'Cadastro com Google será conectado em breve.'
      : 'Login com Google será conectado em breve.');
  });
  $('#logout').onclick = logout;
  $('#login-form').onsubmit = async (event) => {
    event.preventDefault();
    const button = event.target.querySelector('button[type="submit"]');
    button.disabled = true;
    $('#login-error').textContent = '';
    try {
      const result = await api('/auth/login', { method: 'POST', body: JSON.stringify({ email: $('#email').value.trim(), senha: $('#password').value }) });
      token = result.access_token;
      localStorage.setItem('token', token);
      localStorage.setItem('name', result.nome || 'gestor');
      await start();
    } catch (error) {
      $('#login-error').textContent = error.message;
      if (/Confirme seu e-mail/i.test(error.message)) $('#resend-verification').classList.remove('hidden');
    } finally {
      button.disabled = false;
    }
  };
  $('#register-form').onsubmit = async (event) => {
    event.preventDefault();
    if (!event.target.checkValidity()) {
      event.target.reportValidity();
      return;
    }
    const button = event.target.querySelector('button[type="submit"]');
    const data = Object.fromEntries(new FormData(event.target));
    button.disabled = true;
    try {
      const result = await api('/auth/register', { method: 'POST', body: JSON.stringify(data) });
      event.target.reset();
      $('#register-notice').textContent = result.message;
      $('#register-notice').classList.remove('hidden');
      $('#login-form').classList.remove('hidden');
      $('#register-form').classList.add('hidden');
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
    if (!email) { $('#login-error').textContent = 'Informe seu Gmail acima para reenviar o link.'; return; }
    const button = $('#resend-verification');
    button.disabled = true;
    try {
      const result = await api('/auth/reenviar-confirmacao', { method: 'POST', body: JSON.stringify({ email }) });
      $('#verification-notice').textContent = result.message;
      $('#verification-notice').classList.remove('hidden');
    } catch (error) { $('#login-error').textContent = error.message; }
    finally { button.disabled = false; }
  };
}

function bindNavigation() {
  $$('nav button[data-view]').forEach((button) => { button.onclick = () => show(button.dataset.view); });
  $$('[data-go]').forEach((button) => { button.onclick = () => show(button.dataset.go); });
  $('#menu').onclick = () => $('.sidebar').classList.contains('open') ? closeSidebar() : openSidebar();
  $('#menu-close').onclick = closeSidebar;
  $('#overlay').onclick = closeSidebar;
  document.addEventListener('keydown', (event) => { if (event.key === 'Escape') closeSidebar(); });
  $('#agenda-date').onchange = () => { agendaWeekAnchor = startOfWeek(new Date($('#agenda-date').value + 'T12:00:00')); loadAppointments().catch((error) => toast(error.message)); };
  $('#agenda-professional-filter').onclick = (event) => {
    const button = event.target.closest('[data-agenda-professional]');
    if (!button) return;
    $('#agenda-barber').value = button.dataset.agendaProfessional;
    localStorage.setItem('agendaProfessional', button.dataset.agendaProfessional);
    renderAgendaCalendar();
  };
  $('#agenda-prev').onclick = () => { agendaWeekAnchor = addDays(agendaWeekAnchor || new Date($('#agenda-date').value + 'T12:00:00'), -7); $('#agenda-date').value = isoDate(agendaWeekAnchor); loadAppointments().catch((error) => toast(error.message)); };
  $('#agenda-next').onclick = () => { agendaWeekAnchor = addDays(agendaWeekAnchor || new Date($('#agenda-date').value + 'T12:00:00'), 7); $('#agenda-date').value = isoDate(agendaWeekAnchor); loadAppointments().catch((error) => toast(error.message)); };
  $('#agenda-today').onclick = () => { agendaWeekAnchor = new Date(); $('#agenda-date').value = localDate(); loadAppointments().catch((error) => toast(error.message)); };
  $('#account-logo-file').onchange = (event) => {
    const file = event.target.files?.[0];
    if (file) $('#account-logo-preview').src = URL.createObjectURL(file);
  };
  $('#account-form').onsubmit = saveProfile;
  $('#barber-account-form').onsubmit = saveBarberSelf;
  $('#barber-account-photo-file').onchange = (event) => {
    const file = event.target.files?.[0];
    if (file) $('#barber-account-photo-preview').src = URL.createObjectURL(file);
  };
  $('#copy-booking-link').onclick = copyBookingLink;
  $('#manage-subscription').onclick = openBillingPortal;
  $('#finance-export-xlsx').onclick = () => downloadFinancial('xlsx').catch((error) => toast(error.message));
  $('#finance-export-pdf').onclick = () => downloadFinancial('pdf').catch((error) => toast(error.message));
  $$('[data-subscription-plan]').forEach((button) => {
    button.onclick = () => chooseSubscription(button.dataset.subscriptionPlan, button);
  });
  document.addEventListener('click', (event) => {
    const actionButton = event.target.closest('[data-action]');
    if (!actionButton) return;
    const action = actionButton.dataset.action;
    const id = Number(actionButton.dataset.id);
    if (action === 'add-barber') openBarber();
    if (action === 'add-service') openService();
    if (action === 'add-product') openProduct();
    if (action === 'add-expense') openExpense();
    if (action === 'add-appointment') {
      const client = customerClients.find((item) => Number(item.id) === Number(actionButton.dataset.clientId));
      openAppointment(null, client ? {
        cliente_nome: client.nome || '',
        cliente_telefone: client.telefone || '',
        cliente_email: client.email || ''
      } : {});
    }
    if (action === 'edit-appointment') openAppointment(id);
    if (action === 'confirm') confirmAppointment(id);
    if (action === 'complete') concludeAppointment(id);
    if (action === 'no-show') markNoShow(id);
    if (action === 'cancel') cancelAppointment(id);
    if (action === 'remove-appointment') removeAppointment(id);
    if (action === 'edit-barber') openBarber(id);
    if (action === 'remove-barber') removeBarber(id);
    if (action === 'edit-service') openService(id);
    if (action === 'remove-service') removeService(id);
    if (action === 'edit-product') openProduct(id);
    if (action === 'remove-product') removeProduct(id);
    if (action === 'edit-expense') openExpense(id);
    if (action === 'remove-expense') removeExpense(id);
  });
}

function bindPricing() {
  $$('[data-plan]').forEach((button) => {
    button.onclick = async () => {
      button.disabled = true;
      const original = button.textContent;
      button.textContent = 'Abrindo checkout...';
      try {
        const result = await fetch('/api/billing/checkout', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ plan: button.dataset.plan })
        });
        const data = await result.json().catch(() => null);
        if (!result.ok) throw new Error(data?.detail || 'Não foi possível abrir o checkout.');
        window.location.href = data.url;
      } catch (error) {
        alert(error.message);
        button.disabled = false;
        button.textContent = original;
      }
    };
  });
}

async function start() {
  $('#login').classList.add('hidden');
  $('#app').classList.remove('hidden');
  const ownerName = (localStorage.getItem('name') || 'gestor').split(' ')[0];
  $('#owner-name').textContent = ownerName;
  const avatar = $('#topbar-avatar');
  if (avatar) avatar.textContent = ownerName.slice(0, 1).toUpperCase();
  $('#today').textContent = new Date().toLocaleDateString('pt-BR', { weekday: 'long', day: '2-digit', month: 'long' });
  $('#agenda-date').value = localDate();
  try {
    sessionContext = await api('/auth/contexto');
    localStorage.setItem('name', sessionContext.nome || 'gestor');
    applyAccessMode();
    await refreshPushStatus().catch(() => {
      setPushButton('Indisponível agora', 'Não foi possível consultar as notificações neste momento.', { disabled: true });
    });
    if (sessionContext.perfil === 'barbeiro') {
      await loadBarberSelf();
      show('conta');
      return;
    }
    await confirmCheckout();
    subscription = await api('/billing/subscription');
    if (!subscription.active) {
      document.body.classList.add('subscription-locked');
      show('assinatura');
      return;
    }
    document.body.classList.remove('subscription-locked');
    await Promise.all([loadBarbers(), loadServices(), loadProfile()]);
    await loadDashboard();
    if (location.hash === '#agenda') show('agenda');
  } catch (error) {
    if (/Sessão expirada|Autenticação|Token inválido/i.test(error.message)) {
      logout();
      return;
    }
    toast(error.message);
  }
}

async function confirmCheckout() {
  const params = new URLSearchParams(location.search);
  const checkout = params.get('checkout');
  const sessionId = params.get('session_id');
  if (checkout === 'sucesso' && sessionId) {
    await api('/billing/confirm', {
      method: 'POST',
      body: JSON.stringify({ session_id: sessionId })
    });
    localStorage.removeItem('selectedPlan');
    toast('Assinatura confirmada. Seu painel está liberado.');
  } else if (checkout === 'cancelado') {
    toast('Checkout cancelado. Nenhuma cobrança foi feita.');
  }
  if (checkout) history.replaceState({}, '', '/painel');
}

async function loadSubscription() {
  $('#subscription-loading').classList.remove('hidden');
  $('#subscription-content').classList.add('hidden');
  subscription = await api('/billing/subscription');
  renderAccountSubscription(subscription);
  const names = { essencial: 'Essencial', profissional: 'Profissional', premium: 'Premium' };
  const descriptions = {
    essencial: 'Agenda e gestão essenciais para um profissional.',
    profissional: 'Operação completa para equipes com até dois profissionais.',
    premium: 'Equipe ilimitada e visão avançada do negócio.'
  };
  const active = subscription.active;
  $('#subscription-plan-name').textContent = names[subscription.plan] || (active ? 'Acesso atual' : 'Sem assinatura');
  $('#subscription-description').textContent = descriptions[subscription.plan] || (active
    ? 'Sua conta existente continua com acesso liberado.'
    : 'Escolha um plano abaixo para liberar todos os recursos do painel.');
  const badge = $('#subscription-status-badge');
  badge.textContent = active ? (subscription.cancel_at_period_end ? 'CANCELAMENTO AGENDADO' : 'ASSINATURA ATIVA') : 'AGUARDANDO ASSINATURA';
  badge.classList.toggle('inactive', !active || subscription.cancel_at_period_end);
  const renewal = subscription.current_period_end ? new Date(subscription.current_period_end).toLocaleDateString('pt-BR') : '—';
  $('#subscription-renewal-date').textContent = renewal;
  $('#subscription-renewal-note').textContent = subscription.cancel_at_period_end
    ? 'O acesso permanece até esta data'
    : (subscription.current_period_end ? 'Renovação automática mensal' : 'Escolha um plano para iniciar');
  $('#manage-subscription').classList.toggle('hidden', !subscription.managed_by_stripe);
  $$('[data-subscription-card]').forEach((card) => {
    const current = active && card.dataset.subscriptionCard === subscription.plan;
    card.classList.toggle('current', current);
    const button = card.querySelector('[data-subscription-plan]');
    button.disabled = current;
    button.textContent = current ? 'Plano atual' : (subscription.managed_by_stripe ? 'Alterar plano' : 'Escolher plano');
  });
  $('#subscription-loading').classList.add('hidden');
  $('#subscription-content').classList.remove('hidden');
}

function subscriptionDate(value) {
  if (!value) return '';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '';
  return date.toLocaleDateString('pt-BR', { day: '2-digit', month: 'long', year: 'numeric' });
}

function renderAccountSubscription(data) {
  const names = { essencial: 'Plano Essencial', profissional: 'Plano Profissional', premium: 'Plano Premium' };
  const planName = names[data?.plan] || data?.plan_name || (data?.active ? 'Acesso ativo sem plano vinculado' : 'Sem assinatura ativa');
  const renewal = subscriptionDate(data?.current_period_end);
  const started = subscriptionDate(data?.started_at);
  const badge = $('#account-subscription-badge');
  $('#account-subscription-title').textContent = planName;
  $('#account-subscription-description').textContent = data?.plan
    ? `Sua assinatura ${names[data.plan] || data.plan_name || data.plan} está vinculada a esta conta.`
    : (data?.active
      ? `Seu acesso está liberado${started ? ` desde ${started}` : ''}, mas o plano de cobrança ainda não foi vinculado.`
      : 'Escolha um plano para ativar todos os recursos do CortaFlow.');
  badge.textContent = data?.active
    ? (data.cancel_at_period_end ? 'CANCELAMENTO AGENDADO' : 'ASSINATURA ATIVA')
    : 'ASSINATURA INATIVA';
  badge.classList.toggle('inactive', !data?.active || Boolean(data?.cancel_at_period_end));
  $('#account-subscription-date-label').textContent = data?.cancel_at_period_end ? 'ACESSO DISPONÍVEL ATÉ' : 'PRÓXIMA RENOVAÇÃO';
  $('#account-subscription-date').textContent = renewal || 'Não cadastrada';
  $('#account-subscription-note').textContent = renewal
    ? (data.cancel_at_period_end ? 'A assinatura não será renovada depois desta data.' : 'Consulte cobranças e renovação em Minha assinatura.')
    : (data?.managed_by_stripe
      ? 'Aguardando a Stripe informar o próximo ciclo.'
      : 'Renove ou vincule um plano em Minha assinatura.');
}

async function chooseSubscription(plan, button) {
  if (subscription?.managed_by_stripe) return openBillingPortal();
  const original = button.textContent;
  button.disabled = true;
  button.textContent = 'Abrindo checkout...';
  try {
    localStorage.setItem('selectedPlan', plan);
    const result = await api('/billing/checkout', {
      method: 'POST',
      body: JSON.stringify({ plan })
    });
    location.href = result.url;
  } catch (error) {
    button.disabled = false;
    button.textContent = original;
    toast(error.message);
  }
}

async function openBillingPortal() {
  const button = $('#manage-subscription');
  button.disabled = true;
  try {
    const result = await api('/billing/portal', { method: 'POST' });
    location.href = result.url;
  } catch (error) {
    button.disabled = false;
    toast(error.message);
  }
}

function applyShopBrand(profile) {
  if (!profile) return;
  $('#admin-shop-name').textContent = profile.nome;
  $('#admin-shop-logo').src = profile.logo_url || '/assets/cortaflow-icon-default.png';
  const bookingPath = `/agendar/${encodeURIComponent(profile.slug)}`;
  const bookingUrl = new URL(bookingPath, location.origin).href;
  $('#public-booking-link').href = bookingPath;
  $('#booking-link-value').value = bookingUrl;
  $('#open-booking-link').href = bookingPath;
}

async function copyBookingLink() {
  const value = $('#booking-link-value').value;
  try {
    if (navigator.clipboard?.writeText) await navigator.clipboard.writeText(value);
    else {
      $('#booking-link-value').select();
      document.execCommand('copy');
      window.getSelection()?.removeAllRanges();
    }
    toast('Link copiado com sucesso.');
  } catch (error) {
    toast('Não foi possível copiar. Selecione o link manualmente.');
  }
}

async function loadProfile() {
  if (sessionContext?.perfil === 'barbeiro') return loadBarberSelf();
  [shopProfile, businessHours, subscription] = await Promise.all([
    api('/barbearia/perfil'),
    api('/barbearia/horarios-funcionamento'),
    api('/billing/subscription')
  ]);
  renderAccountSubscription(subscription);
  applyShopBrand(shopProfile);
  const form = $('#account-form');
  ['nome', 'telefone', 'endereco', 'cnpj', 'logo_url'].forEach((name) => {
    form.elements[name].value = shopProfile[name] || '';
  });
  form.elements.email_notificacoes.value = shopProfile.email_notificacoes || '';
  form.elements.notificar_novos_agendamentos.checked = shopProfile.notificar_novos_agendamentos !== false;
  form.elements.public_booking_enabled.checked = shopProfile.public_booking_enabled !== false;
  $('#account-logo-preview').src = shopProfile.logo_url || '/assets/cortaflow-icon-default.png';
  renderBusinessHours();
}

function renderBusinessHours() {
  const dayNames = ['Segunda-feira', 'Terça-feira', 'Quarta-feira', 'Quinta-feira', 'Sexta-feira', 'Sábado', 'Domingo'];
  $('#business-hours-list').innerHTML = businessHours.map((item) => {
    const start = String(item.hora_inicio || '09:00').slice(0, 5);
    const end = String(item.hora_fim || '19:00').slice(0, 5);
    return `<div class="business-hour-row" data-day="${item.dia_semana}">
      <label class="business-day-toggle"><input type="checkbox" ${item.ativo ? 'checked' : ''}><span>${dayNames[item.dia_semana]}</span></label>
      <div class="business-time-fields ${item.ativo ? '' : 'is-closed'}">
        <label><span>Abre</span><input class="business-start" type="time" value="${start}" ${item.ativo ? '' : 'disabled'}></label>
        <i>até</i>
        <label><span>Fecha</span><input class="business-end" type="time" value="${end}" ${item.ativo ? '' : 'disabled'}></label>
      </div><strong class="business-closed">${item.ativo ? '' : 'Fechado'}</strong>
    </div>`;
  }).join('');
  $$('.business-day-toggle input').forEach((input) => {
    input.onchange = () => {
      const row = input.closest('.business-hour-row');
      row.querySelectorAll('input[type="time"]').forEach((field) => { field.disabled = !input.checked; });
      row.querySelector('.business-time-fields').classList.toggle('is-closed', !input.checked);
      row.querySelector('.business-closed').textContent = input.checked ? '' : 'Fechado';
    };
  });
}

function collectBusinessHours() {
  return Array.from($$('.business-hour-row')).map((row) => {
    const active = row.querySelector('.business-day-toggle input').checked;
    return { dia_semana: Number(row.dataset.day), ativo: active,
      hora_inicio: active ? row.querySelector('.business-start').value : null,
      hora_fim: active ? row.querySelector('.business-end').value : null };
  });
}

async function saveProfile(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const submit = form.querySelector('button[type="submit"]');
  const data = Object.fromEntries(new FormData(form));
  data.email_notificacoes = data.email_notificacoes.trim() || null;
  data.notificar_novos_agendamentos = form.elements.notificar_novos_agendamentos.checked;
  data.public_booking_enabled = form.elements.public_booking_enabled.checked;
  submit.disabled = true;
  $('#account-error').textContent = '';
  try {
    const file = $('#account-logo-file').files?.[0];
    if (file) data.logo_url = await uploadImage(file);
    shopProfile = await api('/barbearia/atualizar', { method: 'POST', body: JSON.stringify(data) });
    const hoursResult = await api('/barbearia/horarios-funcionamento', { method: 'PUT', body: JSON.stringify(collectBusinessHours()) });
    businessHours = hoursResult.horarios;
    renderBusinessHours();
    applyShopBrand(shopProfile);
    $('#account-logo-url').value = shopProfile.logo_url || '';
    $('#account-logo-file').value = '';
    toast('Dados e horários da barbearia atualizados');
  } catch (error) {
    $('#account-error').textContent = error.message;
  } finally {
    submit.disabled = false;
  }
}

async function loadBarbers() {
  barbers = await api('/barbearia/barbeiros');
  const active = barbers.filter((barber) => barber.ativo);
  $('#team-count').textContent = active.length;
  $('#agenda-barber').innerHTML = '<option value="">Todos os barbeiros</option>' + active.map((barber) => `<option value="${barber.id}">${escapeHTML(barber.nome)}</option>`).join('');
  const savedProfessional = localStorage.getItem('agendaProfessional') || '';
  $('#agenda-barber').value = active.some((barber) => String(barber.id) === savedProfessional) ? savedProfessional : '';
  renderAgendaProfessionalFilter([]);
  $('#barber-grid').innerHTML = barbers.map((barber) => {
    const emailReady = Boolean(barber.notification_email);
    const contact = barber.whatsapp || barber.telefone || 'Telefone não informado';
    return `<article class="media-card professional-card${barber.ativo ? '' : ' is-inactive'}"><div class="admin-card-photo professional-admin-photo">${barber.foto_url ? `<img src="${escapeHTML(barber.foto_url)}" alt="Foto de ${escapeHTML(barber.nome)}" loading="lazy">` : `<span>${escapeHTML(barber.nome.slice(0, 2).toUpperCase())}</span>`}<i class="photo-status"></i></div><div class="admin-card-body"><div class="professional-badges"><span class="badge">${barber.ativo ? 'Ativo' : 'Inativo'}</span><span class="notification-badge ${emailReady ? 'is-ready' : 'is-missing'}">${emailReady ? 'E-mail configurado' : 'E-mail não configurado'}</span></div><h3>${escapeHTML(barber.nome)}</h3><p>${escapeHTML(barber.cargo || 'Barbeiro')}</p><div class="professional-contacts"><span>${escapeHTML(barber.notification_email || 'Sem e-mail para avisos')}</span><span>${escapeHTML(contact)}</span></div><footer><b>${Number(barber.comissao_percentual)}% comissão</b><button class="link" type="button" data-action="edit-barber" data-id="${barber.id}">Editar</button>${barber.ativo ? `<button class="danger" type="button" data-action="remove-barber" data-id="${barber.id}">Desativar</button>` : ''}</footer></div></article>`;
  }).join('') || '<p class="empty">Adicione o primeiro profissional.</p>';
}

function isPwaInstalled() {
  return window.matchMedia('(display-mode: standalone)').matches || navigator.standalone === true;
}

function isAppleMobile() {
  return /iPhone|iPad|iPod/i.test(navigator.userAgent)
    || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
}

function openInstallInstructions() {
  const dialog = $('#pwa-install-dialog');
  const appleMobile = isAppleMobile();
  dialog.querySelector('[data-install-ios]').classList.toggle('hidden', !appleMobile);
  dialog.querySelector('[data-install-browser]').classList.toggle('hidden', appleMobile);
  if (typeof dialog.showModal === 'function') dialog.showModal();
  else dialog.setAttribute('open', '');
}

function bindPwaInstall() {
  const buttons = $$('[data-install-app]');
  if (!buttons.length) return;
  if (isPwaInstalled()) {
    buttons.forEach((button) => {
      button.classList.add('is-installed');
      button.querySelector('span').textContent = 'Aplicativo instalado';
    });
  }
  buttons.forEach((button) => {
    button.addEventListener('click', async () => {
      if (isPwaInstalled()) {
        toast('O CortaFlow já está instalado neste aparelho.');
        return;
      }
      if (!deferredInstallPrompt) {
        openInstallInstructions();
        return;
      }
      const promptEvent = deferredInstallPrompt;
      deferredInstallPrompt = null;
      button.classList.remove('install-ready');
      await promptEvent.prompt();
      const choice = await promptEvent.userChoice;
      if (choice.outcome === 'accepted') toast('Instalação iniciada.');
    });
  });
}

function urlBase64ToUint8Array(value) {
  const padding = '='.repeat((4 - value.length % 4) % 4);
  const base64 = (value + padding).replace(/-/g, '+').replace(/_/g, '/');
  const raw = atob(base64);
  return Uint8Array.from([...raw].map((character) => character.charCodeAt(0)));
}

function setPushButton(label, status, { disabled = false, active = false } = {}) {
  const button = $('#push-notifications');
  if (!button) return;
  button.querySelector('span').textContent = label;
  button.disabled = disabled;
  button.classList.toggle('is-active', active);
  $('#push-notification-status').textContent = status;
}

async function refreshPushStatus() {
  if (!$('#push-notifications')) return;
  if (!('serviceWorker' in navigator) || !('PushManager' in window) || !('Notification' in window)) {
    setPushButton('Não compatível', 'Este aparelho ou navegador não oferece notificações para PWA.', { disabled: true });
    return;
  }
  const config = await api('/push/config');
  if (!config.enabled) {
    setPushButton('Aguardando configuração', 'As chaves de notificação ainda precisam ser configuradas no servidor.', { disabled: true });
    return;
  }
  const registration = await navigator.serviceWorker.ready;
  const subscription = await registration.pushManager.getSubscription();
  if (subscription && Notification.permission === 'granted') {
    setPushButton('Notificações ativadas', 'Este aparelho receberá avisos de novos horários.', { active: true });
  } else if (Notification.permission === 'denied') {
    setPushButton('Permissão bloqueada', 'Libere as notificações nas configurações do navegador ou do aparelho.', { disabled: true });
  } else {
    setPushButton('Ativar notificações', 'Toque para permitir avisos mesmo com o aplicativo fechado.');
  }
}

async function togglePushNotifications() {
  const button = $('#push-notifications');
  if (!button || button.disabled) return;
  button.disabled = true;
  try {
    const config = await api('/push/config');
    if (!config.enabled) throw new Error('Notificações ainda não foram configuradas no servidor.');
    const registration = await navigator.serviceWorker.ready;
    let subscription = await registration.pushManager.getSubscription();
    if (subscription) {
      await api('/push/subscriptions', { method: 'DELETE', body: JSON.stringify(subscription.toJSON()) });
      await subscription.unsubscribe();
      setPushButton('Ativar notificações', 'Notificações desativadas neste aparelho.');
      return;
    }
    const permission = await Notification.requestPermission();
    if (permission !== 'granted') throw new Error('Permissão de notificação não concedida.');
    subscription = await registration.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: urlBase64ToUint8Array(config.public_key)
    });
    await api('/push/subscriptions', { method: 'POST', body: JSON.stringify(subscription.toJSON()) });
    setPushButton('Notificações ativadas', 'Este aparelho receberá avisos de novos horários.', { active: true });
    toast('Notificações ativadas neste aparelho');
  } catch (error) {
    toast(error.message);
    await refreshPushStatus().catch(() => {});
  } finally {
    button.disabled = false;
  }
}

function rememberAppointments(items) {
  items.forEach((item) => appointmentCache.set(Number(item.id), item));
}

function appointmentActionButton(action, id, icon, label, tone = '') {
  return `<button class="appointment-action ${tone}" type="button" data-action="${action}" data-id="${id}" title="${escapeHTML(label)}" aria-label="${escapeHTML(label)}"><span aria-hidden="true">${icon}</span><b>${escapeHTML(label)}</b></button>`;
}

function appointmentActions(appointment, compact = false) {
  const status = appointment.status || 'agendado';
  const id = appointment.id;
  if (status === 'cancelado' || status === 'nao_compareceu') {
    return appointmentActionButton('remove-appointment', id, '⌫', 'Apagar', 'danger');
  }
  if (['concluido', 'realizado'].includes(status)) return '<span class="appointment-completed">✓ Concluído</span>';
  const edit = appointmentActionButton('edit-appointment', id, '↻', 'Reagendar');
  const noShow = appointmentActionButton('no-show', id, '!', 'Não veio', 'warning');
  const cancel = appointmentActionButton('cancel', id, '×', 'Cancelar', 'danger');
  if (status === 'agendado') {
    return edit + appointmentActionButton('confirm', id, '✓', 'Confirmar', 'success') + noShow + cancel;
  }
  return edit + appointmentActionButton('complete', id, '✓', compact ? 'Concluir' : 'Concluir atendimento', 'success') + noShow + cancel;
}

function appointmentHTML(appointment) {
  const status = appointment.status || 'agendado';
  const actions = appointmentActions(appointment);
  return `<div class="appointment"><div class="appointment-time">${new Date(appointment.data_hora).toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' })}</div><div class="appointment-info"><b>${escapeHTML(appointment.cliente_nome)}</b><small><strong>Responsável:</strong> ${escapeHTML(appointment.barbeiro_nome || 'Equipe')} · ${escapeHTML(appointment.servico)} · ${money(appointment.preco)}</small></div><span class="badge status-${escapeHTML(status)}">${escapeHTML(statusLabel[status] || status)}</span><div class="appointment-actions">${actions}</div></div>`;
}

async function loadDashboard() {
  const today = localDate();
  const [report, appointments, dashboardProducts, dashboardClients] = await Promise.all([
    api('/relatorios/dia?data=' + today),
    api('/agendamentos?data=' + today),
    api('/produtos'),
    api('/relatorios/fidelidade')
  ]);
  rememberAppointments(appointments);
  $('#revenue').textContent = money(report.total.total);
  $('#cuts').textContent = report.total.cortes;
  const upcoming = appointments.filter((appointment) => new Date(appointment.data_hora) > new Date() && !['cancelado', 'concluido', 'realizado', 'nao_compareceu'].includes(appointment.status));
  $('#upcoming-count').textContent = upcoming.length;
  $('#upcoming').innerHTML = upcoming.slice(0, 6).map(appointmentHTML).join('') || `<div class="list-empty">
    <span class="list-empty-icon"><svg viewBox="0 0 24 24"><rect x="3" y="5" width="18" height="16" rx="2"/><path d="M16 3v4M8 3v4M3 10h18"/></svg></span>
    <b>Nenhum próximo atendimento hoje</b>
    <small>Sua agenda está livre. Que tal criar um novo agendamento agora?</small>
    <button class="button button-primary" type="button" data-action="add-appointment">+ Novo agendamento</button>
  </div>`;
  const nextAppointment = upcoming[0];
  $('#hero-next').textContent = nextAppointment
    ? new Date(nextAppointment.data_hora).toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' })
    : 'Agenda livre';
  $('#hero-next-detail').textContent = nextAppointment
    ? `${nextAppointment.cliente_nome} · ${nextAppointment.servico}`
    : 'nenhum atendimento próximo';
  $('#hero-pace').textContent = `${Number(report.total.cortes || 0)} realizado${Number(report.total.cortes || 0) === 1 ? '' : 's'}`;
  $('#hero-pace-detail').textContent = upcoming.length
    ? `${upcoming.length} horário${upcoming.length === 1 ? '' : 's'} ainda pela frente`
    : 'dia concluído ou agenda livre';

  const pending = upcoming.filter((appointment) => appointment.status === 'agendado');
  const lowStock = dashboardProducts.filter((product) => Number(product.quantidade_estoque) <= 3);
  const nearReward = dashboardClients.filter((client) => Number(client.cortes_para_premio) <= 2);
  const attention = [
    ...pending.slice(0, 2).map((appointment) => ({
      tone: 'warning',
      eyebrow: 'CONFIRMAÇÃO',
      title: appointment.cliente_nome,
      detail: `${new Date(appointment.data_hora).toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' })} · aguardando confirmação`,
      view: 'agenda'
    })),
    ...lowStock.slice(0, 2).map((product) => ({
      tone: 'stock',
      eyebrow: 'ESTOQUE BAIXO',
      title: product.nome,
      detail: `${Number(product.quantidade_estoque)} unidade${Number(product.quantidade_estoque) === 1 ? '' : 's'} restante${Number(product.quantidade_estoque) === 1 ? '' : 's'}`,
      view: 'produtos'
    })),
    ...nearReward.slice(0, 2).map((client) => ({
      tone: 'loyalty',
      eyebrow: 'FIDELIDADE',
      title: client.cliente_nome || client.cliente_telefone,
      detail: `falta${Number(client.cortes_para_premio) === 1 ? '' : 'm'} ${Number(client.cortes_para_premio)} corte${Number(client.cortes_para_premio) === 1 ? '' : 's'} para o prêmio`,
      view: 'clientes'
    }))
  ];
  $('#attention-count').textContent = attention.length;
  $('#attention-list').innerHTML = attention.slice(0, 5).map((item) => `
    <button class="attention-item ${item.tone}" type="button" data-attention-view="${item.view}">
      <i aria-hidden="true"></i>
      <span><small>${escapeHTML(item.eyebrow)}</small><b>${escapeHTML(item.title)}</b><em>${escapeHTML(item.detail)}</em></span>
      <strong aria-hidden="true">→</strong>
    </button>`).join('') || '<div class="attention-empty"><span>✓</span><b>Operação em dia</b><small>Nenhuma pendência encontrada agora.</small></div>';
  $$('[data-attention-view]').forEach((button) => { button.onclick = () => show(button.dataset.attentionView); });
}

async function loadAppointmentsLegacy() {
  let query = '?data=' + $('#agenda-date').value;
  if ($('#agenda-barber').value) query += '&barbeiro_id=' + $('#agenda-barber').value;
  const appointments = await api('/agendamentos' + query);
  $('#appointments').innerHTML = appointments.map(appointmentHTML).join('') || `<div class="list-empty">
    <span class="list-empty-icon"><svg viewBox="0 0 24 24"><rect x="3" y="5" width="18" height="16" rx="2"/><path d="M16 3v4M8 3v4M3 10h18"/></svg></span>
    <b>Agenda livre nesta data</b>
    <small>Não há atendimentos marcados para o dia selecionado.</small>
    <button class="button button-primary" type="button" data-action="add-appointment">+ Novo agendamento</button>
  </div>`;
}

const isoDate = (date) => { const d = new Date(date); const offset = d.getTimezoneOffset() * 60000; return new Date(d.getTime() - offset).toISOString().slice(0, 10); };
const addDays = (date, days) => { const next = new Date(date); next.setDate(next.getDate() + days); return next; };
const startOfWeek = (date) => { const d = new Date(date); d.setHours(12, 0, 0, 0); const day = d.getDay(); d.setDate(d.getDate() - (day === 0 ? 6 : day - 1)); return d; };
function renderAgendaProfessionalFilter(appointments) {
  const active = barbers.filter((barber) => barber.ativo);
  const selected = $('#agenda-barber').value;
  const option = (id, name, photo, count) => {
    const value = String(id);
    const isActive = selected === value;
    const initials = name.split(/\s+/).filter(Boolean).slice(0, 2).map((part) => part[0]).join('').toUpperCase();
    const avatar = photo ? `<img src="${escapeHTML(photo)}" alt="">` : `<span>${escapeHTML(initials)}</span>`;
    return `<button class="professional-filter-button ${isActive ? 'is-active' : ''}" type="button" data-agenda-professional="${escapeHTML(value)}" aria-pressed="${isActive}">
      <i class="professional-filter-avatar">${avatar}</i>
      <b>${escapeHTML(name)}</b>
      <small>${count} ${count === 1 ? 'horário' : 'horários'}</small>
      <em aria-hidden="true">✓</em>
    </button>`;
  };
  const all = option('', 'Toda a equipe', '', appointments.length);
  const professionals = active.map((barber) => option(
    barber.id,
    barber.nome,
    barber.foto_url,
    appointments.filter((item) => Number(item.barbeiro_id) === Number(barber.id)).length
  )).join('');
  $('#agenda-professional-filter').innerHTML = all + professionals;
}
async function loadAppointments() {
  const selected = new Date($('#agenda-date').value + 'T12:00:00'); agendaWeekAnchor = startOfWeek(selected);
  agendaWeekDays = Array.from({ length: 7 }, (_, index) => addDays(agendaWeekAnchor, index));
  agendaWeekAppointments = await api(`/agendamentos/semana?inicio=${isoDate(agendaWeekDays[0])}&fim=${isoDate(agendaWeekDays[6])}`);
  rememberAppointments(agendaWeekAppointments);
  renderAgendaCalendar();
}

function renderAgendaCalendar() {
  const days = agendaWeekDays;
  if (!days.length) return;
  const barber = $('#agenda-barber').value;
  renderAgendaProfessionalFilter(agendaWeekAppointments);
  const appointments = barber
    ? agendaWeekAppointments.filter((item) => Number(item.barbeiro_id) === Number(barber))
    : agendaWeekAppointments;
  $('#agenda-range').textContent = `${days[0].toLocaleDateString('pt-BR', { day: '2-digit', month: 'short' })} – ${days[6].toLocaleDateString('pt-BR', { day: '2-digit', month: 'short', year: 'numeric' })}`;
  const today = localDate(); const byDay = (day) => appointments.filter((item) => isoDate(new Date(item.data_hora)) === isoDate(day));
  const card = (item) => { const status = item.status || 'agendado'; return `<article class="agenda-card status-${escapeHTML(status)}"><div class="agenda-card-time">${new Date(item.data_hora).toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' })}</div><div class="agenda-card-body"><strong>${escapeHTML(item.cliente_nome)}</strong><span>${escapeHTML(item.servico || 'Atendimento')}</span><small><b>Responsável:</b> ${escapeHTML(item.barbeiro_nome || 'Equipe')} · ${Number(item.duracao_minutos || 30)} min · ${money(item.preco)}</small></div><span class="agenda-card-status">${escapeHTML(statusLabel[status] || status)}</span><div class="agenda-card-actions">${appointmentActions(item, true)}</div></article>`; };
  $('#agenda-week').innerHTML = days.map((day) => { const list = byDay(day); const key = isoDate(day); return `<div class="agenda-day ${key === today ? 'is-today' : ''}"><header><span>${day.toLocaleDateString('pt-BR', { weekday: 'short' }).replace('.', '')}</span><b>${day.getDate()}</b><small>${list.length} ${list.length === 1 ? 'atendimento' : 'atendimentos'}</small></header><div class="agenda-day-list">${list.map(card).join('') || '<div class="agenda-empty">Horários livres</div>'}</div></div>`; }).join('');
  $('#agenda-mobile-list').innerHTML = days.map((day) => { const list = byDay(day); const key = isoDate(day); return `<section class="agenda-mobile-day ${key === today ? 'is-today' : ''}"><h3>${day.toLocaleDateString('pt-BR', { weekday: 'long', day: '2-digit', month: 'long' })}</h3>${list.map(card).join('') || '<p class="agenda-empty">Horários livres</p>'}</section>`; }).join('');
}

function renderClients(query = '') {
  const normalized = query.trim().toLocaleLowerCase('pt-BR');
  const filtered = customerClients.filter((client) => {
    const searchable = `${client.nome || ''} ${client.telefone || ''} ${client.email || ''}`.toLocaleLowerCase('pt-BR');
    return searchable.includes(normalized);
  });
  $('#client-grid').innerHTML = filtered.map((client) => {
    const name = client.nome || client.telefone || 'Cliente';
    const initials = name.split(/\s+/).filter(Boolean).slice(0, 2).map((part) => part[0]).join('').toUpperCase();
    const visits = Number(client.total_visitas || 0);
    const spent = Number(client.total_gasto || 0);
    const next = client.proximo_agendamento ? new Date(client.proximo_agendamento) : null;
    const last = client.ultima_visita ? new Date(client.ultima_visita) : null;
    const daysSince = last ? Math.floor((Date.now() - last.getTime()) / 86400000) : null;
    const needsReturn = !next && daysSince !== null && daysSince >= 30;
    const digits = String(client.telefone || '').replace(/\D/g, '');
    const destination = digits.startsWith('55') ? digits : `55${digits}`;
    const message = encodeURIComponent(`Olá, ${name.split(' ')[0]}! Tudo bem? Aqui é da barbearia. Gostaria de agendar seu próximo horário?`);
    const whatsappStatus = {
      ENVIADO: 'Mensagem enviada', ENTREGUE: 'Mensagem entregue', LIDO: 'Mensagem lida',
      PENDENTE: 'Envio pendente', ENVIANDO: 'Enviando confirmação', FALHOU: 'Falha no WhatsApp'
    }[client.whatsapp_status] || '';
    const tag = next ? '<span class="client-tag scheduled">Agendado</span>'
      : needsReturn ? '<span class="client-tag return">Hora de retornar</span>'
      : visits === 0 ? '<span class="client-tag new">Novo cliente</span>' : '<span class="client-tag">Ativo</span>';
    return `<article class="client-card">
      <div class="client-card-head">
        <span class="client-avatar">${escapeHTML(initials)}</span>
        <div><h3>${escapeHTML(name)}</h3><p>${escapeHTML(client.telefone || 'Telefone não informado')}</p></div>
        ${tag}
      </div>
      <div class="client-facts">
        <span><small>Visitas</small><b>${visits}</b></span>
        <span><small>Total gasto</small><b>${money(spent)}</b></span>
        <span><small>Última visita</small><b>${last ? last.toLocaleDateString('pt-BR') : 'Ainda não veio'}</b></span>
        <span><small>Serviço habitual</small><b>${escapeHTML(client.ultimo_servico || client.proximo_servico || 'A descobrir')}</b></span>
      </div>
      ${next ? `<div class="client-next"><small>PRÓXIMO HORÁRIO</small><b>${next.toLocaleDateString('pt-BR')} às ${next.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' })}</b><span>${escapeHTML(client.proximo_servico || '')} · ${escapeHTML(client.barbeiro_nome || 'Equipe')}</span>${whatsappStatus ? `<em class="whatsapp-status status-${escapeHTML(String(client.whatsapp_status || '').toLowerCase())}">${escapeHTML(whatsappStatus)}</em>` : ''}</div>` : ''}
      <footer><a class="client-whatsapp" href="https://wa.me/${destination}?text=${message}" target="_blank" rel="noopener">Chamar no WhatsApp <span>↗</span></a><button type="button" data-action="add-appointment" data-client-id="${client.id}">Novo horário</button></footer>
    </article>`;
  }).join('') || `<div class="client-empty"><b>${normalized ? 'Nenhum cliente encontrado' : 'Sua base de clientes aparecerá aqui'}</b><span>${normalized ? 'Tente buscar por outro nome ou telefone.' : 'Os clientes entram automaticamente depois do primeiro agendamento.'}</span></div>`;
}

async function loadClients() {
  customerClients = await api('/clientes');
  const now = Date.now();
  const scheduled = customerClients.filter((client) => client.proximo_agendamento).length;
  const returnDue = customerClients.filter((client) => !client.proximo_agendamento && client.ultima_visita && (now - new Date(client.ultima_visita).getTime()) >= 30 * 86400000).length;
  const sent = customerClients.filter((client) => ['ENVIADO', 'ENTREGUE', 'LIDO'].includes(client.whatsapp_status)).length;
  $('#client-total').textContent = customerClients.length;
  $('#client-scheduled').textContent = scheduled;
  $('#client-return').textContent = returnDue;
  $('#client-whatsapp').textContent = sent;
  const search = $('#client-search');
  search.oninput = () => renderClients(search.value);
  renderClients(search.value);
}

function fields(html, title, handler) {
  const modal = $('#modal');
  $('#modal-title').textContent = title;
  $('#modal-fields').innerHTML = html;
  $('#modal-error').textContent = '';
  bindImagePreview();
  $('#modal-form').onsubmit = async (event) => {
    event.preventDefault();
    const submit = $('#modal-submit');
    submit.disabled = true;
    try {
      await handler(Object.fromEntries(new FormData(event.target)));
      modal.close();
      toast('Salvo com sucesso');
    } catch (error) {
      $('#modal-error').textContent = error.message;
    } finally {
      submit.disabled = false;
    }
  };
  modal.showModal();
}

function openBarber(id = null) {
  const barber = id ? barbers.find((item) => item.id === id) : null;
  if (id && !barber) return toast('Profissional não encontrado.');
  const value = (key, fallback = '') => escapeHTML(barber?.[key] ?? fallback);
  fields(`<div class="grid2"><label>Nome<input name="nome" value="${value('nome')}" required></label><label>Cargo<input name="cargo" maxlength="80" value="${value('cargo', 'Barbeiro')}"></label><label>E-mail para notificações<input name="notification_email" type="email" autocomplete="email" value="${value('notification_email')}" placeholder="profissional@email.com"><small>Receberá somente os agendamentos deste profissional.</small></label><label>Telefone<input name="telefone" type="tel" inputmode="tel" value="${value('telefone')}" placeholder="(00) 00000-0000"></label><label>WhatsApp<input name="whatsapp" type="tel" inputmode="tel" value="${value('whatsapp')}" placeholder="Deixe vazio para usar o telefone"></label><label>Comissão (%)<input name="comissao_percentual" type="number" min="0" max="100" step="0.01" value="${value('comissao_percentual', 40)}" required><small>Percentual recebido por serviço concluído.</small></label></div>${imageUploadField('foto_url', barber?.foto_url || '', 'Foto do profissional')}<label class="notification-toggle compact"><input name="ativo" type="checkbox"${barber?.ativo !== false ? ' checked' : ''}><span><b>Profissional ativo</b><small>Profissionais inativos não aparecem no agendamento.</small></span></label><label class="notification-toggle compact"><input name="enviar_convite" type="checkbox"><span><b>${barber?.usuario_id ? 'Reenviar acesso ao painel' : 'Convidar para acessar o painel'}</b><small>Envia um link para criar a senha e editar os próprios contatos.</small></span></label>`, barber ? 'Editar profissional' : 'Novo barbeiro', async (data) => {
    const file = data.foto_url_arquivo;
    delete data.foto_url_arquivo;
    if (file?.size) data.foto_url = await uploadImage(file);
    data.comissao_percentual = Number(data.comissao_percentual);
    data.notification_email = data.notification_email.trim() || null;
    data.ativo = $('#modal-form').elements.ativo.checked;
    data.enviar_convite = $('#modal-form').elements.enviar_convite.checked;
    await api(barber ? '/barbearia/barbeiros/' + barber.id : '/barbearia/barbeiros', { method: barber ? 'PUT' : 'POST', body: JSON.stringify(data) });
    await loadBarbers();
  });
}

async function removeBarber(id) {
  if (!confirm('Desativar este profissional?')) return;
  await api('/barbearia/barbeiros/' + id, { method: 'DELETE' });
  await loadBarbers();
  toast('Profissional desativado');
}

function nextAppointmentDateTime() {
  const next = new Date(Date.now() + 30 * 60000);
  next.setMinutes(Math.ceil(next.getMinutes() / 30) * 30, 0, 0);
  const offset = next.getTimezoneOffset() * 60000;
  return new Date(next.getTime() - offset).toISOString().slice(0, 16);
}

function openAppointment(id = null, preset = {}) {
  const active = barbers.filter((barber) => barber.ativo);
  if (!active.length) return toast('Cadastre um barbeiro primeiro.');
  if (!services.length) return toast('Cadastre um serviço primeiro.');
  const appointment = id ? appointmentCache.get(Number(id)) : null;
  if (id && !appointment) return toast('Agendamento não encontrado. Atualize a agenda e tente novamente.');
  const dateValue = appointment
    ? new Date(appointment.data_hora).toLocaleString('sv-SE').slice(0, 16)
    : nextAppointmentDateTime();
  const barberOptions = active.map((item) => `<option value="${item.id}"${Number(item.id) === Number(appointment?.barbeiro_id) ? ' selected' : ''}>${escapeHTML(item.nome)}</option>`).join('');
  const serviceOptions = services.map((service) => `<option value="${service.id}"${Number(service.id) === Number(appointment?.servico_id) ? ' selected' : ''}>${escapeHTML(service.nome)} · ${money(service.preco)}</option>`).join('');
  if (appointment) {
    fields(`<div class="appointment-edit-notice"><b>Editar agendamento #${String(appointment.id).padStart(4, '0')}</b><span>${escapeHTML(appointment.cliente_nome)} · ${escapeHTML(appointment.servico)}</span><small>Alterações de horário ou profissional geram um novo aviso.</small></div><div class="grid2"><label>Cliente<input name="cliente_nome" value="${escapeHTML(appointment.cliente_nome || '')}" required></label><label>Telefone<input name="cliente_telefone" type="tel" value="${escapeHTML(appointment.cliente_telefone || '')}"></label><label>E-mail do cliente<input name="cliente_email" type="email" value="${escapeHTML(appointment.cliente_email || '')}" placeholder="cliente@email.com"></label><label>Responsável<select name="barbeiro_id" required>${barberOptions}</select></label><label>Data e hora<input name="data_hora" type="datetime-local" value="${dateValue}" required></label><label>Serviço<select name="servico_id" required>${serviceOptions}</select></label></div><label>Observações<textarea name="observacoes" maxlength="500" rows="3" placeholder="Preferências ou informações importantes">${escapeHTML(appointment.observacoes || '')}</textarea></label>`, 'Editar agendamento', async (data) => {
      data.barbeiro_id = Number(data.barbeiro_id);
      data.servico_id = Number(data.servico_id);
      data.cliente_email = data.cliente_email.trim() || null;
      await api('/agendamentos/' + appointment.id, { method: 'PUT', body: JSON.stringify(data) });
      await loadDashboard();
      await loadAppointments();
      toast('Agendamento atualizado');
    });
    return;
  }
  fields(`<div class="grid2"><label>Cliente<input name="cliente_nome" value="${escapeHTML(preset.cliente_nome || '')}" required></label><label>Telefone<input name="cliente_telefone" type="tel" value="${escapeHTML(preset.cliente_telefone || '')}" required></label><label>E-mail do cliente<input name="cliente_email" type="email" value="${escapeHTML(preset.cliente_email || '')}" placeholder="cliente@email.com"><small>Opcional. Envia a confirmação da reserva.</small></label><label>Responsável pelo atendimento<select name="barbeiro_id" required>${barberOptions}</select></label><label>Data e hora<input name="data_hora" type="datetime-local" value="${dateValue}" required></label><label>Serviço<select name="servico_id" required>${serviceOptions}</select></label></div><label>Observações<textarea name="observacoes" maxlength="500" rows="3" placeholder="Preferências ou informações importantes"></textarea></label>`, 'Novo agendamento', async (data) => {
    data.barbeiro_id = Number(data.barbeiro_id);
    data.servico_id = Number(data.servico_id);
    data.cliente_email = data.cliente_email.trim() || null;
    await api('/agendamentos', { method: 'POST', body: JSON.stringify(data) });
    await loadDashboard();
    if (!$('#agenda').classList.contains('hidden')) await loadAppointments();
  });
}

async function updateAppointmentStatus(id, status, successMessage) {
  await api('/agendamentos/' + id, { method: 'PUT', body: JSON.stringify({ status }) });
  toast(successMessage);
  await loadDashboard();
  if (!$('#agenda').classList.contains('hidden')) await loadAppointments();
}

async function confirmAppointment(id) {
  if (!await confirmAction({
    title: 'Confirmar este horário?',
    message: 'O horário ficará marcado como confirmado. Isso ainda não conclui o atendimento.',
    confirmLabel: 'Confirmar horário',
    cancelLabel: 'Voltar',
    tone: 'success'
  })) return;
  await updateAppointmentStatus(id, 'confirmado', 'Horário confirmado');
}

async function markNoShow(id) {
  if (!await confirmAction({
    title: 'Cliente não compareceu?',
    message: 'O horário será encerrado sem contar visita ou faturamento. Depois você poderá apagá-lo da agenda.',
    confirmLabel: 'Marcar que não veio',
    cancelLabel: 'Voltar',
    tone: 'danger'
  })) return;
  await updateAppointmentStatus(id, 'nao_compareceu', 'Marcado como não compareceu');
}

function confirmAction({ title = 'Confirmar ação', message = '', confirmLabel = 'Confirmar', cancelLabel = 'Cancelar', tone = 'danger' } = {}) {
  let dialog = document.querySelector('#confirm-modal');
  if (!dialog) {
    dialog = document.createElement('dialog');
    dialog.id = 'confirm-modal';
    dialog.innerHTML = `<form method="dialog" class="confirm-modal-form">
      <div class="confirm-modal-icon" aria-hidden="true">!</div>
      <div class="confirm-modal-copy"><span class="eyebrow">CONFIRMAÇÃO</span><h2 id="confirm-modal-title"></h2><p id="confirm-modal-message"></p></div>
      <div class="confirm-modal-actions"><button type="button" class="button button-ghost" data-confirm-cancel></button><button type="button" class="button button-primary" data-confirm-ok></button></div>
    </form>`;
    document.body.appendChild(dialog);
  }
  const form = dialog.querySelector('form');
  const ok = dialog.querySelector('[data-confirm-ok]');
  const cancel = dialog.querySelector('[data-confirm-cancel]');
  const icon = dialog.querySelector('.confirm-modal-icon');
  dialog.querySelector('#confirm-modal-title').textContent = title;
  dialog.querySelector('#confirm-modal-message').textContent = message;
  ok.textContent = confirmLabel;
  cancel.textContent = cancelLabel;
  icon.className = `confirm-modal-icon ${tone}`;
  return new Promise((resolve) => {
    let settled = false;
    const finish = (value) => { if (settled) return; settled = true; dialog.close(); resolve(value); };
    const onCancel = (event) => { event.preventDefault(); finish(false); };
    const onKey = (event) => { if (event.key === 'Escape') { event.preventDefault(); finish(false); } };
    const onOk = async () => {
      ok.disabled = true; cancel.disabled = true; ok.classList.add('is-loading');
      await new Promise((r) => setTimeout(r, 220));
      finish(true);
    };
    dialog.addEventListener('cancel', onCancel, { once: true });
    dialog.addEventListener('keydown', onKey, { once: false });
    cancel.onclick = () => finish(false);
    ok.onclick = onOk;
    dialog.addEventListener('close', () => { dialog.removeEventListener('keydown', onKey); ok.disabled = false; cancel.disabled = false; ok.classList.remove('is-loading'); }, { once: true });
    dialog.showModal();
    ok.focus();
  });
}

async function concludeAppointment(id) {
  const warning = 'Ao concluir este agendamento, o e-mail e o telefone associados serão removidos permanentemente. Deseja continuar?';
  if (!await confirmAction({ title: 'Concluir atendimento?', message: warning, confirmLabel: 'Concluir atendimento', cancelLabel: 'Voltar', tone: 'success' })) return;
  const actionButton = document.querySelector(`[data-action="complete"][data-id="${id}"]`);
  try {
    if (actionButton) {
      actionButton.disabled = true;
      actionButton.textContent = 'Concluindo...';
    }
    const result = await api('/agendamentos/' + id + '/concluir', { method: 'PATCH' });
    if (actionButton) {
      actionButton.classList.add('is-completed');
      actionButton.textContent = '✓ Concluído';
    }
    toast(result.message || 'Agendamento concluído e dados de contato removidos com sucesso.');
    await loadDashboard();
    if (!$('#agenda').classList.contains('hidden')) await loadAppointments();
  } catch (error) {
    if (actionButton) {
      actionButton.disabled = false;
      actionButton.textContent = 'Concluir';
    }
    toast(error.message || 'Não foi possível concluir o agendamento. Os dados foram preservados.');
  }
}

async function cancelAppointment(id) {
  if (!confirm('Cancelar este horário?')) return;
  await api('/agendamentos/' + id, { method: 'DELETE' });
  toast('Agendamento cancelado');
  await loadDashboard();
  if (!$('#agenda').classList.contains('hidden')) await loadAppointments();
}

async function removeAppointment(id) {
  if (!await confirmAction({ title: 'Apagar agendamento?', message: 'O agendamento será removido definitivamente da agenda.', confirmLabel: 'Apagar', cancelLabel: 'Voltar' })) return;
  await api('/agendamentos/' + id + '/remover', { method: 'DELETE' });
  toast('Agendamento apagado');
  await loadDashboard();
  if (!$('#agenda').classList.contains('hidden')) await loadAppointments();
}

async function loadProducts() {
  products = await api('/produtos');
  $('#product-grid').innerHTML = products.map((product) => `<article><span class="badge">${product.quantidade_estoque} em estoque</span><h3>${escapeHTML(product.nome)}</h3><strong>${money(product.preco)}</strong><p>Custo: ${money(product.custo_unitario)}</p><footer><button class="link" type="button" data-action="edit-product" data-id="${product.id}">Editar</button><button class="danger" type="button" data-action="remove-product" data-id="${product.id}">Excluir</button></footer></article>`).join('') || '<p class="empty">Nenhum produto cadastrado.</p>';
}

async function loadServices() {
  services = await api('/servicos');
  $('#service-grid').innerHTML = services.map((service) => `<article class="media-card"><div class="admin-card-photo service-admin-photo">${service.imagem_url ? `<img src="${escapeHTML(service.imagem_url)}" alt="${escapeHTML(service.nome)}" loading="lazy">` : '<img src="/assets/cortaflow-icon-default.png" alt="CortaFlow">'}</div><div class="admin-card-body"><span class="badge">${service.duracao_minutos} minutos</span><h3>${escapeHTML(service.nome)}</h3><p>${escapeHTML(service.descricao || 'Sem descrição')}</p><strong>${money(service.preco)}</strong><footer><button class="link" type="button" data-action="edit-service" data-id="${service.id}">Editar</button><button class="danger" type="button" data-action="remove-service" data-id="${service.id}">Desativar</button></footer></div></article>`).join('') || '<p class="empty">Cadastre o primeiro serviço oferecido pela barbearia.</p>';
}

function openService(id) {
  const service = id ? services.find((item) => item.id === id) : null;
  if (id && !service) return toast('Serviço não encontrado.');
  const value = (key, fallback = '') => escapeHTML(service?.[key] ?? fallback);
  fields(`<label>Nome do serviço<input name="nome" value="${value('nome')}" required></label><label>Descrição<input name="descricao" value="${value('descricao')}" placeholder="Ex.: corte com acabamento"></label>${imageUploadField('imagem_url', service?.imagem_url || '', 'Foto do corte ou serviço')}<div class="grid2"><label>Duração (minutos)<input name="duracao_minutos" type="number" min="10" max="480" value="${value('duracao_minutos', 30)}" required></label><label>Preço<input name="preco" type="number" min="0" step=".01" value="${value('preco', 45)}" required></label></div>`, service ? 'Editar serviço' : 'Novo serviço', async (data) => {
    const file = data.imagem_url_arquivo;
    delete data.imagem_url_arquivo;
    if (file?.size) data.imagem_url = await uploadImage(file);
    data.duracao_minutos = Number(data.duracao_minutos);
    data.preco = Number(data.preco);
    await api(service ? '/servicos/' + service.id : '/servicos', { method: service ? 'PUT' : 'POST', body: JSON.stringify(data) });
    await loadServices();
  });
}

async function removeService(id) {
  if (!confirm('Desativar este serviço? Ele deixará de aparecer para novos clientes.')) return;
  await api('/servicos/' + id, { method: 'DELETE' });
  await loadServices();
  toast('Serviço desativado');
}

function openProduct(id = null) {
  const product = id ? products.find((item) => item.id === id) : null;
  if (id && !product) return toast('Produto não encontrado.');
  const value = (key, fallback = '') => escapeHTML(product?.[key] ?? fallback);
  fields(`<label>Produto<input name="nome" value="${value('nome')}" required></label><div class="grid2"><label>Preço de venda<input name="preco" type="number" min="0" step=".01" value="${value('preco')}" required><small>Valor cobrado do cliente.</small></label><label>Custo unitário<input name="custo_unitario" type="number" min="0" step=".01" value="${value('custo_unitario', 0)}" required><small>Quanto a barbearia paga pelo item.</small></label><label>Estoque<input name="quantidade_estoque" type="number" min="0" value="${value('quantidade_estoque', 0)}" required></label></div>`, product ? 'Editar produto' : 'Novo produto', async (data) => {
    data.preco = Number(data.preco);
    data.custo_unitario = Number(data.custo_unitario);
    data.quantidade_estoque = Number(data.quantidade_estoque);
    await api(product ? '/produtos/' + product.id : '/produtos', { method: product ? 'PUT' : 'POST', body: JSON.stringify(data) });
    await loadProducts();
  });
}

function applyAccessMode() {
  const barberMode = sessionContext?.perfil === 'barbeiro';
  document.body.classList.toggle('barber-session', barberMode);
  $$('.owner-only').forEach((element) => element.classList.toggle('hidden', barberMode));
  $('#barber-account-form').classList.toggle('hidden', !barberMode);
  $$('nav button[data-view]').forEach((button) => {
    button.classList.toggle('hidden', barberMode && button.dataset.view !== 'conta');
  });
}

async function loadBarberSelf() {
  const profile = await api('/barbeiro/me');
  const form = $('#barber-account-form');
  ['nome', 'cargo', 'notification_email', 'telefone', 'whatsapp', 'foto_url'].forEach((name) => {
    form.elements[name].value = profile[name] || '';
  });
  $('#barber-account-photo-preview').src = profile.foto_url || '/assets/favicon-cortaflow-transparent.png';
}

async function saveBarberSelf(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const submit = form.querySelector('button[type="submit"]');
  const data = Object.fromEntries(new FormData(form));
  data.notification_email = data.notification_email.trim() || null;
  submit.disabled = true;
  $('#barber-account-error').textContent = '';
  try {
    const file = $('#barber-account-photo-file').files?.[0];
    if (file) data.foto_url = await uploadImage(file);
    const profile = await api('/barbeiro/me', { method: 'PUT', body: JSON.stringify(data) });
    form.elements.foto_url.value = profile.foto_url || '';
    $('#barber-account-photo-preview').src = profile.foto_url || '/assets/favicon-cortaflow-transparent.png';
    $('#barber-account-photo-file').value = '';
    toast('Seus dados foram atualizados');
  } catch (error) {
    $('#barber-account-error').textContent = error.message;
  } finally {
    submit.disabled = false;
  }
}

Object.assign(window, { openBarber, openService, openProduct });

async function removeProduct(id) {
  if (!confirm('Excluir produto?')) return;
  await api('/produtos/' + id, { method: 'DELETE' });
  await loadProducts();
  toast('Produto excluído');
}

const reportMonths = ['Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho', 'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro'];
const expenseCategories = {
  aluguel: 'Aluguel', agua: 'Água', energia: 'Energia', internet: 'Internet',
  materiais: 'Materiais', marketing: 'Marketing', manutencao: 'Manutenção',
  impostos: 'Impostos', outros: 'Outros'
};

function setupFinanceFilters() {
  const now = new Date();
  if (!$('#finance-month').options.length) {
    $('#finance-month').innerHTML = reportMonths.map((name, index) => `<option value="${index + 1}">${name}</option>`).join('');
    $('#finance-year').innerHTML = Array.from({ length: 7 }, (_, index) => now.getFullYear() - index).map((year) => `<option value="${year}">${year}</option>`).join('');
    $('#finance-month').value = String(now.getMonth() + 1);
    $('#finance-year').value = String(now.getFullYear());
    ['finance-month', 'finance-year'].forEach((id) => { $('#' + id).onchange = () => loadFinance().catch((error) => toast(error.message)); });
  }
}

async function loadFinance() {
  setupFinanceFilters();
  const month = Number($('#finance-month').value);
  const year = Number($('#finance-year').value);
  const result = await api(`/financeiro/resumo?mes=${month}&ano=${year}`);
  financeExpenses = result.despesas || [];
  const outflows = Number(result.comissoes) + Number(result.custos_produtos) + Number(result.despesas_total);
  $('#finance-revenue').textContent = money(result.faturamento_total);
  $('#finance-outflows').textContent = money(outflows);
  $('#finance-profit').textContent = money(result.lucro_liquido);
  $('#finance-margin').textContent = `${Number(result.margem_liquida).toLocaleString('pt-BR', { maximumFractionDigits: 1 })}%`;
  $('#expense-total').textContent = money(result.despesas_total);
  $('.finance-profit-card').classList.toggle('is-negative', Number(result.lucro_liquido) < 0);
  const rows = [
    ['Faturamento de serviços', result.faturamento_servicos, 'positive'],
    ['Vendas de produtos', result.faturamento_produtos, 'positive'],
    ['Comissões da equipe', -Number(result.comissoes), 'negative'],
    ['Custos dos produtos', -Number(result.custos_produtos), 'negative'],
    ['Despesas cadastradas', -Number(result.despesas_total), 'negative'],
  ];
  $('#finance-breakdown').innerHTML = rows.map(([label, value, tone]) => `<div class="finance-breakdown-row"><span>${escapeHTML(label)}</span><b class="${tone}">${value >= 0 ? '+' : '−'} ${money(Math.abs(value))}</b></div>`).join('') + `<div class="finance-breakdown-row total"><span>Lucro líquido</span><b>${money(result.lucro_liquido)}</b></div>`;
  $('#expense-list').innerHTML = financeExpenses.map((expense) => `<article class="expense-row"><span class="expense-date">${new Date(expense.data + 'T12:00:00').toLocaleDateString('pt-BR', { day: '2-digit', month: 'short' })}</span><div><b>${escapeHTML(expense.descricao)}</b><small>${escapeHTML(expense.categoria_label || expenseCategories[expense.categoria] || expense.categoria)}${expense.recorrente ? ' · recorrente' : ''}</small></div><strong>${money(expense.valor)}</strong><div class="expense-actions"><button class="link" type="button" data-action="edit-expense" data-id="${expense.id}">Editar</button><button class="danger" type="button" data-action="remove-expense" data-id="${expense.id}">Excluir</button></div></article>`).join('') || '<div class="finance-empty"><b>Nenhuma despesa neste mês</b><span>Cadastre aluguel, materiais, contas e outros custos para ver o lucro real.</span><button class="button button-outline" type="button" data-action="add-expense">Cadastrar primeira despesa</button></div>';
}

function openExpense(id = null) {
  const expense = id ? financeExpenses.find((item) => item.id === id) : null;
  if (id && !expense) return toast('Despesa não encontrada.');
  const value = (key, fallback = '') => escapeHTML(expense?.[key] ?? fallback);
  const options = Object.entries(expenseCategories).map(([key, label]) => `<option value="${key}"${expense?.categoria === key ? ' selected' : ''}>${label}</option>`).join('');
    fields(`<label>Descrição<input name="descricao" value="${value('descricao')}" placeholder="Ex.: Conta de energia" required></label><div class="grid2"><label>Categoria<select name="categoria" required>${options}</select></label><label>Valor<input name="valor" type="number" min=".01" step=".01" value="${value('valor')}" required></label><label>Data<input name="data" type="date" value="${value('data', localDate())}" required></label></div><label class="notification-toggle compact"><input name="recorrente" type="checkbox"${expense?.recorrente ? ' checked' : ''}><span><b>Despesa recorrente</b><small>Identifica contas mensais; cada mês deve ser lançado separadamente.</small></span></label><label>Observação<textarea name="observacao" rows="3" maxlength="500" placeholder="Informação opcional">${value('observacao')}</textarea></label>`, expense ? 'Editar despesa' : 'Nova despesa', async (data) => {
    data.valor = Number(data.valor);
    data.recorrente = data.recorrente === 'on';
    await api(expense ? '/despesas/' + expense.id : '/despesas', { method: expense ? 'PUT' : 'POST', body: JSON.stringify(data) });
    await loadFinance();
  });
}

async function removeExpense(id) {
  if (!await confirmAction({ title: 'Excluir despesa?', message: 'A despesa será removida do cálculo de lucro deste mês.', confirmLabel: 'Excluir despesa' })) return;
  await api('/despesas/' + id, { method: 'DELETE' });
  await loadFinance();
  toast('Despesa excluída');
}

async function downloadFinancial(format) {
  const month = Number($('#finance-month').value);
  const year = Number($('#finance-year').value);
  const response = await fetch(`/api/financeiro/exportar.${format}?mes=${month}&ano=${year}`, { headers: token ? { Authorization: `Bearer ${token}` } : {} });
  if (!response.ok) {
    const data = await response.json().catch(() => null);
    throw new Error(data?.detail || 'Não foi possível gerar o arquivo.');
  }
  const blob = await response.blob();
  const link = document.createElement('a');
  link.href = URL.createObjectURL(blob);
  link.download = `financeiro-${year}-${String(month).padStart(2, '0')}.${format}`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(link.href);
  toast(format === 'xlsx' ? 'Excel gerado com sucesso' : 'PDF gerado com sucesso');
}

function setupReportFilters() {
  const now = new Date();
  if (!$('#report-month').options.length) {
    $('#report-month').innerHTML = reportMonths.map((name, index) => `<option value="${index + 1}">${name}</option>`).join('');
    $('#report-month').value = String(now.getMonth() + 1);
    $('#report-year').innerHTML = Array.from({ length: 7 }, (_, index) => now.getFullYear() - index).map((year) => `<option value="${year}">${year}</option>`).join('');
    ['report-period', 'report-month', 'report-year'].forEach((id) => { $('#' + id).onchange = () => loadReports().catch((error) => toast(error.message)); });
  }
  $('#report-month-wrap').classList.toggle('hidden', $('#report-period').value === 'anual');
}

function completeReportPoints(report, month, year) {
  const values = new Map(report.pontos.map((item) => [String(item.periodo).slice(0, 10), Number(item.atendimentos)]));
  if (report.periodo === 'anual') return reportMonths.map((label, index) => ({
    label: label.slice(0, 3),
    fullLabel: label,
    value: values.get(`${year}-${String(index + 1).padStart(2, '0')}-01`) || 0
  }));
  const days = new Date(year, month, 0).getDate();
  return Array.from({ length: days }, (_, index) => {
    const day = index + 1;
    const date = new Date(year, month - 1, day, 12);
    const weekday = date.toLocaleDateString('pt-BR', { weekday: 'short' }).replace('.', '');
    return {
      label: String(day),
      fullLabel: `${String(day).padStart(2, '0')} de ${reportMonths[month - 1]} · ${weekday}`,
      value: values.get(`${year}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}`) || 0
    };
  });
}

function renderAttendanceChartLegacy(points) {
  const width = 760, height = 270, left = 42, right = 18, top = 22, bottom = 38;
  const chartWidth = width - left - right, chartHeight = height - top - bottom;
  const maximum = Math.max(1, ...points.map((point) => point.value));
  const x = (index) => left + (points.length === 1 ? 0 : index * chartWidth / (points.length - 1));
  const y = (value) => top + chartHeight - (value / maximum * chartHeight);
  const line = points.map((point, index) => `${index ? 'L' : 'M'}${x(index).toFixed(1)},${y(point.value).toFixed(1)}`).join(' ');
  const area = `${line} L${x(points.length - 1).toFixed(1)},${top + chartHeight} L${left},${top + chartHeight} Z`;
  const labelStep = Math.max(1, Math.ceil(points.length / 7));
  const grid = Array.from({ length: 5 }, (_, index) => { const value = Math.round(maximum * (4 - index) / 4); const py = top + chartHeight * index / 4; return `<line x1="${left}" y1="${py}" x2="${width - right}" y2="${py}"/><text x="${left - 9}" y="${py + 3}">${value}</text>`; }).join('');
  const labels = points.map((point, index) => (index % labelStep === 0 || index === points.length - 1) ? `<text x="${x(index)}" y="${height - 13}" text-anchor="middle">${escapeHTML(point.label)}</text>` : '').join('');
  const dots = points.map((point, index) => `<circle cx="${x(index)}" cy="${y(point.value)}" r="4"><title>${escapeHTML(point.label)}: ${point.value} atendimento${point.value === 1 ? '' : 's'}</title></circle>`).join('');
  $('#attendance-chart').innerHTML = `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Gráfico de atendimentos no período"><g class="chart-grid">${grid}${labels}</g><path class="chart-area" d="${area}"/><path class="chart-line" d="${line}"/>${dots}</svg>`;
}

async function loadReports() {
  setupReportFilters();
  const period = $('#report-period').value;
  const month = Number($('#report-month').value);
  const year = Number($('#report-year').value);
  const [report, loyalty] = await Promise.all([api(`/relatorios/periodo?periodo=${period}&mes=${month}&ano=${year}`), api('/relatorios/fidelidade')]);
  $('#report-month-wrap').classList.toggle('hidden', period === 'anual');
  $('#report-total').textContent = money(report.total.faturamento);
  $('#report-cuts').textContent = report.total.atendimentos;
  $('#report-ticket').textContent = money(report.total.ticket_medio);
  $('#report-chart-title').textContent = period === 'anual' ? 'Atendimentos por mês' : 'Atendimentos por dia';
  $('#report-chart-description').textContent = period === 'anual'
    ? `Visão consolidada de ${year}, mês a mês.`
    : `Movimento diário de ${reportMonths[month - 1]} de ${year}. Passe sobre uma coluna para ver os detalhes.`;
  if (report.melhor_periodo) {
    const date = String(report.melhor_periodo.periodo).slice(0, 10);
    $('#report-best').textContent = period === 'anual' ? reportMonths[Number(date.slice(5, 7)) - 1] : `${Number(date.slice(8, 10))}/${date.slice(5, 7)}`;
    $('#report-best-detail').textContent = `${report.melhor_periodo.atendimentos} atendimento${Number(report.melhor_periodo.atendimentos) === 1 ? '' : 's'}`;
  } else {
    $('#report-best').textContent = '—';
    $('#report-best-detail').textContent = 'sem atendimentos';
  }
  const chartPoints = completeReportPoints(report, month, year);
  const chartTotal = chartPoints.reduce((sum, point) => sum + point.value, 0);
  const activePeriods = chartPoints.filter((point) => point.value > 0).length;
  const peak = chartPoints.reduce((best, point) => point.value > best.value ? point : best, { value: 0, fullLabel: '—' });
  $('#chart-active-periods').textContent = `${activePeriods} de ${chartPoints.length}`;
  $('#chart-average').textContent = (chartTotal / Math.max(chartPoints.length, 1)).toLocaleString('pt-BR', { maximumFractionDigits: 1 });
  $('#chart-peak').textContent = peak.value ? `${peak.value} · ${peak.fullLabel}` : '—';
  renderAttendanceChart(chartPoints);
  $('#barber-report').innerHTML = report.por_barbeiro.map((item) => `<div class="report-row"><b>${escapeHTML(item.nome)}</b><span>${item.cortes} cortes</span><span>${money(item.faturamento)}</span></div>`).join('') || '<p class="empty">Sem dados no período.</p>';
  $('#loyalty-report').innerHTML = loyalty.slice(0, 10).map((item) => `<div class="report-row"><b>${escapeHTML(item.cliente_nome || item.cliente_telefone)}</b><span>${item.total_cortes} cortes</span><span>faltam ${item.cortes_para_premio}</span></div>`).join('') || '<p class="empty">Sem clientes fidelizados ainda.</p>';
}

// Bar chart: one column per period makes daily volume easier to compare than a smoothed line.
function renderAttendanceChart(points) {
  const width = 760, height = 286, left = 46, right = 18, top = 30, bottom = 46;
  const chartWidth = width - left - right, chartHeight = height - top - bottom;
  const maximum = Math.max(1, ...points.map((point) => point.value));
  const scaleMax = Math.max(4, Math.ceil(maximum / 4) * 4);
  const slot = chartWidth / Math.max(points.length, 1);
  const barWidth = Math.max(5, Math.min(28, slot * .62));
  const x = (index) => left + slot * index + slot / 2;
  const y = (value) => top + chartHeight - (value / scaleMax * chartHeight);
  const labelStep = Math.max(1, Math.ceil(points.length / 9));
  const grid = Array.from({ length: 5 }, (_, index) => {
    const value = Math.round(scaleMax * (4 - index) / 4);
    const py = top + chartHeight * index / 4;
    return `<line x1="${left}" y1="${py}" x2="${width - right}" y2="${py}"/><text x="${left - 9}" y="${py + 3}">${value}</text>`;
  }).join('');
  const labels = points.map((point, index) => (index % labelStep === 0 || index === points.length - 1)
    ? `<text x="${x(index)}" y="${height - 14}" text-anchor="middle">${escapeHTML(point.label)}</text>` : '').join('');
  const bestValue = Math.max(...points.map((point) => point.value), 0);
  const bars = points.map((point, index) => {
    const barHeight = point.value ? Math.max(3, point.value / scaleMax * chartHeight) : 0;
    const barX = x(index) - barWidth / 2;
    const barY = top + chartHeight - barHeight;
    const best = point.value === bestValue && bestValue > 0 ? ' is-best' : '';
    const valueLabel = point.value > 0 && (point.value === bestValue || points.length <= 12)
      ? `<text class="chart-value" x="${x(index)}" y="${barY - 7}" text-anchor="middle">${point.value}</text>` : '';
    const accessibleLabel = `${point.fullLabel || point.label}: ${point.value} atendimento${point.value === 1 ? '' : 's'}`;
    return `<rect class="chart-bar${best}" tabindex="0" aria-label="${escapeHTML(accessibleLabel)}" x="${barX.toFixed(1)}" y="${barY.toFixed(1)}" width="${barWidth.toFixed(1)}" height="${barHeight.toFixed(1)}" rx="5"><title>${escapeHTML(accessibleLabel)}</title></rect>${valueLabel}`;
  }).join('');
  const empty = bestValue === 0 ? '<p class="chart-empty">Ainda não há atendimentos concluídos neste período.</p>' : '';
  $('#attendance-chart').innerHTML = `${empty}<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Gráfico de atendimentos no período"><g class="chart-grid">${grid}${labels}</g><g class="chart-bars">${bars}</g></svg>`;
}

const modal = $('#modal');
const modalClose = $('#modal-close');
if (modal && modalClose) {
  modalClose.addEventListener('click', () => modal.close());
  modal.addEventListener('cancel', (event) => {
    event.preventDefault();
    modal.close();
  });
}

bindAuth();
bindNavigation();
bindTheme();
bindPricing();
bindPwaInstall();
$('#push-notifications').onclick = togglePushNotifications;
if (token) start();
else location.replace('/');
