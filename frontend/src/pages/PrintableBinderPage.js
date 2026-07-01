import React, { useState, useEffect } from 'react';
import { useAuth } from '@/context/AuthContext';
import { useNavigate } from 'react-router-dom';
import { fetchWithAuth } from '@/utils/api';
import PageHelpButton from '@/components/PageHelpButton';
import {
  FileText, Shield, HeartPulse, Landmark, Building2, Users,
  ClipboardList, Mail, BookOpen, FilePen, Home, Car,
  Printer, ChevronDown, ChevronUp, ArrowLeft, Download
} from 'lucide-react';

// ==================== SECTION DATA ====================

const SECTION_TABS = [
  { id: 'trust-documents', number: 1, title: 'Trust Documents', icon: FileText,
    description: 'Declaration of Trust, amendments, restatements, and organizational meeting minutes.' },
  { id: 'powers-of-attorney', number: 2, title: 'Powers of Attorney', icon: Shield,
    description: 'Financial Power of Attorney, Healthcare Power of Attorney, and HIPAA authorizations.' },
  { id: 'healthcare-directives', number: 3, title: 'Healthcare Directives', icon: HeartPulse,
    description: 'Living will, advance directive, POLST/DNR forms, and medical authorizations.' },
  { id: 'financial-accounts', number: 4, title: 'Financial Accounts', icon: Landmark,
    description: 'Bank accounts, investment accounts, retirement accounts, and debt records.' },
  { id: 'property-assets', number: 5, title: 'Property & Assets', icon: Building2,
    description: 'Real estate deeds, vehicle titles, business interests, and personal property records.' },
  { id: 'key-contacts', number: 6, title: 'Key Contacts', icon: Users,
    description: 'Attorney, CPA, financial advisor, insurance agent, executor, and trustee contacts.' },
  { id: 'resolutions-minutes', number: 7, title: 'Resolutions & Minutes', icon: ClipboardList,
    description: 'Trustee meeting minutes, formal resolutions, and decision records.' },
  { id: 'correspondence', number: 8, title: 'Correspondence', icon: Mail,
    description: 'Letters to and from beneficiaries, professionals, institutions, and government agencies.' },
];

const QUICK_REFERENCE = {
  duties: [
    { title: 'Duty of Loyalty', text: 'Act solely in the best interest of the beneficiaries. Never use trust assets for personal benefit.' },
    { title: 'Duty of Care', text: 'Manage trust assets with the same care a prudent person would use for their own property.' },
    { title: 'Duty of Impartiality', text: 'Treat all beneficiaries fairly. Do not favor one beneficiary over another unless the trust document directs it.' },
    { title: 'Duty to Inform', text: 'Keep beneficiaries reasonably informed about the trust\'s status, assets, and administration.' },
  ],
  decisionFilter: [
    'Is this action in the best interest of ALL beneficiaries?',
    'Does the trust document authorize this action?',
    'Is this a prudent use of trust assets?',
    'Have I documented my reasoning?',
    'Should I consult the trust attorney first?',
  ],
  signingRule: 'Always sign as "Trustee of the [Trust Name]" — never individually. Include the date and trust name on every document.',
  emergency: ['A lawsuit is filed against the trust or trustee', 'A beneficiary disputes a trust decision', 'A significant asset change occurs (sale, purchase, damage)', 'You are unsure whether an action is authorized'],
};

// ==================== PRINT STYLES ====================

const PRINT_STYLES = `
@media print {
  /* Hide everything except the printable area */
  body * { visibility: hidden; }
  .printable-area, .printable-area * { visibility: visible; }
  .printable-area {
    position: absolute;
    left: 0;
    top: 0;
    width: 100%;
  }
  .no-print { display: none !important; }

  /* Letter-size optimization */
  @page {
    size: letter;
    margin: 0.75in 0.75in 0.75in 1.5in;
  }

  /* Section divider specific */
  .section-divider-print {
    page-break-after: always;
    display: flex !important;
    flex-direction: column;
    justify-content: center;
    align-items: center;
    min-height: 85vh;
    text-align: center;
  }

  .section-divider-print h1 {
    font-size: 28pt !important;
    margin-bottom: 8pt !important;
  }

  .section-divider-print .section-number {
    font-size: 72pt !important;
    font-weight: 700 !important;
    opacity: 0.15 !important;
    margin-bottom: 12pt !important;
  }

  .section-divider-print .section-desc {
    font-size: 12pt !important;
    max-width: 400pt !important;
    line-height: 1.5 !important;
  }

  /* Quick reference specific */
  .quick-ref-print {
    page-break-after: always;
    font-size: 10pt !important;
  }

  .quick-ref-print h2 {
    font-size: 16pt !important;
  }

  .quick-ref-print h3 {
    font-size: 12pt !important;
  }
}
`;

