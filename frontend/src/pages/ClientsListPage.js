import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { useAuth } from '@/context/AuthContext';
import { Sidebar } from '@/components/Sidebar';
import { MobileBottomNav } from '@/components/MobileBottomNav';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { fetchWithAuth } from '@/utils/api';
import PageHelpButton from '@/components/PageHelpButton';
import { toast } from 'sonner';
import { showError } from '../utils/errors';
import { format, parseISO } from 'date-fns';
import {
  Users,
  Mail,
  Phone,
  Shield,
  Plus,
  ChevronRight,
  RefreshCw,
  Save,
} from 'lucide-react';

export default function ClientsListPage() {
  const { user } = useAuth();
  const [clients, setClients] = useState([]);
  const [loading, setLoading] = useState(true);
  const [addOpen, setAddOpen] = useState(false);
  const [saving, setSaving] = useState(false);

  const [newClient, setNewClient] = useState({
    name: '',
    email: '',
    phone: '',
    address: '',
    notes: '',
  });

  useEffect(() => {
    loadClients();
  }, []);

  const loadClients = async () => {
    setLoading(true);
    try {
      const res = await fetchWithAuth('/clients');
      if (res.ok) {
        const data = await res.json();
        setClients(Array.isArray(data) ? data : data.clients || []);
      } else {
        const err = await res.json().catch(() => ({}));
        showError(toast, new Error(err.detail || 'Failed to load clients'), {
          operation: 'load_clients',
          page: 'ClientsList',
        });
      }
    } catch (error) {
      console.error('Failed to load clients:', error);
      showError(toast, error, { operation: 'load_clients', page: 'ClientsList' });
    } finally {
      setLoading(false);
    }
  };

  const handleAddClient = async () => {
    if (!newClient.name.trim()) {
      toast.error('Client name is required');
      return;
    }

    setSaving(true);
    try {
      const res = await fetchWithAuth('/clients', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(newClient),
      });

      if (res.ok) {
        toast.success('Client created successfully');
        setAddOpen(false);
        setNewClient({ name: '', email: '', phone: '', address: '', notes: '' });
        loadClients();
      } else {
        const err = await res.json().catch(() => ({}));
        showError(toast, new Error(err.detail || 'Failed to create client'), {
          operation: 'create_client',
          page: 'ClientsList',
        });
      }
    } catch (error) {
      showError(toast, error, { operation: 'create_client', page: 'ClientsList' });
    } finally {
      setSaving(false);
    }
  };

  const formatDate = (dateString) => {
    try {
      return format(parseISO(dateString), 'MMM d, yyyy');
    } catch {
      return dateString;
    }
  };

  return (
    <div className="main-layout" data-testid="clients-list-page">
      <Sidebar />
      <main className="main-content dot-grid">
        <div className="page-container">
          {/* Page Header */}
          <div className="page-header flex items-center justify-between">
            <div>
              <h1 className="page-title">Clients</h1>
              <p className="page-subtitle">
                Manage multi-trust clients — view health, deadlines, and meetings across all linked trusts
              </p>
            </div>
            <div className="flex items-center gap-2">
              <PageHelpButton
                items={[
                  { text: 'View all your multi-trust clients in one place' },
                  { text: 'Click a client card to see their full dashboard' },
                  { text: 'Add new clients and link trusts to them' },
                ]}
                taPrompt="Walk me through the Clients page and how to manage multi-trust clients"
              />
              <Button
                onClick={loadClients}
                variant="outline"
                className="btn-secondary"
                data-testid="refresh-btn"
              >
                <RefreshCw className="w-4 h-4 mr-2" />
                Refresh
              </Button>
              <Button
                onClick={() => setAddOpen(true)}
                className="btn-primary"
                data-testid="add-client-btn"
              >
                <Plus className="w-4 h-4 mr-2" />
                Add Client
              </Button>
            </div>
          </div>

          {loading ? (
            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
              {[1, 2, 3].map((i) => (
                <div key={i} className="card-trust">
                  <div className="skeleton h-36 w-full"></div>
                </div>
              ))}
            </div>
          ) : clients.length === 0 ? (
            <div className="card-trust text-center py-12">
              <Users className="w-12 h-12 text-navy/30 mx-auto mb-4" />
              <h2 className="font-serif text-xl text-navy mb-2">No clients yet</h2>
              <p className="text-sm text-muted-foreground mb-6 max-w-md mx-auto">
                Create your first client to start tracking multiple trusts, deadlines, and meetings in one place.
              </p>
              <Button onClick={() => setAddOpen(true)} className="btn-primary">
                <Plus className="w-4 h-4 mr-2" />
                Add Your First Client
              </Button>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
              {clients.map((client) => (
                <Link
                  key={client.client_id}
                  to={`/clients/${client.client_id}`}
                  className="block"
                >
                  <Card className="card-trust border border-border hover:border-navy/30 transition-colors cursor-pointer h-full">
                    <CardContent className="p-5">
                      <div className="flex items-start justify-between mb-3">
                        <div className="flex items-center gap-3 min-w-0">
                          <div className="w-10 h-10 rounded-lg bg-navy/5 flex items-center justify-center shrink-0">
                            <Users className="w-5 h-5 text-navy" />
                          </div>
                          <div className="min-w-0">
                            <h3 className="font-semibold text-navy text-sm truncate">
                              {client.name || 'Unnamed Client'}
                            </h3>
                            {client.email && (
                              <p className="text-xs text-muted-foreground truncate flex items-center mt-0.5">
                                <Mail className="w-3 h-3 mr-1 shrink-0" />
                                {client.email}
                              </p>
                            )}
                            {client.phone && (
                              <p className="text-xs text-muted-foreground flex items-center mt-0.5">
                                <Phone className="w-3 h-3 mr-1 shrink-0" />
                                {client.phone}
                              </p>
                            )}
                          </div>
                        </div>
                        <ChevronRight className="w-4 h-4 text-muted-foreground shrink-0 mt-1" />
                      </div>

                      <div className="flex items-center justify-between mt-4 pt-3 border-t border-border">
                        <div className="flex items-center gap-1.5">
                          <Shield className="w-3.5 h-3.5 text-navy/50" />
                          <span className="text-xs text-muted-foreground">
                            {client.trust_count ?? 0} trust{(client.trust_count ?? 0) === 1 ? '' : 's'}
                          </span>
                        </div>
                        {client.created_at && (
                          <span className="text-[10px] text-muted-foreground font-mono">
                            Added {formatDate(client.created_at)}
                          </span>
                        )}
                      </div>
                    </CardContent>
                  </Card>
                </Link>
              ))}
            </div>
          )}
        </div>
      </main>
      <MobileBottomNav />

      {/* Add Client Dialog */}
      <Dialog open={addOpen} onOpenChange={setAddOpen}>
        <DialogContent className="sm:max-w-[480px]">
          <DialogHeader>
            <DialogTitle>Add New Client</DialogTitle>
            <DialogDescription>
              Create a new client to link trusts and track health across their portfolio.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-2">
            <div>
              <Label htmlFor="add-name">Name *</Label>
              <Input
                id="add-name"
                value={newClient.name}
                onChange={(e) => setNewClient({ ...newClient, name: e.target.value })}
                placeholder="Client name"
              />
            </div>
            <div>
              <Label htmlFor="add-email">Email</Label>
              <Input
                id="add-email"
                type="email"
                value={newClient.email}
                onChange={(e) => setNewClient({ ...newClient, email: e.target.value })}
                placeholder="client@example.com"
              />
            </div>
            <div>
              <Label htmlFor="add-phone">Phone</Label>
              <Input
                id="add-phone"
                value={newClient.phone}
                onChange={(e) => setNewClient({ ...newClient, phone: e.target.value })}
                placeholder="(555) 123-4567"
              />
            </div>
            <div>
              <Label htmlFor="add-address">Address</Label>
              <Input
                id="add-address"
                value={newClient.address}
                onChange={(e) => setNewClient({ ...newClient, address: e.target.value })}
                placeholder="123 Main St, City, State ZIP"
              />
            </div>
            <div>
              <Label htmlFor="add-notes">Notes</Label>
              <Textarea
                id="add-notes"
                value={newClient.notes}
                onChange={(e) => setNewClient({ ...newClient, notes: e.target.value })}
                placeholder="Internal notes about this client"
                rows={3}
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setAddOpen(false)}>
              Cancel
            </Button>
            <Button onClick={handleAddClient} disabled={saving} className="btn-primary">
              <Save className="w-4 h-4 mr-1.5" />
              {saving ? 'Creating…' : 'Create Client'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
