/** Site-wide constants and link helpers. */
export const SITE = {
  title: 'Boost Brigade — the Power Shuffler',
  shortTitle: 'Boost Brigade',
  description:
    'A differential power processor for partially shaded solar strings: control design, hardware, simulation ladder, bench and carpark results. QUT EGH490 capstone, 2026.',
  repo: 'https://github.com/saunders-jared-final/Boost-Brigade',
  branch: 'main',
  author: 'Jared Saunders',
  linkedin: 'https://www.linkedin.com/',
  qspice: 'https://www.qorvo.com/design-hub/design-tools/interactive/qspice',
  kicad: 'https://www.kicad.org/download/',
};

export const NAV = [
  { href: '/', label: 'Home' },
  { href: '/story/', label: 'Story' },
  { href: '/hardware/', label: 'Hardware' },
  { href: '/control/', label: 'Control' },
  { href: '/simulation/', label: 'Simulation' },
  { href: '/results/', label: 'Results' },
  { href: '/handover/', label: 'Handover' },
  { href: '/media/', label: 'Media' },
  { href: '/about/', label: 'About' },
];

/** Prefix an internal path with the deploy base (handles '/Boost-Brigade'). */
export function href(path: string): string {
  const base = import.meta.env.BASE_URL.replace(/\/$/, '');
  if (!path.startsWith('/')) path = '/' + path;
  return base + path;
}

/** GitHub blob URL for a repo-relative path (spaces and apostrophes escaped). */
export function repoUrl(relPath: string, lines?: [number, number?]): string {
  const clean = relPath.replace(/^\/+/, '');
  const enc = clean.split('/').map(encodeURIComponent).join('/');
  let url = `${SITE.repo}/blob/${SITE.branch}/${enc}`;
  if (lines) url += `#L${lines[0]}` + (lines[1] ? `-L${lines[1]}` : '');
  return url;
}

/** GitHub tree URL for a repo folder. */
export function repoDir(relPath: string): string {
  const clean = relPath.replace(/^\/+/, '').replace(/\/+$/, '');
  const enc = clean.split('/').map(encodeURIComponent).join('/');
  return `${SITE.repo}/tree/${SITE.branch}/${enc}`;
}

/** Raw file URL (for downloads such as PDFs). */
export function rawUrl(relPath: string): string {
  const clean = relPath.replace(/^\/+/, '');
  const enc = clean.split('/').map(encodeURIComponent).join('/');
  return `${SITE.repo}/raw/${SITE.branch}/${enc}`;
}
