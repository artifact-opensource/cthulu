// API + live stream client. No dependencies.
const KEY = 'cthulu_token';
export const getToken = () => { try { return localStorage.getItem(KEY) || ''; } catch { return ''; } };
export const setToken = (t) => { try { localStorage.setItem(KEY, t); } catch { /* private mode */ } };

let onAuth = null;
export const onAuthNeeded = (fn) => { onAuth = fn; };

export async function api(path, body, method) {
  const m = method || (body === undefined ? 'GET' : 'POST');
  const headers = { 'Content-Type': 'application/json' };
  const t = getToken();
  if (t) headers.Authorization = 'Bearer ' + t;
  let res;
  try {
    res = await fetch(path, { method: m, headers, body: body === undefined ? undefined : JSON.stringify(body) });
  } catch {
    throw new Error('Cannot reach the agent server. Is it still running?');
  }
  let data = {};
  try { data = await res.json(); } catch { /* empty */ }
  if (res.status === 401 && onAuth) { await onAuth(); return api(path, body, method); }
  if (!res.ok) throw new Error(data.error || ('Request failed (' + res.status + ')'));
  return data;
}

export function openStream(onEvent, onState) {
  let es, retry = 1000, closed = false;
  const connect = () => {
    const t = getToken();
    es = new EventSource('/api/stream' + (t ? '?token=' + encodeURIComponent(t) : ''));
    es.onopen = () => { retry = 1000; onState(true); };
    es.onmessage = (e) => { try { onEvent(JSON.parse(e.data)); } catch { /* ignore */ } };
    es.onerror = () => {
      onState(false); es.close();
      if (!closed) setTimeout(connect, retry = Math.min(retry * 1.7, 15000));
    };
  };
  connect();
  return () => { closed = true; es && es.close(); };
}
