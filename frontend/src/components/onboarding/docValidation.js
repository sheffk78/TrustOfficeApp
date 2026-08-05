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
    toast.error('File is too large. Maximum size is 16MB.');
    return false;
  }
  return true;
}
