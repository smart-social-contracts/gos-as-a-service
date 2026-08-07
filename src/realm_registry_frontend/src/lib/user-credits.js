/**
 * Spendable credits = balance on `realm_registry_backend` (what deploy uses).
 *
 * We read the canister from the browser when possible. If that fails, we fall
 * back to the billing service GET `/credits/{principal}`, which calls the same
 * `get_credits` on the registry server-side.
 */
import { CONFIG } from '$lib/config.js';

/** Estimated ongoing hosting per live realm per calendar month (credits). */
export const MONTHLY_HOSTING_CREDITS_PER_REALM = 1;

function isCurrentMonth(timestampSec) {
  const d = new Date(Number(timestampSec) * 1000);
  const now = new Date();
  return d.getFullYear() === now.getFullYear() && d.getMonth() === now.getMonth();
}

export function sumSpentThisMonth(transactions) {
  if (!Array.isArray(transactions)) return 0;
  return transactions
    .filter((t) => isCurrentMonth(t.timestamp))
    .filter((t) => t.transaction_type === 'spend' || t.transaction_type === 'hold')
    .reduce((sum, t) => sum + Math.abs(Number(t.amount) || 0), 0);
}

export function predictMonthlyCost(spentThisMonth, liveRealmCount) {
  const hosting = Math.max(0, Number(liveRealmCount) || 0) * MONTHLY_HOSTING_CREDITS_PER_REALM;
  return Number(spentThisMonth) + hosting;
}

async function fetchCreditsRecord(principalText) {
  try {
    const { backend } = await import('$lib/canisters.js');
    const result = await backend.get_credits(principalText);
    if ('Ok' in result) {
      return {
        balance: Number(result.Ok.balance),
        total_purchased: Number(result.Ok.total_purchased),
        total_spent: Number(result.Ok.total_spent),
      };
    }
  } catch (e) {
    console.warn('fetchCreditsRecord: canister get_credits failed, trying billing proxy', e);
  }

  const billingUrl = CONFIG.billing_service_url || 'https://billing.realmsgos.dev';
  try {
    const br = await fetch(`${billingUrl}/credits/${encodeURIComponent(principalText)}`);
    if (br.ok) {
      const j = await br.json();
      if (j && j.credits != null) {
        return {
          balance: Number(j.credits),
          total_purchased: 0,
          total_spent: 0,
        };
      }
    }
  } catch (e) {
    console.error('fetchCreditsRecord: billing proxy failed', e);
  }

  return { balance: 0, total_purchased: 0, total_spent: 0 };
}

async function fetchTransactions(principalText) {
  try {
    const { backend } = await import('$lib/canisters.js');
    const result = await backend.get_transactions(principalText, 100n);
    if ('Ok' in result) {
      return result.Ok.map((t) => ({
        amount: Number(t.amount),
        transaction_type: t.transaction_type,
        timestamp: Number(t.timestamp),
      }));
    }
  } catch (e) {
    console.warn('fetchTransactions failed', e);
  }
  return [];
}

export async function fetchUserCreditBalance(principalText) {
  const record = await fetchCreditsRecord(principalText);
  return record.balance;
}

export async function fetchUserBillingSummary(principalText, liveRealmCount = 0) {
  const record = await fetchCreditsRecord(principalText);
  const transactions = await fetchTransactions(principalText);
  const spentThisMonth = sumSpentThisMonth(transactions);
  return {
    ...record,
    spentThisMonth,
    predictedThisMonth: predictMonthlyCost(spentThisMonth, liveRealmCount),
  };
}
