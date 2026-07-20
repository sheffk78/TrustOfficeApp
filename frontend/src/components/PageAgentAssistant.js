import { useEffect, useRef, useState, useCallback } from 'react';
import { PageAgent, tool } from 'page-agent';
import { z } from 'zod/v4';
import { API } from '@/utils/api';

/**
 * PageAgentAssistant — reusable Page Agent integration component.
 *
 * The agent is restricted to the provided container via `interactiveWhitelist`,
 * so it can only fill/draft fields inside that container. It is NEVER allowed
 * to submit — the system instructions forbid clicking submit/approve buttons,
 * and the `execute_javascript` tool is disabled.
 *
 * All LLM calls route through the backend proxy at `/api/page-agent/llm/chat/completions`,
 * which authenticates the JWT and appends the OpenRouter API key server-side.
 *
 * Props:
 *   containerRef            — ref to the form container DOM element (interactiveWhitelist target)
 *   systemInstructions      — page-specific system instructions string (REQUIRED)
 *   pageName                — short page name for console logging (e.g. "Distributions", "Onboarding")
 *   extractedFields         — optional dynamic fields passed to the agent via getPageInstructions
 *   placeholder            — optional placeholder text for the instruction input
 *   idleMessage            — optional idle status message
 *   helpText              — optional help text shown below the input
 *
 * Legacy props (OnboardingConfirmStep, optional — kept for backward compat):
 *   trustData, setTrustData, trusteeNames, setTrusteeNames
 */
