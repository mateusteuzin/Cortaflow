(() => {
  'use strict';

  const returnParams = new URLSearchParams(window.location.search);
  const needsFullAuthFlow = ['email_confirmado', 'checkout', 'google', 'reset_password']
    .some(key => returnParams.has(key));
  if (needsFullAuthFlow) {
    window.location.replace(`/landing.html${window.location.search}`);
    return;
  }

  const authUrl = (access, plan = '') => {
    const query = new URLSearchParams({ access });
    if (plan) query.set('plan', plan);
    return `/landing.html?${query.toString()}`;
  };
  const goToAuth = (access, plan = '') => {
    window.location.assign(authUrl(access, plan));
  };

  document.querySelectorAll('[data-open-signup]').forEach(button => button.addEventListener('click', () => goToAuth('register')));
  document.querySelectorAll('[data-plan]').forEach(button => button.addEventListener('click', () => goToAuth('register', button.dataset.plan)));
  document.querySelectorAll('[data-login]').forEach(button => button.addEventListener('click', () => goToAuth('login')));

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
  });

  window.PreviewDesign = { authUrl };
})();
