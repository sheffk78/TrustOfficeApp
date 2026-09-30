import React, { useEffect, useState } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { AlertCircle, CheckCircle2, Users } from 'lucide-react';
import { fetchWithAuth } from '@/utils/api';
import { useAuth } from '@/context/AuthContext';

const AcceptInvitePage = () => {
  const { token } = useParams();
  const navigate = useNavigate();
  const { user, loading: authLoading } = useAuth();
  const [status, setStatus] = useState('idle'); // idle | accepting | done | error
  const [errorMsg, setErrorMsg] = useState('');
  const [orgName, setOrgName] = useState('');
  const [inviterName, setInviterName] = useState('');

  useEffect(() => {
    if (!user || authLoading) return;
    if (status !== 'idle') return;
    const accept = async () => {
      setStatus('accepting');
      try {
        const res = await fetchWithAuth(`/orgs/invites/${encodeURIComponent(token || '')}/accept`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
        });
        if (!res.ok) {
          const data = await res.json().catch(() => ({}));
          const code = data?.detail?.code || '';
          if (res.status === 403 && code === 'invite_email_mismatch') {
            setErrorMsg(
              'This invite was sent to a different email address. Log in with the email that received the invitation, or contact the person who invited you for help.'
            );
          } else if (res.status === 404 || res.status === 410) {
            setErrorMsg('This invite link is no longer valid — it may have expired or already been used. Ask the person who invited you to send a fresh one.');
          } else {
            setErrorMsg('Something went wrong accepting your invite. Please try again, or reply to the email you received for help.');
          }
          setStatus('error');
          return;
        }
        const data = await res.json().catch(() => ({}));
        if (data && data.org_name) setOrgName(data.org_name);
        if (data && data.inviter_name) setInviterName(data.inviter_name);
        // The accept endpoint returns only member/org ids. Pull the real org
        // name + inviter name from the org members endpoints (a new member can
        // read both), so the page shows the actual org — never a hardcoded one.
        if (!orgName && data?.org_id) {
          try {
            const orgRes = await fetchWithAuth(`/orgs/${encodeURIComponent(data.org_id)}`);
            if (orgRes.ok) {
              const org = await orgRes.json().catch(() => ({}));
              if (org?.name) setOrgName(org.name);
            }
            const memRes = await fetchWithAuth(`/orgs/${encodeURIComponent(data.org_id)}/members`);
            if (memRes.ok) {
              const members = await memRes.json().catch(() => ([]));
              if (Array.isArray(members)) {
                const owner = members.find(m => m.role === 'owner') || null;
                if (owner?.name) setInviterName(owner.name);
              }
            }
          } catch { /* branding detail only — never block the accept flow */ }
        }
        setStatus('done');
      } catch (e) {
        setErrorMsg('Something went wrong accepting your invite. Please try again in a moment.');
        setStatus('error');
      }
    };
    accept();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user, authLoading, token]);

  if (authLoading || status === 'accepting') {
    return (
      <div className="min-h-screen bg-subtle-bg px-6 py-16 text-gray-900">
        <div className="mx-auto max-w-lg animate-pulse space-y-4">
          <div className="h-8 w-2/3 rounded bg-gray-200" />
          <div className="h-40 rounded bg-white shadow-sm" />
        </div>
      </div>
    );
  }

  if (!user) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-subtle-bg px-6 py-12 text-gray-900">
        <div className="w-full max-w-lg rounded border border-gray-200 bg-white p-8 text-center shadow-sm sm:p-12">
          <Users className="mx-auto mb-4 h-10 w-10 text-gold" aria-hidden="true" />
          <h1 className="mb-3 text-2xl font-bold">{orgName ? <>You're invited to {orgName}</> : "You're invited to TrustOffice"}</h1>
          <p className="mb-6 text-sm leading-6 text-gray-500">
            You've been invited to join your organization's workspace inside TrustOffice. One quick step: log in with the
            email this invitation was sent to, and your membership is confirmed automatically.
          </p>
          <Link
            to={`/login?invite=${encodeURIComponent(token || '')}`}
            data-testid="invite-login"
            className="inline-block bg-navy px-6 py-3 text-sm font-semibold text-white shadow-sm hover:opacity-90"
          >
            Log in to accept your invite
          </Link>
          <p className="mt-6 text-xs text-gray-400">
            New to TrustOffice? This invite works with the account tied to your email.
          </p>
        </div>
      </div>
    );
  }

  if (status === 'error') {
    return (
      <div className="flex min-h-screen items-center justify-center bg-subtle-bg px-6 py-12 text-gray-900">
        <div className="w-full max-w-lg rounded border border-gray-200 bg-white p-8 text-center shadow-sm sm:p-12">
          <AlertCircle className="mx-auto mb-4 h-10 w-10 text-gold" aria-hidden="true" />
          <h1 className="mb-3 text-2xl font-bold">We couldn't accept this invite</h1>
          <p className="text-sm leading-6 text-gray-500">{errorMsg}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-subtle-bg px-6 py-12 text-gray-900">
      <div className="w-full max-w-lg rounded border border-gray-200 bg-white p-8 text-center shadow-sm sm:p-12">
        <CheckCircle2 className="mx-auto mb-4 h-10 w-10 text-gold" aria-hidden="true" />
        <h1 className="mb-3 text-2xl font-bold">You're all set</h1>
        <p className="mb-6 text-sm leading-6 text-gray-500">
          You're now a member of <strong>{orgName || 'your organization'}</strong>.
          {inviterName
            ? <> {inviterName} invited you — the organization owner decides which clients' trusts you can work on and grants access from their side.</>
            : <> The organization owner decides which clients' trusts you can work on and grants access from their side.</>}
          {' '}Open the organization console to see what's been granted to you so far.
        </p>
        <button
          onClick={() => navigate('/org-console')}
          data-testid="invite-success-cta"
          className="inline-block bg-navy px-6 py-3 text-sm font-semibold text-white shadow-sm hover:opacity-90"
        >
          Go to your organization console
        </button>
      </div>
    </div>
  );
};

export default AcceptInvitePage;
