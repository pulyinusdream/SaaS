'use strict';

// A small, consistent SVG icon set keeps the site independent of runtime libraries.
const iconPaths = {
  'arrow-up-right':'<path d="M7 17 17 7M7 7h10v10"/>',
  'arrow-right':'<path d="M4 12h16m-6-6 6 6-6 6"/>',
  'check':'<path d="m5 12 4 4L19 6"/>',
  'check-check':'<path d="m2 12 4 4L16 6m-5 10 10-10"/>',
  'menu':'<path d="M4 6h16M4 12h16M4 18h16"/>',
  'x':'<path d="m6 6 12 12M6 18 18 6"/>',
  'play':'<path d="m9 5 11 7-11 7z"/>',
  'grid':'<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>',
  'inbox':'<path d="m4 4-2 10v6h20v-6L20 4ZM2 14h6l2 3h4l2-3h6"/>',
  'calendar':'<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M16 3v4M8 3v4M3 11h18"/>',
  'calendar-check':'<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M16 3v4M8 3v4M3 11h18m-13 5 3 3 5-5"/>',
  'users':'<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2m20 0v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75"/><circle cx="9" cy="7" r="4"/>',
  'user':'<circle cx="12" cy="7" r="4"/><path d="M5 21v-2a7 7 0 0 1 14 0v2"/>',
  'settings':'<path d="m9 3-.5 3-2.5 1-2.5-1.5-2 3.5L4 11v2l-2.5 2 2 3.5L6 17l2.5 1 .5 3h4l.5-3 2.5-1 2.5 1.5 2-3.5-2.5-2v-2l2.5-2-2-3.5L16 7l-2.5-1-.5-3Z"/><circle cx="11" cy="12" r="3"/>',
  'message-square':'<path d="M21 15a3 3 0 0 1-3 3H8l-5 4V5a3 3 0 0 1 3-3h12a3 3 0 0 1 3 3Z"/><path d="M7 7h10M7 12h6"/>',
  'phone':'<path d="M22 16.9v3a2 2 0 0 1-2.2 2 19.8 19.8 0 0 1-8.6-3.1 19.5 19.5 0 0 1-6-6A19.8 19.8 0 0 1 2.1 4.2 2 2 0 0 1 4.1 2h3a2 2 0 0 1 2 1.7c.1.9.4 1.7.7 2.5a2 2 0 0 1-.5 2.1L8 9.6a16 16 0 0 0 6 6l1.3-1.3a2 2 0 0 1 2.1-.5c.8.3 1.6.6 2.5.7a2 2 0 0 1 2.1 2.4Z"/>',
  'phone-outgoing':'<path d="M15 3h6v6m-6 0 6-6M9 3H5a2 2 0 0 0-2 2c0 8.8 7.2 16 16 16a2 2 0 0 0 2-2v-4l-5-1-2 2a13 13 0 0 1-6-6l2-2Z"/>',
  'more':'<circle cx="5" cy="12" r="1"/><circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/>',
  'wind':'<path d="M3 8h12a3 3 0 1 0-3-3M2 12h17a3 3 0 1 1-3 3M4 16h5a3 3 0 1 1-3 3"/>',
  'droplet':'<path d="M12 3c-3 4-7 8-7 12a7 7 0 0 0 14 0c0-4-4-8-7-12Z"/><path d="M8 15a4 4 0 0 0 4 4"/>',
  'house':'<path d="m3 10 9-7 9 7M5 9v12h14V9M9 21v-8h6v8"/>',
  'door':'<path d="M3 21h18M5 21V3h14v18M8 6h8M8 10h8M8 14h8M8 18h8"/>',
  'zap':'<path d="m13 2-9 12h7l-1 8 10-12h-7l1-8Z"/>',
  'headphones':'<path d="M3 14v-3a9 9 0 0 1 18 0v3M3 14a2 2 0 0 1 2-2h2v8H5a2 2 0 0 1-2-2Zm18 0a2 2 0 0 0-2-2h-2v8h2a2 2 0 0 0 2-2Z"/>',
  'layers':'<path d="m12 3 10 5-10 5L2 8Zm-10 9 10 5 10-5M2 16l10 5 10-5"/>',
  'info':'<circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7h.01"/>',
  'shield-check':'<path d="M12 2 3 6v6c0 5 9 10 9 10s9-5 9-10V6ZM8 12l3 3 5-6"/>',
  'monitor':'<rect x="2" y="3" width="20" height="14" rx="2"/><path d="M8 21h8m-4-4v4"/>',
  'lock':'<rect x="4" y="10" width="16" height="11" rx="2"/><path d="M8 10V7a4 4 0 0 1 8 0v3m-4 5v2"/>',
  'plus':'<path d="M12 5v14M5 12h14"/>',
  'copy':'<rect x="8" y="8" width="13" height="13" rx="2"/><path d="M16 8V3H3v13h5"/>',
  'download':'<path d="M12 3v12m-5-5 5 5 5-5M4 16v5h16v-5"/>',
  'sparkle':'<path d="m12 2 2.5 7.5L22 12l-7.5 2.5L12 22l-2.5-7.5L2 12l7.5-2.5Z"/>'
};

