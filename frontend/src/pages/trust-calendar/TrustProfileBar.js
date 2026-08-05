// Trust profile info bar: shows EIN + tax year end (or a prompt to set them
// in Settings → Trust Profile). Only rendered when the current filter includes
// tax deadlines and there are tax events in the filtered set.
//
// Props:
//   trustProfile    – { ein, stateCode, taxYearEndMonth, taxYearEndDay, isFiscalYear }
//   hasTaxInFilter  – boolean (filteredEvents.some(e => e.event_type === 'tax_deadline'))
export default function TrustProfileBar({ trustProfile, hasTaxInFilter }) {
  if (!hasTaxInFilter) return null;

  const hasEinAndMonth = trustProfile.ein && trustProfile.taxYearEndMonth;

  return (
    <div className="mb-4 bg-white border border-navy/10 px-4 py-2.5" data-testid="trust-profile-bar">
      <div className="text-sm text-muted-foreground truncate">
        {hasEinAndMonth ? (
          <>
            EIN: <b className="text-navy">{trustProfile.ein}</b> · {' '}
            {trustProfile.isFiscalYear ? 'Fiscal year ends' : 'Tax year ends'}: {' '}
            <b className="text-navy">{trustProfile.taxYearEndMonth}/{trustProfile.taxYearEndDay}</b>
            {trustProfile.isFiscalYear && (
              <span className="ml-2 text-xs bg-warning/10 text-warning px-1.5 py-0.5">Fiscal</span>
            )}
          </>
        ) : (
          <>Set your trust EIN and tax year end in <b className="text-navy">Settings → Trust Profile</b> for accurate deadlines.</>
        )}
      </div>
    </div>
  );
}