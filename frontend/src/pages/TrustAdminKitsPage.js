import { useState, useEffect, useCallback } from 'react';
import { Link } from 'react-router-dom';
import { useAuth } from '@/context/AuthContext';
import { Sidebar } from '@/components/Sidebar';
import { MobileBottomNav } from '@/components/MobileBottomNav';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { fetchWithAuth } from '@/utils/api';
import { toast } from 'sonner';
import { showError } from '../utils/errors';
import {
  Car, Building, Home, FileText, Shield, Briefcase,
  ArrowLeft, Trash2, Download, CheckCircle2, AlertCircle,
  Loader2, FilePen, MapPin, Calendar, DollarSign, Clock,
  FolderOpen, ChevronRight, Printer
} from 'lucide-react';

// Icon map for kit types
const KIT_ICONS = {
  Car, Building, Home, FileText, Shield, Briefcase
};

export default function TrustAdminKitsPage() {
  const { user, trusts, selectedTrust } = useAuth();
  const trustId = selectedTrust?.trust_id;

  // View state: 'select' | 'preview' | 'detail'
  const [view, setView] = useState('select');
  const [kitTypes, setKitTypes] = useState([]);
  const [selectedKitType, setSelectedKitType] = useState(null);
  const [previewData, setPreviewData] = useState(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [formInputs, setFormInputs] = useState({});
  const [generating, setGenerating] = useState(false);
  const [currentKit, setCurrentKit] = useState(null);
  const [existingKits, setExistingKits] = useState([]);
  const [kitsLoading, setKitsLoading] = useState(true);
  const [viewKitLoading, setViewKitLoading] = useState(false);

  // Load kit types on mount
  useEffect(() => {
    fetchWithAuth(`/trust-admin-kits/types`)
      .then(res => res.json())
      .then(data => { setKitTypes(data.kit_types || []); })
      .catch(err => { console.error('Failed to load kit types', err); });
  }, []);

  // Load existing kits when trust changes
  const loadKits = useCallback(() => {
    if (!trustId) return;
    setKitsLoading(true);
    fetchWithAuth(`/trust-admin-kits?trust_id=${trustId}`)
      .then(res => res.json())
      .then(data => { setExistingKits(data.kits || []); })
      .catch(err => { console.error('Failed to load kits', err); })
      .finally(() => setKitsLoading(false));
  }, [trustId]);

  useEffect(() => { loadKits(); }, [loadKits]);

  // Select a kit type and load preview
  const selectKitType = async (kitType) => {
    if (!trustId) {
      toast.error('Please select a trust first.');
      return;
    }
    setSelectedKitType(kitType);
    setView('preview');
    setPreviewLoading(true);
    setPreviewData(null);
    setFormInputs({});
    try {
      const res = await fetchWithAuth(
        `/trust-admin-kits/preview/${kitType}?trust_id=${trustId}`
      );
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || 'Failed to load preview');
      }
      const data = await res.json();
      setPreviewData(data);
      // Pre-fill default_from fields
      const initialInputs = {};
      Object.entries(data.user_needs_to_provide || {}).forEach(([key, spec]) => {
        if (spec.default) initialInputs[key] = spec.default;
      });
      setFormInputs(initialInputs);
    } catch (err) {
      showError(toast, err, { operation: 'load_kit_preview', page: 'TrustAdminKits' });
      setView('select');
    } finally {
      setPreviewLoading(false);
    }
  };

  const updateInput = (key, value) => {
    setFormInputs(prev => ({ ...prev, [key]: value }));
  };

  // Check if all required fields are filled
  const requiredFieldsFilled = () => {
    if (!previewData) return false;
    const fields = previewData.user_needs_to_provide || {};
    return Object.entries(fields).every(([key, spec]) => {
      if (!spec.required) return true;
      return formInputs[key] && formInputs[key].trim() !== '';
    });
  };

  // Generate the kit
  const generateKit = async () => {
    if (!selectedKitType || !trustId) return;
    setGenerating(true);
    try {
      const res = await fetchWithAuth(`/trust-admin-kits/generate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          kit_type: selectedKitType,
          trust_id: trustId,
          user_inputs: formInputs,
        }),
      });
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || 'Generation failed');
      }
      const kit = await res.json();
      setCurrentKit(kit);
      setView('detail');
      toast.success('Kit generated successfully');
      loadKits();
    } catch (err) {
      showError(toast, err, { operation: 'generate_kit', page: 'TrustAdminKits' });
    } finally {
      setGenerating(false);
    }
  };

  // View an existing kit
  const viewKit = async (kitId) => {
    setViewKitLoading(true);
    try {
      const res = await fetchWithAuth(`/trust-admin-kits/${kitId}`);
      if (!res.ok) throw new Error('Failed to load kit');
      const kit = await res.json();
      setCurrentKit(kit);
      setView('detail');
    } catch (err) {
      showError(toast, err, { operation: 'view_kit', page: 'TrustAdminKits' });
    } finally {
      setViewKitLoading(false);
    }
  };

  // Delete a kit
  const deleteKit = async (kitId) => {
    if (!window.confirm('Delete this kit?')) return;
    try {
      const res = await fetchWithAuth(`/trust-admin-kits/${kitId}`, {
        method: 'DELETE',
      });
      if (!res.ok) {
        const errBody = await res.json().catch(() => ({}));
        throw new Error(errBody.detail || 'Failed to delete');
      }
      toast.success('Kit deleted');
      loadKits();
    } catch (err) {
      showError(toast, err, { operation: 'delete_kit', page: 'TrustAdminKits' });
    }
  };

  // Print kit
  const printKit = () => {
    window.print();
  };

  const backToSelect = () => {
    setView('select');
    setSelectedKitType(null);
    setPreviewData(null);
    setFormInputs({});
    setCurrentKit(null);
  };

  // ==================== RENDER: KIT TYPE SELECTION ====================
  const renderSelectView = () => (
    <>
      <div className="page-header flex items-center justify-between">
        <div>
          <h1 className="page-title">Administration Kits</h1>
          <p className="page-subtitle">Generate ready-to-go paperwork packets for DMV visits, bank account setup, tax prep, and more</p>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 mt-6">
        {kitTypes.map(kt => {
          const Icon = KIT_ICONS[kt.icon] || FileText;
          return (
            <Card
              key={kt.kit_type}
              className="cursor-pointer hover:shadow-lg hover:border-gold/40 transition-all group"
              onClick={() => selectKitType(kt.kit_type)}
            >
              <CardContent className="p-5">
                <div className="flex items-start gap-3">
                  <div className="p-2.5 bg-gold/10 text-gold">
                    <Icon className="w-6 h-6" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <h3 className="font-semibold text-sm mb-1 group-hover:text-gold transition-colors">
                      {kt.label}
                    </h3>
                    <p className="text-xs text-muted-foreground leading-relaxed">{kt.description}</p>
                  </div>
                </div>
                <div className="mt-3 flex items-center justify-end">
                  <span className="text-xs font-medium text-gold flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                    Generate Kit <ChevronRight className="w-3 h-3" />
                  </span>
                </div>
              </CardContent>
            </Card>
          );
        })}
      </div>

      {/* Existing Kits */}
      {kitsLoading ? (
        <div className="mt-8 animate-pulse space-y-3">
          <div className="h-5 w-48 bg-muted rounded" />
          <div className="h-16 bg-muted " />
          <div className="h-16 bg-muted " />
        </div>
      ) : existingKits.length > 0 ? (
        <div className="mt-8">
          <h2 className="text-lg font-semibold mb-4">Your Generated Kits</h2>
          {viewKitLoading && (
            <div className="mb-3 flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="w-4 h-4 animate-spin" /> Loading kit…
            </div>
          )}
          {existingKits.map(kit => {
            const Icon = KIT_ICONS[kitTypes.find(k => k.kit_type === kit.kit_type)?.icon] || FileText;
            return (
              <Card
                key={kit.kit_id}
                className="mb-3 cursor-pointer hover:shadow-md transition-shadow"
                onClick={() => viewKit(kit.kit_id)}
              >
                <CardContent className="flex items-center justify-between p-4">
                  <div className="flex items-center gap-3">
                    <div className="p-2 bg-muted">
                      <Icon className="w-4 h-4 text-muted-foreground" />
                    </div>
                    <div>
                      <p className="font-medium text-sm">{kit.kit_title}</p>
                      <p className="text-xs text-muted-foreground">
                        {new Date(kit.created_at).toLocaleDateString()}
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <Badge variant="outline">{kit.status}</Badge>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={(e) => { e.stopPropagation(); deleteKit(kit.kit_id); }}
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>
      ) : (
        !kitsLoading && existingKits.length === 0 && (
          <div className="mt-8 text-center py-8 text-muted-foreground">
            <FilePen className="w-8 h-8 mx-auto mb-2 opacity-40" />
            <p className="text-sm">No kits generated yet. Pick a kit type above to get started.</p>
          </div>
        )
      )}
    </>
  );

  // ==================== RENDER: PREVIEW & INPUT VIEW ====================
  const renderPreviewView = () => {
    const kitType = kitTypes.find(k => k.kit_type === selectedKitType);
    const Icon = KIT_ICONS[kitType?.icon] || FileText;

    return (
      <>
        <div className="page-header flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Button variant="ghost" size="sm" onClick={backToSelect}>
              <ArrowLeft className="w-4 h-4 mr-1" /> Back
            </Button>
            <div>
              <h1 className="page-title">{kitType?.label || 'Kit'}</h1>
              <p className="page-subtitle">{kitType?.description}</p>
            </div>
          </div>
        </div>

        {previewLoading ? (
          <div className="flex flex-col items-center justify-center py-20 gap-3">
            <Loader2 className="w-8 h-8 animate-spin text-gold" />
            <p className="text-sm text-muted-foreground">Reading your trust profile...</p>
          </div>
        ) : !previewData ? (
          <div className="flex flex-col items-center justify-center py-20 gap-3">
            <AlertCircle className="w-8 h-8 text-destructive" />
            <p className="text-sm text-muted-foreground">Failed to load preview. Please try again.</p>
            <Button variant="outline" size="sm" onClick={() => selectKitType(selectedKitType)}>Retry</Button>
          </div>
        ) : (
          <div className="max-w-2xl mx-auto mt-6 space-y-6">
            {/* What we already know */}
            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="text-base flex items-center gap-2">
                  <CheckCircle2 className="w-5 h-5 text-success" />
                  What We Already Know
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-2">
                {[
                  ['Trust Name', previewData.auto_gathered?.trust_name],
                  ['Trustee', previewData.auto_gathered?.trustee_name],
                  ['EIN', previewData.auto_gathered?.ein],
                  ['State', previewData.auto_gathered?.state_code],
                  ['Formation Date', previewData.auto_gathered?.formation_date?.split('T')[0]],
                  ['Trust Type', previewData.auto_gathered?.trust_type],
                ].filter(([, v]) => v).map(([label, value]) => (
                  <div key={label} className="flex items-center justify-between text-sm py-1.5 border-b border-border/50 last:border-0">
                    <span className="text-muted-foreground">{label}</span>
                    <span className="font-medium">{value}</span>
                  </div>
                ))}
                {/* Vault docs */}
                {previewData.auto_gathered?.vault_docs?.length > 0 && (
                  <div className="pt-3">
                    <p className="text-xs font-medium text-muted-foreground mb-2 flex items-center gap-1">
                      <FolderOpen className="w-3.5 h-3.5" /> Documents in Your Vault
                    </p>
                    {previewData.auto_gathered.vault_docs.map(doc => (
                      <div key={doc.doc_id} className="flex items-center gap-2 text-xs py-1">
                        <CheckCircle2 className="w-3.5 h-3.5 text-success shrink-0" />
                        <span className="truncate">{doc.title || doc.file_name}</span>
                        <Badge variant="outline" className="text-[10px] py-0 px-1.5">{doc.category}</Badge>
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>

            {/* What we need from you */}
            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="text-base flex items-center gap-2">
                  <FilePen className="w-5 h-5 text-gold" />
                  What We Need From You
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                {Object.entries(previewData.user_needs_to_provide || {}).length === 0 ? (
                  <p className="text-sm text-muted-foreground">
                    Everything needed is already in your trust profile. Click generate below.
                  </p>
                ) : (
                  Object.entries(previewData.user_needs_to_provide || {}).map(([key, field]) => {
                    const isAutoFilled = field.default && previewData.auto_gathered?.state_code;
                    if (field.type === 'select') {
                      return (
                        <div key={key}>
                          <label className="text-sm font-medium block mb-1.5">
                            {field.label}{field.required && <span className="text-destructive"> *</span>}
                          </label>
                          <select
                            value={formInputs[key] || ''}
                            onChange={(e) => updateInput(key, e.target.value)}
                            className="w-full px-3 py-2 border border-border bg-background text-sm focus:ring-2 focus:ring-gold/40 focus:border-gold/40 outline-none"
                          >
                            <option value="">Select...</option>
                            {field.options?.map(opt => (
                              <option key={opt} value={opt}>{opt}</option>
                            ))}
                          </select>
                        </div>
                      );
                    }
                    return (
                      <div key={key}>
                        <label className="text-sm font-medium block mb-1.5">
                          {field.label}{field.required && <span className="text-destructive"> *</span>}
                        </label>
                        <input
                          type="text"
                          value={formInputs[key] || ''}
                          onChange={(e) => updateInput(key, e.target.value)}
                          placeholder={field.placeholder || ''}
                          className={`w-full px-3 py-2 border text-sm outline-none transition-colors ${
                            isAutoFilled
                              ? 'bg-success/10 dark:bg-success/20 border-success/30 dark:border-success/40'
                              : 'bg-background border-border focus:ring-2 focus:ring-gold/40 focus:border-gold/40'
                          }`}
                        />
                        {isAutoFilled && (
                          <p className="text-xs text-success mt-1 flex items-center gap-1">
                            <CheckCircle2 className="w-3 h-3" /> From your trust profile (editable)
                          </p>
                        )}
                      </div>
                    );
                  })
                )}
              </CardContent>
            </Card>

            {/* Generate button */}
            <div className="flex items-center justify-end gap-3">
              <Button variant="outline" onClick={backToSelect}>Cancel</Button>
              <Button
                onClick={generateKit}
                disabled={!requiredFieldsFilled() || generating}
                className="btn-gold"
              >
                {generating ? (
                  <><Loader2 className="w-4 h-4 mr-2 animate-spin" /> Generating...</>
                ) : (
                  <>Generate Kit</>
                )}
              </Button>
            </div>

            {generating && (
              <p className="text-center text-xs text-muted-foreground">
                AI is assembling your state-specific kit. This takes a few seconds...
              </p>
            )}
          </div>
        )}
      </>
    );
  };

  // ==================== RENDER: KIT DETAIL VIEW ====================
  const renderDetailView = () => {
    const kit = currentKit;
    if (!kit) return null;
    const content = kit.generated_content || {};
    const kitType = kitTypes.find(k => k.kit_type === kit.kit_type);
    const Icon = KIT_ICONS[kitType?.icon] || FileText;

    return (
      <>
        <style>{`
          @media print {
            /* Hide sidebar, mobile nav, and action buttons */
            nav, [class*="MobileBottomNav"], [class*="sidebar"],
            .page-header button, [class*="bottom-nav"] {
              display: none !important;
            }
            /* Reset layout for print */
            .flex.min-h-screen { display: block !important; }
            .flex-1 { width: 100% !important; max-width: 100% !important; }
            .page-content { padding: 0 !important; }
            .max-w-3xl { max-width: 100% !important; }
            /* Remove card shadows/borders for clean print */
            [class*="Card"] { box-shadow: none !important; border: 1px solid #ccc !important; }
          }
        `}</style>
        <div className="page-header flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Button variant="ghost" size="sm" onClick={backToSelect}>
              <ArrowLeft className="w-4 h-4 mr-1" /> Back to Kits
            </Button>
          </div>
          <Button variant="outline" size="sm" onClick={printKit}>
            <Printer className="w-4 h-4 mr-1" /> Print
          </Button>
        </div>

        <div className="max-w-3xl mx-auto mt-4 space-y-6">
          {/* Kit header */}
          <Card>
            <CardContent className="p-5">
              <div className="flex items-start gap-3 mb-3">
                <div className="p-2.5 bg-gold/10 text-gold">
                  <Icon className="w-6 h-6" />
                </div>
                <div className="flex-1">
                  <h1 className="text-lg font-bold">{content.kit_title || kit.kit_title}</h1>
                  <p className="text-sm text-muted-foreground mt-1">{content.summary}</p>
                </div>
              </div>
              <div className="flex flex-wrap gap-3 text-xs">
                {content.where_to_submit && (
                  <div className="flex items-center gap-1.5 text-muted-foreground">
                    <MapPin className="w-3.5 h-3.5" /> {content.where_to_submit}
                  </div>
                )}
                {content.estimated_time && (
                  <div className="flex items-center gap-1.5 text-muted-foreground">
                    <Clock className="w-3.5 h-3.5" /> {content.estimated_time}
                  </div>
                )}
              </div>
            </CardContent>
          </Card>

          {/* Instructions */}
          {content.instructions && (
            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="text-base">Step-by-Step Instructions</CardTitle>
              </CardHeader>
              <CardContent>
                {content.instructions.overview && (
                  <p className="text-sm text-muted-foreground mb-4">{content.instructions.overview}</p>
                )}
                <div className="space-y-3">
                  {(content.instructions.steps || []).map((step, i) => (
                    <div key={i} className="flex gap-3">
                      <div className="shrink-0 w-7 h-7 rounded-full bg-gold/10 text-gold flex items-center justify-center text-sm font-bold">
                        {step.step || i + 1}
                      </div>
                      <div className="flex-1 pb-1">
                        <p className="font-medium text-sm">{step.title}</p>
                        <p className="text-sm text-muted-foreground mt-0.5">{step.description}</p>
                        {step.documents_needed && step.documents_needed.length > 0 && (
                          <div className="mt-2 flex flex-wrap gap-1.5">
                            {step.documents_needed.map((d, j) => (
                              <Badge key={j} variant="outline" className="text-[10px]">{d}</Badge>
                            ))}
                          </div>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          )}

          {/* Forms */}
          {content.forms && content.forms.length > 0 && (
            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="text-base">Forms You'll Need</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                {content.forms.map((form, i) => (
                  <div key={i} className="border border-border p-4">
                    <div className="flex items-start justify-between gap-2 mb-2">
                      <div>
                        <p className="font-medium text-sm">{form.form_name}</p>
                        <p className="text-xs text-muted-foreground mt-0.5">{form.form_purpose}</p>
                      </div>
                      {form.download_url && (
                        <a
                          href={form.download_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="shrink-0"
                        >
                          <Button variant="outline" size="sm">
                            <Download className="w-3.5 h-3.5 mr-1" /> Download
                          </Button>
                        </a>
                      )}
                    </div>
                    {form.pre_fill_data && Object.keys(form.pre_fill_data).length > 0 && (
                      <div className="mt-2 bg-muted/50 p-3">
                        <p className="text-[10px] font-medium text-muted-foreground uppercase tracking-wide mb-1.5">Pre-fill Data</p>
                        <div className="space-y-1">
                          {Object.entries(form.pre_fill_data).map(([k, v]) => (
                            <div key={k} className="flex justify-between text-xs">
                              <span className="text-muted-foreground">{k.replace(/_/g, ' ')}</span>
                              <span className="font-medium">{String(v)}</span>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                    {form.where_to_get && (
                      <p className="text-xs text-muted-foreground mt-2 flex items-center gap-1">
                        <MapPin className="w-3 h-3" /> {form.where_to_get}
                      </p>
                    )}
                  </div>
                ))}
              </CardContent>
            </Card>
          )}

          {/* Documents to bring */}
          {content.documents_to_bring && content.documents_to_bring.length > 0 && (
            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="text-base flex items-center gap-2">
                  <FolderOpen className="w-5 h-5" /> Documents to Bring
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-2">
                {content.documents_to_bring.map((doc, i) => (
                  <div key={i} className="flex items-center gap-3 py-1.5 border-b border-border/40 last:border-0">
                    <CheckCircle2 className="w-4 h-4 text-success shrink-0" />
                    <div className="flex-1 min-w-0">
                      <span className="text-sm font-medium">{doc.document}</span>
                      {doc.source && (
                        <span className="text-xs text-muted-foreground ml-2">({doc.source})</span>
                      )}
                    </div>
                    {doc.vault_doc_id && (
                      <Link to="/vault">
                        <Button variant="ghost" size="sm" className="text-xs">
                          <FolderOpen className="w-3.5 h-3.5 mr-1" /> In Vault
                        </Button>
                      </Link>
                    )}
                  </div>
                ))}
              </CardContent>
            </Card>
          )}

          {/* Fees */}
          {content.fees && content.fees.length > 0 && (
            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="text-base flex items-center gap-2">
                  <DollarSign className="w-5 h-5" /> Fees
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-2">
                  {content.fees.map((fee, i) => (
                    <div key={i} className="flex items-center justify-between text-sm py-1.5 border-b border-border/40 last:border-0">
                      <span className="text-muted-foreground">{fee.fee_name}</span>
                      <span className="font-medium">{fee.amount}</span>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          )}

          {/* Special notes */}
          {content.special_notes && content.special_notes.length > 0 && (
            <Card className="border-warning/30 bg-warning/5 dark:bg-warning/10">
              <CardContent className="p-4">
                <div className="flex items-start gap-2">
                  <AlertCircle className="w-5 h-5 text-warning shrink-0 mt-0.5" />
                  <div>
                    <p className="font-medium text-sm mb-1.5">Important Notes</p>
                    <ul className="space-y-1.5">
                      {content.special_notes.map((note, i) => (
                        <li key={i} className="text-sm text-muted-foreground flex gap-2">
                          <span className="text-warning">•</span> {note}
                        </li>
                      ))}
                    </ul>
                  </div>
                </div>
              </CardContent>
            </Card>
          )}

          {/* Actions */}
          <div className="flex items-center justify-between pb-8">
            <Button variant="outline" onClick={backToSelect}>
              <ArrowLeft className="w-4 h-4 mr-1" /> Back to Kits
            </Button>
            <Button variant="outline" onClick={printKit}>
              <Printer className="w-4 h-4 mr-1" /> Print Kit
            </Button>
          </div>
        </div>
      </>
    );
  };

  // ==================== MAIN RENDER ====================
  return (
    <div className="main-layout">
      <Sidebar />
      <div className="main-content dot-grid">
        <div className="page-container">
          {!trustId && view !== 'select' ? (
            <div className="flex flex-col items-center justify-center py-20 gap-3">
              <AlertCircle className="w-8 h-8 text-warning" />
              <p className="text-sm text-muted-foreground">Please select a trust to use Administration Kits.</p>
            </div>
          ) : (
            <>
              {view === 'select' && renderSelectView()}
              {view === 'preview' && renderPreviewView()}
              {view === 'detail' && renderDetailView()}
            </>
          )}
        </div>
      </div>
      <MobileBottomNav />
    </div>
  );
}