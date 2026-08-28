const STORAGE_KEY = 'realms_deployment_attempt_memory';
const STAGE_TIMES_KEY = 'realms_deployment_stage_times';

function canUseSession() {
	try {
		return typeof sessionStorage !== 'undefined';
	} catch {
		return false;
	}
}

const FAILED_STATUSES = new Set(['failed', 'failed_verification', 'cancelled']);
const ACTIVE_STATUSES = new Set([
	'pending',
	'provisioning',
	'deploying',
	'verifying',
	'extensions',
	'registering',
	'in_progress'
]);

/**
 * Collapse an error string that was concatenated with itself.
 * @param {string} [error]
 * @returns {string}
 */
export function uniqueErrorText(error) {
	const text = typeof error === 'string' ? error.trim() : '';
	if (!text) return '';

	const parts = text
		.split(/\n\n+/)
		.map((part) => part.trim())
		.filter(Boolean);
	if (parts.length > 1) {
		const seen = new Set();
		const out = [];
		for (const part of parts) {
			if (seen.has(part)) continue;
			seen.add(part);
			out.push(part);
		}
		return out.join('\n\n');
	}

	const lines = text
		.split(/\n+/)
		.map((part) => part.trim())
		.filter(Boolean);
	if (lines.length > 1 && lines.every((line) => line === lines[0])) {
		return lines[0];
	}

	if (text.length >= 20 && text.length % 2 === 0) {
		const half = text.length / 2;
		if (text.slice(0, half) === text.slice(half)) {
			return text.slice(0, half);
		}
	}
	return text;
}

function loadStore() {
	if (!canUseSession()) return {};
	try {
		return JSON.parse(sessionStorage.getItem(STORAGE_KEY) || '{}');
	} catch {
		return {};
	}
}

function saveStore(store) {
	if (!canUseSession()) return;
	try {
		sessionStorage.setItem(STORAGE_KEY, JSON.stringify(store));
	} catch {
		/* quota / private mode */
	}
}

function toTimestampMs(value) {
	if (value == null || value === '') return null;
	const n = typeof value === 'bigint' ? Number(value) : Number(value);
	if (!Number.isFinite(n) || n <= 0) return null;
	return n > 1e12 ? n : n * 1000;
}

function clearStageObservation(jobId) {
	if (!canUseSession() || !jobId) return;
	try {
		const raw = JSON.parse(sessionStorage.getItem(STAGE_TIMES_KEY) || '{}');
		delete raw[jobId];
		sessionStorage.setItem(STAGE_TIMES_KEY, JSON.stringify(raw));
	} catch {
		/* quota / private mode */
	}
}

function jobStatus(job) {
	return (job?.raw_status || job?.status || '').toLowerCase();
}

/**
 * Remember the last failure for a job so a heartbeat reopen can show
 * "Retrying automatically" with one copy of the error.
 *
 * @param {string} jobId
 * @param {object} job
 * @param {number} [nowMs]
 * @returns {{ lastError: string, failedAtMs: number|null, attemptStartedAtMs: number|null, autoRetrying: boolean } | null}
 */
export function rememberJobAttempt(jobId, job, nowMs = Date.now()) {
	if (!jobId || !job) return null;
	const status = jobStatus(job);
	const error = uniqueErrorText(job.last_error || job.previous_error || job.error || '');
	const createdAtMs = toTimestampMs(job.created_at);
	const completedAtMs = toTimestampMs(job.completed_at);
	const store = loadStore();
	const prev = store[jobId] || {};

	if (status === 'completed' && !error) {
		delete store[jobId];
		saveStore(store);
		clearStageObservation(jobId);
		return null;
	}

	if (FAILED_STATUSES.has(status)) {
		const next = {
			lastError: error || prev.lastError || '',
			failedAtMs: completedAtMs || nowMs,
			attemptStartedAtMs: prev.attemptStartedAtMs || createdAtMs || nowMs,
			autoRetrying: false
		};
		store[jobId] = next;
		saveStore(store);
		return next;
	}

	if (ACTIVE_STATUSES.has(status) && (prev.lastError || completedAtMs)) {
		const alreadyRetrying = prev.autoRetrying && prev.attemptStartedAtMs;
		const attemptStartedAtMs = alreadyRetrying ? prev.attemptStartedAtMs : nowMs;
		if (!alreadyRetrying) {
			clearStageObservation(jobId);
		}
		const next = {
			lastError: error || prev.lastError || '',
			failedAtMs: prev.failedAtMs || completedAtMs,
			attemptStartedAtMs,
			autoRetrying: true
		};
		store[jobId] = next;
		saveStore(store);
		return next;
	}

	return prev.lastError || prev.autoRetrying ? prev : null;
}

export function getJobAttemptMemory(jobId) {
	if (!jobId) return null;
	return loadStore()[jobId] || null;
}
