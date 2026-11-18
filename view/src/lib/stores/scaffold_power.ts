import { writable } from 'svelte/store';

export interface ScaffoldPowerState { dut: boolean; platform: boolean; }

export const scaffoldPowerStore = writable<ScaffoldPowerState>({ dut: false, platform: false });
