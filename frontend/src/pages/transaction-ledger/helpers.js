/**
 * Pure helper functions for the Transaction Ledger.
 * Kept side-effect free so they are easy to test and reuse.
 */
import { format, parseISO } from 'date-fns';

/**
 * Filter the transactions list by entity, classification, direction and a
 * free-text search term. Returns a new array; does not mutate inputs.
 *
 * @param {Array} transactions  - all transactions
 * @param {Object} filters      - { entity, classification, direction, search }
 * @returns {Array} filtered transactions
 */
export const filterTransactions = (transactions, {
  entity = 'all',
  classification = 'all',
  direction = 'all',
  search = '',
} = {}) => {
  const s = search ? search.toLowerCase() : '';
  return transactions.filter((t) => {
    if (entity !== 'all' && t.entity_id !== entity) return false;
    if (classification !== 'all' && t.governance_classification !== classification) return false;
    if (direction !== 'all' && t.direction !== direction) return false;
    if (s) {
      return (
        t.purpose_memo?.toLowerCase().includes(s) ||
        t.source_account?.toLowerCase().includes(s) ||
        t.destination_account?.toLowerCase().includes(s) ||
        t.entity_name?.toLowerCase().includes(s)
      );
    }
    return true;
  });
};

/**
 * Compute inflow / outflow / net totals from a list of transactions.
 */
export const computeFlowTotals = (transactions) => {
  const totalInflows = transactions
    .filter((t) => t.direction === 'inflow')
    .reduce((sum, t) => sum + (t.amount || 0), 0);
  const totalOutflows = transactions
    .filter((t) => t.direction === 'outflow')
    .reduce((sum, t) => sum + (t.amount || 0), 0);
  return { totalInflows, totalOutflows, netFlow: totalInflows - totalOutflows };
};

/**
 * Parse raw CSV text into { headers, rows } objects. Returns null if the CSV
 * is invalid (no header row + at least one data row).
 */
export const parseCsvText = (text) => {
  const lines = text.split('\n').map((l) => l.trim()).filter(Boolean);
  if (lines.length < 2) return null;
  const headers = lines[0].split(',').map((h) => h.replace(/"/g, '').trim());
  const rows = lines.slice(1).map((line) => {
    const vals = line.split(',').map((v) => v.replace(/"/g, '').trim());
    const obj = {};
    headers.forEach((h, i) => { obj[h] = vals[i] || ''; });
    return obj;
  });
  return { headers, rows };
};

/**
 * Auto-detect common CSV column mappings (date / amount / description) from a
 * set of headers.
 */
export const autoDetectCsvMapping = (headers) => {
  const lower = headers.map((h) => h.toLowerCase());
  return {
    date: headers[lower.findIndex((h) => h.includes('date'))] || '',
    amount:
      headers[
        lower.findIndex((h) => h.includes('amount') || h.includes('debit') || h.includes('credit'))
      ] || '',
    description:
      headers[lower.findIndex((h) => h.includes('desc') || h.includes('memo') || h.includes('payee'))] || '',
  };
};

/**
 * Transform mapped CSV rows into the shape expected by the import API, inferring
 * direction from the sign of the amount. Rows with amount <= 0 are filtered out.
 */
export const buildImportRows = (csvData, csvMapping) =>
  csvData
    .map((row) => {
      const rawAmount = parseFloat(row[csvMapping.amount]?.replace(/[^0-9.\-]/g, '')) || 0;
      const direction = rawAmount < 0 ? 'outflow' : 'inflow';
      return {
        date: row[csvMapping.date] || new Date().toISOString().slice(0, 10),
        amount: Math.abs(rawAmount),
        direction,
        description: row[csvMapping.description] || '',
        purpose_memo: row[csvMapping.description] || '',
      };
    })
    .filter((r) => r.amount > 0);

/**
 * Safe date formatter — falls back to the raw value when parsing fails.
 */
export const safeFormatDate = (isoDate, fmt = 'MMM d, yyyy') => {
  try {
    return format(parseISO(isoDate), fmt);
  } catch {
    return isoDate;
  }
};

/**
 * Build a Map from threshold alert transaction_id -> alert, for O(1) lookups in
 * the table renderer.
 */
export const buildThresholdAlertByTxn = (thresholdAlerts) =>
  new Map(thresholdAlerts.map((a) => [a.transaction_id, a]));