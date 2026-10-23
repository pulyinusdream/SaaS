(function () {
  'use strict';
  document.body.classList.add('js');
  const menu = document.querySelector('.sidebar');
  const toggle = document.querySelector('.nav-toggle');
  const main = document.querySelector('.work-sheet');
  const mobile = window.matchMedia('(max-width:820px)');
  function closeMenu(returnFocus = true) {
    document.body.classList.remove('nav-open');
    if (toggle) { toggle.setAttribute('aria-expanded', 'false'); toggle.setAttribute('aria-label', 'Open navigation'); }
    if (main) main.inert = false;
    if (menu) menu.inert = mobile.matches;
    if (returnFocus && toggle && mobile.matches) toggle.focus();
  }
  if (toggle && menu) {
    const close = document.createElement('button');
    close.type = 'button'; close.className = 'icon-button mobile-nav-close';
    close.setAttribute('aria-label', 'Close navigation');
    close.innerHTML = '<svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" aria-hidden="true"><path d="m6 6 12 12M6 18 18 6"/></svg>'; 
    menu.prepend(close);
    close.addEventListener('click', () => closeMenu());
    toggle.addEventListener('click', () => {
      if (document.body.classList.contains('nav-open')) { closeMenu(); return; }
      document.body.classList.add('nav-open'); menu.inert = false;
      toggle.setAttribute('aria-expanded', 'true'); toggle.setAttribute('aria-label', 'Close navigation');
      if (main) main.inert = true;
      close.focus();
    });
    document.addEventListener('keydown', event => {
      if (!document.body.classList.contains('nav-open')) return;
      if (event.key === 'Escape') { closeMenu(); return; }
      if (event.key === 'Tab') {
        const focusable = [...menu.querySelectorAll('a,button')].filter(el => !el.disabled && el.getClientRects().length);
        const first = focusable[0], last = focusable[focusable.length - 1];
        if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
        else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
      }
    });
    document.addEventListener('click', event => {
      if (document.body.classList.contains('nav-open') && !menu.contains(event.target) && !toggle.contains(event.target)) closeMenu();
    });
    mobile.addEventListener('change', () => closeMenu(false));
    closeMenu(false);
  }
  document.querySelectorAll('time[data-local-time]').forEach(el => {
    const date = new Date(el.dateTime);
    if (!Number.isNaN(date.getTime())) {
      el.textContent = new Intl.DateTimeFormat(undefined, { month: 'short', day: 'numeric', year: 'numeric', hour: 'numeric', minute: '2-digit' }).format(date);
      el.title = `${el.textContent} (${Intl.DateTimeFormat().resolvedOptions().timeZone})`;
    }
  });
  const toast = document.querySelector('.toast');
  let toastTimer;
  function notify(message) {
    if (!toast) return;
    clearTimeout(toastTimer); toast.textContent = message; toast.hidden = false;
    toastTimer = setTimeout(() => { toast.hidden = true; }, 4500);
  }
  document.querySelectorAll('[data-copy],[data-copy-target]').forEach(button => {
    button.addEventListener('click', async () => {
      const input = button.dataset.copyTarget ? document.getElementById(button.dataset.copyTarget) : null;
      const text = input ? input.value : button.dataset.copy;
      try {
        await navigator.clipboard.writeText(text);
        notify('Link copied. Local links work on this computer.');
      } catch (_error) {
        if (input) { input.focus(); input.select(); notify('Copy is unavailable here. The link is selected for you to copy.'); }
        else {
          // The native form link remains usable when clipboard permission is unavailable.
          const link = document.querySelector('.capture-actions a');
          if (link) link.focus();
          notify('Copy is unavailable here. Open the form and copy its address.');
        }
      }
    });
  });
  document.querySelectorAll('form[data-pending]').forEach(form => {
    form.addEventListener('submit', () => {
      const button = form.querySelector('button:not([type="button"])');
      if (!button || button.disabled) return;
      button.dataset.original = button.innerHTML;
      button.textContent = form.dataset.pending;
      button.disabled = true;
      form.setAttribute('aria-busy', 'true');
    });
  });
  window.addEventListener('pageshow', () => {
    document.querySelectorAll('button[data-original]').forEach(button => { button.innerHTML = button.dataset.original; button.disabled = false; });
    document.querySelectorAll('form[aria-busy]').forEach(form => form.removeAttribute('aria-busy'));
  });
  // Native summaries work without JS. Deep links and validation anchors also
  // reveal their containing sections before the browser scrolls/focuses them.
  function revealFragment(fragment) {
    let id;
    try { id = decodeURIComponent(fragment.replace(/^#/, '')); }
    catch (_error) { return null; }
    if (!id) return null;
    const target = document.getElementById(id);
    if (!target) return null;
    let parent = target;
    while (parent) {
      if (parent.tagName === 'DETAILS') parent.open = true;
      parent = parent.parentElement;
    }
    return target;
  }
  document.addEventListener('click', event => {
    const link = event.target.closest('a[href^="#"]');
    if (link) revealFragment(link.getAttribute('href'));
  });
  window.addEventListener('hashchange', () => {
    const target = revealFragment(window.location.hash);
    if (target) target.scrollIntoView({ block: 'start' });
  });
  const initialTarget = revealFragment(window.location.hash);
  if (initialTarget) requestAnimationFrame(() => initialTarget.scrollIntoView({ block: 'start' }));
  const errors = document.querySelector('[data-error-summary]');
  if (errors) {
    const firstError = errors.querySelector('a[href^="#"]');
    if (firstError) revealFragment(firstError.getAttribute('href'));
    errors.focus();
  }
})();
