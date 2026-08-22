import { Crown, BarChart3, UserPlus, XCircle } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';

export function AdminsTab({ admins, statsUsers, onAddAdmin, onRemoveAdmin, onRevokeStats }) {
  return (
    <>
      <div className="card-trust">
        <div className="flex flex-wrap items-center justify-between gap-3 mb-6">
          <h2 className="font-serif text-xl text-navy dark:text-white">Administrator Accounts</h2>
          <Button className="btn-primary" onClick={onAddAdmin}>
            <UserPlus className="w-4 h-4 mr-2" />
            Add Admin
          </Button>
        </div>

        <div className="space-y-4">
          {admins.map((admin) => (
            <div key={admin.user_id} className="flex flex-wrap items-center justify-between gap-3 p-4 border border-navy/10 dark:border-white/10 rounded">
              <div className="flex items-center gap-4 min-w-0">
                <div className="w-10 h-10 rounded-full bg-gold/20 flex items-center justify-center">
                  <Crown className="w-5 h-5 text-gold" />
                </div>
                <div>
                  <p className="font-medium text-navy dark:text-white">{admin.name}</p>
                  <p className="text-sm text-muted-foreground">{admin.email}</p>
                </div>
              </div>
              <div className="flex items-center gap-2">
                {admin.email !== 'contact@trustoffice.app' && (
                  <Button
                    variant="ghost"
                    size="sm"
                    className="text-red-500 hover:text-red-600 hover:bg-red-50"
                    onClick={() => onRemoveAdmin(admin.user_id)}
                  >
                    <XCircle className="w-4 h-4 mr-2" />
                    Remove
                  </Button>
                )}
                {admin.email === 'contact@trustoffice.app' && (
                  <Badge className="bg-gold/20 text-gold">Primary Admin</Badge>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Stats Users Section */}
      <div className="card-trust mt-6">
        <div className="flex items-center justify-between mb-6">
          <h2 className="font-serif text-xl text-navy dark:text-white flex items-center gap-2">
            <BarChart3 className="w-5 h-5 text-gold" />
            Stats Users
          </h2>
          <p className="text-sm text-muted-foreground">Users with read-only revenue dashboard access</p>
        </div>

        {statsUsers.length === 0 ? (
          <p className="text-center text-muted-foreground py-8">No stats users configured. Grant stats access from the customer detail view.</p>
        ) : (
          <div className="space-y-4">
            {statsUsers.map((su) => (
              <div key={su.user_id} className="flex flex-wrap items-center justify-between gap-3 p-4 border border-navy/10 dark:border-white/10 rounded">
                <div className="flex items-center gap-4 min-w-0">
                  <div className="w-10 h-10 rounded-full bg-gold/20 flex items-center justify-center">
                    <BarChart3 className="w-5 h-5 text-gold" />
                  </div>
                  <div>
                    <p className="font-medium text-navy dark:text-white">
                      {su.name}
                      {su.is_admin && <Crown className="w-4 h-4 text-gold ml-2 inline" />}
                    </p>
                    <p className="text-sm text-muted-foreground">{su.email}</p>
                    {su.stats_granted_at && (
                      <p className="text-xs text-muted-foreground">Granted: {new Date(su.stats_granted_at).toLocaleDateString()}</p>
                    )}
                  </div>
                </div>
                <Button
                  variant="ghost"
                  size="sm"
                  className="text-red-500 hover:text-red-600 hover:bg-red-50"
                  onClick={() => onRevokeStats(su.user_id)}
                >
                  <XCircle className="w-4 h-4 mr-2" />
                  Revoke Stats
                </Button>
              </div>
            ))}
          </div>
        )}
      </div>
    </>
  );
}
