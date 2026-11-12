export const MAX_UPLOAD_BYTES = 256 * 1024 * 1024;

const ALLOWED_EXACT_TYPES = new Set([
  "application/pdf",
  "text/plain",
  "application/zip",
]);

export function validateUpload(filename: string, contentType: string, size: number): boolean {
  const safeFilename = filename.trim();
  const allowedType = contentType.startsWith("image/") ||
    contentType.startsWith("video/") ||
    contentType.startsWith("audio/") ||
    ALLOWED_EXACT_TYPES.has(contentType);

  return safeFilename.length > 0 && safeFilename.length <= 100 && allowedType &&
    Number.isSafeInteger(size) && size > 0 && size <= MAX_UPLOAD_BYTES;
}
