import { useEffect, useRef, useCallback } from 'react';
import { toast } from 'sonner';
import { fetchWithAuth } from '@/utils/api';

/**
 * Autosave hook — debounced 30s, calls POST /minutes/autosave.
 * Shows "Draft saved" toast on success.
 *
 * @param {object} params
 * @param {object|null} params.selectedTrust - Current trust from AuthContext
 * @param {object} params.formData - The full form data to autosave
 * @param {Array} params.sections - Template sections
 * @param {boolean} params.enabled - Whether autosave is active (e.g. only after step 1)
 * @param {number} [params.debounceMs=30000] - Debounce interval in ms
 */
export function useMinutesAutosave({ selectedTrust, formData, sections, enabled, debounceMs = 30000 }) {
  const timerRef = useRef(null);
  const lastSavedRef = useRef(null);
  const formDataRef = useRef(formData);
  const sectionsRef = useRef(sections);

  // Keep refs current
  formDataRef.current = formData;
  sectionsRef.current = sections;

  const saveDraft = useCallback(async () => {
    if (!selectedTrust?.trust_id || !enabled) return;

    // Build a deterministic key to avoid no-op saves
    const saveKey = JSON.stringify({ formData: formDataRef.current, sections: sectionsRef.current });
    if (saveKey === lastSavedRef.current) return;

    try {
      const res = await fetchWithAuth('/minutes/autosave', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          trust_id: selectedTrust.trust_id,
          ...formDataRef.current,
          sections: sectionsRef.current,
          status: 'draft'
        })
      });

      if (res.ok) {
        lastSavedRef.current = saveKey;
        toast.success('Draft saved', { duration: 2000 });
      }
      // Silently ignore failures — autosave is best-effort
    } catch {
      // Silently ignore network errors
    }
  }, [selectedTrust?.trust_id, enabled]);

  useEffect(() => {
    if (!enabled) return;

    // Clear any existing timer
    if (timerRef.current) clearTimeout(timerRef.current);

    // Set a new debounced save
    timerRef.current = setTimeout(() => {
      saveDraft();
    }, debounceMs);

    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, [enabled, formData, sections, debounceMs, saveDraft]);

  // Expose a manual save function
  return { saveDraft };
}