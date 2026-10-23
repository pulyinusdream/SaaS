(function () {
  'use strict';
  if (document.getElementById('kjancy-chat-widget')) return;

  const icons = {
    chat: '<path d="M21 15a3 3 0 0 1-3 3H8l-5 4V5a3 3 0 0 1 3-3h12a3 3 0 0 1 3 3Z"/><path d="M7 7h10M7 12h6"/>',
    close: '<path d="m6 6 12 12M6 18 18 6"/>',
    reset: '<path d="M3 11a9 9 0 1 1 2.6 7M3 4v7h7"/>',
    send: '<path d="m22 2-7 20-4-9-9-4Zm0 0L11 13"/>',
    arrow: '<path d="M7 17 17 7M7 7h10v10"/>'
  };
  const icon = (name) => `<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">${icons[name]}</svg>`;
  const widget = document.createElement('div');
  widget.id = 'kjancy-chat-widget';
  widget.className = 'chat-widget';
  widget.setAttribute('data-ui', '');
  // Static markup only. All visitor input and response text is rendered with textContent.
  widget.innerHTML = `
    <section class="chat-panel" id="kjancy-chat-panel" role="dialog" aria-modal="false" aria-labelledby="kjancy-chat-title" aria-describedby="kjancy-chat-description" hidden>
      <header class="chat-header">
        <span class="chat-avatar">${icon('chat')}</span>
        <div class="chat-title-group"><h2 id="kjancy-chat-title">KJAncy guide</h2><p>Practical answers. A clearer next step.</p></div>
        <button type="button" class="chat-icon-button" id="chat-reset" aria-label="Start a new chat" title="Start over">${icon('reset')}</button>
        <button type="button" class="chat-icon-button" id="chat-close" aria-label="Close chat">${icon('close')}</button>
      </header>
      <p class="chat-intro-note" id="kjancy-chat-description">Automated website guide · Preset service answers, not a live agent.</p>
      <div class="chat-log" id="chat-log" role="log" aria-label="Chat conversation" aria-live="polite" aria-relevant="additions" tabindex="0"></div>
      <div class="chat-suggestions" id="chat-suggestions" role="group" aria-label="Suggested questions"></div>
      <form class="chat-composer" id="chat-form" novalidate>
        <label class="chat-sr-only" for="chat-question">Your question about KJAncy</label>
        <div class="chat-input-row"><textarea class="chat-input" id="chat-question" placeholder="Ask a question…" rows="1" maxlength="500" aria-describedby="chat-input-help chat-status"></textarea><button type="submit" class="chat-send" aria-label="Send message" disabled>${icon('send')}</button></div>
        <span class="chat-sr-only" id="chat-input-help">Up to 500 characters. Enter sends your message. Shift plus Enter starts a new line.</span>
        <p class="chat-status" id="chat-status" role="status" aria-live="polite"></p>
        <span class="chat-counter" id="chat-counter" hidden></span>
        <p class="chat-footnote"><span>Chat stays on this page.</span><a href="privacy.html">Privacy</a></p>
      </form>
    </section>
    <button type="button" class="chat-launcher" aria-controls="kjancy-chat-panel" aria-expanded="false" aria-label="Open KJAncy chat"><span class="chat-launcher-icon">${icon('chat')}</span><span class="chat-launcher-text">Ask KJAncy</span></button>`;
  document.body.appendChild(widget);

  const panel = widget.querySelector('.chat-panel');
  const launcher = widget.querySelector('.chat-launcher');
  const closeButton = widget.querySelector('#chat-close');
  const resetButton = widget.querySelector('#chat-reset');
  const chatForm = widget.querySelector('#chat-form');
  const input = widget.querySelector('#chat-question');
  const sendButton = widget.querySelector('.chat-send');
  const log = widget.querySelector('#chat-log');
  const suggestions = widget.querySelector('#chat-suggestions');
  const status = widget.querySelector('#chat-status');
  const counter = widget.querySelector('#chat-counter');
  const guide = window.KJAncyChatGuide;
  let state = {};
  let started = false;
  let turnCount = 0;

  function destination(action) {
    const paths = {
      email: 'mailto:vicentepaulandrei1823@gmail.com?subject=KJAncy%20service%20question',
      privacy: 'privacy.html', websites: 'websites.html',
      pricing: 'index.html#pricing', how: 'index.html#how'
    };
    if (action.kind === 'contact') {
      const plan = guide && guide.plans[action.plan];
      return plan ? `index.html?plan=${encodeURIComponent(plan.name)}#contact` : 'index.html#contact';
    }
    return paths[action.kind] || 'index.html#contact';
  }

  function setOpen(open, restoreFocus = true) {
    if (open && !started) startConversation();
    panel.hidden = !open;
    launcher.setAttribute('aria-expanded', String(open));
    launcher.setAttribute('aria-label', open ? 'Close KJAncy chat' : 'Open KJAncy chat');
    widget.querySelector('.chat-launcher-icon').innerHTML = icon(open ? 'close' : 'chat');
    widget.querySelector('.chat-launcher-text').textContent = open ? 'Close chat' : 'Ask KJAncy';
    if (open) {
      if (input.disabled) closeButton.focus({ preventScroll: true });
      else input.focus({ preventScroll: true });
      scrollToLatest();
    } else if (restoreFocus) launcher.focus({ preventScroll: true });
  }

  function scrollToLatest() { log.scrollTop = log.scrollHeight; }

  function addMessage(sender, text, actions = []) {
    const message = document.createElement('div');
    message.className = sender === 'user' ? 'chat-message is-user' : 'chat-message';
    const label = document.createElement('span');
    label.className = 'chat-message-label';
    label.textContent = sender === 'user' ? 'You' : 'KJAncy guide';
    const bubble = document.createElement('div');
    bubble.className = 'chat-bubble';
    const body = document.createElement('p');
    body.textContent = text;
    bubble.appendChild(body);
    for (const action of actions) {
      const link = document.createElement('a');
      link.className = 'chat-action';
      link.href = destination(action);
      const title = document.createElement('span');
      title.textContent = action.label;
      link.appendChild(title);
      const arrow = document.createElement('span');
      arrow.innerHTML = icon('arrow');
      link.appendChild(arrow);
      link.addEventListener('click', (event) => {
        // Preserve normal browser behavior for modified clicks and new-tab requests.
        if (event.ctrlKey || event.metaKey || event.shiftKey || event.altKey || event.button !== 0) return;
        const contactForm = document.getElementById('walkthrough-form');
        const samePageId = { pricing: 'pricing', how: 'how', contact: 'contact' }[action.kind];
        const section = samePageId ? document.getElementById(samePageId) : null;
        if (!section) return;
        event.preventDefault();
        if (action.kind === 'contact' && contactForm) {
          const plan = guide && guide.plans[action.plan];
          if (plan) {
            contactForm.elements.namedItem('plan').value = plan.name;
            contactForm.elements.namedItem('plan').dispatchEvent(new Event('change', { bubbles: true }));
          }
        }
        setOpen(false, false);
        section.scrollIntoView({ behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth', block: 'start' });
        if (action.kind === 'contact' && contactForm) contactForm.elements.namedItem('name').focus({ preventScroll: true });
        else {
          const heading = section.querySelector('h2');
          if (heading) { heading.tabIndex = -1; heading.focus({ preventScroll: true }); }
        }
      });
      bubble.appendChild(link);
    }
    message.append(label, bubble);
    log.appendChild(message);
    scrollToLatest();
  }

  function showSuggestions(items) {
    suggestions.replaceChildren();
    for (const text of items) {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'chat-suggestion';
      button.textContent = text;
      button.addEventListener('click', () => submitQuestion(text));
      suggestions.appendChild(button);
    }
  }

  function startConversation() {
    state = {};
    turnCount = 0;
    log.replaceChildren();
    suggestions.replaceChildren();
    input.value = '';
    input.disabled = false;
    input.removeAttribute('aria-invalid');
    status.textContent = '';
    counter.hidden = true;
    sendButton.disabled = true;
    started = true;
    if (!guide || typeof guide.replyFor !== 'function') {
      addMessage('assistant', 'The website guide could not load. Please reload this page or email the team for help.', [{ kind: 'email', label: 'Email the team' }]);
      input.disabled = true;
      return;
    }
    addMessage('assistant', guide.welcome);
    showSuggestions(guide.initialSuggestions);
  }

  function submitQuestion(value) {
    const text = value.trim();
    if (!text) {
      status.textContent = 'Type a question or choose a suggested topic.';
      input.setAttribute('aria-invalid', 'true');
      input.focus({ preventScroll: true });
      return;
    }
    if (text.length > 500) {
      status.textContent = 'Please keep your question to 500 characters or fewer.';
      input.setAttribute('aria-invalid', 'true');
      input.focus({ preventScroll: true });
      return;
    }
    if (!guide || input.disabled) return;
    status.textContent = '';
    input.removeAttribute('aria-invalid');
    addMessage('user', text);
    input.value = '';
    counter.hidden = true;
    sendButton.disabled = true;
    try {
      const result = guide.replyFor(text, state);
      state = result.state;
      addMessage('assistant', result.text, result.actions);
      turnCount += 1;
      showSuggestions(result.suggestions);
      if (turnCount >= 30) {
        showSuggestions([]);
        addMessage('assistant', 'For more detailed questions, email the team or start a new chat with the reset button above.', [{ kind: 'email', label: 'Email the team' }]);
        input.disabled = true;
        closeButton.focus({ preventScroll: true });
      } else input.focus({ preventScroll: true });
    } catch {
      addMessage('assistant', 'I couldn’t prepare that answer. You can try another question, start a new chat, or email the team.', [{ kind: 'email', label: 'Email the team' }]);
      showSuggestions(guide.initialSuggestions);
      input.focus({ preventScroll: true });
    }
  }

  launcher.addEventListener('click', () => setOpen(panel.hidden));
  closeButton.addEventListener('click', () => setOpen(false));
  resetButton.addEventListener('click', () => { startConversation(); input.disabled ? closeButton.focus() : input.focus(); });
  chatForm.addEventListener('submit', (event) => { event.preventDefault(); submitQuestion(input.value); });
  input.addEventListener('input', () => {
    sendButton.disabled = !input.value.trim();
    counter.hidden = input.value.length < 400;
    counter.textContent = `${input.value.length}/500`;
    status.textContent = '';
    input.removeAttribute('aria-invalid');
  });
  input.addEventListener('keydown', (event) => {
    if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) {
      event.preventDefault();
      submitQuestion(input.value);
    }
  });
  widget.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && !panel.hidden) { event.stopPropagation(); setOpen(false); }
  });
  // Keep the modal example's focus and visual priority intact.
  const demo = document.getElementById('demo-dialog');
  if (demo) {
    const syncModal = () => {
      widget.classList.toggle('is-suspended', demo.open);
      widget.inert = demo.open;
    };
    new MutationObserver(syncModal).observe(demo, { attributes: true, attributeFilter: ['open'] });
    syncModal();
  }
})();
