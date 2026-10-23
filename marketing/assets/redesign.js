(function(){
  'use strict';
  const options={
    lead:{name:'Lead Booking System',price:'$997',description:'Website, chat, and human follow-up for new online inquiries. Incoming phone answering is not included.'},
    dispatcher:{name:'Dedicated Dispatcher System',price:'$1,997',description:'Online lead follow-up plus a dedicated person answering incoming calls. Working hours and expected call volume are agreed before onboarding; it is not 24/7.'}
  };
  document.querySelectorAll('[data-fit]').forEach(button=>button.addEventListener('click',()=>{
    const selected=options[button.dataset.fit];if(!selected)return;
    document.querySelectorAll('[data-fit]').forEach(item=>{const active=item===button;item.setAttribute('aria-pressed',String(active));item.classList.toggle('active',active);});
    document.getElementById('fit-name').textContent=selected.name;
    const price=document.getElementById('fit-price');price.replaceChildren(document.createTextNode(selected.price));
    const period=document.createElement('span');period.textContent='/ month';price.appendChild(period);
    document.getElementById('fit-description').textContent=selected.description;
    document.getElementById('fit-cta').dataset.plan=selected.name;
  }));
  if('IntersectionObserver' in window&&!window.matchMedia('(prefers-reduced-motion: reduce)').matches){
    const observer=new IntersectionObserver(entries=>entries.forEach(entry=>{if(entry.isIntersecting){entry.target.classList.add('is-arriving');observer.unobserve(entry.target);}}),{threshold:.12});
    document.querySelectorAll('.reveal').forEach(element=>observer.observe(element));
  }
})();
