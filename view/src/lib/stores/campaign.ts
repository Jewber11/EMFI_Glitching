import { writable } from 'svelte/store';

export interface CampaignProgress {
	campaign_id: string;
	active: boolean;
	completed_attempts: number;
	total_attempts: number;
	current_position: [number, number, number] | null;
	last_outcome: string | null;
}

export const activeCampaign = writable<CampaignProgress | null>(null);
