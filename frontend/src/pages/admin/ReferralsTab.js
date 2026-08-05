import { RefreshCw, Link2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';

export function ReferralsTab({ referrals, referralsLoading, onRefresh, onFixReferral }) {
  return (
    <div className="card-trust">
      <div className="flex items-center justify-between mb-6">
        <h2 className="font-serif text-xl text-navy dark:text-white">Referral Relationships</h2>
        <div className="flex gap-2">
          <Button variant="outline" onClick={onRefresh}>
            <RefreshCw className={`w-4 h-4 ${referralsLoading ? 'animate-spin' : ''}`} />
          </Button>
          <Button className="btn-primary" onClick={onFixReferral}>
            <Link2 className="w-4 h-4 mr-2" />
            Fix Referral
          </Button>
        </div>
      </div>

      {referrals.length === 0 ? (
        <p className="text-center text-muted-foreground py-8">No referrals found</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="border-b border-navy/10 dark:border-white/10">
                <th className="text-left py-3 px-4 text-sm font-medium text-muted-foreground">Referrer</th>
                <th className="text-left py-3 px-4 text-sm font-medium text-muted-foreground">Referee</th>
                <th className="text-left py-3 px-4 text-sm font-medium text-muted-foreground">Status</th>
                <th className="text-left py-3 px-4 text-sm font-medium text-muted-foreground">Created</th>
              </tr>
            </thead>
            <tbody>
              {referrals.map((ref) => (
                <tr key={ref.referral_id || ref.referee_user_id} className="border-b border-navy/5 dark:border-white/5">
                  <td className="py-3 px-4">
                    <p className="font-medium text-navy dark:text-white">{ref.referrer_name}</p>
                    <p className="text-sm text-muted-foreground">{ref.referrer_email}</p>
                  </td>
                  <td className="py-3 px-4">
                    <p className="font-medium text-navy dark:text-white">{ref.referee_name}</p>
                    <p className="text-sm text-muted-foreground">{ref.referee_email}</p>
                  </td>
                  <td className="py-3 px-4">
                    <Badge className={ref.status === 'converted' ? 'bg-success/10 text-success' : 'bg-warning/10 text-warning'}>
                      {ref.status}
                    </Badge>
                  </td>
                  <td className="py-3 px-4 text-sm text-muted-foreground">
                    {ref.created_at ? new Date(ref.created_at).toLocaleDateString() : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
