const LOWERCASE = 'abcdefghijkmnopqrstuvwxyz';
const UPPERCASE = 'ABCDEFGHJKLMNPQRSTUVWXYZ';
const DIGITS = '23456789';
const SYMBOLS = '!@#$%&*+-=?';

const GROUPS = [LOWERCASE, UPPERCASE, DIGITS, SYMBOLS] as const;
const ALL_CHARACTERS = GROUPS.join('');

function secureRandomIndex(max: number): number {
  if (!globalThis.crypto?.getRandomValues) {
    throw new Error('Secure random generation is not available.');
  }

  // Discard the uneven end of the byte range to avoid modulo bias.
  const limit = Math.floor(256 / max) * max;
  const byte = new Uint8Array(1);
  do {
    globalThis.crypto.getRandomValues(byte);
  } while (byte[0] >= limit);

  return byte[0] % max;
}

function pick(characters: string): string {
  return characters[secureRandomIndex(characters.length)];
}

/** Generates a strong password locally; the value never leaves the browser until saved. */
export function generateSecurePassword(length = 16): string {
  if (!Number.isInteger(length) || length < GROUPS.length) {
    throw new RangeError(`Password length must be an integer of at least ${GROUPS.length}.`);
  }

  const password = GROUPS.map(pick);
  while (password.length < length) password.push(pick(ALL_CHARACTERS));

  // Fisher-Yates shuffle using the same cryptographically secure source.
  for (let index = password.length - 1; index > 0; index -= 1) {
    const swapWith = secureRandomIndex(index + 1);
    [password[index], password[swapWith]] = [password[swapWith], password[index]];
  }

  return password.join('');
}
