import { writable } from 'svelte/store';
import type { Project, BuildArtifact, GlitchTarget } from '$lib/types';

export const projects = writable<Project[]>([]);
export const currentProject = writable<Project | null>(null);
export const buildLog = writable<string[]>([]);
export const buildStatus = writable<string>('idle');
export const agentOutput = writable<string[]>([]);
export const currentBuild = writable<BuildArtifact | null>(null);
export const targets = writable<GlitchTarget[]>([]);
