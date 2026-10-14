import React from 'react';

/**
 * Spinner — the one canonical loading spinner.
 *
 * CSS border spinner (matches the app's animate-spin idiom): navy ring on
 * navy/20 track, sharp environment aside. Data-heavy sections use skeletons
 * instead. Pages must not import Loader2 or hand-roll spinners.
 *
 * Props:
 *   size  — px, default 32
 *   label — aria label, default 'Loading'
 *   className — extra classes on the wrapper
 */
const Spinner = ({ size = 32, label = 'Loading', className = '' }) => (
  <div
    role="status"
    aria-label={label}
    aria-busy="true"
    className={`inline-block animate-spin rounded-full border-2 border-navy/20 border-t-navy ${className}`}
    style={{ width: size, height: size }}
  />
);

export default Spinner;