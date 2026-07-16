/**
 * LegalTextRenderer.js
 *
 * Parses legal document text (WHEREAS clauses, RESOLVED clauses, section headers,
 * dividers, bullets, key-value pairs, signature blocks) and renders as structured
 * HTML instead of a raw <pre> text block.
 *
 * Port of backend _parse_legal_document_text() from minutes.py
 */

import React from 'react';

const DIVIDER_RE = /^[═─]{10,}$/;
const ALL_CAPS_RE = /^[A-Z\s,.&()\-/]{2,80}$/;

function renderLine(line, key) {
  const trimmed = line.trim();
  if (!trimmed) return null;

  // Section dividers (═══ or ─── lines)
  if (DIVIDER_RE.test(trimmed)) {
    return <hr key={key} className="border-t border-border my-4" />;
  }

  // Signature lines (underscores)
  if (/^_{10,}/.test(trimmed)) {
    return (
      <div key={key} className="mt-8 pt-4 border-t border-border">
        <div className="w-64 border-b border-foreground/40 mb-1" />
      </div>
    );
  }

  // VOTE lines
  if (/^VOTE:/i.test(trimmed)) {
    return (
      <p key={key} className="text-xs italic text-muted-foreground mt-1 mb-4 pl-4 font-mono">
        {trimmed}
      </p>
    );
  }

  // WHEREAS clauses
  if (/^WHEREAS/i.test(trimmed)) {
    const withoutWhereas = trimmed.replace(/^WHEREAS,?\s*/i, '');
    return (
      <p key={key} className="pl-4 border-l-2 border-navy/20 dark:border-gold/20 text-sm leading-relaxed mb-2 font-serif text-foreground">
        <span className="font-bold">WHEREAS</span>, {withoutWhereas}
      </p>
    );
  }

  // BE IT FURTHER RESOLVED
  if (/^BE IT FURTHER RESOLVED/i.test(trimmed)) {
    const rest = trimmed.replace(/^BE IT FURTHER RESOLVED,?\s*/i, '');
    return (
      <p key={key} className="pl-4 border-l-2 border-navy/30 dark:border-gold/30 text-sm leading-relaxed mb-2 font-serif text-foreground">
        <span className="font-bold">BE IT FURTHER RESOLVED</span>, {rest}
      </p>
    );
  }

  // BE IT RESOLVED
  if (/^BE IT RESOLVED/i.test(trimmed)) {
    const rest = trimmed.replace(/^BE IT RESOLVED,?\s*/i, '');
    return (
      <p key={key} className="pl-4 border-l-2 border-navy/30 dark:border-gold/30 text-sm leading-relaxed mb-2 font-serif text-foreground">
        <span className="font-bold">BE IT RESOLVED</span>, {rest}
      </p>
    );
  }

  // NOW THEREFORE
  if (/^NOW,?\s*THEREFORE/i.test(trimmed)) {
    return (
      <p key={key} className="pl-4 border-l-2 border-navy/30 dark:border-gold/30 text-sm leading-relaxed mb-2 font-serif text-foreground">
        <span className="font-bold">{trimmed.match(/^NOW,?\s*THEREFORE/i)[0]}</span>{trimmed.replace(/^NOW,?\s*THEREFORE/i, '')}
      </p>
    );
  }

  // RESOLVED (standalone)
  if (/^RESOLVED/i.test(trimmed)) {
    const rest = trimmed.replace(/^RESOLVED,?\s*/i, '');
    return (
      <p key={key} className="pl-4 border-l-2 border-navy/30 dark:border-gold/30 text-sm leading-relaxed mb-2 font-serif text-foreground">
        <span className="font-bold">RESOLVED</span>, {rest}
      </p>
    );
  }

  // All-caps section headers (not WHEREAS/RESOLVED, under 80 chars)
  if (ALL_CAPS_RE.test(trimmed) && !/^WHEREAS/i.test(trimmed) && !/^BE IT/i.test(trimmed) && !/^RESOLVED/i.test(trimmed) && trimmed.length < 80) {
    // Check if it looks like a section header (contains letters, not just symbols)
    if (/[A-Z]{3,}/.test(trimmed)) {
      return (
        <h3 key={key} className="font-serif font-bold text-navy dark:text-gold text-base mt-6 mb-2">
          {trimmed}
        </h3>
      );
    }
  }

  // Bullet points (starting with •, -, *)
  if (/^[•\-*]\s+/.test(trimmed)) {
    const bulletText = trimmed.replace(/^[•\-*]\s*/, '');
    return (
      <li key={key} className="text-sm font-serif text-foreground ml-6 list-disc mb-1">
        {bulletText}
      </li>
    );
  }

  // Indented bullet points (starting with spaces then bullet)
  if (/^\s+[•\-*]\s+/.test(line)) {
    const bulletText = line.trim().replace(/^[•\-*]\s*/, '');
    return (
      <li key={key} className="text-sm font-serif text-foreground ml-10 list-disc mb-1">
        {bulletText}
      </li>
    );
  }

  // Sub-items like (a), (b), (c)
  if (/^\([a-z]\)\s+/.test(trimmed)) {
    const match = trimmed.match(/^(\([a-z]\))\s+(.*)/);
    return (
      <p key={key} className="text-sm font-serif text-foreground ml-8 mb-1">
        <span className="font-mono font-semibold">{match[1]}</span> {match[2]}
      </p>
    );
  }

  // Key-value pairs (Label: Value where colon is within first 30 chars)
  const colonIdx = trimmed.indexOf(':');
  if (colonIdx > 0 && colonIdx < 30) {
    const label = trimmed.substring(0, colonIdx).trim();
    const value = trimmed.substring(colonIdx + 1).trim();
    // Make sure label looks like a label (not a sentence with a colon)
    if (label.length < 30 && /^[A-Z]/.test(label)) {
      return (
        <p key={key} className="text-sm leading-relaxed font-serif mb-2 text-foreground">
          <span className="font-bold">{label}:</span> {value}
        </p>
      );
    }
  }

  // Date lines under signature blocks
  if (/^Date:/i.test(trimmed)) {
    return (
      <p key={key} className="text-sm font-serif text-muted-foreground mt-1">
        {trimmed}
      </p>
    );
  }

  // Regular paragraph
  return (
    <p key={key} className="text-sm leading-relaxed font-serif mb-2 text-foreground">
      {trimmed}
    </p>
  );
}

