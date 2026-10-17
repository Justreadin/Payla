/* ============================================================
   PAYLA — NAME MATCHING
   Fuzzy comparison between a user's full name and a
   bank-confirmed account name.

   Rules:
     - Case-insensitive
     - Order-independent
     - Punctuation-insensitive
     - Match if 2+ meaningful name tokens overlap
       (meaningful = 3+ characters, to avoid initials)
     - Superset in either direction counts as a match

   Returns one of: 'matched' | 'mismatch' | 'pending'
   ============================================================ */

const MIN_TOKEN_LENGTH = 3;
const MIN_OVERLAP = 2;

/**
 * Normalize a name into a set of lowercase tokens.
 * Strips punctuation, collapses whitespace.
 *
 * @param {string} name
 * @returns {string[]}
 */
function normalizeTokens(name) {
  if (!name || typeof name !== 'string') return [];

  return name
    .toLowerCase()
    .replace(/[^\p{L}\p{N}\s]/gu, '') // keep letters, numbers, spaces
    .split(/\s+/)
    .filter(Boolean);
}

/**
 * Compare a user's full name to a bank account name.
 *
 * @param {string} userFullName
 * @param {string} bankAccountName
 * @returns {'matched'|'mismatch'|'pending'}
 */
export function matchName(userFullName, bankAccountName) {
  if (!userFullName || !bankAccountName) {
    return 'pending';
  }

  const userTokens = normalizeTokens(userFullName);
  const bankTokens = normalizeTokens(bankAccountName);

  if (!userTokens.length || !bankTokens.length) {
    return 'pending';
  }

  const userSet = new Set(userTokens);
  const bankSet = new Set(bankTokens);

  // Tokens that appear in both
  const common = [...userSet].filter((t) => bankSet.has(t));

  // Filter down to meaningful tokens (3+ chars)
  const meaningful = common.filter((t) => t.length >= MIN_TOKEN_LENGTH);

  if (meaningful.length >= MIN_OVERLAP) {
    return 'matched';
  }

  // Superset check — the entire shorter side is contained in the longer
  const userIsSubset = [...userSet].every((t) => bankSet.has(t));
  const bankIsSubset = [...bankSet].every((t) => userSet.has(t));

  if (userIsSubset || bankIsSubset) {
    return 'matched';
  }

  return 'mismatch';
}

/**
 * Convenience: check if the match status should light the trust stamp.
 */
export function isVerified(matchStatus) {
  return matchStatus === 'matched';
}