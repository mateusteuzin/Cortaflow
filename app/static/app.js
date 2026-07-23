const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => document.querySelectorAll(selector);
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
let toastTimer;

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
  $('#title').textContent = { dashboard: 'Resumo do dia', agenda: 'Agenda', barbeiros: 'Barbeiros', servicos: 'Serviços', produtos: 'Produtos', relatorios: 'Relatórios', assinatura: 'Minha assinatura', conta: 'Minha conta' }[view] || 'Painel';
  closeSidebar();
  const loaders = { agenda: loadAppointments, servicos: loadServices, produtos: loadProducts, relatorios: loadReports, assinatura: loadSubscription, conta: loadProfile };
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
  $('#show-register').onclick = (event) => { event.preventDefault(); location.href = '/#planos'; };
  $('#show-login').onclick = (event) => { event.preventDefault(); $('#register-form').classList.add('hidden'); $('#login-form').classList.remove('hidden'); };
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
  $('#agenda-date').onchange = () => loadAppointments().catch((error) => toast(error.message));
  $('#agenda-barber').onchange = () => loadAppointments().catch((error) => toast(error.message));
  $('#account-logo-file').onchange = (event) => {
    const file = event.target.files?.[0];
    if (file) $('#account-logo-preview').src = URL.createObjectURL(file);
  };
  $('#account-form').onsubmit = saveProfile;
  $('#copy-booking-link').onclick = copyBookingLink;
  $('#manage-subscription').onclick = openBillingPortal;
  $$('[data-subscription-plan]').forEach((button) => {
    button.onclick = () => chooseSubscription(button.dataset.subscriptionPlan, button);
  });
  document.addEventListener('click', (event) => {
    const actionButton = event.target.closest('[data-action]');
    if (!actionButton) return;
    const action = actionButton.dataset.action;
    const id = Number(actionButton.dataset.id);
    if (action === 'complete') concludeAppointment(id);
    if (action === 'cancel') cancelAppointment(id);
    if (action === 'remove-appointment') removeAppointment(id);
    if (action === 'edit-barber') openBarber(id);
    if (action === 'remove-barber') removeBarber(id);
    if (action === 'edit-service') openService(id);
    if (action === 'remove-service') removeService(id);
    if (action === 'remove-product') removeProduct(id);
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
  $('#owner-name').textContent = (localStorage.getItem('name') || 'gestor').split(' ')[0];
  $('#today').textContent = new Date().toLocaleDateString('pt-BR', { weekday: 'long', day: '2-digit', month: 'long' });
  $('#agenda-date').value = localDate();
  try {
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
  [shopProfile, businessHours] = await Promise.all([
    api('/barbearia/perfil'),
    api('/barbearia/horarios-funcionamento')
  ]);
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
  $('#barber-grid').innerHTML = active.map((barber) => `<article class="media-card professional-card"><div class="admin-card-photo professional-admin-photo">${barber.foto_url ? `<img src="${escapeHTML(barber.foto_url)}" alt="Foto de ${escapeHTML(barber.nome)}" loading="lazy">` : `<span>${escapeHTML(barber.nome.slice(0, 2).toUpperCase())}</span>`}<i class="photo-status"></i></div><div class="admin-card-body"><span class="badge">Ativo</span><h3>${escapeHTML(barber.nome)}</h3><p>${escapeHTML(barber.telefone || 'Sem telefone')}</p><footer><b>${Number(barber.comissao_percentual)}% comissão</b><button class="link" type="button" data-action="edit-barber" data-id="${barber.id}">Editar</button><button class="danger" type="button" data-action="remove-barber" data-id="${barber.id}">Desativar</button></footer></div></article>`).join('') || '<p class="empty">Adicione o primeiro profissional.</p>';
}

function appointmentHTML(appointment) {
  const status = appointment.status || 'agendado';
  const actions = !['concluido', 'realizado', 'cancelado', 'nao_compareceu'].includes(status)
    ? `<button type="button" data-action="complete" data-id="${appointment.id}">Concluir</button><button class="danger" type="button" data-action="cancel" data-id="${appointment.id}">Cancelar</button>`
    : status === 'cancelado' ? `<button class="danger" type="button" data-action="remove-appointment" data-id="${appointment.id}">Apagar</button>` : '';
  return `<div class="appointment"><div class="appointment-time">${new Date(appointment.data_hora).toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' })}</div><div class="appointment-info"><b>${escapeHTML(appointment.cliente_nome)}</b><small>${escapeHTML(appointment.barbeiro_nome || '')} · ${escapeHTML(appointment.servico)} · ${money(appointment.preco)}</small></div><span class="badge status-${escapeHTML(status)}">${escapeHTML(statusLabel[status] || status)}</span><div class="appointment-actions">${actions}</div></div>`;
}

async function loadDashboard() {
  const today = localDate();
  const [report, appointments] = await Promise.all([api('/relatorios/dia?data=' + today), api('/agendamentos?data=' + today)]);
  $('#revenue').textContent = money(report.total.total);
  $('#cuts').textContent = report.total.cortes;
  const upcoming = appointments.filter((appointment) => new Date(appointment.data_hora) > new Date() && !['cancelado', 'concluido', 'realizado', 'nao_compareceu'].includes(appointment.status));
  $('#upcoming-count').textContent = upcoming.length;
  $('#upcoming').innerHTML = upcoming.slice(0, 6).map(appointmentHTML).join('') || '<div class="empty">Nenhum próximo atendimento hoje.</div>';
}

async function loadAppointments() {
  let query = '?data=' + $('#agenda-date').value;
  if ($('#agenda-barber').value) query += '&barbeiro_id=' + $('#agenda-barber').value;
  const appointments = await api('/agendamentos' + query);
  $('#appointments').innerHTML = appointments.map(appointmentHTML).join('') || '<div class="empty">Agenda livre nesta data.</div>';
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
  fields(`<label>Nome<input name="nome" value="${value('nome')}" required></label><label>Telefone<input name="telefone" type="tel" value="${value('telefone')}"></label>${imageUploadField('foto_url', barber?.foto_url || '', 'Foto do profissional')}<label>Comissão (%)<input name="comissao_percentual" type="number" min="0" max="100" step="0.01" value="${value('comissao_percentual', 40)}" required><small>Percentual recebido pelo profissional em cada serviço concluído.</small></label>`, barber ? 'Editar profissional' : 'Novo barbeiro', async (data) => {
    const file = data.foto_url_arquivo;
    delete data.foto_url_arquivo;
    if (file?.size) data.foto_url = await uploadImage(file);
    data.comissao_percentual = Number(data.comissao_percentual);
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

function openAppointment() {
  const active = barbers.filter((barber) => barber.ativo);
  if (!active.length) return toast('Cadastre um barbeiro primeiro.');
  if (!services.length) return toast('Cadastre um serviço primeiro.');
  fields(`<div class="grid2"><label>Cliente<input name="cliente_nome" required></label><label>Telefone<input name="cliente_telefone" type="tel" required></label><label>Barbeiro<select name="barbeiro_id">${active.map((barber) => `<option value="${barber.id}">${escapeHTML(barber.nome)}</option>`).join('')}</select></label><label>Data e hora<input name="data_hora" type="datetime-local" required></label><label>Serviço<select name="servico_id">${services.map((service) => `<option value="${service.id}">${escapeHTML(service.nome)} · ${money(service.preco)}</option>`).join('')}</select></label></div>`, 'Novo agendamento', async (data) => {
    data.barbeiro_id = Number(data.barbeiro_id);
    data.servico_id = Number(data.servico_id);
    await api('/agendamentos', { method: 'POST', body: JSON.stringify(data) });
    await loadDashboard();
    if (!$('#agenda').classList.contains('hidden')) await loadAppointments();
  });
}

async function concludeAppointment(id) {
  const warning = 'Ao concluir este agendamento, o e-mail e o telefone associados serão removidos permanentemente. Deseja continuar?';
  if (!confirm(warning)) return;
  try {
    const result = await api('/agendamentos/' + id + '/concluir', { method: 'PATCH' });
    toast(result.message || 'Agendamento concluído e dados de contato removidos com sucesso.');
    await loadDashboard();
    if (!$('#agenda').classList.contains('hidden')) await loadAppointments();
  } catch (error) {
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
  if (!confirm('Apagar este agendamento cancelado definitivamente? Esta ação não pode ser desfeita.')) return;
  await api('/agendamentos/' + id + '/remover', { method: 'DELETE' });
  toast('Agendamento apagado');
  await loadDashboard();
  if (!$('#agenda').classList.contains('hidden')) await loadAppointments();
}

async function loadProducts() {
  products = await api('/produtos');
  $('#product-grid').innerHTML = products.map((product) => `<article><span class="badge">${product.quantidade_estoque} em estoque</span><h3>${escapeHTML(product.nome)}</h3><strong>${money(product.preco)}</strong><footer><span>Estoque atual</span><button class="danger" type="button" data-action="remove-product" data-id="${product.id}">Excluir</button></footer></article>`).join('') || '<p class="empty">Nenhum produto cadastrado.</p>';
}

async function loadServices() {
  services = await api('/servicos');
  $('#service-grid').innerHTML = services.map((service) => `<article class="media-card"><div class="admin-card-photo service-admin-photo">${service.imagem_url ? `<img src="${escapeHTML(service.imagem_url)}" alt="${escapeHTML(service.nome)}" loading="lazy">` : '<img src="/assets/cortaflow-icon-default.png" alt="CortaFlow">'}</div><div class="admin-card-body"><span class="badge">${service.duracao_minutos} minutos</span><h3>${escapeHTML(service.nome)}</h3><p>${escapeHTML(service.descricao || 'Sem descrição')}</p><strong>${money(service.preco)}</strong><footer><button class="link" type="button" data-action="edit-service" data-id="${service.id}">Editar</button><button class="danger" type="button" data-action="remove-service" data-id="${service.id}">Desativar</button></footer></div></article>`).join('') || '<p class="empty">Cadastre o primeiro serviço oferecido pela barbearia.</p>';
}

function openService(id) {
  const service = services.find((item) => item.id === id);
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

function openProduct() {
  fields('<label>Produto<input name="nome" required></label><div class="grid2"><label>Preço<input name="preco" type="number" min="0" step=".01" required></label><label>Estoque<input name="quantidade_estoque" type="number" min="0" value="0" required></label></div>', 'Novo produto', async (data) => {
    data.preco = Number(data.preco);
    data.quantidade_estoque = Number(data.quantidade_estoque);
    await api('/produtos', { method: 'POST', body: JSON.stringify(data) });
    await loadProducts();
  });
}

async function removeProduct(id) {
  if (!confirm('Excluir produto?')) return;
  await api('/produtos/' + id, { method: 'DELETE' });
  await loadProducts();
  toast('Produto excluído');
}

const reportMonths = ['Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho', 'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro'];

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
  if (report.periodo === 'anual') return reportMonths.map((label, index) => ({ label: label.slice(0, 3), value: values.get(`${year}-${String(index + 1).padStart(2, '0')}-01`) || 0 }));
  const days = new Date(year, month, 0).getDate();
  return Array.from({ length: days }, (_, index) => {
    const day = index + 1;
    return { label: String(day), value: values.get(`${year}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}`) || 0 };
  });
}

function renderAttendanceChart(points) {
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
  if (report.melhor_periodo) {
    const date = String(report.melhor_periodo.periodo).slice(0, 10);
    $('#report-best').textContent = period === 'anual' ? reportMonths[Number(date.slice(5, 7)) - 1] : `${Number(date.slice(8, 10))}/${date.slice(5, 7)}`;
    $('#report-best-detail').textContent = `${report.melhor_periodo.atendimentos} atendimento${Number(report.melhor_periodo.atendimentos) === 1 ? '' : 's'}`;
  } else {
    $('#report-best').textContent = '—';
    $('#report-best-detail').textContent = 'sem atendimentos';
  }
  renderAttendanceChart(completeReportPoints(report, month, year));
  $('#barber-report').innerHTML = report.por_barbeiro.map((item) => `<div class="report-row"><b>${escapeHTML(item.nome)}</b><span>${item.cortes} cortes</span><span>${money(item.faturamento)}</span></div>`).join('') || '<p class="empty">Sem dados no período.</p>';
  $('#loyalty-report').innerHTML = loyalty.slice(0, 10).map((item) => `<div class="report-row"><b>${escapeHTML(item.cliente_nome || item.cliente_telefone)}</b><span>${item.total_cortes} cortes</span><span>faltam ${item.cortes_para_premio}</span></div>`).join('') || '<p class="empty">Sem clientes fidelizados ainda.</p>';
}

bindAuth();
bindNavigation();
bindTheme();
bindPricing();
if (token) start();
else location.replace('/');
