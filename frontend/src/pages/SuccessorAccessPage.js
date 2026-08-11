import React, { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import {
  AlertCircle, BookOpen, Building2, Calendar, CheckCircle2, ClipboardList,
  FileText, Landmark, Shield, Users,
} from 'lucide-react';
import { API } from '@/utils/api';

const fmtDate = (value) => {
  if (!value) return '';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleDateString('en-US', {
    year: 'numeric', month: 'long', day: 'numeric',
  });
};

const display = (value) => {
  if (value === null || value === undefined || value === '') return 'Not specified';
  if (typeof value === 'boolean') return value ? 'Yes' : 'No';
  return String(value);
};

const InfoRow = ({ label, value }) => (
  <div className="flex flex-col gap-1 border-b border-gray-100 py-3 sm:flex-row sm:gap-4">
    <div className="w-full flex-shrink-0 text-sm text-gray-500 sm:w-44">{label}</div>
    <div className="whitespace-pre-wrap break-words text-sm font-medium text-gray-900">{display(value)}</div>
  </div>
);

const SectionTitle = ({ icon: Icon, title }) => (
  <div className="mb-4 flex items-center gap-2">
    <Icon className="h-5 w-5 text-gold" aria-hidden="true" />
    <h2 className="text-lg font-bold text-gray-900">{title}</h2>
  </div>
);

const EmptyState = ({ children = 'No information was provided for this section.' }) => (
  <p className="text-sm italic text-gray-400">{children}</p>
);

const DataTable = ({ columns, rows, emptyText }) => {
  if (!rows.length) return <EmptyState>{emptyText}</EmptyState>;
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[520px] border-collapse">
        <thead>
          <tr className="border-b-2 border-gray-200">
            {columns.map(({ label }) => (
              <th key={label} className="px-2 py-2 text-left text-xs font-semibold uppercase tracking-wide text-gray-500">{label}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr key={row.id || index} className="border-b border-gray-100 last:border-0">
              {columns.map(({ key, format }) => (
                <td key={key} className="px-2 py-3 text-sm text-gray-700">{display(format ? format(row[key], row) : row[key])}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};

const SuccessorAccessPage = () => {
  const { token } = useParams();
  const [packet, setPacket] = useState(null);
  const [status, setStatus] = useState('loading');
  const [errorStatus, setErrorStatus] = useState(null);

  useEffect(() => {
    let cancelled = false;
    const loadPacket = async () => {
      try {
        const response = await fetch(`${API}/successor-access/${encodeURIComponent(token || '')}`, {
          method: 'GET',
          headers: { Accept: 'application/json' },
        });
        if (!response.ok) {
          if (!cancelled) {
            setErrorStatus(response.status);
            setStatus('error');
          }
          return;
        }
        const data = await response.json();
        if (!cancelled) {
          setPacket(data);
          setStatus('success');
        }
      } catch {
        if (!cancelled) {
          setErrorStatus('network');
          setStatus('error');
        }
      }
    };
    loadPacket();
    return () => { cancelled = true; };
  }, [token]);

  if (status === 'loading') {
    return (
      <div className="min-h-screen bg-subtle-bg px-6 py-16 text-gray-900">
        <div className="mx-auto max-w-3xl animate-pulse space-y-6">
          <div className="h-8 w-2/3 rounded bg-gray-200" />
          <div className="h-4 w-1/2 rounded bg-gray-200" />
          <div className="h-52 rounded bg-white shadow-sm" />
          <div className="h-52 rounded bg-white shadow-sm" />
        </div>
      </div>
    );
  }

  if (status === 'error') {
    const invalidLink = errorStatus === 404 || errorStatus === 410;
    return (
      <div className="flex min-h-screen items-center justify-center bg-subtle-bg px-6 py-12 text-gray-900">
        <div className="w-full max-w-lg rounded border border-gray-200 bg-white p-8 text-center shadow-sm sm:p-12">
          <AlertCircle className="mx-auto mb-4 h-10 w-10 text-gold" aria-hidden="true" />
          <h1 className="mb-3 text-2xl font-bold">{invalidLink ? 'This link is no longer valid' : 'We could not load this packet'}</h1>
          <p className="text-sm leading-6 text-gray-500">
            {invalidLink
              ? 'It may have expired or already been used. If you need access, ask the current trustee to send you a new link.'
              : 'Please try again in a moment. If the problem continues, ask the current trustee to send you a new link.'}
          </p>
        </div>
      </div>
    );
  }

  const trust = packet.trust || {};
  const entities = Array.isArray(packet.entities) ? packet.entities : [];
  const beneficiaries = Array.isArray(packet.beneficiaries) ? packet.beneficiaries : [];
  const bankAccounts = Array.isArray(packet.bank_accounts) ? packet.bank_accounts : [];
  const vaultDocuments = Array.isArray(packet.vault_documents) ? packet.vault_documents : [];
  const governanceTasks = Array.isArray(packet.governance_tasks) ? packet.governance_tasks : [];
  const taxCalendar = Array.isArray(packet.tax_calendar) ? packet.tax_calendar : [];
  const trustName = packet.trust_name || trust.name || 'Trust packet';

  return (
    <div className="min-h-screen bg-subtle-bg px-4 py-8 text-gray-900 sm:px-6 sm:py-12">
      <main className="mx-auto max-w-4xl">
        <header className="mb-8 border-b border-gray-200 pb-8">
          <div className="mb-5 text-xs font-semibold uppercase tracking-[0.2em] text-gold">TrustOffice</div>
          <h1 className="text-3xl font-bold tracking-tight text-gray-900 sm:text-4xl">{trustName}</h1>
          <p className="mt-2 text-lg text-gray-500">Successor information for {packet.successor_name || 'you'}</p>
          <div className="mt-6 flex items-start gap-3 rounded border border-gold/30 bg-gold/5 p-4 text-sm leading-6 text-gray-700">
            <CheckCircle2 className="mt-0.5 h-5 w-5 flex-shrink-0 text-gold" aria-hidden="true" />
            <p>You don&apos;t need to do anything right now. This packet is here so you have the information you may need if you ever step into the successor trustee role.</p>
          </div>
        </header>

        <div className="space-y-5">
          <section className="rounded border border-gray-200 bg-white p-5 shadow-sm sm:p-6">
            <SectionTitle icon={FileText} title="Trust Details" />
            <InfoRow label="Trust name" value={trust.name || packet.trust_name} />
            <InfoRow label="Trust type" value={trust.trust_type} />
            <InfoRow label="Formation date" value={fmtDate(trust.start_date || trust.formation_date)} />
            <InfoRow label="Jurisdiction" value={trust.jurisdiction || trust.state_code} />
            <InfoRow label="Current trustee" value={packet.trustee_name || trust.trustees} />
            <InfoRow label="Description" value={trust.description} />
          </section>

          <section className="rounded border border-gray-200 bg-white p-5 shadow-sm sm:p-6">
            <SectionTitle icon={Building2} title="Entities" />
            {entities.length ? <div className="space-y-3">{entities.map((entity, index) => <div key={entity.id || index} className="rounded bg-gray-50 p-4"><div className="font-semibold text-gray-900">{entity.name || entity.legal_name || 'Entity'}</div><div className="mt-1 text-sm text-gray-500">{[entity.entity_type && `Type: ${entity.entity_type}`, entity.ein && `EIN: ${entity.ein}`, entity.governing_law && `Governing law: ${entity.governing_law}`].filter(Boolean).join(' · ') || 'No additional details provided'}</div></div>)}</div> : <EmptyState />}
          </section>

          <section className="rounded border border-gray-200 bg-white p-5 shadow-sm sm:p-6"><SectionTitle icon={Users} title="Beneficiaries" /><DataTable columns={[{ label: 'Name', key: 'holder_name' }, { label: 'Email', key: 'email' }, { label: 'Phone', key: 'phone' }, { label: 'Share', key: 'units' }]} rows={beneficiaries} emptyText="No beneficiary records were provided." /></section>

          <section className="rounded border border-gray-200 bg-white p-5 shadow-sm sm:p-6"><SectionTitle icon={Landmark} title="Bank Accounts" /><DataTable columns={[{ label: 'Account', key: 'account', format: (_, row) => row.nickname || row.name }, { label: 'Institution', key: 'institution_name', format: (_, row) => row.institution_name }, { label: 'Type', key: 'account_type', format: (_, row) => row.account_type || row.type }, { label: 'Last four', key: 'last_four', format: (_, row) => row.last_four || row.last4 ? `•••• ${row.last_four || row.last4}` : '' }]} rows={bankAccounts} emptyText="No bank account records were provided." /></section>

          <section className="rounded border border-gray-200 bg-white p-5 shadow-sm sm:p-6"><SectionTitle icon={ClipboardList} title="Vault Documents" /><DataTable columns={[{ label: 'Document', key: 'name', format: (_, row) => row.name || row.title || row.filename }, { label: 'Category', key: 'category', format: (_, row) => row.category || row.document_type }, { label: 'Added', key: 'date', format: (_, row) => fmtDate(row.uploaded_at || row.date || row.created_at) }]} rows={vaultDocuments} emptyText="No vault documents were provided." /></section>

          <section className="rounded border border-gray-200 bg-white p-5 shadow-sm sm:p-6"><SectionTitle icon={Shield} title="Governance Tasks" /><DataTable columns={[{ label: 'Task', key: 'title', format: (_, row) => row.title || row.task_type }, { label: 'Due', key: 'due_date', format: fmtDate }]} rows={governanceTasks} emptyText="No governance tasks were provided." /></section>

          <section className="rounded border border-gray-200 bg-white p-5 shadow-sm sm:p-6"><SectionTitle icon={Calendar} title="Tax Calendar" /><DataTable columns={[{ label: 'Deadline', key: 'deadline', format: (_, row) => row.deadline_type || row.title }, { label: 'Due', key: 'due_date', format: fmtDate }]} rows={taxCalendar} emptyText="No tax calendar entries were provided." /></section>

          <section className="rounded border border-gray-200 bg-white p-5 shadow-sm sm:p-6"><SectionTitle icon={BookOpen} title="Successor Instructions" /><div className="whitespace-pre-wrap text-sm leading-7 text-gray-700">{packet.successor_instructions || <EmptyState>No successor instructions were provided.</EmptyState>}</div></section>
        </div>

        <footer className="mt-8 border-t border-gray-200 pt-6 text-center text-xs leading-5 text-gray-400">This is operational information, not legal advice. Please consult qualified legal and tax professionals for guidance about your responsibilities.</footer>
      </main>
    </div>
  );
};

export default SuccessorAccessPage;
