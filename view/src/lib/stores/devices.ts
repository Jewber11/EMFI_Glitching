import { writable } from 'svelte/store';

export type DeviceName = 'chipshover' | 'chipshouter' | 'scaffold' | 'xds110' | 'ad2';

export const KNOWN_DEVICES: DeviceName[] = ['chipshover', 'chipshouter'];

export interface DeviceStatus {
	name: string;
	available: boolean;
	connected: boolean;
	port: string | null;
	label: string | null;
	last_error: string | null;
	busy: boolean;

	// Optional chipshouter-specific extras — present in payload when emitted by Control.
	voltage_v?: number | null;
	voltage_measured_v?: number | null;
	faults?: string[] | null;
	state?: string | null;
}

export function placeholderStatus(name: string): DeviceStatus {
	return {
		name,
		available: false,
		connected: false,
		port: null,
		label: null,
		last_error: null,
		busy: false,
	};
}

export const devicesStore = writable<Map<string, DeviceStatus>>(new Map());
