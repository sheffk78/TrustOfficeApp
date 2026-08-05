import {
  AlertTriangle, Check, Clock, Gift, XCircle,
} from 'lucide-react';

// Renders the small status pill shown next to the current plan name.
// Encapsulates the (formerly inline) switch over subscription.status,
// including canceling, gifted, free-access, expired, past_due, canceled.
//
// Props:
//   subscription – the subscription object (or null)
export default function StatusBadge({ subscription }) {
  if (!subscription) return null;

  const status = subscription.status;
  const cancelAtPeriodEnd = subscription.cancel_at_period_end;

  if (status === 'active' && cancelAtPeriodEnd) {
    return (
      <div className="flex items-center gap-2 px-3 py-1.5 bg-warning/10 text-warning border border-warning/20">
        <Clock className="w-4 h-4" />
        <span className="font-mono text-xs uppercase">Canceling</span>
      </div>
    );
  }

  switch (status) {
    case 'active':
      if (subscription?.is_gifted) {
        return (
          <div className="flex items-center gap-2 px-3 py-1.5 bg-gold/20 text-gold border border-gold/30">
            <Gift className="w-4 h-4" />
            <span className="font-mono text-xs uppercase">
              Gifted
            </span>
          </div>
        );
      }
      if (subscription?.plan_type === 'forever_free' || subscription?.plan_type === 'trial' || subscription?.plan_type === 'free') {
        return (
          <div className="flex items-center gap-2 px-3 py-1.5 bg-success/10 text-success border border-success/20">
            <Check className="w-4 h-4" />
            <span className="font-mono text-xs uppercase">
              Free Access
            </span>
          </div>
        );
      }
      return (
        <div className="flex items-center gap-2 px-3 py-1.5 bg-success/10 text-success border border-success/20">
          <Check className="w-4 h-4" />
          <span className="font-mono text-xs uppercase">Active</span>
        </div>
      );
    case 'trialing':
      if (subscription?.is_gifted) {
        return (
          <div className="flex items-center gap-2 px-3 py-1.5 bg-gold/20 text-gold border border-gold/30">
            <Gift className="w-4 h-4" />
            <span className="font-mono text-xs uppercase">
              Gifted
            </span>
          </div>
        );
      }
      return (
        <div className="flex items-center gap-2 px-3 py-1.5 bg-success/10 text-success border border-success/20">
          <Check className="w-4 h-4" />
          <span className="font-mono text-xs uppercase">
            Free Access
          </span>
        </div>
      );
    case 'expired':
      return (
        <div className="flex items-center gap-2 px-3 py-1.5 bg-error/10 text-error border border-error/20">
          <AlertTriangle className="w-4 h-4" />
          <span className="font-mono text-xs uppercase">Access Expired</span>
        </div>
      );
    case 'past_due':
      return (
        <div className="flex items-center gap-2 px-3 py-1.5 bg-warning/10 text-warning border border-warning/20">
          <AlertTriangle className="w-4 h-4" />
          <span className="font-mono text-xs uppercase">Payment Due</span>
        </div>
      );
    case 'canceled':
      return (
        <div className="flex items-center gap-2 px-3 py-1.5 bg-muted text-muted-foreground border border-border">
          <XCircle className="w-4 h-4" />
          <span className="font-mono text-xs uppercase">Canceled</span>
        </div>
      );
    default:
      return null;
  }
}