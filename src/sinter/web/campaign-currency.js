/** Entered funding denominations; project costs remain AUD, without conversion. */
export const CEILING_CURRENCY_OPTIONS = Object.freeze([
  ['AUD', 'AUD · Australian dollars'], ['USD', 'USD · US dollars'],
  ['EUR', 'EUR · euros'], ['GBP', 'GBP · pounds sterling'],
  ['NZD', 'NZD · New Zealand dollars'], ['CAD', 'CAD · Canadian dollars'],
  ['unconfirmed', 'Currency not confirmed'],
  ['other', 'Another currency · comparison unsupported'],
].map(row => Object.freeze(row)));

export function campaignCeilingCurrency(row = {}) {
  const value = row.ceiling_currency === undefined ? 'AUD' : row.ceiling_currency;
  if (!CEILING_CURRENCY_OPTIONS.some(([code]) => code === value)) {
    throw new Error('Choose a supported funding currency, unconfirmed or other.');
  }
  return value;
}

export function campaignFundingAmount(row) {
  if (row.route_type === 'non_cash_support') return 'No grant cash';
  const currency = campaignCeilingCurrency(row);
  if (row.ceiling == null || row.ceiling === '') {
    return currency === 'AUD' ? 'Amount not recorded'
      : `Amount not recorded · ${currency === 'unconfirmed' ? 'currency unconfirmed'
        : currency === 'other' ? 'other currency (unsupported)' : currency}`;
  }
  const value = Number(row.ceiling);
  const rendered = new Intl.NumberFormat('en-AU', {
    minimumFractionDigits: Number.isInteger(value) ? 0 : 2,
    maximumFractionDigits: 2,
  }).format(value);
  const amount = currency === 'AUD' ? 'A$' + rendered
    : currency === 'unconfirmed' ? rendered + ' (currency unconfirmed)'
    : currency === 'other' ? rendered + ' (other currency; comparison unsupported)'
    : currency + ' ' + rendered;
  return 'Up to ' + amount;
}

export function campaignCurrencyComparisonNote(row) {
  if (row.route_type === 'non_cash_support'
      || row.ceiling == null || row.ceiling === '') return '';
  const currency = campaignCeilingCurrency(row);
  if (currency === 'AUD') return '';
  const reason = currency === 'unconfirmed' ? 'Funding ceiling currency is unconfirmed'
    : currency === 'other' ? 'Funding ceiling uses another currency (comparison unsupported)'
    : 'Funding ceiling is recorded in ' + currency;
  return reason + '; project costs are AUD. No currency conversion or ceiling comparison '
    + 'was made. Review the funding terms and costs separately.';
}
