import React from 'react';
import { Popover, PopoverTrigger, PopoverContent } from '@/components/ui/popover';
import { Info } from 'lucide-react';

/**
 * InfoTooltip — inline info icon with popover text.
 *
 * Props:
 *   text: string — the explanation shown when the icon is clicked/hovered
 *   label: string (optional) — the term being defined, rendered before the icon
 *
 * Usage:
 *   <InfoTooltip label="UTC Adoption" text="The Uniform Trust Code..." />
 *   <InfoTooltip text="A spendthrift clause prevents..." />
 */
const InfoTooltip = ({ text, label }) => (
  <>
    {label && <span>{label}</span>}
    <Popover>
      <PopoverTrigger asChild>
        <button
          type="button"
          className="inline-flex items-center ml-1 text-navy/40 hover:text-navy"
          aria-label="More information"
        >
          <Info className="w-3.5 h-3.5" />
        </button>
      </PopoverTrigger>
      <PopoverContent className="w-64 p-3 text-sm text-muted-foreground">
        {text}
      </PopoverContent>
    </Popover>
  </>
);

export default InfoTooltip;