import { Search, RefreshCw, UserPlus, CheckSquare, ChevronLeft, ChevronRight, Eye, LogIn, Gift, Crown, BarChart3, Trash2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Checkbox } from '@/components/ui/checkbox';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Badge } from '@/components/ui/badge';
import { formatLastActive, getStatusBadgeClass } from './helpers';

export function CustomersTab({
  customers, customerTotal, customerPage, customerSearch, statusFilter,
  selectedCustomerIds,
  onSearchChange, onStatusFilterChange, onRefresh, onAddUser,
  onClearSelection, onBulkDelete, onSelectAll, onSelectCustomer,
  onViewCustomer, onImpersonate, onGrantAccess,
  onPrevPage, onNextPage,
}) {
  const selectableCount = customers.filter(c => !c.is_admin && c.email !== 'contact@trustoffice.app').length;
  const allSelected = selectableCount > 0 && selectedCustomerIds.size === selectableCount;

  return (
    <div className="card-trust">
      {/* Search and Filters */}
      <div className="flex flex-col md:flex-row gap-4 mb-6">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
          <Input
            placeholder="Search by email or name..."
            value={customerSearch}
            onChange={(e) => onSearchChange(e.target.value)}
            className="pl-10 input-trust"
          />
        </div>
        <Select value={statusFilter} onValueChange={onStatusFilterChange}>
          <SelectTrigger className="w-40 input-trust">
            <SelectValue placeholder="All Status" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All Status</SelectItem>
            <SelectItem value="active">Active</SelectItem>
            <SelectItem value="trialing">Trialing</SelectItem>
            <SelectItem value="expired">Expired</SelectItem>
            <SelectItem value="canceled">Canceled</SelectItem>
          </SelectContent>
        </Select>
        <Button onClick={onRefresh} variant="outline">
          <RefreshCw className="w-4 h-4" />
        </Button>
        <Button onClick={onAddUser} className="btn-primary">
          <UserPlus className="w-4 h-4 mr-2" />
          Add User
        </Button>
      </div>

      {/* Bulk Action Bar */}
      {selectedCustomerIds.size > 0 && (
        <div className="flex items-center justify-between p-3 mb-4 bg-navy/5 dark:bg-white/5 rounded border border-navy/10 dark:border-white/10">
          <div className="flex items-center gap-3">
            <CheckSquare className="w-5 h-5 text-navy dark:text-white" />
            <span className="font-medium text-navy dark:text-white">
              {selectedCustomerIds.size} account{selectedCustomerIds.size !== 1 ? 's' : ''} selected
            </span>
            <Button variant="ghost" size="sm" onClick={onClearSelection}>
              Clear
            </Button>
          </div>
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              className="text-red-500 hover:text-red-600 hover:bg-red-50 dark:hover:bg-red-900/20"
              onClick={onBulkDelete}
            >
              <Trash2 className="w-4 h-4 mr-2" />
              Delete Selected
            </Button>
          </div>
        </div>
      )}

      {/* Customer List */}
      <div className="overflow-x-auto">
        <table className="w-full">
          <thead>
            <tr className="border-b border-navy/10 dark:border-white/10">
              <th className="w-12 py-3 px-4">
                <Checkbox
                  checked={allSelected}
                  onCheckedChange={onSelectAll}
                  aria-label="Select all"
                />
              </th>
              <th className="text-left py-3 px-4 text-sm font-medium text-muted-foreground">User</th>
              <th className="text-left py-3 px-4 text-sm font-medium text-muted-foreground">Status</th>
              <th className="text-left py-3 px-4 text-sm font-medium text-muted-foreground">Plan</th>
              <th className="text-left py-3 px-4 text-sm font-medium text-muted-foreground">Trusts</th>
              <th className="text-left py-3 px-4 text-sm font-medium text-muted-foreground">Joined</th>
              <th className="text-left py-3 px-4 text-sm font-medium text-muted-foreground">Last Active</th>
              <th className="text-right py-3 px-4 text-sm font-medium text-muted-foreground">Actions</th>
            </tr>
          </thead>
          <tbody>
            {customers.map((customer) => {
              const isSelectable = !customer.is_admin && customer.email !== 'contact@trustoffice.app';
              const isSelected = selectedCustomerIds.has(customer.user_id);

              return (
              <tr
                key={customer.user_id}
                className={`border-b border-navy/5 dark:border-white/5 hover:bg-navy/5 dark:hover:bg-white/5 ${isSelected ? 'bg-navy/10 dark:bg-white/10' : ''}`}
              >
                <td className="py-3 px-4">
                  {isSelectable ? (
                    <Checkbox
                      checked={isSelected}
                      onCheckedChange={() => onSelectCustomer(customer.user_id)}
                      aria-label={`Select ${customer.name}`}
                    />
                  ) : (
                    <div className="w-4 h-4" />
                  )}
                </td>
                <td className="py-3 px-4">
                  <div>
                    <p className="font-medium text-navy dark:text-white flex items-center gap-2">
                      {customer.name}
                      {customer.is_admin && (
                        <Crown className="w-4 h-4 text-gold" />
                      )}
                      {customer.is_stats_user && !customer.is_admin && (
                        <BarChart3 className="w-4 h-4 text-gold" />
                      )}
                    </p>
                    <p className="text-sm text-muted-foreground">{customer.email}</p>
                  </div>
                </td>
                <td className="py-3 px-4">
                  <Badge className={getStatusBadgeClass(customer.subscription_status)}>
                    {customer.subscription_status}
                  </Badge>
                </td>
                <td className="py-3 px-4 text-sm text-muted-foreground">
                  {customer.subscription_plan}
                </td>
                <td className="py-3 px-4 text-sm text-muted-foreground">
                  {customer.trust_count}
                </td>
                <td className="py-3 px-4 text-sm text-muted-foreground">
                  {customer.created_at ? new Date(customer.created_at).toLocaleDateString() : '—'}
                </td>
                <td className="py-3 px-4 text-sm text-muted-foreground">
                  {formatLastActive(customer.last_login)}
                </td>
                <td className="py-3 px-4 text-right">
                  <div className="flex items-center justify-end gap-2">
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => onViewCustomer(customer)}
                    >
                      <Eye className="w-4 h-4" />
                    </Button>
                    {!customer.is_admin && (
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => onImpersonate(customer)}
                        title="Login as this user"
                        className="text-orange-500 hover:text-orange-600 hover:bg-orange-50 dark:hover:bg-orange-900/20"
                      >
                        <LogIn className="w-4 h-4" />
                      </Button>
                    )}
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => onGrantAccess(customer)}
                    >
                      <Gift className="w-4 h-4" />
                    </Button>
                  </div>
                </td>
              </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      <div className="flex items-center justify-between mt-4 pt-4 border-t border-navy/10 dark:border-white/10">
        <p className="text-sm text-muted-foreground">
          Showing {customers.length} of {customerTotal} customers
        </p>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => onPrevPage()}
            disabled={customerPage === 1}
          >
            <ChevronLeft className="w-4 h-4" />
          </Button>
          <span className="text-sm text-muted-foreground">Page {customerPage}</span>
          <Button
            variant="outline"
            size="sm"
            onClick={() => onNextPage()}
            disabled={customers.length < 20}
          >
            <ChevronRight className="w-4 h-4" />
          </Button>
        </div>
      </div>
    </div>
  );
}
