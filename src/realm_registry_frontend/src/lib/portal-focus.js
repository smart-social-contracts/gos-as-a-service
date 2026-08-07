import { writable } from 'svelte/store';

/** Document focus pushed from an embedded realm iframe (`focus:push`). */
export const portalDocumentFocus = writable(null);
