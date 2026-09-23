// TrustAccessPanel.js — "Who has access" panel on trust settings (M3)
// Rendered only when TOGGLE_INSTITUTION is on.
import React from "react";

export default function TrustAccessPanel({ trustId }) {
  return (
    <div>
      <h2>Who has access</h2>
      <p>Stub: list org grants + party grants for trust {trustId} with revoke buttons.</p>
    </div>
  );
}
