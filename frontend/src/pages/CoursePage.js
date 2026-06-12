import { useEffect } from 'react';
export default function CoursePage() {
  useEffect(() => {
    window.location.href = 'https://trustoffice.app/trustee-101';
  }, []);
  return null;
}