function renderIcons(root = document) {
  root.querySelectorAll('[data-icon]').forEach((node) => {
    const name = node.dataset.icon;
    if (!iconPaths[name]) return;
    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.setAttribute('viewBox', '0 0 24 24');
    svg.setAttribute('class', 'icon');
    svg.setAttribute('aria-hidden', 'true');
    svg.setAttribute('focusable', 'false');
    svg.innerHTML = iconPaths[name];
    node.replaceWith(svg);
  });
}
renderIcons();
document.querySelectorAll('[data-year]').forEach((node) => { node.textContent = String(new Date().getFullYear()); });

const menuToggle = document.querySelector('.menu-toggle');
const mainNav = document.getElementById('main-nav');
if (menuToggle && mainNav) {
  const setMenu = (open) => {
    mainNav.classList.toggle('is-open', open);
    menuToggle.setAttribute('aria-expanded', String(open));
    menuToggle.setAttribute('aria-label', open ? 'Close navigation' : 'Open navigation');
    menuToggle.innerHTML = `<i data-icon="${open ? 'x' : 'menu'}"></i>`;
    renderIcons(menuToggle);
  };
  menuToggle.addEventListener('click', () => setMenu(menuToggle.getAttribute('aria-expanded') !== 'true'));
  mainNav.querySelectorAll('a').forEach((link) => link.addEventListener('click', () => setMenu(false)));
  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && menuToggle.getAttribute('aria-expanded') === 'true') {
      setMenu(false);
      menuToggle.focus();
    }
  });
  document.addEventListener('click', (event) => {
    // The icon is replaced when toggling; the original event target can be detached.
    // The event path retains the button even after that replacement.
    const path = event.composedPath();
    if (!path.includes(mainNav) && !path.includes(menuToggle)) setMenu(false);
  });
  const desktopQuery = window.matchMedia('(min-width:721px)');
  desktopQuery.addEventListener('change', () => setMenu(false));
}

