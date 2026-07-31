(() => {
  'use strict';

  const returnParams = new URLSearchParams(window.location.search);
  const needsFullAuthFlow = ['email_confirmado', 'checkout', 'google', 'reset_password']
    .some(key => returnParams.has(key));
  if (needsFullAuthFlow) {
    window.location.replace(`/landing.html${window.location.search}`);
    return;
  }

  const plans = {
    essencial: { name: 'Essencial', price: 'R$ 29,90', capacity: '1 profissional', rank: 1 },
    profissional: { name: 'Profissional', price: 'R$ 44,90', capacity: 'Até 2 profissionais', rank: 2 },
    premium: { name: 'Premium', price: 'R$ 64,90', capacity: 'Equipe ilimitada', rank: 3 }
  };
  const teamPlanMap = { solo: 'essencial', duo: 'profissional', team: 'premium' };
  const teamLabels = { solo: '1 profissional', duo: 'Até 2 profissionais', team: '3 ou mais profissionais' };
  const modal = document.querySelector('#signup-modal');
  const form = document.querySelector('#signup-form');
  let step = 1;
  let chosenPlan = null;
  let lastFocused = null;

  const recommendedPlanForTeam = team => teamPlanMap[team] || null;
  const isPlanCompatible = (team, plan) => Boolean(plans[plan] && plans[recommendedPlanForTeam(team)] && plans[plan].rank >= plans[recommendedPlanForTeam(team)].rank);
  const firstChargeDate = () => {
    const date = new Date();
    date.setDate(date.getDate() + 14);
    return new Intl.DateTimeFormat('pt-BR', { day: '2-digit', month: 'long', year: 'numeric' }).format(date);
  };
  const teamValue = () => form?.elements.team_size?.value || '';
  const showToast = message => {
    const toast = document.querySelector('#toast');
    toast.textContent = message;
    toast.classList.add('show');
    window.setTimeout(() => toast.classList.remove('show'), 4200);
  };

  function updateStep(nextStep) {
    step = Math.max(1, Math.min(3, nextStep));
    document.querySelectorAll('.signup-step').forEach(section => { section.hidden = Number(section.dataset.step) !== step; });
    document.querySelectorAll('.signup-progress i').forEach((item, index) => {
      item.classList.toggle('active', index + 1 === step);
      item.classList.toggle('done', index + 1 < step);
    });
    const copy = [
      ['Quantos profissionais trabalham na barbearia?', 'Vamos indicar o plano compatível com sua operação.'],
      ['Crie sua conta', 'Preencha os dados para preparar seu acesso ao CortaFlow.'],
      ['Revise antes de continuar', 'Confira o plano, o período grátis e os dados da sua equipe.']
    ][step - 1];
    document.querySelector('#step-label').textContent = `ETAPA ${step} DE 3`;
    document.querySelector('#signup-title').textContent = copy[0];
    document.querySelector('#step-description').textContent = copy[1];
    document.querySelector('#signup-back').hidden = step === 1;
    document.querySelector('#signup-next').hidden = step === 3;
    document.querySelector('#signup-submit').hidden = step !== 3;
    document.querySelector('#signup-error').textContent = '';
    if (step === 3) updateReview();
  }

  function updateRecommendation() {
    const recommended = recommendedPlanForTeam(teamValue());
    chosenPlan = recommended;
    document.querySelector('#instant-plan').textContent = recommended ? `${plans[recommended].name} · ${plans[recommended].price}/mês` : 'Selecione sua equipe';
  }

  function updateReview() {
    const team = teamValue();
    const recommended = recommendedPlanForTeam(team);
    if (!isPlanCompatible(team, chosenPlan)) chosenPlan = recommended;
    const plan = plans[chosenPlan];
    document.querySelector('#review-plan').textContent = plan.name;
    document.querySelector('#review-team').textContent = teamLabels[team];
    document.querySelector('#review-price').textContent = plan.price;
    document.querySelector('#first-charge').textContent = firstChargeDate();
    const choices = document.querySelector('#compatible-plans');
    choices.innerHTML = Object.entries(plans)
      .filter(([key]) => isPlanCompatible(team, key))
      .map(([key, value]) => `<button type="button" data-compatible-plan="${key}"${key === chosenPlan ? ' aria-current="true"' : ''}><span>${value.name}</span><strong>${value.price}/mês</strong></button>`)
      .join('');
  }

  function openSignup(plan) {
    lastFocused = document.activeElement;
    modal.hidden = false;
    document.body.classList.add('modal-open');
    if (plan && plans[plan]) {
      const matchingTeam = Object.keys(teamPlanMap).find(key => teamPlanMap[key] === plan);
      const radio = form.querySelector(`[name="team_size"][value="${matchingTeam}"]`);
      if (radio) radio.checked = true;
      chosenPlan = plan;
      updateRecommendation();
    }
    updateStep(1);
    window.setTimeout(() => modal.querySelector('input, button')?.focus(), 0);
  }

  function closeSignup() {
    modal.hidden = true;
    document.body.classList.remove('modal-open');
    lastFocused?.focus();
  }

  document.querySelectorAll('[data-open-signup]').forEach(button => button.addEventListener('click', () => openSignup()));
  document.querySelectorAll('[data-plan]').forEach(button => button.addEventListener('click', () => openSignup(button.dataset.plan)));
  document.querySelectorAll('[data-close-signup]').forEach(button => button.addEventListener('click', closeSignup));
  document.querySelectorAll('[data-login]').forEach(button => button.addEventListener('click', () => { window.location.href = '/landing.html?access=login'; }));
  form?.addEventListener('change', event => { if (event.target.name === 'team_size') updateRecommendation(); });
  document.querySelector('#signup-next')?.addEventListener('click', () => {
    if (step === 1 && !teamValue()) return void (document.querySelector('#signup-error').textContent = 'Escolha o tamanho da sua equipe.');
    if (step === 2) {
      const fields = [...form.querySelectorAll('[data-step="2"] input[required]')];
      const invalid = fields.find(field => !field.checkValidity());
      if (invalid) { invalid.reportValidity(); return; }
    }
    updateStep(step + 1);
  });
  document.querySelector('#signup-back')?.addEventListener('click', () => updateStep(step - 1));
  document.querySelector('[data-change-plan]')?.addEventListener('click', () => {
    const choices = document.querySelector('#compatible-plans');
    choices.hidden = !choices.hidden;
  });
  document.querySelector('#compatible-plans')?.addEventListener('click', event => {
    const button = event.target.closest('[data-compatible-plan]');
    if (!button || !isPlanCompatible(teamValue(), button.dataset.compatiblePlan)) return;
    chosenPlan = button.dataset.compatiblePlan;
    updateReview();
    document.querySelector('#compatible-plans').hidden = true;
  });
  document.querySelector('[data-toggle-password]')?.addEventListener('click', event => {
    const input = document.querySelector('#preview-password');
    input.type = input.type === 'password' ? 'text' : 'password';
    event.currentTarget.textContent = input.type === 'password' ? 'Mostrar' : 'Ocultar';
  });
  document.querySelector('#preview-password')?.addEventListener('input', event => {
    const length = event.target.value.length;
    document.querySelector('#password-strength').textContent = length >= 12 ? 'Boa: a senha atende ao mínimo de 12 caracteres.' : `Faltam ${12 - length} caracteres.`;
  });
  form?.addEventListener('submit', async event => {
    event.preventDefault();
    if (!chosenPlan || !isPlanCompatible(teamValue(), chosenPlan)) return;
    const submit = document.querySelector('#signup-submit');
    submit.disabled = true;
    submit.textContent = 'Criando conta…';
    const data = new FormData(form);
    const payload = { nome: data.get('nome'), barbearia_nome: data.get('barbearia_nome'), email: data.get('email'), telefone: data.get('telefone'), senha: data.get('senha'), plano: chosenPlan };
    try {
      const response = await fetch('/api/auth/register', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
      const result = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(result.detail || result.message || 'Não foi possível criar sua conta.');
      closeSignup();
      form.reset();
      chosenPlan = null;
      showToast('Conta criada. Confira seu e-mail para confirmar o acesso.');
    } catch (error) {
      document.querySelector('#signup-error').textContent = error.message;
    } finally {
      submit.disabled = false;
      submit.textContent = 'Confirmar e-mail';
    }
  });

  const tabs = [...document.querySelectorAll('[role="tab"]')];
  function selectTab(tab) {
    tabs.forEach(item => item.setAttribute('aria-selected', String(item === tab)));
    document.querySelectorAll('[role="tabpanel"]').forEach(panel => panel.classList.toggle('active', panel.dataset.panel === tab.dataset.feature));
  }
  tabs.forEach((tab, index) => {
    tab.tabIndex = index === 0 ? 0 : -1;
    tab.addEventListener('click', () => selectTab(tab));
    tab.addEventListener('keydown', event => {
      const keys = { ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1 };
      if (!(event.key in keys) && event.key !== 'Home' && event.key !== 'End') return;
      event.preventDefault();
      const next = event.key === 'Home' ? 0 : event.key === 'End' ? tabs.length - 1 : (index + keys[event.key] + tabs.length) % tabs.length;
      tabs.forEach((item, i) => { item.tabIndex = i === next ? 0 : -1; });
      tabs[next].focus(); selectTab(tabs[next]);
    });
  });

  const showcaseLightbox = document.querySelector('#showcase-lightbox');
  let showcaseLastFocused = null;
  function closeShowcase() {
    if (!showcaseLightbox || showcaseLightbox.hidden) return;
    showcaseLightbox.hidden = true;
    document.body.classList.remove('modal-open');
    showcaseLastFocused?.focus();
  }
  document.querySelectorAll('[data-expand-image]').forEach(button => button.addEventListener('click', () => {
    showcaseLastFocused = button;
    const image = showcaseLightbox.querySelector('img');
    image.src = button.dataset.expandImage;
    image.alt = button.dataset.expandAlt || '';
    showcaseLightbox.querySelector('#showcase-lightbox-title').textContent = button.dataset.expandAlt || 'Tela do CortaFlow';
    showcaseLightbox.hidden = false;
    document.body.classList.add('modal-open');
    showcaseLightbox.querySelector('header [data-close-showcase]')?.focus();
  }));
  document.querySelectorAll('[data-close-showcase]').forEach(button => button.addEventListener('click', closeShowcase));

  const menu = document.querySelector('.menu-button');
  const nav = document.querySelector('#nav');
  menu?.addEventListener('click', () => { const open = nav.classList.toggle('open'); menu.setAttribute('aria-expanded', String(open)); });
  nav?.addEventListener('click', event => { if (event.target.closest('a,button')) { nav.classList.remove('open'); menu?.setAttribute('aria-expanded', 'false'); } });
  document.querySelectorAll('.faq details').forEach(details => details.addEventListener('toggle', () => {
    if (details.open && window.matchMedia('(max-width: 820px)').matches) document.querySelectorAll('.faq details').forEach(item => { if (item !== details) item.open = false; });
  }));
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && showcaseLightbox && !showcaseLightbox.hidden) {
      closeShowcase();
      return;
    }
    if (event.key === 'Escape' && !modal.hidden) closeSignup();
    if (event.key === 'Tab' && !modal.hidden) {
      const focusable = [...modal.querySelectorAll('button:not([disabled]), input:not([disabled])')].filter(item => item.offsetParent !== null);
      if (!focusable.length) return;
      const first = focusable[0], last = focusable.at(-1);
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    }
  });

  window.PreviewDesign = { plans, teamPlanMap, recommendedPlanForTeam, isPlanCompatible, firstChargeDate };
})();
