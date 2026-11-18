import { writable } from 'svelte/store';

export interface ArmState {
  armed: boolean;
  auto_disarm_seconds: number;
  seconds_until_auto_disarm: number | null;
}

export const armStore = writable<ArmState>({
  armed: false,
  auto_disarm_seconds: 300,
  seconds_until_auto_disarm: null
});
