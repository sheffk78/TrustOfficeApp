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
  const [orgName, setOrgName] = useState('WingPoint Trust Group');

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
              'This invite was sent to a different email address. Log in with the email that received the invitation, or contact Jeff for help.'
            );
          } else if (res.status === 404 || res.status === 410) {
            setErrorMsg('This invite link is no longer valid — it may have expired or already been used. Ask Jeff to send a fresh one.');
          } else {
            setErrorMsg('Something went wrong accepting your invite. Please try again, or reply to the email you received for help.');
          }
          setStatus('error');
          return;
        }
        const data = await res.json().catch(() => ({}));
        if (data && data.org_name) setOrgName(data.org_name);
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
          <h1 className="mb-3 text-2xl font-bold">You're invited to {orgName}</h1>
          <p className="mb-6 text-sm leading-6 text-gray-500">
            Jeff Kohler has invited you to connect with his desk inside TrustOffice. One quick step: log in with the
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
          You're now a member of <strong>{orgName}</strong>. Your connection to Jeff's desk is confirmed — you decide
          the access level, and you can change or remove it any time.
        </p>
        <button
          onClick={() => navigate('/trust-access')}
          data-testid="invite-success-cta"
          className="inline-block bg-navy px-6 py-3 text-sm font-semibold text-white shadow-sm hover:opacity-90"
        >
          Choose your access level
        </button>
      </div>
    </div>
  );
};

export default AcceptInvitePage;