export default function LegalTextRenderer({ text }) {
  if (!text || typeof text !== 'string') {
    return <p className="text-sm text-muted-foreground italic">No content recorded.</p>;
  }

  // Split by double newlines into paragraphs
  const paragraphs = text.split(/\n\s*\n/);
  const elements = [];
  let bulletGroup = [];
  let keyCounter = 0;

  const flushBullets = () => {
    if (bulletGroup.length > 0) {
      elements.push(
        <ul key={`ul-${keyCounter++}`} className="list-disc pl-4 mb-2">
          {bulletGroup}
        </ul>
      );
      bulletGroup = [];
    }
  };

  for (const para of paragraphs) {
    const trimmedPara = para.trim();
    if (!trimmedPara) continue;

    // Check for standalone section dividers
    if (DIVIDER_RE.test(trimmedPara)) {
      flushBullets();
      elements.push(<hr key={`hr-${keyCounter++}`} className="border-t border-border my-4" />);
      continue;
    }

    // Check for all-caps paragraph headers (like "FIRST ORGANIZATIONAL MEETING MINUTES")
    if (ALL_CAPS_RE.test(trimmedPara) && trimmedPara.length < 80 && /[A-Z]{3,}/.test(trimmedPara)) {
      flushBullets();
      elements.push(
        <h2 key={`h2-${keyCounter++}`} className="font-serif font-bold text-navy dark:text-gold text-lg mt-4 mb-2 text-center">
          {trimmedPara}
        </h2>
      );
      continue;
    }

    // Process each line in the paragraph
    const lines = para.split('\n');
    for (const line of lines) {
      const rendered = renderLine(line, `line-${keyCounter++}`);
      if (!rendered) continue;

      // Group bullet items into <ul> elements
      if (rendered.type === 'li') {
        bulletGroup.push(rendered);
      } else {
        flushBullets();
        elements.push(rendered);
      }
    }
  }
  flushBullets();

  return (
    <div className="font-serif space-y-0">
      {elements}
    </div>
  );
}