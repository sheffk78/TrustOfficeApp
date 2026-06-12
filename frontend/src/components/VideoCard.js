import React from 'react';
import { Play, Clock } from 'lucide-react';

const VideoCard = ({ card, onClick }) => {
  return (
    <div
      className="action-card card-trust cursor-pointer hover:border-gold/40 transition-colors relative group"
      onClick={() => onClick?.(card)}
    >
      <div className="corner-mark" />

      <div className="flex items-start gap-3">
        {/* Play icon */}
        <div className="flex-shrink-0 w-10 h-10 bg-navy/5 border border-navy/10 flex items-center justify-center group-hover:bg-gold/10 group-hover:border-gold/30 transition-colors">
          <Play className="w-4 h-4 text-navy group-hover:text-gold transition-colors" />
        </div>

        <div className="flex-1 min-w-0">
          {/* Title */}
          {card.title && (
            <p className="font-serif font-semibold text-sm text-foreground truncate">{card.title}</p>
          )}

          {/* Module & duration badges */}
          <div className="flex items-center gap-2 mt-1">
            {card.module_number && (
              <span className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground border border-navy/10 px-1.5 py-0.5">
                Module {card.module_number}
              </span>
            )}
            {card.duration && (
              <span className="inline-flex items-center gap-1 font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
                <Clock className="w-3 h-3" />
                {card.duration}
              </span>
            )}
          </div>

          {/* Description */}
          {card.description && (
            <p className="font-mono text-xs text-muted-foreground mt-2 line-clamp-2">{card.description}</p>
          )}
        </div>
      </div>
    </div>
  );
};

export default VideoCard;