export default function PageAgentAssistant({
  containerRef,
  systemInstructions,
  pageName = 'Page',
  extractedFields,
  placeholder = 'Type an instruction for the agent…',
  idleMessage = 'Ready. Type an instruction for the agent.',
  helpText = 'The agent can fill draft values and explain fields. It will never submit the form — you review and confirm yourself.',
  // Legacy props (unused by Distributions, kept for onboarding compat)
  trustData: _trustData,
  setTrustData: _setTrustData,
  trusteeNames: _trusteeNames,
  setTrusteeNames: _setTrusteeNames,
}) {
  const agentRef = useRef(null);
  const [status, setStatus] = useState('idle'); // idle | thinking | acting | done | error
  const [statusMessage, setStatusMessage] = useState('');
  const [instruction, setInstruction] = useState('');
  const [history, setHistory] = useState([]); // [{ role, text, ts }]
  const [agentError, setAgentError] = useState(null);

  // ---------------- PII masking for page content ----------------
  // NOTE: Must be defined before any code that references it.
  // In dev mode hoisting makes order irrelevant, but the minified production
  // build enforces TDZ — "Cannot access 'v' before initialization".
  const maskPII = useCallback((content) => {
    if (!content || typeof content !== 'string') return content;
    let masked = content;
    // SSN: XXX-XX-XXXX
    masked = masked.replace(/\b\d{3}-\d{2}-\d{4}\b/g, 'XXX-XX-XXXX');
    // EIN: XX-XXXXXXX (employer id)
    masked = masked.replace(/\b\d{2}-\d{7}\b/g, 'XX-XXXXXXX');
    // Credit card numbers: 13-19 digit runs, optionally grouped by 4
    masked = masked.replace(/\b(?:\d[ -]*){13,19}\d\b/g, (m) => {
      const digits = m.replace(/\D/g, '');
      if (digits.length >= 13 && digits.length <= 19) return '[CARD REDACTED]';
      return m;
    });
    return masked;
  }, []);

  const transformPageContent = useCallback((content) => maskPII(content), [maskPII]);

  // ---------------- Custom tool: Radix Select bridge ----------------
  // Page Agent's built-in selectOption only works on native <select> elements.
  // TrustOffice uses Radix UI Select (button trigger + portal dropdown) for
  // trust type, tax month, distribution type, category, status, trustee.
  // This custom tool:
  //   1. Finds the Radix trigger by data-testid
  //   2. Clicks it to open the dropdown (portal renders at document.body)
  //   3. Finds the option by visible text in the portal
  //   4. Clicks the option (fires Radix's onValueChange)
  //   5. Waits for the dropdown to close
  const radixSelectTool = tool({
    description:
      'Select an option from a Radix UI dropdown (non-native select). ' +
      'Use this when the element is a button with role="combobox" or a Radix SelectTrigger, ' +
      'NOT a native <select>. Pass the data-testid of the trigger element and the exact visible text of the option to select.',
    inputSchema: z.object({
      testid: z.string().describe('The data-testid attribute value of the Radix Select trigger button'),
      optionText: z.string().describe('The exact visible text of the option to select (e.g. "Trust Distribution")'),
    }),
    execute: async function (input, { signal }) {
      const { testid, optionText } = input;
      const trigger = document.querySelector(`[data-testid="${testid}"]`);
      if (!trigger) {
        return `Error: Could not find element with data-testid="${testid}"`;
      }
      // Click the trigger to open the Radix dropdown
      trigger.click();
      // Poll for portal content (Radix renders asynchronously at document.body)
      let options = [];
      for (let i = 0; i < 40; i++) {
        if (signal?.aborted) return 'Task cancelled.';
        options = document.querySelectorAll('[role="option"]');
        if (options.length > 0) break;
        await new Promise((r) => setTimeout(r, 50));
      }
      if (options.length === 0) {
        trigger.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
        return `Error: Radix dropdown did not open for data-testid="${testid}".`;
      }
      let matched = null;
      for (const opt of options) {
        if (opt.textContent?.trim() === optionText.trim()) {
          matched = opt;
          break;
        }
      }
      if (!matched) {
        // Close the dropdown by pressing Escape on the trigger
        trigger.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
        return `Error: Option "${optionText}" not found in Radix dropdown. Available options: ${Array.from(options).map(o => o.textContent?.trim()).join(', ')}`;
      }
      // Click the option — Radix fires onValueChange internally
      matched.click();
      // Wait for dropdown to close and React state to update
      await new Promise((resolve) => setTimeout(resolve, 200));
      if (signal?.aborted) return 'Task cancelled after selection.';
      return `Successfully selected "${optionText}" from ${testid}`;
    },
  });

  // ---------------- customFetch: attach JWT + credentials ----------------
  const customFetch = useCallback(async (url, options = {}) => {
    const token = localStorage.getItem('auth_token');
    const headers = new Headers(options.headers || {});
    headers.set('Content-Type', 'application/json');
    headers.set('Accept', 'application/json');
    if (token) {
      headers.set('Authorization', `Bearer ${token}`);
    }
    const merged = {
      ...options,
      headers,
      credentials: 'include',
    };
    return fetch(url, merged);
  }, []);

  // ---------------- Initialize agent on mount ----------------
  useEffect(() => {
    let cancelled = false;
    let agent = null;

    async function init() {
      if (!containerRef || !containerRef.current) {
        setAgentError('Form container not ready.');
        return;
      }
      if (!systemInstructions) {
        setAgentError('Missing systemInstructions prop.');
        return;
      }
      try {
        agent = new PageAgent({
          model: 'google/gemini-2.5-flash-lite',
          baseURL: `${API}/page-agent/llm`,
          customFetch,
          // Restrict all interaction to the provided form container.
          interactiveWhitelist: [containerRef.current],
          // Disable arbitrary JS execution for safety.
          customTools: {
            execute_javascript: null, // disabled — security
            select_radix_option: radixSelectTool, // bridge for Radix UI Selects
            // Override ask_user to prevent blocking — our UI doesn't support
            // mid-execution back-and-forth. Instead, tell the agent to use best
            // judgment and report the limitation in its final response.
            ask_user: tool({
              description:
                'Ask the user a clarifying question. ' +
                'Use this when you need the user to choose between options or provide information you cannot determine from the page.',
              inputSchema: z.object({
                question: z.string().describe('The question to ask the user'),
              }),
              execute: async (input) => {
                return (
                  `The user cannot respond mid-task. Use your best judgment: ` +
                  `pick the closest matching option from what's available, ` +
                  `or skip the field if nothing fits. ` +
                  `Mention this limitation in your final response. ` +
                  `Original question was: "${input.question}"`
                );
              },
            }),
          },
          enableMask: true,
          maxSteps: 12,
          transformPageContent,
          instructions: {
            system: systemInstructions,
            // Dynamic page instructions re-evaluated each step, so the agent
            // sees updated extractedFields even if they arrive after init.
            getPageInstructions: () => {
              if (!extractedFields || (typeof extractedFields === 'object' && Object.keys(extractedFields).length === 0)) return undefined;
              return `\nCurrent context fields (latest):\n${maskPII(typeof extractedFields === 'string' ? extractedFields : JSON.stringify(extractedFields, null, 2))}`;
            },
          },
        });
        if (cancelled) return;
        agentRef.current = agent;
        setStatus('idle');
        setStatusMessage(idleMessage);
      } catch (e) {
        if (cancelled) return;
        console.error(`[PageAgent:${pageName}] init failed:`, e);
        setAgentError(`Failed to initialize Page Agent: ${e?.message || e}`);
        setStatus('error');
      }
    }

    init();

    return () => {
      cancelled = true;
      // Dispose the agent instance on unmount to release DOM observers.
      try {
        if (agentRef.current && typeof agentRef.current.dispose === 'function') {
          agentRef.current.dispose();
        }
      } catch (e) {
        console.warn(`[PageAgent:${pageName}] dispose failed:`, e);
      }
      agentRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ---------------- Run an instruction ----------------
  const runInstruction = useCallback(async (text) => {
    const trimmed = (text || '').trim();
    if (!trimmed) return;
    const agent = agentRef.current;
    if (!agent) {
      setAgentError('Page Agent is not ready yet.');
      return;
    }
    setAgentError(null);
    setStatus('thinking');
    setStatusMessage('Agent is thinking…');
    setHistory((h) => [...h, { role: 'user', text: trimmed, ts: Date.now() }]);

    try {
      const actingTimer = setTimeout(() => {
        setStatus('acting');
        setStatusMessage('Agent is acting on the form…');
      }, 400);

      const result = await agent.execute(trimmed);
      clearTimeout(actingTimer);

      setStatus('done');
      setStatusMessage('Done.');
      const resultText =
        typeof result === 'string'
          ? result
          : result?.data || (result?.success === false ? 'Task failed.' : JSON.stringify(result || {}));
      setHistory((h) => [
        ...h,
        { role: 'assistant', text: resultText, ts: Date.now() },
      ]);
    } catch (e) {
      console.error(`[PageAgent:${pageName}] execute failed:`, e);
      setStatus('error');
      setStatusMessage('Agent error.');
      setAgentError(`Agent failed: ${e?.message || e}`);
      setHistory((h) => [
        ...h,
        { role: 'assistant', text: `⚠️ ${e?.message || e}`, ts: Date.now(), error: true },
      ]);
    }
  }, [pageName]);

  // ---------------- UI ----------------
  const handleSubmit = (e) => {
    e.preventDefault();
    if (!instruction.trim()) return;
    const text = instruction;
    setInstruction('');
    runInstruction(text);
  };

  const statusColor =
    status === 'error'
      ? '#dc2626'
      : status === 'acting' || status === 'thinking'
      ? '#2563eb'
      : status === 'done'
      ? '#16a34a'
      : '#64748b';

  return (
    <div
      data-testid="page-agent-assistant"
      style={{
        marginTop: '1.5rem',
        padding: '0.75rem 1rem',
        border: '1px solid #cbd5e1',
        borderRadius: '0.5rem',
        background: '#f8fafc',
        fontSize: '0.875rem',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.5rem' }}>
        <span
          data-testid="page-agent-status-dot"
          style={{
            display: 'inline-block',
            width: 8,
            height: 8,
            borderRadius: '50%',
            background: statusColor,
          }}
        />
        <strong style={{ color: '#0f172a' }}>Page Agent</strong>
        <span style={{ color: '#64748b' }}>— {statusMessage}</span>
      </div>

      {agentError && (
        <div
          data-testid="page-agent-error"
          style={{ color: '#dc2626', marginBottom: '0.5rem', fontSize: '0.8125rem' }}
        >
          {agentError}
        </div>
      )}

      {/* Conversation history */}
      {history.length > 0 && (
        <div
          data-testid="page-agent-history"
          style={{
            maxHeight: '180px',
            overflowY: 'auto',
            marginBottom: '0.5rem',
            padding: '0.25rem 0.5rem',
            background: '#fff',
            border: '1px solid #e2e8f0',
            borderRadius: '0.375rem',
          }}
        >
          {history.map((m, i) => (
            <div
              key={i}
              style={{
                marginBottom: '0.25rem',
                color: m.error ? '#dc2626' : m.role === 'user' ? '#1e3a8a' : '#0f172a',
              }}
            >
              <strong>{m.role === 'user' ? 'You' : 'Agent'}:</strong> {m.text}
            </div>
          ))}
        </div>
      )}

      {/* Instruction input */}
      <form onSubmit={handleSubmit} style={{ display: 'flex', gap: '0.5rem' }}>
        <input
          type="text"
          value={instruction}
          onChange={(e) => setInstruction(e.target.value)}
          placeholder={placeholder}
          data-testid="page-agent-instruction-input"
          disabled={status === 'thinking' || status === 'acting'}
          style={{
            flex: 1,
            padding: '0.5rem 0.75rem',
            border: '1px solid #cbd5e1',
            borderRadius: '0.375rem',
            fontSize: '0.875rem',
            background: '#fff',
          }}
        />
        <button
          type="submit"
          disabled={status === 'thinking' || status === 'acting' || !instruction.trim()}
          data-testid="page-agent-run-btn"
          style={{
            padding: '0.5rem 1rem',
            background: status === 'thinking' || status === 'acting' ? '#94a3b8' : '#1e3a8a',
            color: '#fff',
            border: 'none',
            borderRadius: '0.375rem',
            cursor: status === 'thinking' || status === 'acting' ? 'not-allowed' : 'pointer',
            fontSize: '0.875rem',
          }}
        >
          {status === 'thinking' || status === 'acting' ? 'Running…' : 'Run'}
        </button>
      </form>

      <p style={{ marginTop: '0.5rem', fontSize: '0.75rem', color: '#64748b' }}>
        {helpText}
      </p>
    </div>
  );
}