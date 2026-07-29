const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => document.querySelectorAll(selector);
const bookingMatch = location.pathname.match(/^\/agendar\/([^/]+)\/?$/);
const bookingSlug = bookingMatch ? decodeURIComponent(bookingMatch[1]).toLowerCase() : '';
const publicBase = () => `/public/barbearias/${encodeURIComponent(bookingSlug)}`;
const today = () => {
  const now = new Date();
  return new Date(now.getTime() - now.getTimezoneOffset() * 60000).toISOString().slice(0, 10);
};
const escapeHTML = (value) => String(value ?? '').replace(/[&<>"']/g, (char) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;' }[char]));
const money = (value) => Number(value || 0).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });

let shop;
let service;
let barber;
let slot;
let currentStep = 1;
const dateInput = $('#date');
dateInput.min = today();
dateInput.value = dateInput.min;

async function api(path, options = {}) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 30000);
  try {
    const response = await fetch('/api' + path, { ...options, signal: controller.signal, headers: { 'Content-Type': 'application/json', ...(options.headers || {}) } });
    const contentType = response.headers.get('content-type') || '';
    const data = contentType.includes('application/json') ? await response.json() : null;
    if (!response.ok) throw new Error(data?.detail || 'Não foi possível concluir a operação.');
    return data;
  } catch (error) {
    if (error.name === 'AbortError') throw new Error('A conexão demorou demais. Tente novamente.');
    if (error instanceof SyntaxError) throw new Error('A resposta do servidor não pôde ser lida.');
    throw error;
  } finally {
    clearTimeout(timer);
  }
}

function initials(name) {
  return String(name || 'CF').split(/\s+/).slice(0, 2).map((part) => part[0]).join('').toUpperCase();
}

function phone(value) {
  return value.replace(/\D/g, '').replace(/^(\d{2})(\d{5})(\d{0,4}).*/, (_, area, first, last) => `(${area}) ${first}${last ? '-' + last : ''}`).slice(0, 15);
}

function setStep(step) {
  currentStep = step;
  $$('.step').forEach((element) => element.classList.toggle('hidden', Number(element.dataset.step) !== step));
  $('#step-label').textContent = `Etapa ${step} de 3`;
  $('#step-title').textContent = ['Escolha seu horário', 'Seus dados', 'Revise e confirme'][step - 1];
  $('#progress-bar').style.width = `${step * 33.33}%`;
  $$('.progress-steps span').forEach((element, index) => element.classList.toggle('active', index < step));
  $('#error').textContent = '';
  requestAnimationFrame(() => {
    const bookingShell = $('.booking-shell');
    if (!bookingShell) return;
    const target = bookingShell.getBoundingClientRect().top + window.scrollY - 16;
    window.scrollTo({ top: Math.max(0, target), behavior: 'smooth' });
  });
}

async function init() {
  try {
    if (!bookingSlug) throw new Error('Barbearia não encontrada. Verifique se o link está correto.');
    shop = await api(publicBase());
    await Promise.all([loadServices(), loadBarbers()]);
    $('#shop-name').textContent = shop.nome;
    $('#shop-initials').textContent = initials(shop.nome);
    $('#shop-address').textContent = shop.endereco || 'Agendamento online';
    $$('.shop-brand-name').forEach((element) => { element.textContent = shop.nome; });
    $$('.shop-logo').forEach((image) => {
      const fallback = '/assets/cortaflow-icon-default.png';
      image.src = shop.logo_url || fallback;
      image.alt = shop.logo_url ? `Logo da ${shop.nome}` : 'CortaFlow';
      image.addEventListener('error', () => {
        if (image.src.endsWith(fallback)) return;
        image.src = fallback;
        image.alt = 'CortaFlow';
      }, { once: true });
    });
    document.title = `Agende seu horário · ${shop.nome}`;
    $('#loading').classList.add('hidden');
    $('#flow').classList.remove('hidden');
  } catch (error) {
    $('#loading').classList.add('hidden');
    $('#fatal').classList.remove('hidden');
    $('#fatal-message').textContent = error.message;
  }
}

async function loadServices() {
  const list = await api(`${publicBase()}/servicos`);
  if (!list.length) throw new Error('Esta barbearia ainda não possui serviços disponíveis.');
  $('#services').innerHTML = list.map((item, index) => `<button class="service-option" type="button" role="radio" aria-checked="false" aria-label="${escapeHTML(`${item.nome}, ${money(item.preco)}, ${item.duracao_minutos} minutos`)}" data-index="${index}"><span class="service-photo"><img src="${escapeHTML(item.imagem_url || '/assets/service-degrade.webp')}" alt="" loading="lazy"></span><span class="service-copy"><span><b>${escapeHTML(item.nome)}</b><small>${escapeHTML(item.descricao || 'Serviço profissional')}</small></span><strong>${money(item.preco)}</strong><span class="duration">${item.duracao_minutos} minutos</span></span></button>`).join('');
  $$('.service-option').forEach((button) => {
    button.onclick = () => {
      service = list[Number(button.dataset.index)];
      $$('.service-option').forEach((element) => {
        const selected = element === button;
        element.classList.toggle('active', selected);
        element.setAttribute('aria-checked', String(selected));
      });
      $('#barber-block').classList.add('ready');
      if (barber) loadSlots();
    };
  });
}

