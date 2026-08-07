import { writable } from 'svelte/store';
import { defaultPanelWidth } from '$lib/panel-width.js';

/** @type {import('svelte/store').Writable<{ open: boolean, docked: boolean, width: number, resizing: boolean }>} */
export const assistantChrome = writable({ open: false, docked: false, width: defaultPanelWidth(), resizing: false });
