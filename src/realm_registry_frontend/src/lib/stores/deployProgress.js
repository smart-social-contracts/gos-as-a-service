import { writable } from 'svelte/store';

/** @typedef {'prepare' | 'submit' | 'redirect'} DeployStep */

const INITIAL = {
  open: false,
  phase: 'running',
  activeStep: /** @type {DeployStep} */ ('prepare'),
  errorMessage: '',
};

export const deployProgress = writable({ ...INITIAL });

export function resetDeployProgress() {
  deployProgress.set({ ...INITIAL });
}

export function openDeployProgress() {
  deployProgress.set({
    ...INITIAL,
    open: true,
  });
}

/** @param {DeployStep} step */
export function setDeployProgressStep(step) {
  deployProgress.update((state) => ({
    ...state,
    activeStep: step,
  }));
}

export function failDeployProgress(message) {
  deployProgress.update((state) => ({
    ...state,
    open: true,
    phase: 'error',
    errorMessage: message || 'Deployment failed. Please try again.',
  }));
}

export function closeDeployProgress() {
  deployProgress.set({ ...INITIAL });
}
