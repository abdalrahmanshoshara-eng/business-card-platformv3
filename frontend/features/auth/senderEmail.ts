/**
 * Quick check of the sender email typed in the setup popup, so an obvious typo
 * is caught before the request. The backend validates it again (EmailField).
 */
const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

/** User-facing reason the address can't be saved, or '' when it looks fine. */
export function senderEmailError(value: string): string {
  const email = value.trim();
  if (!email) return 'اكتب بريد المُرسِل.';
  if (!EMAIL_PATTERN.test(email)) return 'يرجى إدخال بريد إلكتروني صالح.';
  return '';
}