async function loadBarbers() {
  const list = await api(`${publicBase()}/profissionais`);
  if (!list.length) throw new Error('Esta barbearia ainda não possui profissionais disponíveis.');
  $('#barbers').innerHTML = list.map((item, index) => `<button class="professional" type="button" data-index="${index}"><span class="avatar">${item.foto_url ? `<img src="${escapeHTML(item.foto_url)}" alt="Foto de ${escapeHTML(item.nome)}" loading="lazy">` : escapeHTML(initials(item.nome))}</span><span><b>${escapeHTML(item.nome)}</b><small>Profissional disponível</small></span></button>`).join('');
  $$('.professional').forEach((button) => {
    button.onclick = () => {
      const item = list[Number(button.dataset.index)];
      barber = { id: item.id, name: item.nome, photo: item.foto_url || '' };
      $$('.professional').forEach((element) => element.classList.toggle('active', element === button));
      $('#date-block').classList.add('ready');
      loadSlots();
    };
  });
}

async function loadSlots() {
  if (!barber || !dateInput.value) return;
  slot = null;
  $('#to-details').disabled = true;
  $('#time-block').classList.add('ready');
  $('#slots').innerHTML = '<span class="spinner"></span>';
  try {
    const result = await api(`${publicBase()}/horarios?data=${dateInput.value}&barbeiro_id=${barber.id}&servico_id=${service.id}`);
    $('#slot-count').textContent = result.horarios.length ? `${result.horarios.length} opções` : '';
    $('#slots').innerHTML = result.horarios.map((hour) => `<button class="slot" type="button" data-hour="${escapeHTML(hour)}">${escapeHTML(hour)}</button>`).join('') || '<p class="helper">Nenhum horário livre neste dia. Tente outra data.</p>';
    $$('.slot').forEach((button) => {
      button.onclick = () => {
        slot = button.dataset.hour;
        $$('.slot').forEach((element) => element.classList.toggle('active', element === button));
        $('#to-details').disabled = false;
      };
    });
  } catch (error) {
    $('#slots').innerHTML = `<p class="helper">${escapeHTML(error.message)}</p>`;
  }
}

function showError(message) { $('#error').textContent = message; }
function formatDate(value) { return new Date(value + 'T12:00:00').toLocaleDateString('pt-BR', { weekday: 'long', day: '2-digit', month: 'long' }); }

dateInput.onchange = loadSlots;
$('#to-details').onclick = () => setStep(2);
$$('[data-back]').forEach((button) => { button.onclick = () => setStep(Number(button.dataset.back)); });
$('#phone').oninput = (event) => { event.target.value = phone(event.target.value); };

$('#to-review').onclick = () => {
  if ($('#name').value.trim().length < 2) return showError('Informe seu nome completo.');
  if ($('#phone').value.replace(/\D/g, '').length < 10) return showError('Informe um WhatsApp válido.');
  if (!$('#client-email').checkValidity()) return showError('Informe um e-mail válido.');
  const icons = {
    person: '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="8" r="3.2"/><path d="M5 20c.7-3.5 3.1-5.4 7-5.4s6.3 1.9 7 5.4"/></svg>',
    calendar: '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="4" y="5" width="16" height="15" rx="1"/><path d="M8 3v4M16 3v4M4 9h16M8 13h3M8 16h5"/></svg>',
    scissors: '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="6.5" cy="7" r="2.5"/><circle cx="6.5" cy="17" r="2.5"/><path d="m8.5 8.5 11 8M8.5 15.5l11-8"/></svg>',
    mail: '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="3" y="5" width="18" height="14" rx="1"/><path d="m4 7 8 6 8-6"/></svg>'
  };
  const shopLogo = shop.logo_url
    ? `<img src="${escapeHTML(shop.logo_url)}" alt="Logo da ${escapeHTML(shop.nome)}">`
    : `<span aria-hidden="true">${escapeHTML(initials(shop.nome))}</span>`;
  const barberVisual = barber.photo
    ? `<span class="review-avatar"><img src="${escapeHTML(barber.photo)}" alt="Foto de ${escapeHTML(barber.name)}"></span>`
    : `<span class="review-icon">${icons.person}</span>`;
  $('#review').innerHTML = `
    <div class="review-brand">
      <span class="review-logo">${shopLogo}</span>
      <span class="review-brand-copy"><small>Seu atendimento em</small><b>${escapeHTML(shop.nome)}</b><em><i></i> Agenda oficial</em></span>
      <span class="review-seal" aria-label="Estabelecimento verificado"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="m8.5 12 2.2 2.2 4.8-5"/><circle cx="12" cy="12" r="9"/></svg></span>
    </div>
    <div class="review-details">
      <div class="review-item review-date"><span class="review-icon">${icons.calendar}</span><span><small>Data e horário</small><b>${formatDate(dateInput.value)}</b><strong>${escapeHTML(slot)}</strong></span></div>
      <div class="review-item review-professional">${barberVisual}<span><small>Profissional</small><b>${escapeHTML(barber.name)}</b><em>Barbeiro selecionado</em></span></div>
      <div class="review-item"><span class="review-icon">${icons.scissors}</span><span><small>Serviço escolhido</small><b>${escapeHTML(service.nome)}</b><em>${service.duracao_minutos} min · ${money(service.preco)}</em></span></div>
      <div class="review-item review-email"><span class="review-icon">${icons.mail}</span><span><small>Confirmação enviada para</small><b>${escapeHTML($('#client-email').value.trim())}</b></span></div>
    </div>`;
  setStep(3);
};

