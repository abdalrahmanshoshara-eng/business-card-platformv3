/**
 * Optional image (e.g. an announcement poster) attached to a message and shown
 * inside the email under the text. The backend re-checks everything; these
 * checks only give the user a quick, clear message before uploading.
 */

/** Must match backend `ALLOWED_IMAGE_CONTENT_TYPES`. */
export const MESSAGE_IMAGE_TYPES = ['image/jpeg', 'image/png', 'image/webp', 'image/gif'];

/** Must match backend `MAX_UPLOAD_IMAGE_MB` (default 10). */
export const MESSAGE_IMAGE_MAX_MB = 10;

type FileLike = { type: string; size: number };

/** First image among pasted/dropped/picked files, if any. */
export function firstImageFile<T extends FileLike>(files: ArrayLike<T> | null | undefined): T | null {
  for (const file of Array.from(files || [])) {
    if (file.type.startsWith('image/')) return file;
  }
  return null;
}

/** User-facing reason the image can't be sent, or '' when it's fine. */
export function messageImageError(file: FileLike): string {
  if (!MESSAGE_IMAGE_TYPES.includes(file.type)) return 'نوع الصورة غير مدعوم. المسموح: JPEG, PNG, WEBP, GIF.';
  if (file.size > MESSAGE_IMAGE_MAX_MB * 1024 * 1024) {
    return `حجم الصورة يتجاوز الحد المسموح (${MESSAGE_IMAGE_MAX_MB} ميغابايت).`;
  }
  return '';
}
