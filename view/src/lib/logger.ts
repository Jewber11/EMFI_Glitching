const ENABLED = import.meta.env.VITE_LOG !== 'false';

type Level = 'debug' | 'info' | 'warn' | 'error';

const LEVEL_RANK: Record<Level, number> = { debug: 0, info: 1, warn: 2, error: 3 };
const MIN_LEVEL: Level = (import.meta.env.VITE_LOG_LEVEL as Level) ?? 'debug';

function ts(): string {
	return new Date().toISOString();
}

function emit(level: Level, category: string, msg: string, data?: unknown) {
	if (!ENABLED || LEVEL_RANK[level] < LEVEL_RANK[MIN_LEVEL]) return;
	const prefix = `[${ts()}] [${level.toUpperCase()}] [${category}]`;
	const fn = level === 'error' ? console.error : level === 'warn' ? console.warn : console.log;
	if (data !== undefined) {
		fn(prefix, msg, data);
	} else {
		fn(prefix, msg);
	}
}

export function createLogger(category: string) {
	return {
		debug: (msg: string, data?: unknown) => emit('debug', category, msg, data),
		info: (msg: string, data?: unknown) => emit('info', category, msg, data),
		warn: (msg: string, data?: unknown) => emit('warn', category, msg, data),
		error: (msg: string, data?: unknown) => emit('error', category, msg, data),
	};
}
