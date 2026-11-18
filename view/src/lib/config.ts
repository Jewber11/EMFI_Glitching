// Service endpoint configuration.
//
// Defaults are same-origin proxy paths so a public gateway can expose one
// authenticated origin, e.g. https://emfi.ics.red, while keeping Control and
// Develop bound to localhost on the lab computer.

export const CONTROL_URL = import.meta.env.VITE_CONTROL_URL ?? '/api/control';
export const DEVELOP_URL = import.meta.env.VITE_DEVELOP_URL ?? '/api/develop';
export const DEVELOP_SITE_URL = import.meta.env.VITE_DEVELOP_SITE_URL ?? '/develop/';

function absoluteUrl(httpUrl: string): URL {
  if (typeof window !== 'undefined') {
    return new URL(httpUrl, window.location.origin);
  }
  return new URL(httpUrl, 'http://localhost:8003');
}

export function wsUrl(httpUrl: string, path = '/ws'): string {
  const u = absoluteUrl(httpUrl);
  u.protocol = u.protocol === 'https:' ? 'wss:' : 'ws:';
  u.pathname = `${u.pathname.replace(/\/$/, '')}${path}`;
  return u.toString();
}
