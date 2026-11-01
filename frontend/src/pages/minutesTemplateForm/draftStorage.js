/**
 * draftStorage — debounced localStorage persistence for the Accept-Property
 * multi-row form (2026-11-01 session-kickout data-loss fix, council F7/F8).
 *
 * Scope: exactly ONE key per trust + template type —
 *   `to_draft_acceptance_of_property_<trust_id>`
 * Persisted payload: { items: [...full row objects...], saved_at } where items
 * is propertyData.items (the multi-row form state: grantor_name,
 * property_description, property_value, property_identifier, property_location,
 * conveyance_date, appraiser_name, add_to_schedule_a, schedule_a_category).
 *
 * Guarantees:
 *  - Storage failures (Safari private mode quota/secure errors) are silent
 *    no-ops via try/catch — they must NEVER break the form.
 *  - Race guard (F8): the debounced flush refuses to write a payload captured
 *    BEFORE a later clear (draftGenerationRef generation bump at generation
 *    success). A timer scheduled before the clear must not resurrect the draft.
 */

export const draftKeyFor = (trustId, templateType = 'acceptance_of_property') =>
  `to_draft_${templateType}_${trustId}`;

/**
 * Read a saved draft for a trust + template type.
 * Returns { items: [...], saved_at } or null (missing / corrupt / wrong shape).
 */
export const loadDraft = (trustId, templateType = 'acceptance_of_property') => {
  try {
    const raw = localStorage.getItem(draftKeyFor(trustId, templateType));
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (!parsed || !Array.isArray(parsed.items) || parsed.items.length === 0) {
      return null;
    }
    return parsed;
  } catch (_e) {
    return null; // corrupt or unreadable — treat as no draft
  }
};

/**
 * Clear a draft key (called when generation returns minutes_id, NOT at save).
 * Silent no-op on storage failure.
 */
export const clearDraft = (trustId, templateType = 'acceptance_of_property') => {
  try {
    localStorage.removeItem(draftKeyFor(trustId, templateType));
  } catch (_e) {
    // storage unavailable — nothing to clear
  }
};

/**
 * Create a debounced draft writer for one form.
 *
 * @param {number} delayMs debounce window (default 500ms)
 * @returns {{
 *   schedule: (trustId: string, getData: () => any, templateType?: string) => void,
 *   cancel: () => void
 * }} schedule() captures getData() result SYNCHRONOUSLY (so the generation-ref
 * race guard sees the payload at schedule time, not at flush time), stores it,
 * and writes it `delayMs` later. The flush re-reads the REF
 * passed on each schedule — pass `generationRef` via `setGenerationRefGetter`.
 */
export const createDraftSaver = (delayMs = 500) => {
  let timer = null;
  let pendingPayload = null;
  let pendingKey = null;
  let generationGetter = null; // () => current draft generation number

  const flush = () => {
    timer = null;
    const gen = generationGetter ? generationGetter() : 0;
    // Race guard (F8): if the form generation advanced past the generation at
    // schedule time (a clear-on-success happened), do NOT resurrect the draft.
    if (pendingPayload && pendingPayload.__generation === gen) {
      try {
        localStorage.setItem(pendingKey, JSON.stringify({
          items: pendingPayload.items,
          saved_at: new Date().toISOString(),
        }));
      } catch (_e) {
        // Safari private mode / quota — silent no-op, never break the form.
      }
    }
    pendingPayload = null;
    pendingKey = null;
  };

  return {
    /**
     * @param {string} trustId trust scope for the storage key
     * @param {() => any} getData returns `{ items: [...], generation: number }`
     *   synchronously — items is the CURRENT form rows, generation is the
     *   current draft-generation ref value.
     * @param {string} [templateType]
     */
    schedule(trustId, getData, templateType = 'acceptance_of_property') {
      let snap;
      try {
        snap = getData();
      } catch (_e) {
        return; // form not ready — skip this cycle, keep the old draft
      }
      if (!trustId || !snap || !Array.isArray(snap.items)) return;
      const hasContent = snap.items.some(
        (it) => it && Object.values(it).some((v) => v !== '' && v !== null && v !== undefined && v !== true)
      );
      pendingKey = draftKeyFor(trustId, templateType);
      pendingPayload = { items: snap.items, __generation: snap.generation || 0 };
      if (!timer) {
        timer = setTimeout(flush, delayMs);
      }
      // hasContent is informational (empty rows aren't persisted): if every row
      // is empty, skip persisting to avoid writing noise drafts.
      if (!hasContent) {
        clearTimeout(timer);
        timer = setTimeout(flush, delayMs);
        pendingPayload = null;
      }
    },
    /** Bump the generation AFTER a clear — older scheduled flushes then no-op. */
    setGenerationGetter(getter) {
      generationGetter = getter;
    },
    cancel() {
      if (timer) {
        clearTimeout(timer);
        timer = null;
      }
      pendingPayload = null;
      pendingKey = null;
    },
  };
};