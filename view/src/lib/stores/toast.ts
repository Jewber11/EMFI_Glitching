import { writable } from 'svelte/store';

export interface Toast {
	id: number;
	message: string;
	level: 'info' | 'warn' | 'error';
	where?: string;
	ttl: number;
}

let nextId = 0;

function createToastStore() {
	const { subscribe, update } = writable<Toast[]>([]);

	function add(message: string, level: Toast['level'] = 'info', opts: { where?: string; ttl?: number } = {}) {
		const id = nextId++;
		const ttl = opts.ttl ?? 4000;
		const toast: Toast = { id, message, level, where: opts.where, ttl };
		update((t) => [...t, toast]);
		if (ttl > 0) setTimeout(() => dismiss(id), ttl);
	}

	function dismiss(id: number) {
		update((t) => t.filter((x) => x.id !== id));
	}

	return {
		subscribe,
		info: (msg: string, opts?: { where?: string; ttl?: number }) => add(msg, 'info', opts),
		warn: (msg: string, opts?: { where?: string; ttl?: number }) => add(msg, 'warn', opts),
		error: (msg: string, opts?: { where?: string; ttl?: number }) => add(msg, 'error', opts),
		dismiss,
	};
}

export const toasts = createToastStore();
