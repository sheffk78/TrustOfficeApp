/**
 * Shared upload validation for all vault upload surfaces (Vault form,
 * FileUploadCard, onboarding). One source of truth for what we accept and
 * the exact guidance members see when a file can't be taken.
 *
 * Policy: accept up to 100MB — the server deep-compresses PDFs after upload
 * (3-pass ladder) and stores anything that lands under the 16MB vault cap.
 * Only reject what the server genuinely can't take.
 */

export const MAX_UPLOAD_BYTES = 100 * 1024 * 1024; // 100MB transfer limit

export const ACCEPTED_EXTENSIONS = /\.(pdf|doc|docx|xls|xlsx|txt|jpg|jpeg|png|gif|webp|tiff)$/i;

/** Returns true when the file's extension/type is something we accept. */
export function isAcceptedFileType(file) {
  return ACCEPTED_EXTENSIONS.test(file.name) || (file.type || '').startsWith('image/');
}

export function sizeTooLargeMessage(file) {
  return (
    `${file.name} is ${(file.size / (1024 * 1024)).toFixed(1)}MB. ` +
    `Uploads are limited to 100MB (PDFs are compressed automatically after upload, but the transfer limit is 100MB). ` +
    `To fix: (1) compress the PDF at ilovepdf.com/compress_pdf and upload the smaller file; ` +
    `or (2) use "Link External" on the Vault page to store a link to the file instead.`
  );
}

export function typeNotSupportedMessage(file) {
  return (
    `${file.name} isn't a file type we can store. Supported types: PDF, images (JPG/PNG), Word, Excel, and text files. ` +
    `To fix: (1) export or print your document to PDF (most apps: File → Save As PDF, or File → Print → Save as PDF) and upload that; ` +
    `or (2) photograph paper documents and upload the photos.`
  );
}

/**
 * Validates a file at selection time. Returns an error message string to
 * display, or null when the file is good to proceed.
 */
export function validateVaultFile(file) {
  if (!file) return 'Please select a file to upload first.';
  if (file.size > MAX_UPLOAD_BYTES) return sizeTooLargeMessage(file);
  if (!isAcceptedFileType(file)) return typeNotSupportedMessage(file);
  return null;
}