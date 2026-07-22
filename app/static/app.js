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
let toastTimer;

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
  $('#app').classList.add('hidden');
  $('#login').classList.remove('hidden');
  $('#login-form').classList.remove('hidden');
  $('#register-form').classList.add('hidden');
}

function show(view) {
  $$('.view').forEach((element) => element.classList.toggle('hidden', element.id !== view));
  $$('nav button[data-view]').forEach((button) => button.classList.toggle('active', button.dataset.view === view));
  $('#title').textContent = { dashboard: 'Resumo do dia', agenda: 'Agenda', barbeiros: 'Barbeiros', servicos: 'Serviços', produtos: 'Produtos', relatorios: 'Relatórios', conta: 'Minha conta' }[view] || 'Painel';
  closeSidebar();
  const loaders = { agenda: loadAppointments, servicos: loadServices, produtos: loadProducts, relatorios: loadReports, conta: loadProfile };
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
  $('#toggle-password').onclick = () => {
    const password = $('#password');
    const showing = password.type === 'text';
    password.type = showing ? 'password' : 'text';
    $('#toggle-password').textContent = showing ? 'Mostrar' : 'Ocultar';
    $('#toggle-password').setAttribute('aria-label', showing ? 'Mostrar senha' : 'Ocultar senha');
  };
  $('#show-register').onclick = (event) => { event.preventDefault(); $('#login-form').classList.add('hidden'); $('#register-form').classList.remove('hidden'); $('#login-error').textContent = ''; };
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
      token = result.access_token;
      localStorage.setItem('token', token);
      localStorage.setItem('name', data.nome);
      await start();
    } catch (error) {
      toast(error.message);
    } finally {
      button.disabled = false;
    }
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

async function start() {
  $('#login').classList.add('hidden');
  $('#app').classList.remove('hidden');
  $('#owner-name').textContent = (localStorage.getItem('name') || 'gestor').split(' ')[0];
  $('#today').textContent = new Date().toLocaleDateString('pt-BR', { weekday: 'long', day: '2-digit', month: 'long' });
  $('#agenda-date').value = localDate();
  try {
    await Promise.all([loadBarbers(), loadServices(), loadProfile()]);
    await loadDashboard();
  } catch (error) {
    logout();
    $('#login-error').textContent = error.message;
  }
}

function applyShopBrand(profile) {
  if (!profile) return;
  $('#admin-shop-name').textContent = profile.nome;
  $('#admin-shop-logo').src = profile.logo_url || '/assets/cortaflow-icon-default.png';
  $('#public-booking-link').href = `/cliente.html?barbearia=${profile.id}`;
}

async function loadProfile() {
  shopProfile = await api('/barbearia/perfil');
  applyShopBrand(shopProfile);
  const form = $('#account-form');
  ['nome', 'telefone', 'endereco', 'cnpj', 'logo_url'].forEach((name) => {
    form.elements[name].value = shopProfile[name] || '';
  });
  form.elements.email_notificacoes.value = shopProfile.email_notificacoes || '';
  form.elements.notificar_novos_agendamentos.checked = shopProfile.notificar_novos_agendamentos !== false;
  $('#account-logo-preview').src = shopProfile.logo_url || '/assets/cortaflow-icon-default.png';
}

async function saveProfile(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const submit = form.querySelector('button[type="submit"]');
  const data = Object.fromEntries(new FormData(form));
  data.email_notificacoes = data.email_notificacoes.trim() || null;
  data.notificar_novos_agendamentos = form.elements.notificar_novos_agendamentos.checked;
  submit.disabled = true;
  $('#account-error').textContent = '';
  try {
    const file = $('#account-logo-file').files?.[0];
    if (file) data.logo_url = await uploadImage(file);
    shopProfile = await api('/barbearia/atualizar', { method: 'POST', body: JSON.stringify(data) });
    applyShopBrand(shopProfile);
    $('#account-logo-url').value = shopProfile.logo_url || '';
    $('#account-logo-file').value = '';
    toast('Identidade da barbearia atualizada');
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

async function loadReports() {
  const [report, loyalty] = await Promise.all([api('/relatorios/dia?data=' + localDate()), api('/relatorios/fidelidade')]);
  $('#report-total').textContent = money(report.total.total);
  $('#report-cuts').textContent = report.total.cortes;
  $('#barber-report').innerHTML = report.por_barbeiro.map((item) => `<div class="report-row"><b>${escapeHTML(item.nome)}</b><span>${item.cortes} cortes</span><span>${money(item.faturamento)}</span></div>`).join('') || '<p class="empty">Sem dados hoje.</p>';
  $('#loyalty-report').innerHTML = loyalty.slice(0, 10).map((item) => `<div class="report-row"><b>${escapeHTML(item.cliente_nome || item.cliente_telefone)}</b><span>${item.total_cortes} cortes</span><span>faltam ${item.cortes_para_premio}</span></div>`).join('') || '<p class="empty">Sem clientes fidelizados ainda.</p>';
}

bindAuth();
bindNavigation();
if (token) start();
