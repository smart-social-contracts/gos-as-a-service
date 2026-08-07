import { writable } from 'svelte/store';

/** @typedef {'prepare' | 'upload' | 'submit' | 'redirect'} DeployStep */

const INITIAL = {
  open: false,
  phase: 'running',
  activeStep: /** @type {DeployStep} */ ('prepare'),
  uploadDetail: '',
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
export function setDeployProgressStep(step, uploadDetail = '') {
  deployProgress.update((state) => ({
    ...state,
    activeStep: step,
    uploadDetail: step === 'upload' ? uploadDetail : '',
  }));
}

export function setDeployProgressUploadDetail(uploadDetail) {
  deployProgress.update((state) => ({
    ...state,
    uploadDetail: uploadDetail || '',
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
