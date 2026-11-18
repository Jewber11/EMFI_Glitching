import type { WsEvent } from '$lib/types';
import { base } from '$app/paths';

type MessageHandler = (event: WsEvent) => void;

class DevelopWs {
  private ws: WebSocket | null = null;
  private handlers = new Map<string, Set<MessageHandler>>();
  private subscribedTopics = new Set<string>();
  private reconnectDelay = 1000;
  private maxReconnectDelay = 30000;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;

  connect(): void {
    if (this.ws && this.ws.readyState <= WebSocket.OPEN) return;

    const proto = location.protocol === 'https:' ? 'wss' : 'ws';
    this.ws = new WebSocket(`${proto}://${location.host}${base}/ws`);

    this.ws.onopen = () => {
      this.reconnectDelay = 1000;
      for (const topic of this.subscribedTopics) {
        this.ws?.send(JSON.stringify({ type: 'subscribe', topic }));
      }
    };

    this.ws.onmessage = (ev) => {
      try {
        const event: WsEvent = JSON.parse(ev.data);
        if (event.topic) {
          const fns = this.handlers.get(event.topic);
          if (fns) fns.forEach((fn) => fn(event));
        }
      } catch { /* ignore parse errors */ }
    };

    this.ws.onclose = () => this.scheduleReconnect();
    this.ws.onerror = () => this.ws?.close();
  }

  subscribe(topic: string, handler: MessageHandler): void {
    if (!this.handlers.has(topic)) this.handlers.set(topic, new Set());
    this.handlers.get(topic)!.add(handler);
    this.subscribedTopics.add(topic);

    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({ type: 'subscribe', topic }));
    }
  }

  unsubscribe(topic: string, handler: MessageHandler): void {
    this.handlers.get(topic)?.delete(handler);
    if (this.handlers.get(topic)?.size === 0) {
      this.handlers.delete(topic);
      this.subscribedTopics.delete(topic);
    }
  }

  disconnect(): void {
    if (this.reconnectTimer) clearTimeout(this.reconnectTimer);
    this.ws?.close();
    this.ws = null;
  }

  private scheduleReconnect(): void {
    if (this.reconnectTimer) return;
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null;
      this.reconnectDelay = Math.min(this.reconnectDelay * 2, this.maxReconnectDelay);
      this.connect();
    }, this.reconnectDelay);
  }
}

export const ws = new DevelopWs();
