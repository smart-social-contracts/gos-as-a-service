import { writable } from 'svelte/store';

/** Increment to request the mundus assistant open. */
export const assistantOpenRequest = writable(0);

/** Increment to toggle the mundus assistant open/closed. */
export const assistantToggleRequest = writable(0);

/** Increment to request the mundus assistant close. */
export const assistantCloseRequest = writable(0);

export function requestAssistantOpen() {
	assistantOpenRequest.update((n) => n + 1);
}

export function requestAssistantToggle() {
	assistantToggleRequest.update((n) => n + 1);
}

export function requestAssistantClose() {
	assistantCloseRequest.update((n) => n + 1);
}
