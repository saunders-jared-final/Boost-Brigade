/** Site-wide constants and link helpers. */
export const SITE = {
  title: 'Boost Brigade — the Power Shuffler',
  shortTitle: 'Boost Brigade',
  description:
    'Knowledge hub for the Boost Brigade power shuffler: a differential power processor for partially shaded solar strings. PCB and enclosure design, control design, simulation, bench and carpark results, and the handover. QUT EGH490 capstone, 2026.',
  repo: 'https://github.com/saunders-jared-final/Boost-Brigade',
  branch: 'main',
  authors: 'Jared Saunders and Son Nguyen',
  qspice: 'https://www.qorvo.com/design-hub/design-tools/interactive/qspice',
  kicad: 'https://www.kicad.org/download/',
};

/** The two final reports (PDF) in the repository. */
export const REPORTS = {
  control: '0_Documentation/n11034459_ProjectDeliveryReport_V1.pdf',
  hardware: '0_Documentation/son_report.pdf',
  proposal: '0_Documentation/jared-assessment/CapstoneProjectProposal.pdf',
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

export const HARDWARE_NAV = [
  { href: '/hardware/', label: 'Overview' },
  { href: '/hardware/pcb/', label: 'PCB design' },
  { href: '/hardware/enclosure/', label: 'Enclosure design' },
];

/** Prefix an internal path with the deploy base (handles '/Boost-Brigade'). */
export function href(path: string): string {
  const base = import.meta.env.BASE_URL.replace(/\/$/, '');
  if (!path.startsWith('/')) path = '/' + path;
  return base + path;
}

function enc(relPath: string): string {
  return relPath.replace(/^\/+/, '').replace(/\/+$/, '').split('/').map(encodeURIComponent).join('/');
}

/** GitHub blob URL for a repo-relative path (spaces and apostrophes escaped). */
export function repoUrl(relPath: string, lines?: [number, number?]): string {
  let url = `${SITE.repo}/blob/${SITE.branch}/${enc(relPath)}`;
  if (lines) url += `#L${lines[0]}` + (lines[1] ? `-L${lines[1]}` : '');
  return url;
}

/** GitHub tree URL for a repo folder. */
export function repoDir(relPath: string): string {
  return `${SITE.repo}/tree/${SITE.branch}/${enc(relPath)}`;
}

/** Raw file URL (for downloads such as PDFs and videos). */
export function rawUrl(relPath: string): string {
  return `${SITE.repo}/raw/${SITE.branch}/${enc(relPath)}`;
}

/** Link to a page of one of the reports. */
export function reportUrl(which: keyof typeof REPORTS, page?: number): string {
  return rawUrl(REPORTS[which]) + (page ? `#page=${page}` : '');
}
