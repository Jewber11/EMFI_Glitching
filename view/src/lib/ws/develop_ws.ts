import { createLogger } from '../logger';
import { DEVELOP_URL, wsUrl } from '../config';

const log = createLogger('develop-ws');

export function connect(): WebSocket {
  const url = wsUrl(DEVELOP_URL);
  log.info(`connecting to ${url}`);
  const ws = new WebSocket(url);
  ws.onopen = () => log.info('connected');
  ws.onclose = (ev) => log.warn(`disconnected code=${ev.code} reason=${ev.reason || '(none)'}`);
  ws.onerror = () => log.error('connection error');
  return ws;
}
