/** Build-time access to files in the parent repository (one level above site/). */
import { readFileSync, existsSync } from 'node:fs';
import path from 'node:path';

/** The build always runs from site/, so the repository root is its parent. */
export const REPO_ROOT = process.env.BB_REPO_ROOT ?? path.resolve(process.cwd(), '..');

export function repoPath(rel: string): string {
  return path.join(REPO_ROOT, rel);
}

export function repoExists(rel: string): boolean {
  return existsSync(repoPath(rel));
}

/** Read a repo file; throws with a clear message if it moved (keeps the handover honest). */
export function readRepo(rel: string): string {
  const p = repoPath(rel);
  if (!existsSync(p)) throw new Error(`[site] repo file not found: ${rel} (looked in ${p})`);
  return readFileSync(p, 'utf8');
}

/** Read lines [from, to] (1-based, inclusive) of a repo file. */
export function readRepoLines(rel: string, from: number, to?: number): string {
  const lines = readRepo(rel).split(/\r?\n/);
  const a = Math.max(1, from);
  const b = Math.min(lines.length, to ?? lines.length);
  return lines.slice(a - 1, b).join('\n');
}

/** Extract a markdown section (from a heading line matching `re` to the next heading of equal or higher level). */
export function markdownSection(md: string, re: RegExp): string {
  const lines = md.split(/\r?\n/);
  const start = lines.findIndex((l) => re.test(l));
  if (start < 0) return '';
  const level = (lines[start].match(/^#+/) || ['#'])[0].length;
  let end = lines.length;
  for (let i = start + 1; i < lines.length; i++) {
    const m = lines[i].match(/^(#+)\s/);
    if (m && m[1].length <= level) { end = i; break; }
  }
  return lines.slice(start, end).join('\n');
}
