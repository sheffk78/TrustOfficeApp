import { Card, CardContent } from '@/components/ui/card';
import { AlertTriangle, X } from 'lucide-react';

/**
 * Dismissible banner listing missing critical documents from the vault summary.
 */
export default function CriticalDocumentsAlert({ missingCritical, onDismiss }) {
  if (!missingCritical || missingCritical.length === 0) return null;
  return (
    <Card className="mb-6 border-warning/20 bg-warning/5">
      <CardContent className="p-4">
        <div className="flex items-center gap-2 mb-2">
          <AlertTriangle className="w-5 h-5 text-warning" />
          <h3 className="font-semibold text-warning">Critical Documents Missing</h3>
          <button
            onClick={onDismiss}
            className="ml-auto p-1 text-warning/40 hover:text-warning transition-colors"
            title="Dismiss"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
        <ul className="text-sm text-warning space-y-1">
          {missingCritical.map((m, i) => (
            <li key={i} className="flex items-center gap-2">
              <span className="w-1.5 h-1.5 bg-warning rounded-full" />
              {m.label} · {m.message}
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  );
}
