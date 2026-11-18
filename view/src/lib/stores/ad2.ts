import { writable } from 'svelte/store';

export interface AD2Channel {
	source: string;
	label?: string;
	unit?: string;
	probe_ratio?: number;
	scaled_unit?: string;
	scaled_label?: string;
	values: number[];
}

export interface AD2Capture {
	name: string;
	available: boolean;
	connected: boolean;
	timestamp?: number;
	mode?: string;
	triggered?: boolean;
	timeout?: boolean;
	auto_triggered?: boolean;
	trigger_level_v?: number;
	sample_rate_hz: number;
	samples: number;
	duration_s?: number;
	analog_range_v?: number;
	pulse_probe_ratio?: number;
	mapping?: Record<string, unknown>;
	channels: {
		pulse?: AD2Channel;
		trigger?: AD2Channel;
		clock?: AD2Channel;
		status0?: AD2Channel;
		status1?: AD2Channel;
	};
}

export const ad2CaptureStore = writable<AD2Capture | null>(null);