// ==================== COMPONENT ====================

const PrintableBinderPage = () => {
  const { user, selectedTrust } = useAuth();
  const navigate = useNavigate();
  const [coverData, setCoverData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [activePrint, setActivePrint] = useState(null);

  useEffect(() => {
    const fetchCoverData = async () => {
      try {
        const response = await fetchWithAuth('/binder/cover-sheet-data');
        if (response.ok) {
          const data = await response.json();
          setCoverData(data);
        }
      } catch (e) {
        console.error('Failed to load binder data:', e);
      } finally {
        setLoading(false);
      }
    };
    fetchCoverData();
  }, []);

  const handlePrint = (sectionId) => {
    setActivePrint(sectionId);
    setTimeout(() => {
      window.print();
      setActivePrint(null);
    }, 100);
  };

  // ==================== RENDER ====================

  return (
    <>
      <style>{PRINT_STYLES}</style>
      <div className="no-print min-h-screen bg-subtle-bg dark:bg-slate-900 p-4 md:p-8">
        {/* Header */}
        <div className="max-w-5xl mx-auto">
          <button
            onClick={() => navigate('/dashboard')}
            className="mb-4 flex items-center text-sm text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200"
          >
            <ArrowLeft className="w-4 h-4 mr-1" /> Back to Dashboard
          </button>

          <h1 className="text-2xl md:text-3xl font-bold text-gray-900 dark:text-white mb-2">
            Printable Binder Tools
          </h1>
          <div className="flex items-center gap-2 mb-2">
            <PageHelpButton
              items={[
                { text: 'Print cover sheets, tab dividers, and reference cards for your physical trust binder' },
                { text: 'Use a 3-ring binder with tab dividers for best results' },
                { text: 'Print on standard letter-size paper' },
              ]}
              taPrompt="How do I set up a physical trust compliance binder?"
            />
          </div>
          <p className="text-gray-600 dark:text-gray-400 mb-8 max-w-2xl">
            Organize your trust documents with these printable inserts. Print on standard letter-size paper.
            Use a 3-ring binder with tab dividers for best results.
          </p>

          {/* COVER SHEET SECTION */}
          <div className="mb-10">
            <h2 className="text-lg font-semibold text-gray-800 dark:text-gray-200 mb-4 flex items-center gap-2">
              <FileText className="w-5 h-5 text-gold" />
              Binder Cover Sheet
            </h2>
            <div className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 p-6 shadow-sm">
              {loading ? (
                <div className="animate-pulse space-y-3">
                  <div className="h-8 bg-gray-200 dark:bg-gray-700 rounded w-1/2"></div>
                  <div className="h-4 bg-gray-200 dark:bg-gray-700 rounded w-1/3"></div>
                  <div className="h-4 bg-gray-200 dark:bg-gray-700 rounded w-1/4"></div>
                </div>
              ) : (
                <>
                  <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
                    <div>
                      <h3 className="text-xl font-bold text-gray-900 dark:text-white">
                        {coverData?.trust_name || 'Your Trust Name'}
                      </h3>
                      <div className="text-sm text-gray-500 dark:text-gray-400 mt-1 space-y-0.5">
                        {coverData?.trust_type && <div>{coverData.trust_type}</div>}
                        {coverData?.formation_date && <div>Formed: {coverData.formation_date}</div>}
                        {coverData?.ein && <div>EIN: {coverData.ein}</div>}
                        {coverData?.jurisdiction && <div>Jurisdiction: {coverData.jurisdiction}</div>}
                        {coverData?.trustees?.length > 0 && (
                          <div>Trustee{coverData.trustees.length > 1 ? 's' : ''}: {coverData.trustees.join(', ')}</div>
                        )}
                      </div>
                    </div>
                    <button
                      onClick={() => handlePrint('cover')}
                      className="flex items-center gap-2 px-4 py-2 bg-gold hover:bg-gold/80 text-navy font-medium shadow-sm transition-colors"
                    >
                      <Printer className="w-4 h-4" /> Print Cover Sheet
                    </button>
                  </div>
                </>
              )}
            </div>
          </div>

          {/* SECTION DIVIDERS */}
          <div className="mb-10">
            <h2 className="text-lg font-semibold text-gray-800 dark:text-gray-200 mb-4">
              Section Tab Dividers
            </h2>
            <p className="text-sm text-gray-500 dark:text-gray-400 mb-4">
              Print each divider on cardstock or heavy paper and place behind a tab divider in your binder.
            </p>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {SECTION_TABS.map((section) => {
                const Icon = section.icon;
                return (
                  <div
                    key={section.id}
                    className="flex items-start gap-3 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 p-4 shadow-sm hover:shadow-md transition-shadow"
                  >
                    <div className="flex-shrink-0 w-10 h-10 bg-gold/10 dark:bg-gold/20 flex items-center justify-center">
                      <Icon className="w-5 h-5 text-gold" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="text-xs font-bold text-gold">Section {section.number}</span>
                        <h3 className="text-sm font-semibold text-gray-900 dark:text-white">{section.title}</h3>
                      </div>
                      <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">{section.description}</p>
                      <button
                        onClick={() => handlePrint(`tab-${section.id}`)}
                        className="mt-2 flex items-center gap-1 text-xs font-medium text-gold hover:text-gold/80 transition-colors"
                      >
                        <Printer className="w-3 h-3" /> Print Divider
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* REFERENCE CARD */}
          <div className="mb-10">
            <h2 className="text-lg font-semibold text-gray-800 dark:text-gray-200 mb-4 flex items-center gap-2">
              <BookOpen className="w-5 h-5 text-gold" />
              Trustee Quick Reference Card
            </h2>
            <div className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 p-6 shadow-sm">
              <p className="text-sm text-gray-600 dark:text-gray-400 mb-3">
                A single-page cheat sheet covering your fiduciary duties, decision filter, signing rules, and emergency protocols.
                Print this and keep it at the front of your binder.
              </p>
              <button
                onClick={() => handlePrint('quick-ref')}
                className="flex items-center gap-2 px-4 py-2 bg-gold hover:bg-gold/80 text-navy font-medium shadow-sm transition-colors"
              >
                <Printer className="w-4 h-4" /> Print Reference Card
              </button>
            </div>
          </div>

          {/* RESOLUTION TEMPLATE */}
          <div className="mb-10">
            <h2 className="text-lg font-semibold text-gray-800 dark:text-gray-200 mb-4 flex items-center gap-2">
              <FilePen className="w-5 h-5 text-gold" />
              Resolution Template
            </h2>
            <div className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 p-6 shadow-sm">
              <p className="text-sm text-gray-600 dark:text-gray-400 mb-3">
                A blank WHEREAS/BE IT RESOLVED template with signature, witness, and notary blocks.
                Print a fresh copy each time you need to record a formal trust resolution.
              </p>
              <button
                onClick={() => handlePrint('resolution')}
                className="flex items-center gap-2 px-4 py-2 bg-gold hover:bg-gold/80 text-navy font-medium shadow-sm transition-colors"
              >
                <Printer className="w-4 h-4" /> Print Resolution Template
              </button>
            </div>
          </div>

          {/* TRANSFER CHECKLISTS */}
          <div className="mb-10">
            <h2 className="text-lg font-semibold text-gray-800 dark:text-gray-200 mb-4">
              Asset Transfer Checklists
            </h2>
            <p className="text-sm text-gray-500 dark:text-gray-400 mb-4">
              Step-by-step checklists for transferring specific asset types into or out of your trust. Print when you're ready to start a transfer.
            </p>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <div className="flex items-start gap-3 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 p-4 shadow-sm">
                <div className="flex-shrink-0 w-10 h-10 bg-gold/10 dark:bg-gold/20 flex items-center justify-center">
                  <Home className="w-5 h-5 text-gold" />
                </div>
                <div className="flex-1">
                  <h3 className="text-sm font-semibold text-gray-900 dark:text-white">Real Estate Transfer</h3>
                  <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">Deed recording, insurance, mortgage, and tax steps.</p>
                  <button
                    onClick={() => handlePrint('checklist-real-estate')}
                    className="mt-2 flex items-center gap-1 text-xs font-medium text-gold hover:text-gold/80 transition-colors"
                  >
                    <Printer className="w-3 h-3" /> Print Checklist
                  </button>
                </div>
              </div>
              <div className="flex items-start gap-3 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 p-4 shadow-sm">
                <div className="flex-shrink-0 w-10 h-10 bg-gold/10 dark:bg-gold/20 flex items-center justify-center">
                  <Car className="w-5 h-5 text-gold" />
                </div>
                <div className="flex-1">
                  <h3 className="text-sm font-semibold text-gray-900 dark:text-white">Vehicle Transfer</h3>
                  <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">Title transfer, DMV, insurance, and registration steps.</p>
                  <button
                    onClick={() => handlePrint('checklist-vehicle')}
                    className="mt-2 flex items-center gap-1 text-xs font-medium text-gold hover:text-gold/80 transition-colors"
                  >
                    <Printer className="w-3 h-3" /> Print Checklist
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* ==================== PRINTABLE AREAS ==================== */}
      <div className="printable-area" style={{ display: activePrint ? 'block' : 'none' }}>

        {/* COVER SHEET */}
        {activePrint === 'cover' && (
          <div className="p-8" style={{ paddingLeft: '1.5in', paddingTop: '1in' }}>
            <div className="text-center border-2 border-gray-300 rounded p-12" style={{ minHeight: '8in' }}>
              <div className="mb-8 pt-4">
                <div className="text-xs tracking-widest text-gray-400 uppercase mb-2">Trust Governance Workspace</div>
                <div className="w-16 h-0.5 bg-gold mx-auto mb-6"></div>
              </div>
              <h1 className="text-3xl font-bold text-gray-900 mb-2" style={{ fontSize: '28pt' }}>
                TRUST COMPLIANCE BINDER
              </h1>
              <div className="w-24 h-0.5 bg-gray-300 mx-auto my-6"></div>
              <div className="mt-8 space-y-3" style={{ fontSize: '14pt' }}>
                <div className="text-xl font-semibold text-gray-900">{coverData?.trust_name || '_________________'}</div>
                {coverData?.trust_type && <div className="text-gray-600">{coverData.trust_type}</div>}
                {coverData?.formation_date && <div className="text-gray-600">Formed: {coverData.formation_date}</div>}
                {coverData?.ein && <div className="text-gray-600">EIN: {coverData.ein}</div>}
                {coverData?.jurisdiction && <div className="text-gray-600">Jurisdiction: {coverData.jurisdiction}</div>}
                {coverData?.trustees?.length > 0 && (
                  <div className="text-gray-600">Trustee{coverData.trustees.length > 1 ? 's' : ''}: {coverData.trustees.join(', ')}</div>
                )}
              </div>
              <div className="mt-16 pt-8 border-t border-gray-200">
                <div className="text-xs text-gray-400">
                  Maintained with TrustOffice — trustoffice.app
                </div>
              </div>
            </div>
          </div>
        )}

        {/* SECTION DIVIDERS */}
        {SECTION_TABS.map((section) => (
          activePrint === `tab-${section.id}` && (
            <div key={section.id} className="section-divider-print p-8" style={{ paddingLeft: '1.5in', paddingTop: '0.75in' }}>
              <div className="flex flex-col items-center justify-center" style={{ minHeight: '700px' }}>
                <div className="section-number" style={{ fontSize: '72pt', fontWeight: 700, color: 'rgba(217, 119, 6, 0.15)' }}>
                  {section.number}
                </div>
                <h1 className="text-4xl font-bold text-gray-900 mb-4" style={{ fontSize: '28pt' }}>
                  {section.title}
                </h1>
                <div className="w-32 h-0.5 bg-gold mb-6"></div>
                <p className="text-gray-500 text-center max-w-md" style={{ fontSize: '12pt', lineHeight: 1.6 }}>
                  {section.description}
                </p>
                <div className="mt-8 w-full max-w-md pt-6 border-t border-gray-200">
                  <p className="text-xs text-gray-400 text-center">Place behind tab divider {section.number} in your trust compliance binder.</p>
                </div>
              </div>
              <div className="text-center mt-8 text-xs text-gray-400">
                TrustOffice — trustoffice.app
              </div>
            </div>
          )
        ))}

        {/* TRUSTEE QUICK REFERENCE CARD */}
        {activePrint === 'quick-ref' && (
          <div className="quick-ref-print p-8" style={{ paddingLeft: '1.5in', paddingTop: '0.75in' }}>
            <div className="max-w-lg mx-auto">
              <h1 className="text-2xl font-bold text-gray-900 mb-1" style={{ fontSize: '18pt' }}>
                Trustee Quick Reference
              </h1>
              <div className="w-16 h-0.5 bg-gold mb-6 mt-2"></div>

              <h2 className="text-lg font-semibold text-gray-900 mb-3" style={{ fontSize: '13pt' }}>Fiduciary Duties</h2>
              {QUICK_REFERENCE.duties.map((d, i) => (
                <div key={i} className="mb-3 pl-3 border-l-2 border-warning">
                  <div className="font-semibold text-gray-900" style={{ fontSize: '11pt' }}>{d.title}</div>
                  <div className="text-gray-600" style={{ fontSize: '10pt' }}>{d.text}</div>
                </div>
              ))}

              <h2 className="text-lg font-semibold text-gray-900 mb-3 mt-6" style={{ fontSize: '13pt' }}>Decision Filter</h2>
              <p className="text-gray-600 mb-2" style={{ fontSize: '10pt' }}>
                Before taking any action as trustee, ask yourself:
              </p>
              {QUICK_REFERENCE.decisionFilter.map((q, i) => (
                <div key={i} className="flex items-start gap-2 mb-1">
                  <span className="text-gold font-bold" style={{ fontSize: '10pt' }}>✓</span>
                  <span className="text-gray-700" style={{ fontSize: '10pt' }}>{q}</span>
                </div>
              ))}
              <p className="mt-2 text-gray-500 italic" style={{ fontSize: '9pt' }}>
                If you cannot answer "yes" confidently, seek professional guidance before proceeding.
              </p>

              <h2 className="text-lg font-semibold text-gray-900 mb-2 mt-6" style={{ fontSize: '13pt' }}>Signing Rule</h2>
              <p className="text-gray-700 bg-subtle-bg p-3" style={{ fontSize: '10pt' }}>
                {QUICK_REFERENCE.signingRule}
              </p>

              <h2 className="text-lg font-semibold text-gray-900 mb-2 mt-6" style={{ fontSize: '13pt' }}>Contact Your Attorney Immediately If:</h2>
              {QUICK_REFERENCE.emergency.map((e, i) => (
                <div key={i} className="flex items-start gap-2 mb-1">
                  <span className="text-red-500 font-bold" style={{ fontSize: '10pt' }}>⚠</span>
                  <span className="text-gray-700" style={{ fontSize: '10pt' }}>{e}</span>
                </div>
              ))}

              <div className="mt-8 pt-4 border-t border-gray-200 text-center">
                <p className="text-xs text-gray-400">TrustOffice — trustoffice.app</p>
              </div>
            </div>
          </div>
        )}

        {/* RESOLUTION TEMPLATE */}
        {activePrint === 'resolution' && (
          <div className="p-8" style={{ paddingLeft: '1.5in', paddingTop: '0.75in' }}>
            <div className="max-w-xl mx-auto">
              <h1 className="text-2xl font-bold text-center text-gray-900 mb-2" style={{ fontSize: '16pt' }}>
                RESOLUTION
              </h1>
              <h2 className="text-center text-gray-600 mb-8" style={{ fontSize: '12pt' }}>
                OF {coverData?.trust_name ? <span className="font-semibold">{coverData.trust_name.toUpperCase()}</span> : <span className="border-b border-gray-400" style={{ minWidth: '200px', display: 'inline-block' }}>&nbsp;</span>}
              </h2>

              <div className="mb-6">
                <p className="text-gray-600 mb-3" style={{ fontSize: '10pt' }}>WHEREAS, the Trustee(s) of the above-named Trust deem it necessary and appropriate to take the following action;</p>
                <div className="mb-6" style={{ fontSize: '10pt' }}>
                  <div className="border-b border-gray-300 py-2 text-gray-400">Describe the reason or background for this resolution</div>
                  <div className="border-b border-gray-300 py-2 text-gray-400">Continue background as needed</div>
                  <div className="border-b border-gray-300 py-2 text-gray-400">&nbsp;</div>
                </div>
              </div>

              <div className="mb-8">
                <p className="text-gray-600 mb-3" style={{ fontSize: '10pt' }}>NOW, THEREFORE, BE IT RESOLVED that the Trustee(s) hereby authorize and direct the following action:</p>
                <div style={{ fontSize: '10pt' }}>
                  <div className="border-b border-gray-300 py-2 text-gray-400">Describe the specific action being authorized</div>
                  <div className="border-b border-gray-300 py-2 text-gray-400">Continue description as needed</div>
                  <div className="border-b border-gray-300 py-2 text-gray-400">&nbsp;</div>
                  <div className="border-b border-gray-300 py-2 text-gray-400">&nbsp;</div>
                </div>
              </div>

              <div className="mt-16 space-y-8" style={{ fontSize: '10pt' }}>
                <div className="grid grid-cols-2 gap-8">
                  <div>
                    <div className="border-b border-gray-900 mb-1 h-8"></div>
                    <div className="text-gray-600">Trustee Signature</div>
                  </div>
                  <div>
                    <div className="border-b border-gray-900 mb-1 h-8"></div>
                    <div className="text-gray-600">Date</div>
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-8">
                  <div>
                    <div className="border-b border-gray-900 mb-1 h-8"></div>
                    <div className="text-gray-600">Printed Name</div>
                  </div>
                  <div>
                    <div className="border-b border-gray-900 mb-1 h-8"></div>
                    <div className="text-gray-600">Title (Trustee)</div>
                  </div>
                </div>
              </div>

              <div className="mt-12 pt-6 border-t border-gray-200">
                <h3 className="text-sm font-semibold text-gray-700 mb-3">Witness</h3>
                <div className="grid grid-cols-2 gap-8" style={{ fontSize: '10pt' }}>
                  <div>
                    <div className="border-b border-gray-900 mb-1 h-8"></div>
                    <div className="text-gray-600">Witness Signature</div>
                  </div>
                  <div>
                    <div className="border-b border-gray-900 mb-1 h-8"></div>
                    <div className="text-gray-600">Date</div>
                  </div>
                </div>
              </div>

              <div className="mt-10 pt-6 border-t border-gray-200">
                <h3 className="text-sm font-semibold text-gray-700 mb-3">Notary Acknowledgment</h3>
                <p className="text-gray-600 mb-4" style={{ fontSize: '9pt' }}>
                  State of _____________, County of _____________
                </p>
                <p className="text-gray-600 mb-4" style={{ fontSize: '9pt' }}>
                  On this _____ day of _____________, 20_____, before me personally appeared the above-named Trustee, known to me to be the person whose name is subscribed to the foregoing instrument, and acknowledged that they executed the same for the purposes therein contained.
                </p>
                <div className="grid grid-cols-2 gap-8" style={{ fontSize: '10pt' }}>
                  <div>
                    <div className="border-b border-gray-900 mb-1 h-8"></div>
                    <div className="text-gray-600">Notary Public Signature</div>
                  </div>
                  <div>
                    <div className="border-b border-gray-900 mb-1 h-8"></div>
                    <div className="text-gray-600">Commission Expiration</div>
                  </div>
                </div>
              </div>

              <div className="mt-6 text-center">
                <p className="text-xs text-gray-400">TrustOffice — trustoffice.app</p>
              </div>
            </div>
          </div>
        )}

        {/* REAL ESTATE TRANSFER CHECKLIST */}
        {activePrint === 'checklist-real-estate' && (
          <div className="p-8" style={{ paddingLeft: '1.5in', paddingTop: '0.75in' }}>
            <div className="max-w-lg mx-auto">
              <h1 className="text-2xl font-bold text-gray-900 mb-1" style={{ fontSize: '16pt' }}>
                Real Estate Transfer Checklist
              </h1>
              <p className="text-gray-500 mb-6" style={{ fontSize: '10pt' }}>
                {coverData?.trust_name || 'Trust Name: _______________'}
              </p>
              <div className="w-16 h-0.5 bg-gold mb-6"></div>

              {[
                'Obtain certified copy of the Trust Agreement',
                'Obtain Certification of Trust (summary of key provisions)',
                'Prepare deed transferring property to/from the Trust',
                'Record deed with County Recorder\'s Office',
                'Update property insurance to reflect Trust ownership (add Trust as additional insured)',
                'Notify mortgage company of Trust ownership',
                'Update property tax records with new ownership',
                'File any required state transfer tax forms or exemptions',
                'Store recorded deed in Section 5 of this binder',
              ].map((step, i) => (
                <div key={i} className="flex items-start gap-3 mb-3 py-2 border-b border-gray-100">
                  <div className="w-6 h-6 border-2 border-gray-300 rounded flex-shrink-0 mt-0.5"></div>
                  <span className="text-gray-700" style={{ fontSize: '11pt' }}>{step}</span>
                </div>
              ))}

              <div className="mt-8 p-3 bg-subtle-bg text-gray-500" style={{ fontSize: '9pt' }}>
                <strong>Note:</strong> Requirements vary by state. Some states require specific deed forms or have transfer tax exemptions for trusts. Consult your attorney before recording.
              </div>
              <div className="mt-4 text-center text-xs text-gray-400">TrustOffice — trustoffice.app</div>
            </div>
          </div>
        )}

        {/* VEHICLE TRANSFER CHECKLIST */}
        {activePrint === 'checklist-vehicle' && (
          <div className="p-8" style={{ paddingLeft: '1.5in', paddingTop: '0.75in' }}>
            <div className="max-w-lg mx-auto">
              <h1 className="text-2xl font-bold text-gray-900 mb-1" style={{ fontSize: '16pt' }}>
                Vehicle Transfer Checklist
              </h1>
              <p className="text-gray-500 mb-6" style={{ fontSize: '10pt' }}>
                {coverData?.trust_name || 'Trust Name: _______________'}
              </p>
              <div className="w-16 h-0.5 bg-warning mb-6"></div>

              {[
                'Obtain Certification of Trust',
                'Complete vehicle title transfer form (available from your state DMV)',
                'Visit DMV with: Certification of Trust, current title, completed transfer form, and valid ID',
                'Pay title transfer fees',
                'Update vehicle insurance to reflect Trust ownership (add Trust as additional insured)',
                'Update vehicle registration to show Trust as owner',
                'Store new title and registration documents in Section 5 of this binder',
              ].map((step, i) => (
                <div key={i} className="flex items-start gap-3 mb-3 py-2 border-b border-gray-100">
                  <div className="w-6 h-6 border-2 border-gray-300 rounded flex-shrink-0 mt-0.5"></div>
                  <span className="text-gray-700" style={{ fontSize: '11pt' }}>{step}</span>
                </div>
              ))}

              <div className="mt-8 p-3 bg-subtle-bg text-gray-500" style={{ fontSize: '9pt' }}>
                <strong>Note:</strong> Some states require the trust name to appear on the title exactly as stated in the trust document. Contact your DMV for specific requirements.
              </div>
              <div className="mt-4 text-center text-xs text-gray-400">TrustOffice — trustoffice.app</div>
            </div>
          </div>
        )}
      </div>
    </>
  );
};

export default PrintableBinderPage;