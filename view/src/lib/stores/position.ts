import { writable } from 'svelte/store';

export interface Position {
  x: number; y: number; z: number;
  machine_x?: number | null;
  machine_y?: number | null;
  machine_z?: number | null;
}

export const positionStore = writable<Position>({ x: 0, y: 0, z: 0 });
