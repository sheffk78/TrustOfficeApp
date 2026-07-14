import React, { useState, useEffect } from 'react';
import { useAuth } from '@/context/AuthContext';
import { fetchWithAuth } from '@/utils/api';
import PageHelpButton from '@/components/PageHelpButton';
import { Sidebar } from '@/components/Sidebar';
import { MobileBottomNav } from '@/components/MobileBottomNav';
import { Printer, FileText, Users, Building2, Landmark, Phone, Mail, ClipboardList, Calendar, Shield, BookOpen } from 'lucide-react';

const PRINT_STYLES = `
@media print {
  body * { visibility: hidden; }
  .printable-area, .printable-area * { visibility: visible; }
  .printable-area {
    position: absolute;
    left: 0;
    top: 0;
    width: 100%;
  }
  .no-print { display: none !important; }

  @page {
    size: letter;
    margin: 0.75in 0.75in 0.75in 1in;
  }

  .packet-section {
    page-break-after: always;
    font-size: 10pt !important;
  }

  .packet-section h1 {
    font-size: 18pt !important;
    margin-bottom: 4pt !important;
  }

  .packet-section h2 {
    font-size: 13pt !important;
    margin-bottom: 3pt !important;
  }

  .packet-section h3 {
    font-size: 11pt !important;
  }

  .packet-section table {
    font-size: 9pt !important;
  }

  .cover-page {
    page-break-after: always;
    min-height: 9in;
    display: flex;
    flex-direction: column;
    justify-content: center;
    align-items: center;
    text-align: center;
  }

  .cover-page h1 {
    font-size: 28pt !important;
  }
}
`;

const fmtDate = (dateStr) => {
  if (!dateStr) return '';
  try {
    return new Date(dateStr).toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' });
  } catch { return dateStr; }
};

const InfoRow = ({ label, value }) => (
  <div className="flex py-1.5 border-b border-gray-100">
    <div className="w-40 flex-shrink-0 text-gray-500 text-sm">{label}</div>
    <div className="text-gray-900 text-sm font-medium">{value || 'Not specified'}</div>
  </div>
);

const SectionTitle = ({ icon: Icon, title }) => (
  <div className="flex items-center gap-2 mb-4">
    {Icon && <Icon className="w-5 h-5 text-gold" />}
    <h2 className="text-lg font-bold text-gray-900">{title}</h2>
  </div>
);