$('#confirm').onclick = async () => {
  const button = $('#confirm');
  button.disabled = true;
  button.textContent = 'Confirmando...';
  try {
    const appointment = await api(`${publicBase()}/agendamentos`, { method: 'POST', body: JSON.stringify({ barbeiro_id: barber.id, servico_id: service.id, cliente_nome: $('#name').value.trim(), cliente_telefone: $('#phone').value, cliente_email: $('#client-email').value.trim(), data_hora: `${dateInput.value}T${slot}:00`, servico: service.nome, preco: Number(service.preco), duracao_minutos: service.duracao_minutos, whatsapp_autorizado: true }) });
    const reference = String(appointment.id).padStart(4, '0');
    const locationLogo = shop.logo_url
      ? `<span class="summary-shop-logo"><img src="${escapeHTML(shop.logo_url)}" alt="Logo da ${escapeHTML(shop.nome)}"></span>`
      : `<span class="summary-shop-logo summary-shop-initials" aria-hidden="true">${escapeHTML(initials(shop.nome))}</span>`;
    $('#summary').innerHTML = `<div class="summary-highlight"><small>DATA E HORÁRIO</small><strong>${formatDate(dateInput.value)}</strong><b>${escapeHTML(slot)}</b></div><div class="summary-grid"><div><small>Serviço</small><b>${escapeHTML(service.nome)}</b></div><div><small>Profissional</small><b>${escapeHTML(barber.name)}</b></div><div><small>Duração</small><b>${service.duracao_minutos} minutos</b></div><div><small>Valor</small><b>${money(service.preco)}</b></div></div><div class="summary-location">${locationLogo}<p><small>LOCAL CONFIRMADO</small><b>${escapeHTML(shop.nome)}</b><em>${escapeHTML(shop.endereco || 'Endereço informado pela barbearia')}</em></p><span class="summary-verified" aria-label="Local confirmado">✓</span></div><div class="summary-code"><span>NÚMERO DA RESERVA</span><b>#${escapeHTML(reference)}</b></div>`;
    const shopPhone = String(shop.telefone || '').replace(/\D/g, '');
    const whatsapp = $('#whatsapp');
    if (shopPhone.length >= 10) {
      const destination = shopPhone.startsWith('55') ? shopPhone : `55${shopPhone}`;
      whatsapp.href = `https://wa.me/${destination}?text=${encodeURIComponent(`Olá! Minha reserva #${reference} está confirmada para ${formatDate(dateInput.value)} às ${slot}.`)}`;
      whatsapp.classList.remove('hidden');
    } else {
      whatsapp.classList.add('hidden');
    }
    $('#success').classList.remove('hidden');
  } catch (error) {
    showError(error.message);
    setStep(1);
    loadSlots();
  } finally {
    button.disabled = false;
    button.innerHTML = '<span>Confirmar meu agendamento</span><b>✓</b>';
  }
};

$('#find').onclick = (event) => { event.preventDefault(); $('#lookup').showModal(); };
$('#lookup-submit').onclick = async () => {
  const value = $('#lookup-phone').value;
  if (value.replace(/\D/g, '').length < 10) return;
  $('#lookup-result').innerHTML = '<p class="helper">Consultando...</p>';
  try {
    const list = await api(`${publicBase()}/reservas/${encodeURIComponent(value)}`);
    $('#lookup-result').innerHTML = list.length ? list.map((item) => `<div class="lookup-item"><b>${formatDate(item.data_hora.slice(0, 10))} às ${new Date(item.data_hora).toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' })}</b><small>${escapeHTML(item.barbeiro_nome)} · ${escapeHTML(item.servico)} · ${escapeHTML(item.status)}</small></div>`).join('') : '<p class="helper">Nenhuma reserva recente encontrada para este número.</p>';
  } catch (error) {
    $('#lookup-result').innerHTML = `<p class="error">${escapeHTML(error.message)}</p>`;
  }
};
$('#lookup-phone').oninput = (event) => { event.target.value = phone(event.target.value); };

init();
