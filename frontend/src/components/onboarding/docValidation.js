import { toast } from 'sonner';
import { ALLOWED_DOC_TYPES, ALLOWED_DOC_EXTENSIONS, MAX_DOC_SIZE } from './onboardingConstants';

/** Returns true when the file passes type/size validation; shows a toast and returns false otherwise. */
export function validateDocFile(file) {
  if (!file) return false;
  const typeOk = ALLOWED_DOC_TYPES.includes(file.type) || ALLOWED_DOC_EXTENSIONS.test(file.name);
  if (!typeOk) {
    toast.error('Please upload a PDF, Word document, or text file');
    return false;
  }
  if (file.size > MAX_DOC_SIZE) {
    toast.error(
      `${file.name} is ${(file.size / (1024 * 1024)).toFixed(1)}MB. Uploads are limited to 100MB ` +
      '(large PDFs are compressed automatically after upload). Please compress the PDF first (e.g. ilovepdf.com/compress_pdf).'
    );
    return false;
  }
  return true;
}
