const menuButton = document.querySelector('.menu-toggle');
const siteNav = document.querySelector('.site-nav');

if (menuButton && siteNav) {
  menuButton.addEventListener('click', () => {
    const isOpen = menuButton.getAttribute('aria-expanded') === 'true';
    menuButton.setAttribute('aria-expanded', String(!isOpen));
    siteNav.classList.toggle('is-open', !isOpen);
  });

  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && siteNav.classList.contains('is-open')) {
      siteNav.classList.remove('is-open');
      menuButton.setAttribute('aria-expanded', 'false');
      menuButton.focus();
    }
  });
}

const workSearch = document.querySelector('[data-work-search]');
const workYear = document.querySelector('[data-work-year]');
const workCards = [...document.querySelectorAll('.work-card')];

function filterWorks() {
  if (!workCards.length) return;
  const query = workSearch?.value.trim().toLocaleLowerCase('zh-Hant') ?? '';
  const year = workYear?.value ?? 'all';
  let visible = 0;
  workCards.forEach((card) => {
    const matchesQuery = !query || card.dataset.search.includes(query);
    const matchesYear = year === 'all' || card.dataset.year === year;
    card.hidden = !(matchesQuery && matchesYear);
    if (!card.hidden) visible += 1;
  });
  const count = document.querySelector('[data-work-count]');
  const empty = document.querySelector('[data-work-empty]');
  if (count) count.textContent = `${visible} 件作品`;
  if (empty) empty.hidden = visible !== 0;
}

workSearch?.addEventListener('input', filterWorks);
workYear?.addEventListener('change', filterWorks);

const articleFilters = [...document.querySelectorAll('[data-article-filter]')];
const articleRows = [...document.querySelectorAll('.article-row')];

articleFilters.forEach((button) => {
  button.addEventListener('click', () => {
    const category = button.dataset.articleFilter;
    articleFilters.forEach((item) => item.classList.toggle('is-active', item === button));
    articleRows.forEach((row) => {
      row.hidden = category !== 'all' && row.dataset.category !== category;
    });
  });
});

const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
const revealSelector = [
  '.page-hero > div',
  '.page-hero > img',
  '.about-intro',
  '.about-portrait',
  '.about-timeline',
  '.philosophy > *',
  '.catalog-tools',
  '.work-card',
  '.work-detail-grid > *',
  '.section-heading',
  '.exhibition-row',
  '.class-hero-copy',
  '.course-layout > *',
  '.filter-tabs',
  '.article-row',
  '.article-header > *',
  '.article-body > *',
  '.contact-intro > *',
  '.contact-links > *',
  '.inquiry-grid > *',
  '.contact-signature',
].join(',');

const revealItems = [...document.querySelectorAll(revealSelector)];
revealItems.forEach((item, index) => {
  item.classList.add('reveal');
  item.style.setProperty('--reveal-delay', `${(index % 5) * 70}ms`);
});

if (prefersReducedMotion || !('IntersectionObserver' in window)) {
  revealItems.forEach((item) => item.classList.add('is-visible'));
} else {
  const revealObserver = new IntersectionObserver((entries, observer) => {
    entries.forEach((entry) => {
      if (entry.isIntersecting) {
        entry.target.classList.add('is-visible');
        observer.unobserve(entry.target);
      }
    });
  }, { rootMargin: '0px 0px -8% 0px', threshold: 0.12 });

  revealItems.forEach((item) => revealObserver.observe(item));
}
