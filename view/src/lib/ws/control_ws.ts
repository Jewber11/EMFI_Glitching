import { createLogger } from '../logger';
import { CONTROL_URL, wsUrl } from '../config';
import { armStore } from '../stores/arm';
import { ad2CaptureStore } from '../stores/ad2';
import { activeCampaign } from '../stores/campaign';
import { countersStore } from '../stores/counters';
import { devicesStore, type DeviceStatus } from '../stores/devices';
import { logStore } from '../stores/log';
import { positionStore } from '../stores/position';
import { scaffoldPowerStore } from '../stores/scaffold_power';
import { toasts } from '../stores/toast';

const log = createLogger('control-ws');

let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
let reconnectDelay = 500;
const MAX_RECONNECT = 5000;

export function connect(): WebSocket {
  const url = wsUrl(CONTROL_URL);
  log.info(`connecting to ${url}`);
  const ws = new WebSocket(url);

  ws.onopen = () => {
    log.info('connected');
    toasts.info('Backend connected');
    reconnectDelay = 500;
  };

  ws.onclose = (ev) => {
    log.warn(`disconnected code=${ev.code} reason=${ev.reason || '(none)'}`);
    toasts.warn('Backend disconnected — reconnecting…');
    scheduleReconnect();
  };

  ws.onerror = () => log.error('connection error');

  ws.onmessage = (ev) => {
    let msg: any;
    try { msg = JSON.parse(ev.data); } catch {
      log.error('failed to parse message', ev.data);
      return;
    }
    if (msg.type === 'error') {
      log.error('server error', msg);
      toasts.error(msg.error ?? 'Unknown error', { where: msg.where });
      return;
    }
    if (msg.type !== 'event') {
      log.debug(`non-event message type=${msg.type}`, msg);
      return;
    }
    switch (msg.topic) {
      case 'state': {
        const devices = msg.payload?.devices;
        if (devices && typeof devices === 'object') {
          devicesStore.set(new Map(Object.entries(devices) as [string, DeviceStatus][]));
        }
        break;
      }
      case 'position': positionStore.set(msg.payload); break;
      case 'arm':
        log.info('arm state changed', msg.payload);
        armStore.set(msg.payload);
        break;
      case 'counter': countersStore.set(msg.payload); break;
      case 'attempt':
        log.debug(`attempt outcome=${msg.payload?.outcome}`);
        logStore.update((l) => [...l.slice(-199), msg.payload]);
        break;
      case 'scaffold_power':
        log.info('scaffold power changed', msg.payload);
        scaffoldPowerStore.set(msg.payload);
        break;
      case 'device_status':
        log.info(`device ${msg.payload?.name} status changed`, msg.payload);
        devicesStore.update((m) => {
          const next = new Map(m);
          const d = msg.payload as DeviceStatus;
          next.set(d.name, d);
          return next;
        });
        break;
      case 'ad2_capture':
        ad2CaptureStore.set(msg.payload);
        break;
      case 'campaign_progress': {
        log.debug('campaign progress', msg.payload);
        const p = msg.payload ?? {};
        // Control renamed the field `completed` → `completed_attempts` to match
        // the CampaignStatus model. Read the new name, fall back to the old one
        // during rollout so a not-yet-updated Control doesn't render "undefined".
        const completed = p.completed_attempts ?? p.completed ?? 0;
        const total = p.total_attempts ?? p.total ?? 0;
        // Position arrives as `current_xyz` (list) on the new shape; tolerate the
        // legacy `current_position` too. Normalize to the store's tuple shape.
        const xyz = p.current_xyz ?? p.current_position ?? null;
        const current_position =
          Array.isArray(xyz) && xyz.length >= 3
            ? ([xyz[0], xyz[1], xyz[2]] as [number, number, number])
            : null;
        activeCampaign.set({
          ...p,
          completed_attempts: completed,
          total_attempts: total,
          current_position,
        });
        // Keep the 3D probe tracking live during a campaign even if a discrete
        // `position` event lags. Preserve any machine_* fields already in store.
        if (current_position) {
          positionStore.update((pos) => ({
            ...pos,
            x: current_position[0],
            y: current_position[1],
            z: current_position[2],
          }));
        }
        break;
      }
      case 'error':
        log.error('error event', msg.payload);
        toasts.error(msg.payload?.error ?? 'Unknown error', { where: msg.payload?.where });
        break;
      default:
        log.warn(`unknown topic: ${msg.topic}`, msg.payload);
        break;
    }
  };
  return ws;
}

function scheduleReconnect() {
  if (reconnectTimer) return;
  reconnectTimer = setTimeout(() => {
    reconnectTimer = null;
    reconnectDelay = Math.min(reconnectDelay * 1.5, MAX_RECONNECT);
    connect();
  }, reconnectDelay);
}
