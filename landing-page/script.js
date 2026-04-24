document.addEventListener('DOMContentLoaded', () => {
  const root = document.documentElement;
  const saved = localStorage.getItem('polyalpha-theme');
  if (saved) root.dataset.theme = saved;
  document.querySelectorAll('.theme-toggle').forEach((button) => {
    const sync = () => { button.textContent = root.dataset.theme === 'light' ? 'Dark' : 'Light'; };
    sync();
    button.addEventListener('click', () => {
      root.dataset.theme = root.dataset.theme === 'light' ? 'dark' : 'light';
      localStorage.setItem('polyalpha-theme', root.dataset.theme);
      sync();
    });
  });
  const observer = new IntersectionObserver((entries) => {
    entries.forEach((entry) => {
      if (entry.isIntersecting) {
        entry.target.classList.add('visible');
        observer.unobserve(entry.target);
      }
    });
  }, { threshold: 0.08 });
  document.querySelectorAll('.fade-up').forEach((el) => {
    observer.observe(el);
  });
  const form = document.querySelector('#contact-form');
  if (form) {
    form.addEventListener('submit', (event) => {
      event.preventDefault();
      const data = new FormData(form);
      const subject = encodeURIComponent('Poly-Alpha demo request');
      const body = encodeURIComponent(`Name: ${data.get('name') || ''}\nEmail: ${data.get('email') || ''}\n\nUse case:\n${data.get('message') || ''}`);
      window.location.href = `mailto:georgy@polyaialpha.online?subject=${subject}&body=${body}`;
    });
  }
});