const form = document.getElementById('walkthrough-form');
const recipient = 'vicentepaulandrei1823@gmail.com';
if (form && form.dataset.connected !== 'true') {
  const status = document.getElementById('form-status');
  const tools = document.getElementById('request-tools');
  const draftLink = document.getElementById('email-draft-link');
  const copyButton = document.getElementById('copy-request');
  const downloadButton = document.getElementById('download-request');
  let currentRequest = '';
  let mailto = '';
  const requiredFields = ['name', 'company', 'email', 'trade'];
  const errorText = { name: 'Please enter your name.', company: 'Please enter your business name.', email: 'Please enter a valid email address.', trade: 'Please select your trade.' };
  const validateField = (id) => {
    const field = form.elements.namedItem(id);
    const valid = Boolean(field.value.trim()) && field.validity.valid;
    field.setAttribute('aria-invalid', String(!valid));
    field.setAttribute('aria-describedby', `${id}-error`);
    document.getElementById(`${id}-error`).textContent = valid ? '' : errorText[id];
    return valid;
  };
  const clearPreparedRequest = () => {
    currentRequest = '';
    mailto = '';
    tools.hidden = true;
    status.textContent = '';
    status.className = 'form-status';
    copyButton.textContent = 'Copy request';
  };
  form.addEventListener('input', (event) => {
    clearPreparedRequest();
    const id = event.target.id;
    if (requiredFields.includes(id) && event.target.getAttribute('aria-invalid') === 'true') validateField(id);
  });
  form.addEventListener('change', clearPreparedRequest);
  form.addEventListener('submit', (event) => {
    event.preventDefault();
    const invalid = requiredFields.filter((id) => !validateField(id));
    if (invalid.length) {
      tools.hidden = true;
      status.className = 'form-status error';
      status.textContent = 'Please check the highlighted fields so we can prepare your request.';
      form.elements.namedItem(invalid[0]).focus();
      return;
    }
    const data = new FormData(form);
    const name = String(data.get('name')).trim();
    const company = String(data.get('company')).trim();
    const subject = `Free walkthrough request — ${company.replace(/[\r\n]/g, ' ')}`;
    currentRequest = [
      'Hello KJAncy,', '', 'I would like a free walkthrough for my business.', '',
      `Name: ${name}`, `Business: ${company}`, `Email: ${String(data.get('email')).trim()}`,
      `Trade: ${data.get('trade')}`, `Interested in: ${data.get('plan')}`, '',
      'The biggest thing on my plate:', String(data.get('message')).trim() || 'I would like to discuss this during the walkthrough.', '',
      'Please get in touch to discuss a suitable package and coverage hours.'
    ].join('\n');
    mailto = `mailto:${recipient}?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(currentRequest)}`;
    draftLink.href = mailto;
    status.className = 'form-status success';
    status.textContent = 'Your request is ready. Open the email draft below and send it to finish. Nothing has been sent yet. If you don’t use an email app, copy or download your request and email it to ' + recipient + '.';
    tools.hidden = false;
  });
  copyButton.addEventListener('click', async () => {
    if (!currentRequest) return;
    copyButton.disabled = true;
    try {
      await navigator.clipboard.writeText(currentRequest);
      copyButton.textContent = 'Request copied';
      status.textContent = `Request copied. Paste it into an email to ${recipient} and send it to finish.`;
    } catch {
      status.className = 'form-status error';
      status.textContent = 'Your browser could not copy the request. Use Open email draft or Download request instead.';
    } finally { copyButton.disabled = false; }
  });
  downloadButton.addEventListener('click', () => {
    if (!currentRequest) return;
    const blob = new Blob([`To: ${recipient}\nSubject: KJAncy walkthrough request\n\n${currentRequest}`], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = 'kjancy-walkthrough-request.txt';
    document.body.appendChild(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    status.className = 'form-status success';
    status.textContent = `Your request file is ready. Email the downloaded text to ${recipient} to finish. Nothing has been sent automatically.`;
  });
  document.querySelectorAll('[data-plan]').forEach((link) => link.addEventListener('click', () => {
    form.elements.namedItem('plan').value = link.dataset.plan;
    clearPreparedRequest();
  }));
  const requestedPlan = new URLSearchParams(window.location.search).get('plan');
  if (['Lead Booking System', 'Dedicated Dispatcher System'].includes(requestedPlan)) form.elements.namedItem('plan').value = requestedPlan;
}

// The connected site uses a native same-origin POST. The server remains the
// authority for validation and saving; this layer only adds immediate feedback.
if (form && form.dataset.connected === 'true') {
  const fields = ['name', 'company', 'email', 'trade'];
  const messages = {name: 'Enter your name.', company: 'Enter your business name.', email: 'Enter a valid email address.', trade: 'Choose your trade.'};
  const status = document.getElementById('form-status');
  const button = form.querySelector('[type="submit"]');
  const originalButton = button.innerHTML;
  const validate = (id) => {
    const field = form.elements.namedItem(id);
    const valid = Boolean(field.value.trim()) && field.validity.valid;
    field.setAttribute('aria-invalid', String(!valid));
    document.getElementById(`${id}-error`).textContent = valid ? '' : messages[id];
    return valid;
  };
  form.addEventListener('submit', (event) => {
    const invalid = fields.filter((id) => !validate(id));
    if (invalid.length) {
      event.preventDefault();
      status.className = 'form-status error';
      status.textContent = 'Check the highlighted fields. Your request hasn’t been sent.';
      form.elements.namedItem(invalid[0]).focus();
      return;
    }
    if (form.getAttribute('aria-busy') === 'true') { event.preventDefault(); return; }
    form.setAttribute('aria-busy', 'true');
    button.disabled = true;
    button.textContent = 'Sending request…';
    status.textContent = 'Saving your request. Please keep this page open.';
  });
  form.addEventListener('input', (event) => {
    if (fields.includes(event.target.id) && event.target.getAttribute('aria-invalid') === 'true') validate(event.target.id);
  });
  window.addEventListener('pageshow', () => {
    form.removeAttribute('aria-busy'); button.disabled = false; button.innerHTML = originalButton;
    status.textContent = '';
  });
  document.querySelectorAll('[data-plan]').forEach((link) => link.addEventListener('click', () => {
    form.elements.namedItem('plan').value = link.dataset.plan;
  }));
  const requested = new URLSearchParams(window.location.search).get('plan');
  if (['Lead Booking System', 'Dedicated Dispatcher System'].includes(requested)) form.elements.namedItem('plan').value = requested;
}
const formNotice = document.getElementById('walkthrough-errors') || document.getElementById('walkthrough-success');
if (formNotice) formNotice.focus();
if ((form && form.dataset.connected === 'true') || document.getElementById('walkthrough-success')) {
  const alignInitialForm = () => {
    const target = ['#walkthrough-form', '#walkthrough-success'].includes(window.location.hash)
      ? document.getElementById(window.location.hash.slice(1)) : null;
    if (target) document.fonts.ready.then(() => requestAnimationFrame(() => target.scrollIntoView({behavior: 'instant', block: 'start'})));
  };
  if (document.readyState === 'complete') alignInitialForm();
  else window.addEventListener('load', alignInitialForm, {once: true});
}

const demoDialog = document.getElementById('demo-dialog');
if (demoDialog) {
  const tradeSelect = document.getElementById('demo-trade');
  const nextButton = document.getElementById('demo-next');
  const demoCta = document.getElementById('demo-cta');
  const tradeExamples = {
    'HVAC': '“Our AC isn’t cooling. Can you help?”',
    'Plumbing': '“There’s a leak under our kitchen sink. Can we book a visit?”',
    'Roofing': '“We noticed a roof leak after the rain. Can you take a look?”',
    'Garage doors': '“Our garage door won’t open. Can someone come out?”',
    'Electrical': '“A few outlets stopped working. Can we schedule a visit?”'
  };
  let step = 0;
  const updateDemo = () => {
    const stages = [
      { icon: 'message-square', label: 'The inquiry', title: 'An inquiry comes in.', copy: `${tradeExamples[tradeSelect.value]} Your website or chat collects the service needed, contact details, and location.`, button: 'See the follow-up' },
      { icon: 'phone-outgoing', label: 'The follow-up', title: 'A person follows up.', copy: 'During agreed coverage hours, a team member follows up by phone or text, checks the details, and discusses a suitable appointment. A person handles questions and confirms next steps.', button: 'See the handoff' },
      { icon: 'calendar-check', label: 'The handoff', title: 'Your team gets the details.', copy: 'Once availability and the customer’s details are confirmed, the appointment and customer record are updated. Your team has the information it needs for the visit.', button: 'Replay example' }
    ];
    const stage = stages[step];
    document.getElementById('demo-stage-label').textContent = stage.label;
    document.getElementById('demo-stage-title').textContent = stage.title;
    document.getElementById('demo-stage-copy').textContent = stage.copy;
    const icon = document.getElementById('demo-stage-icon');
    icon.innerHTML = `<i data-icon="${stage.icon}"></i>`;
    renderIcons(icon);
    nextButton.innerHTML = `${stage.button} <i data-icon="arrow-right"></i>`;
    renderIcons(nextButton);
    demoDialog.querySelectorAll('.demo-progress>span').forEach((node, index) => {
      node.classList.toggle('active', index <= step);
      if (index === step) node.setAttribute('aria-current', 'step'); else node.removeAttribute('aria-current');
    });
    demoCta.hidden = step !== 2;
  };
  document.querySelectorAll('[data-open-demo]').forEach((button) => button.addEventListener('click', () => {
    step = 0;
    updateDemo();
    demoDialog.showModal();
    document.body.classList.add('dialog-open');
  }));
  demoDialog.querySelector('.dialog-close').addEventListener('click', () => demoDialog.close());
  demoDialog.addEventListener('click', (event) => { if (event.target === demoDialog) { const rect = demoDialog.getBoundingClientRect(); if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) demoDialog.close(); } });
  demoDialog.addEventListener('close', () => document.body.classList.remove('dialog-open'));
  tradeSelect.addEventListener('change', () => { step = 0; updateDemo(); });
  nextButton.addEventListener('click', () => { step = (step + 1) % 3; updateDemo(); });
  demoCta.addEventListener('click', () => demoDialog.close());
  updateDemo();
}
