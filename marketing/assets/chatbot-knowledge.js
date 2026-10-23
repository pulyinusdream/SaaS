/* Published website facts only. No network calls, model, or customer data store. */
(function (root) {
  'use strict';

  const plans = Object.freeze({
    lead: { name: 'Lead Booking System', price: '$997', setup: '$500' },
    dispatcher: { name: 'Dedicated Dispatcher System', price: '$1,997', setup: '$500' }
  });
  const welcome = 'Hi, I’m the KJAncy website guide. I can explain our services, compare packages, and help you take the next step. What would you like to know?';
  const initialSuggestions = ['Compare packages', 'Help me choose a plan', 'What are the coverage hours?'];
  const defaultSuggestions = ['Compare packages', 'How does it work?', 'Request a walkthrough'];

  function replyFor(message, previousState = {}) {
    const state = {
      awaitingFit: previousState.awaitingFit === true,
      plan: Object.hasOwn(plans, previousState.plan) ? previousState.plan : null
    };
    const text = String(message || '').normalize('NFKC').toLowerCase()
      .replace(/[’‘]/g, "'").replace(/[—–-]/g, ' ').replace(/\s+/g, ' ').trim();
    const response = (text, suggestions = defaultSuggestions, actions = []) => ({ text, suggestions, actions, state });
    const contact = (label = 'Request a free walkthrough') => ({ kind: 'contact', label, plan: state.plan });
    const recommend = (key) => {
      state.plan = key;
      state.awaitingFit = false;
      const plan = plans[key];
      const explanation = key === 'lead'
        ? 'If you need follow-up for new website and chat leads, the Lead Booking System is the starting point: $997 USD/month plus a $500 one-time setup fee. It includes a website or landing page, basic AI chat, forms and booking, human lead follow-up, confirmations, customer records, and a monthly report. It does not answer live incoming calls.'
        : 'For live incoming call answering, the Dedicated Dispatcher System is the package to discuss: $1,997 USD/month plus a $500 one-time setup fee. It includes the Lead Booking System plus dedicated dispatch, phone bookings, missed-call support, and old lead and estimate follow-up. Coverage hours and expected call volume are agreed before onboarding; it is not 24/7.';
      return response(explanation + '\n\nThis is a starting suggestion. The team will confirm the right scope for your business.', ['What are the coverage hours?', 'Compare packages'], [contact(`Ask about ${plan.name}`)]);
    };

    if (!text) return response('Type a question, or choose one of the suggested topics.', initialSuggestions);

    if (/\b(are you (an? )?(ai|human|person|bot)|who are you|real person|live agent|is this ai|chatgpt|language model)\b/.test(text)) {
      return response('I’m an automated website guide using preset answers from KJAncy’s published service information. I’m not a live agent or a generative AI model. For a personal conversation, you can contact the team.', ['Compare packages', 'Request a walkthrough'], [{ kind: 'email', label: 'Email the team' }]);
    }
    if (/\b(privacy|private|store|stored|save|saved|personal data|training|delete|history)\b/.test(text)) {
      return response('This chat runs in your browser. Messages are kept only in this page’s memory, are not sent to a server or AI provider, and are cleared by Start over or by reloading or leaving the page. Closing the chat keeps it available on this page. If you choose to email the team, your email is handled by the email services involved.', ['Compare packages', 'Request a walkthrough'], [{ kind: 'privacy', label: 'Read the privacy notice' }]);
    }
    if (/\b(emergency|urgent repair|fix my|repair my|my (ac|air conditioner|roof|sink|toilet|garage door)|gas leak)\b/.test(text)) {
      return response('KJAncy supports home-service businesses with websites, lead follow-up, and dispatch processes. This website cannot arrange a repair or send a technician to your home. Please contact your local service provider for repair help.', ['What services do you offer?', 'Compare packages']);
    }
    if (/\b(refund|cancel|cancellation|contract|minimum term|trial|discount|guarantee|guaranteed|unlimited|payment method)\b/.test(text)) {
      return response('Those commercial details need to be confirmed with the team before onboarding. The site does not publish a trial, discount, refund, or contract-term policy, and it does not guarantee job totals or unlimited call handling.', ['Compare packages', 'What are the coverage hours?'], [contact('Ask the team about terms')]);
    }
    if (/\b(ads?|advertising|seo|google ads|marketing campaign)\b/.test(text)) {
      return response('Ad spend and ongoing SEO campaigns are not included in either package. KJAncy focuses on capturing inquiries, following up, and supporting appointment booking. Job totals are not guaranteed.', ['Compare packages', 'How does it work?'], [contact()]);
    }
    if (/\b(24\s*\/\s*7|24\s+7|24 hours?|all day|overnight|weekends?|coverage|working hours?|business hours?|time zones?|after hours|availability)\b/.test(text)) {
      return response('Human follow-up and live phone answering run during the coverage hours agreed with your business. Specific days, time zones, and call volume are confirmed before onboarding. The Dedicated Dispatcher System is not 24/7.\n\nYour website and lead form can still collect inquiries after hours. Live incoming phone answering is included only in the Dedicated Dispatcher System.', ['Help me choose a plan', 'Compare packages'], [contact('Discuss coverage with the team')]);
    }
    if (/\b(don't|do not|no)\s+(need\s+|want\s+)?(a\s+)?(dedicated\s+)?dispatcher\b/.test(text)) return recommend('lead');
    if (/\b(help me choose|which (plan|package)|best (plan|package)|recommend|not sure|find (my|a) plan)\b/.test(text)) {
      state.awaitingFit = true;
      return response('What would help most: following up with new website and chat leads, answering incoming business calls, or both?', ['Website lead follow-up', 'Answer incoming calls', 'Both']);
    }
    if (/\b(don't|do not|no|without)\s+(need\s+|want\s+)?(live\s+|incoming\s+|business\s+)?(phone|call)[a-z ]{0,12}(answer|coverage|support)|\b(only|just)\s+(website|online|chat)\b/.test(text)) {
      return recommend('lead');
    }
    if (state.awaitingFit && /\b(both|phone|calls?|answering|dispatcher)\b/.test(text)) return recommend('dispatcher');
    if (state.awaitingFit && /\b(website|online|chat|leads?|follow up)\b/.test(text)) return recommend('lead');

    if (/\b(email|contact|speak|talk to|human support|walkthrough|walk through|book (a |an |my )?(call|appointment|demo)|get started|sign up|phone number|reach you)\b/.test(text)) {
      state.awaitingFit = false;
      return response('You can request a free walkthrough to discuss your trade, tools, lead volume, and coverage needs. The form prepares an email draft to vicentepaulandrei1823@gmail.com for you to send.\n\nI can’t confirm an appointment, access a live calendar, send an email, or submit a booking from this chat.', ['Help me choose a plan', 'Compare packages'], [contact(), { kind: 'email', label: 'Email the team directly' }]);
    }
    if (/\b(pric(e|es|ing)|cost|how much|fees?|plans?|packages?|monthly|per month|\d[,.]?997)\b/.test(text)) {
      state.awaitingFit = false;
      return response('Lead Booking System — $997 USD/month, plus $500 one-time setup. Capture and follow up with new website and chat leads. No live incoming call answering.\n\nDedicated Dispatcher System — $1,997 USD/month, plus $500 one-time setup. Everything in Lead Booking, plus a dedicated dispatcher and live incoming call answering during agreed working hours.\n\nCoverage hours, tools, and expected volume are confirmed before onboarding.', ['Help me choose a plan', 'What are the coverage hours?'], [{ kind: 'pricing', label: 'View the full package comparison' }]);
    }
    if (/\b(answer|answering|inbound|incoming|miss(ed|ing) calls?|dispatcher|dispatch|phone|old leads?|estimates?)\b/.test(text)) {
      state.plan = 'dispatcher';
      return response('Live incoming call answering is included in the Dedicated Dispatcher System at $1,997 USD/month plus $500 setup. It also includes phone bookings, missed-call support, old lead and estimate follow-up, outbound calls, and customer record updates.\n\nThe Lead Booking System calls or texts new online leads, but does not answer incoming business calls. All human support is within agreed coverage hours.', ['What are the coverage hours?', 'Compare packages'], [contact('Ask about dedicated dispatch')]);
    }
    if (/\b(already (have|got)|existing|new website|replace (my|our))\b/.test(text)) {
      return response('You may not need a brand-new website. The team can discuss improving your existing site or building a simple website or landing page that makes inquiries and appointment requests easier.', ['Compare packages', 'How does it work?'], [{ kind: 'websites', label: 'Explore websites & AI chat' }, contact()]);
    }
    if (/\b(crm|integrat(e|es|ion|ions)|gohighlevel|go high level|ghl|tools|software|calendar|jobber|servicetitan|housecall)\b/.test(text)) {
      return response('The team will review your existing CRM, scheduling tools, and handoff process before onboarding and confirm what can be connected. Specific platform compatibility is not promised on this website. Both packages include customer records and appointment confirmations.', ['Compare packages', 'Request a walkthrough'], [contact('Discuss your tools')]);
    }
    if (/\b(setup|set up|onboarding|how long|launch|start date|timeline)\b/.test(text)) {
      return response('Both packages have a $500 USD one-time setup fee. First, the team reviews your trade, current tools, coverage requirements, and expected lead or call volume. Scope and handoffs are agreed before onboarding. A fixed launch timeline is not published; the team will confirm timing with you.', ['Compare packages', 'Request a walkthrough'], [contact()]);
    }
    if (/\b(ai|chat|chatbot|bot|website|landing page|automation)\b/.test(text)) {
      return response('Both packages include a website or landing page, AI chat for basic customer questions, contact forms, and online booking. Chat can collect information or help schedule requests; a person handles follow-up or confirmation when needed.\n\nThis website guide itself uses preset service answers and does not book live appointments.', ['Website lead follow-up', 'Compare packages'], [{ kind: 'websites', label: 'Explore websites & AI chat' }]);
    }
    if (/\b(website lead follow up|online leads?|follow up|followup|confirmations?)\b/.test(text)) return recommend('lead');
    if (/\b(hvac|plumb(er|ing)|roof(er|ing)|garage doors?|electric(ian|al)|trades?|industries|contractors?|home services?)\b/.test(text)) {
      return response('KJAncy is built for U.S. home-service businesses, including HVAC, plumbing, roofing, garage doors, and electrical contractors. The team can discuss the details of your trade and confirm whether the service is a fit.', ['Help me choose a plan', 'Compare packages'], [contact()]);
    }
    if (/\b(how (does|do|it)|how can you help|works?|services?|what do you (do|offer)|what is kjancy)\b/.test(text)) {
      return response('The process has three steps:\n\n1. Your website and chat capture the customer’s contact details, location, and service needed.\n2. The team follows up during agreed hours. The dedicated plan also answers incoming calls.\n3. Appointment details are confirmed and your schedule and customer records are updated.', ['Help me choose a plan', 'Compare packages'], [{ kind: 'how', label: 'See how it works' }]);
    }
    if (/^(hi|hello|hey|good (morning|afternoon|evening))[!. ]*$/.test(text)) return response(welcome, initialSuggestions);
    if (/\b(thanks|thank you|helpful|bye|goodbye)\b/.test(text)) return response('You’re welcome. If you’d like to discuss your business, a free walkthrough is a good next step.', ['Compare packages', 'Request a walkthrough'], [contact()]);
    return response('I don’t have a confirmed answer to that in the website’s service information. I can help with packages, coverage, websites, lead follow-up, and dispatch. For anything specific to your business, let’s ask the team.', defaultSuggestions, [contact('Ask the team')]);
  }

  const guide = Object.freeze({ replyFor, welcome, initialSuggestions, plans });
  if (typeof module !== 'undefined' && module.exports) module.exports = guide;
  else root.KJAncyChatGuide = guide;
})(typeof window !== 'undefined' ? window : globalThis);