const SuccessorPacketPage = () => {
  const { selectedTrust } = useAuth();
  const [trustData, setTrustData] = useState(null);
  const [entities, setEntities] = useState([]);
  const [beneficiaries, setBeneficiaries] = useState([]);
  const [bankAccounts, setBankAccounts] = useState([]);
  const [vaultDocs, setVaultDocs] = useState([]);
  const [governanceTasks, setGovernanceTasks] = useState([]);
  const [taxCalendar, setTaxCalendar] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!selectedTrust?.trust_id) return;
    const tid = selectedTrust.trust_id;
    let cancelled = false;

    const fetchAll = async () => {
      try {
        const [trustRes, entitiesRes, beneRes, bankRes, vaultRes, govRes, taxRes] = await Promise.all([
          fetchWithAuth(`/trusts/${tid}`),
          fetchWithAuth(`/entities?trust_id=${tid}`).catch(() => null),
          fetchWithAuth(`/beneficiaries/dashboard?trust_id=${tid}`).catch(() => null),
          fetchWithAuth(`/trusts/${tid}/bank-accounts`).catch(() => null),
          fetchWithAuth(`/vault?trust_id=${tid}`).catch(() => null),
          fetchWithAuth(`/governance/tasks?trust_id=${tid}`).catch(() => null),
          fetchWithAuth(`/tax-calendar?trust_id=${tid}`).catch(() => null),
        ]);

        if (cancelled) return;

        if (trustRes.ok) setTrustData(await trustRes.json());
        if (entitiesRes?.ok) {
          const ed = await entitiesRes.json();
          setEntities(Array.isArray(ed) ? ed : (ed.items || ed.entities || []));
        }
        if (beneRes?.ok) {
          const bd = await beneRes.json();
          setBeneficiaries(bd?.certificates || bd?.beneficiaries || []);
        }
        if (bankRes?.ok) {
          const bk = await bankRes.json();
          setBankAccounts(bk?.accounts || bk?.bank_accounts || []);
        }
        if (vaultRes?.ok) {
          const vd = await vaultRes.json();
          setVaultDocs(vd?.documents || vd || []);
        }
        if (govRes?.ok) {
          const gd = await govRes.json();
          setGovernanceTasks(gd?.tasks || gd || []);
        }
        if (taxRes?.ok) {
          const td = await taxRes.json();
          setTaxCalendar(td?.entries || td?.calendar || []);
        }
      } catch (e) {
        console.error('Failed to load packet data:', e);
        setError('Could not load all trust data. Some sections may be incomplete.');
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    fetchAll();
    return () => { cancelled = true; };
  }, [selectedTrust?.trust_id]);

  if (!selectedTrust) {
    return (
      <div className="main-layout">
        <Sidebar />
        <main className="main-content no-print mobile-layout-offset">
          <div className="page-container max-w-5xl mx-auto">
            <div className="card-trust p-12 flex flex-col items-center justify-center">
              <FileText className="w-12 h-12 text-muted-foreground/60 mb-3"/>
              <h2 className="text-xl font-semibold text-navy mb-1">Select a trust</h2>
              <p className="text-sm text-muted-foreground">Choose a trust to view the Successor Trustee Packet.</p>
            </div>
          </div>
        </main>
        <MobileBottomNav />
      </div>
    );
  }

  const handlePrint = () => {
    setTimeout(() => window.print(), 100);
  };

  const trustName = trustData?.name || selectedTrust?.name || 'Your Trust';
  const today = new Date().toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' });

  return (
    <>
      <style>{PRINT_STYLES}</style>
      <div className="main-layout">
        <Sidebar />
        <main className="main-content no-print">
          <div className="page-container max-w-5xl mx-auto">
            <div className="page-header flex items-center justify-between">
              <div>
                <h1 className="page-title">Successor Trustee Packet</h1>
                <p className="page-subtitle">A complete handoff document for your successor trustee. Print and store with your trust records.</p>
              </div>
              <div className="flex items-center gap-2">
                <PageHelpButton
                  items={[
                    { text: 'This packet compiles everything a successor trustee needs if the current trustee dies or becomes incapacitated' },
                    { text: 'Fill in successor trustee info and key contacts in Settings first for a complete packet' },
                    { text: 'Print on standard letter-size paper. Uses your browser print dialog.' },
                  ]}
                  taPrompt="What should I include in my successor trustee packet?"
                />
                <button
                  onClick={handlePrint}
                  disabled={loading}
                  className="flex items-center gap-2 px-4 py-2 bg-gold hover:bg-gold/80 text-navy font-medium shadow-sm transition-colors disabled:opacity-50"
                >
                  <Printer className="w-4 h-4" /> Print Full Packet
                </button>
              </div>
            </div>

            {error && (
              <div className="mb-4 p-3 bg-warning/5 border border-warning/20 text-warning text-sm rounded">
                {error}
              </div>
            )}

            {loading ? (
              <div className="animate-pulse space-y-4">
                <div className="h-8 bg-subtle-bg rounded w-1/3"></div>
                <div className="h-48 bg-subtle-bg rounded"></div>
                <div className="h-48 bg-subtle-bg rounded"></div>
              </div>
            ) : (
              <div className="card-trust border border-border p-6 shadow-sm">
                <p className="text-sm text-muted-foreground mb-4">
                  Click "Print Full Packet" to generate a printable document with all sections below. The packet includes trust identification, trustee transition info, beneficiaries, assets, bank accounts, professional contacts, governance rules, upcoming deadlines, and your letter of guidance.
                </p>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mt-4">
                  {[
                    { icon: FileText, title: 'Trust Overview', desc: 'Name, EIN, type, jurisdiction, formation date' },
                    { icon: Users, title: 'Trustee Transition', desc: 'Current trustee, successor trustee, contact info' },
                    { icon: Users, title: 'Beneficiaries', desc: 'Names, contacts, allocations, unit certificates' },
                    { icon: Building2, title: 'Asset Inventory', desc: 'Trust Assets, entity structure, ownership' },
                    { icon: Landmark, title: 'Bank Accounts', desc: 'Institutions, account types, last four digits' },
                    { icon: Phone, title: 'Professional Contacts', desc: 'Attorney, CPA, financial advisor' },
                    { icon: ClipboardList, title: 'Document Inventory', desc: 'Vault documents by category' },
                    { icon: Shield, title: 'Governance Rules', desc: 'Review cadence, spending thresholds, compensation' },
                    { icon: Calendar, title: 'Upcoming Deadlines', desc: 'Tax calendar, governance tasks, compliance' },
                    { icon: BookOpen, title: 'Instructions & Guidance', desc: 'Letter of guidance, document location, first steps' },
                  ].map((s, i) => {
                    const Icon = s.icon;
                    return (
                      <div key={i} className="flex items-start gap-3 p-3 bg-subtle-bg rounded border border-border/50">
                        <Icon className="w-4 h-4 text-gold flex-shrink-0 mt-0.5" />
                        <div>
                          <div className="text-sm font-semibold text-navy">{s.title}</div>
                          <div className="text-xs text-muted-foreground">{s.desc}</div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}
          </div>
        </main>
        <MobileBottomNav />
      </div>

      {/* ==================== PRINTABLE PACKET ==================== */}
      <div className="printable-area" style={{ display: loading ? 'none' : 'block' }}>
        {/* COVER PAGE */}
        <div className="cover-page p-8" style={{ paddingLeft: '1in', paddingTop: '1in' }}>
          <div className="text-center" style={{ minHeight: '8in', display: 'flex', flexDirection: 'column', justifyContent: 'center', alignItems: 'center' }}>
            <div className="mb-8 pt-4">
              <div className="text-xs tracking-widest text-gray-400 uppercase mb-2">Trust Governance Workspace</div>
              <div className="w-16 h-0.5 bg-gold mx-auto mb-6"></div>
            </div>
            <h1 className="text-3xl font-bold text-gray-900 mb-2" style={{ fontSize: '28pt' }}>
              SUCCESSOR TRUSTEE PACKET
            </h1>
            <div className="w-24 h-0.5 bg-gray-300 mx-auto my-6"></div>
            <div className="mt-4 space-y-3" style={{ fontSize: '14pt' }}>
              <div className="text-xl font-semibold text-gray-900">{trustName}</div>
              {trustData?.ein && <div className="text-gray-600">EIN: {trustData.ein}</div>}
              {trustData?.jurisdiction && <div className="text-gray-600">Jurisdiction: {trustData.jurisdiction}</div>}
              {trustData?.start_date && <div className="text-gray-600">Formed: {fmtDate(trustData.start_date)}</div>}
            </div>
            <div className="mt-12 pt-8 border-t border-gray-200 w-full max-w-md">
              <div className="text-sm text-gray-500 mb-2">Generated: {today}</div>
              <div className="text-xs text-gray-400">Maintained with TrustOffice — trustoffice.app</div>
            </div>
          </div>
        </div>

        {/* SECTION 1: TRUST OVERVIEW */}
        <div className="packet-section p-8" style={{ paddingLeft: '1in', paddingTop: '0.75in' }}>
          <div className="max-w-lg mx-auto">
            <SectionTitle icon={FileText} title="1. Trust Overview" />
            <div className="bg-gray-50 rounded p-4">
              <InfoRow label="Trust Name" value={trustData?.name} />
              <InfoRow label="Trust Type" value={trustData?.trust_type} />
              <InfoRow label="EIN" value={trustData?.ein} />
              <InfoRow label="Formation Date" value={fmtDate(trustData?.start_date)} />
              <InfoRow label="Jurisdiction" value={trustData?.jurisdiction} />
              <InfoRow label="State" value={trustData?.state_code} />
              <InfoRow label="Tax Year End" value={trustData?.is_fiscal_year ? `${trustData?.tax_year_end_month}/${trustData?.tax_year_end_day}` : 'Calendar Year'} />
              <InfoRow label="Tax Status" value={trustData?.tax_status} />
              <InfoRow label="Description" value={trustData?.description} />
            </div>
          </div>
        </div>

        {/* SECTION 2: TRUSTEE TRANSITION */}
        <div className="packet-section p-8" style={{ paddingLeft: '1in', paddingTop: '0.75in' }}>
          <div className="max-w-lg mx-auto">
            <SectionTitle icon={Users} title="2. Trustee Transition" />
            <div className="bg-gray-50 rounded p-4 mb-4">
              <h3 className="text-sm font-semibold text-gray-700 mb-2">Current Trustee(s)</h3>
              <InfoRow label="Trustee(s)" value={trustData?.trustees} />
              <InfoRow label="Role" value={trustData?.role} />
              <InfoRow label="Authority Clause" value={trustData?.authority_clause} />
              <InfoRow label="Grantor" value={trustData?.grantor_name} />
            </div>
            <div className="bg-cyan-50 rounded p-4 border border-cyan-200">
              <h3 className="text-sm font-semibold text-cyan-700 mb-2">Successor Trustee</h3>
              <InfoRow label="Name" value={trustData?.successor_trustee_name} />
              <InfoRow label="Email" value={trustData?.successor_trustee_email} />
              <InfoRow label="Phone" value={trustData?.successor_trustee_phone} />
              <InfoRow label="Relationship" value={trustData?.successor_trustee_relationship} />
              <InfoRow label="Notes" value={trustData?.successor_trustee_notes} />
            </div>
          </div>
        </div>

        {/* SECTION 3: BENEFICIARIES */}
        <div className="packet-section p-8" style={{ paddingLeft: '1in', paddingTop: '0.75in' }}>
          <div className="max-w-lg mx-auto">
            <SectionTitle icon={Users} title="3. Beneficiaries" />
            {beneficiaries.length > 0 ? (
              <table className="w-full border-collapse">
                <thead>
                  <tr className="border-b-2 border-gray-300">
                    <th className="text-left py-2 text-sm font-semibold text-gray-700">Name</th>
                    <th className="text-left py-2 text-sm font-semibold text-gray-700">Email</th>
                    <th className="text-left py-2 text-sm font-semibold text-gray-700">Phone</th>
                    <th className="text-left py-2 text-sm font-semibold text-gray-700">Units</th>
                  </tr>
                </thead>
                <tbody>
                  {beneficiaries.map((b, i) => (
                    <tr key={i} className="border-b border-gray-100">
                      <td className="py-2 text-sm text-gray-900">{b.holder_name || b.name || ''}</td>
                      <td className="py-2 text-sm text-gray-600">{b.email || ''}</td>
                      <td className="py-2 text-sm text-gray-600">{b.phone || ''}</td>
                      <td className="py-2 text-sm text-gray-600">{b.units || b.allocation_percentage || ''}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <p className="text-sm text-gray-400 italic">No beneficiary records found. Add beneficiaries in the Beneficiaries page.</p>
            )}
          </div>
        </div>

        {/* SECTION 4: ASSET / ENTITY INVENTORY */}
        <div className="packet-section p-8" style={{ paddingLeft: '1in', paddingTop: '0.75in' }}>
          <div className="max-w-lg mx-auto">
            <SectionTitle icon={Building2} title="4. Asset & Entity Inventory" />
            {entities.length > 0 ? (
              <div className="space-y-3">
                {entities.map((e, i) => (
                  <div key={i} className="bg-gray-50 rounded p-3">
                    <div className="font-semibold text-sm text-gray-900">{e.name || e.legal_name || 'Entity'}</div>
                    <div className="text-xs text-gray-500 mt-1">
                      {e.entity_type && <span className="mr-3">Type: {e.entity_type}</span>}
                      {e.ein && <span className="mr-3">EIN: {e.ein}</span>}
                      {e.governing_law && <span>Governing Law: {e.governing_law}</span>}
                    </div>
                    {e.trustee_names && <div className="text-xs text-gray-600 mt-1">Trustees: {e.trustee_names}</div>}
                    {e.manager_names && <div className="text-xs text-gray-600 mt-1">Managers: {e.manager_names}</div>}
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-sm text-gray-400 italic">No entities or assets found. Add entities in the Trust & Entities page.</p>
            )}
          </div>
        </div>

        {/* SECTION 5: BANK ACCOUNTS */}
        <div className="packet-section p-8" style={{ paddingLeft: '1in', paddingTop: '0.75in' }}>
          <div className="max-w-lg mx-auto">
            <SectionTitle icon={Landmark} title="5. Bank Accounts" />
            {bankAccounts.length > 0 ? (
              <table className="w-full border-collapse">
                <thead>
                  <tr className="border-b-2 border-gray-300">
                    <th className="text-left py-2 text-sm font-semibold text-gray-700">Nickname</th>
                    <th className="text-left py-2 text-sm font-semibold text-gray-700">Institution</th>
                    <th className="text-left py-2 text-sm font-semibold text-gray-700">Type</th>
                    <th className="text-left py-2 text-sm font-semibold text-gray-700">Last 4</th>
                  </tr>
                </thead>
                <tbody>
                  {bankAccounts.map((a, i) => (
                    <tr key={i} className="border-b border-gray-100">
                      <td className="py-2 text-sm text-gray-900">{a.nickname || a.name || ''}</td>
                      <td className="py-2 text-sm text-gray-600">{a.institution || a.bank_name || ''}</td>
                      <td className="py-2 text-sm text-gray-600">{a.account_type || a.type || ''}</td>
                      <td className="py-2 text-sm text-gray-600">****{a.last_four || a.last4 || ''}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <p className="text-sm text-gray-400 italic">No bank accounts found. Add bank accounts in the Banking section.</p>
            )}
          </div>
        </div>

        {/* SECTION 6: PROFESSIONAL CONTACTS */}
        <div className="packet-section p-8" style={{ paddingLeft: '1in', paddingTop: '0.75in' }}>
          <div className="max-w-lg mx-auto">
            <SectionTitle icon={Phone} title="6. Professional Contacts" />
            <div className="space-y-4">
              <div className="bg-gray-50 rounded p-4">
                <h3 className="text-sm font-semibold text-gray-700 mb-2">Trust Attorney</h3>
                <InfoRow label="Name" value={trustData?.attorney_name} />
                <InfoRow label="Phone" value={trustData?.attorney_phone} />
                <InfoRow label="Email" value={trustData?.attorney_email} />
              </div>
              <div className="bg-gray-50 rounded p-4">
                <h3 className="text-sm font-semibold text-gray-700 mb-2">CPA / Tax Preparer</h3>
                <InfoRow label="Name" value={trustData?.cpa_name} />
                <InfoRow label="Phone" value={trustData?.cpa_phone} />
                <InfoRow label="Email" value={trustData?.cpa_email} />
              </div>
              <div className="bg-gray-50 rounded p-4">
                <h3 className="text-sm font-semibold text-gray-700 mb-2">Financial Advisor</h3>
                <InfoRow label="Name" value={trustData?.financial_advisor_name} />
                <InfoRow label="Phone" value={trustData?.financial_advisor_phone} />
                <InfoRow label="Email" value={trustData?.financial_advisor_email} />
              </div>
            </div>
          </div>
        </div>

        {/* SECTION 7: DOCUMENT INVENTORY */}
        <div className="packet-section p-8" style={{ paddingLeft: '1in', paddingTop: '0.75in' }}>
          <div className="max-w-lg mx-auto">
            <SectionTitle icon={ClipboardList} title="7. Document Inventory" />
            <div className="bg-gray-50 rounded p-4 mb-4">
              <InfoRow label="Physical Document Location" value={trustData?.document_location} />
            </div>
            {vaultDocs.length > 0 ? (
              <table className="w-full border-collapse">
                <thead>
                  <tr className="border-b-2 border-gray-300">
                    <th className="text-left py-2 text-sm font-semibold text-gray-700">Document</th>
                    <th className="text-left py-2 text-sm font-semibold text-gray-700">Category</th>
                    <th className="text-left py-2 text-sm font-semibold text-gray-700">Date</th>
                  </tr>
                </thead>
                <tbody>
                  {vaultDocs.slice(0, 25).map((d, i) => (
                    <tr key={i} className="border-b border-gray-100">
                      <td className="py-2 text-sm text-gray-900">{d.name || d.title || d.filename || ''}</td>
                      <td className="py-2 text-sm text-gray-600">{d.category || d.document_type || ''}</td>
                      <td className="py-2 text-sm text-gray-600">{fmtDate(d.uploaded_at || d.date || d.created_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <p className="text-sm text-gray-400 italic">No vault documents found. Upload documents in the Vault page.</p>
            )}
          </div>
        </div>

        {/* SECTION 8: GOVERNANCE RULES */}
        <div className="packet-section p-8" style={{ paddingLeft: '1in', paddingTop: '0.75in' }}>
          <div className="max-w-lg mx-auto">
            <SectionTitle icon={Shield} title="8. Governance Rules" />
            <div className="bg-gray-50 rounded p-4">
              <InfoRow label="Review Cadence" value={trustData?.review_cadence} />
              <InfoRow label="Spending Threshold" value={trustData?.governance_settings?.spending_threshold ? `$${trustData.governance_settings.spending_threshold}` : null} />
              <InfoRow label="Benevolence Enabled" value={trustData?.benevolence_enabled ? 'Yes' : 'No'} />
              <InfoRow label="Authority Clause" value={trustData?.authority_clause} />
            </div>
          </div>
        </div>

        {/* SECTION 9: UPCOMING DEADLINES */}
        <div className="packet-section p-8" style={{ paddingLeft: '1in', paddingTop: '0.75in' }}>
          <div className="max-w-lg mx-auto">
            <SectionTitle icon={Calendar} title="9. Upcoming Deadlines" />
            {governanceTasks.length > 0 && (
              <div className="mb-4">
                <h3 className="text-sm font-semibold text-gray-700 mb-2">Governance Tasks</h3>
                <table className="w-full border-collapse">
                  <tbody>
                    {governanceTasks.slice(0, 10).map((t, i) => (
                      <tr key={i} className="border-b border-gray-100">
                        <td className="py-2 text-sm text-gray-900">{t.title || t.task_type || ''}</td>
                        <td className="py-2 text-sm text-gray-600 text-right">{fmtDate(t.due_date)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            {taxCalendar.length > 0 && (
              <div>
                <h3 className="text-sm font-semibold text-gray-700 mb-2">Tax Calendar</h3>
                <table className="w-full border-collapse">
                  <tbody>
                    {taxCalendar.slice(0, 10).map((t, i) => (
                      <tr key={i} className="border-b border-gray-100">
                        <td className="py-2 text-sm text-gray-900">{t.deadline_type || t.title || ''}</td>
                        <td className="py-2 text-sm text-gray-600 text-right">{fmtDate(t.due_date)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            {governanceTasks.length === 0 && taxCalendar.length === 0 && (
              <p className="text-sm text-gray-400 italic">No upcoming deadlines found.</p>
            )}
          </div>
        </div>

        {/* SECTION 10: INSTRUCTIONS & GUIDANCE */}
        <div className="packet-section p-8" style={{ paddingLeft: '1in', paddingTop: '0.75in' }}>
          <div className="max-w-lg mx-auto">
            <SectionTitle icon={BookOpen} title="10. Instructions for Successor Trustee" />

            {trustData?.successor_instructions && (
              <div className="mb-6">
                <h3 className="text-sm font-semibold text-gray-700 mb-2">Letter of Guidance</h3>
                <div className="bg-gray-50 rounded p-4 text-sm text-gray-700 whitespace-pre-wrap" style={{ fontSize: '10pt', lineHeight: 1.6 }}>
                  {trustData.successor_instructions}
                </div>
              </div>
            )}

            <div className="mb-6">
              <h3 className="text-sm font-semibold text-gray-700 mb-2">First 30 Days — Action Plan</h3>
              <div className="bg-gray-50 rounded p-4">
                {[
                  'Obtain certified copies of the death certificate or physician\'s incapacity letter',
                  'Review the trust document and this packet thoroughly',
                  'Contact the trust attorney to confirm your authority and discuss next steps',
                  'Notify beneficiaries of your role as successor trustee',
                  'Inventory all trust assets and confirm account balances',
                  'Obtain a tax identification number (EIN) for the trust if not already on file',
                  'Open a trust bank account in your capacity as trustee',
                  'Transfer trust assets into your name as trustee',
                  'Review state-specific notice requirements for beneficiaries',
                  'Engage a CPA for fiduciary tax return preparation (Form 1041)',
                  'Review upcoming deadlines and tax filing dates',
                  'Schedule a meeting with beneficiaries to discuss administration plans',
                ].map((step, i) => (
                  <div key={i} className="flex items-start gap-3 mb-2 py-1 border-b border-gray-100">
                    <div className="w-5 h-5 border-2 border-gray-300 rounded flex-shrink-0 mt-0.5 flex items-center justify-center text-xs font-bold text-gray-400">{i + 1}</div>
                    <span className="text-sm text-gray-700" style={{ fontSize: '10pt' }}>{step}</span>
                  </div>
                ))}
              </div>
            </div>

            <div className="mb-6">
              <h3 className="text-sm font-semibold text-gray-700 mb-2">Key Reminders</h3>
              <div className="bg-amber-50 rounded p-4 border border-amber-200">
                <ul className="space-y-2 text-sm text-gray-700" style={{ fontSize: '10pt' }}>
                  <li className="flex items-start gap-2"><span className="text-gold font-bold">!</span> Always sign as "Trustee of the {trustName}" never individually.</li>
                  <li className="flex items-start gap-2"><span className="text-gold font-bold">!</span> Never commingle trust assets with personal assets.</li>
                  <li className="flex items-start gap-2"><span className="text-gold font-bold">!</span> Document every significant decision in meeting minutes.</li>
                  <li className="flex items-start gap-2"><span className="text-gold font-bold">!</span> Keep detailed records of all income, expenses, and distributions.</li>
                  <li className="flex items-start gap-2"><span className="text-gold font-bold">!</span> Consult the trust attorney before making major decisions or distributions.</li>
                </ul>
              </div>
            </div>

            {trustData?.document_location && (
              <div className="mb-6">
                <h3 className="text-sm font-semibold text-gray-700 mb-2">Physical Document Location</h3>
                <div className="bg-gray-50 rounded p-4 text-sm text-gray-700" style={{ fontSize: '10pt' }}>
                  {trustData.document_location}
                </div>
              </div>
            )}

            <div className="mt-8 pt-6 border-t border-gray-200 text-center">
              <p className="text-xs text-gray-400">Generated with TrustOffice — trustoffice.app — {today}</p>
            </div>
          </div>
        </div>
      </div>
    </>
  );
};

export default SuccessorPacketPage;