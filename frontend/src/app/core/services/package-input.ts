/**
 * Extracts an npm package name from free-form input: a bare name, a
 * `name@version` spec, an `npm i name` command, or an npmjs.com / registry /
 * unpkg / jsdelivr URL. Returns '' when nothing usable is found.
 */
export function parsePackageInput(raw: string): string {
  let s = raw.trim();
  if (!s) return '';

  s = s.replace(/^(npm|pnpm|yarn|bun)\s+(i|install|add)\s+(-\S+\s+)*/i, '');

  if (/^(https?:\/\/|www\.|npmjs\.com|registry\.|unpkg\.com|cdn\.jsdelivr\.net)/i.test(s)) {
    let url: URL;
    try {
      url = new URL(/^https?:\/\//i.test(s) ? s : `https://${s}`);
    } catch {
      return '';
    }
    let path = decodeURIComponent(url.pathname).replace(/^\/+/, '');
    path = path.replace(/^package\//, '').replace(/^npm\//, '');
    const [first, second] = path.split('/');
    s = first?.startsWith('@') && second ? `${first}/${second}` : (first ?? '');
  }

  // Drop a trailing @version (but keep the leading @ of a scope).
  const at = s.indexOf('@', 1);
  if (at > 0) s = s.slice(0, at);

  s = s.toLowerCase();
  return /^(@[a-z0-9-~][a-z0-9-._~]*\/)?[a-z0-9-~][a-z0-9-._~]*$/.test(s) ? s : '';
}
