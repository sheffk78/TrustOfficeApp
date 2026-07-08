import { useState, useEffect, useRef, useCallback } from 'react';

const API_URL = process.env.REACT_APP_BACKEND_URL || 'https://api.trustoffice.app';

/**
 * useAnalysisPolling - polls the TrustOffice backend for AI document analysis status.
 *
 * @param {string} trustId - the trust ID to poll analysis status for
 * @param {object} options - configuration options
 * @param {boolean} options.enabled - whether polling is enabled (default true)
 * @param {number} options.intervalMs - milliseconds between polls (default 3000)
 * @param {number} options.maxAttempts - max poll attempts before giving up (default 60, i.e. 3 min at 3s)
 * @param {function} options.onComplete - called with extracted_fields when analysis completes
 * @param {function} options.onError - called with error_message when analysis fails
 *
 * @returns {object} { status, extractedFields, error, isPolling, start, stop, reset }
 */
export function useAnalysisPolling(trustId, options = {}) {
  const {
    enabled = true,
    intervalMs = 3000,
    maxAttempts = 60,
    onComplete,
    onError,
  } = options;

  const [status, setStatus] = useState('none');
  const [extractedFields, setExtractedFields] = useState(null);
  const [error, setError] = useState(null);
  const [isPolling, setIsPolling] = useState(false);

  // Refs to hold mutable state across the polling lifecycle without re-creating callbacks
  const intervalRef = useRef(null);
  const attemptCountRef = useRef(0);
  const shouldStopRef = useRef(false);

  // Keep latest callbacks in refs so the polling loop always calls the current version
  // without needing to tear down and recreate the interval on every render
  const onCompleteRef = useRef(onComplete);
  const onErrorRef = useRef(onError);

  // Keep latest trustId in a ref so start() can use the current value even if
  // the caller passes a trustId that was set in the same render cycle (before
  // the hook re-renders with the new prop).
  const trustIdRef = useRef(trustId);

  useEffect(() => {
    trustIdRef.current = trustId;
  }, [trustId]);

  useEffect(() => {
    onCompleteRef.current = onComplete;
  }, [onComplete]);

  useEffect(() => {
    onErrorRef.current = onError;
  }, [onError]);

  /**
   * Performs a single poll request to the analysis-status endpoint.
   * Uses XMLHttpRequest for maximum mobile compatibility (matches OnboardingPage.js).
   */
  const pollOnce = useCallback(() => {
    const tid = trustIdRef.current;
    if (!tid) {
      return;
    }

    const token = localStorage.getItem('auth_token');
    const url = `${API_URL}/api/trusts/${tid}/vault/analysis-status`;

    const xhr = new XMLHttpRequest();
    xhr.open('GET', url, true);
    xhr.setRequestHeader('Content-Type', 'application/json');

    if (token) {
      xhr.setRequestHeader('Authorization', `Bearer ${token}`);
    }

    xhr.onreadystatechange = function () {
      if (xhr.readyState !== 4) {
        return;
      }

      // Network error or aborted request
      if (xhr.status === 0) {
        if (!shouldStopRef.current) {
          setError('Network error: unable to reach the server.');
        }
        return;
      }

      // 401 - session expired
      if (xhr.status === 401) {
        if (!shouldStopRef.current) {
          setError('Your session has expired. Please log in again.');
          stopPolling();
        }
        return;
      }

      // Non-OK status - treat as a network/server error but keep polling
      if (xhr.status < 200 || xhr.status >= 300) {
        if (!shouldStopRef.current) {
          setError(`Server returned status ${xhr.status}.`);
        }
        return;
      }

      // Clear any transient error on a successful response
      setError(null);

      let parsed;
      try {
        parsed = JSON.parse(xhr.responseText);
      } catch (e) {
        if (!shouldStopRef.current) {
          setError('Failed to parse server response.');
        }
        return;
      }

      const analysisStatus = parsed.analysis_status || 'none';

      if (!shouldStopRef.current) {
        setStatus(analysisStatus);

        if (parsed.extracted_fields) {
          setExtractedFields(parsed.extracted_fields);
        }

        if (parsed.error_message) {
          setError(parsed.error_message);
        }
      }

      if (analysisStatus === 'complete') {
        if (!shouldStopRef.current) {
          stopPolling();
        }
        if (onCompleteRef.current && parsed.extracted_fields) {
          onCompleteRef.current(parsed.extracted_fields);
        }
        return;
      }

      if (analysisStatus === 'failed') {
        if (!shouldStopRef.current) {
          stopPolling();
        }
        if (onErrorRef.current) {
          onErrorRef.current(parsed.error_message || 'Analysis failed.');
        }
        return;
      }
    };

    xhr.onerror = function () {
      if (!shouldStopRef.current) {
        setError('Network error: unable to reach the server.');
      }
    };

    xhr.ontimeout = function () {
      if (!shouldStopRef.current) {
        setError('Request timed out.');
      }
    };

    xhr.timeout = 15000;
    xhr.send();
  }, [stopPolling]);

  /**
   * Stops the polling interval and resets polling flags.
   */
  const stopPolling = useCallback(() => {
    shouldStopRef.current = true;
    if (intervalRef.current) {
      clearInterval(intervalRef.current);
      intervalRef.current = null;
    }
    setIsPolling(false);
  }, []);

  /**
   * Starts polling. Does nothing if already polling, disabled, or no trustId.
   */
  const start = useCallback(() => {
    if (!enabled) {
      return;
    }
    if (!trustIdRef.current) {
      return;
    }
    if (intervalRef.current) {
      return; // already polling
    }

    shouldStopRef.current = false;
    attemptCountRef.current = 0;
    setError(null);
    setIsPolling(true);

    // Fire an immediate poll, then set up the interval
    pollOnce();

    let attempt = 0;
    intervalRef.current = setInterval(() => {
      if (shouldStopRef.current) {
        stopPolling();
        return;
      }

      attempt += 1;
      attemptCountRef.current = attempt;

      if (attempt >= maxAttempts) {
        if (!shouldStopRef.current) {
          setError('Analysis is taking longer than expected. Please check back shortly.');
          stopPolling();
        }
        return;
      }

      pollOnce();
    }, intervalMs);
  }, [enabled, intervalMs, maxAttempts, pollOnce, stopPolling]);

  /**
   * Stops polling immediately.
   */
  const stop = useCallback(() => {
    stopPolling();
  }, [stopPolling]);

  /**
   * Stops polling and clears all state back to initial values.
   */
  const reset = useCallback(() => {
    stopPolling();
    setStatus('none');
    setExtractedFields(null);
    setError(null);
    attemptCountRef.current = 0;
  }, [stopPolling]);

  // Cleanup interval on unmount
  useEffect(() => {
    return () => {
      shouldStopRef.current = true;
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
    };
  }, []);

  return {
    status,
    extractedFields,
    error,
    isPolling,
    start,
    stop,
    reset,
  };
}