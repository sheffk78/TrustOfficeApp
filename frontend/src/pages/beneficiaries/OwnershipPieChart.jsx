import { CHART_COLORS } from './constants';

// ========== PIE CHART COMPONENT ==========
// Accepts beneficiaries (person/org holders) and optional classBeneficiaries.
//
// Semantics: certificates are ISSUED ownership — they sum toward 100%.
// Class beneficiaries are RESERVED pools that may OVERLAP with issued
// certificates (a contingent "Descendants" class can include members who
// already hold certificates). They are therefore NOT rendered as additional
// pie slices (that would double-count past 100%); instead the chart shows
// issued ownership as slices, with reserved class coverage drawn as a ring
// segment overlay, and both layers listed in the legend.
export const OwnershipPieChart = ({ beneficiaries, totalAuthorized, classBeneficiaries = [] }) => {
  let gradientStops = [];
  let currentAngle = 0;

  const entries = beneficiaries.map(b => ({
    label: b.holder_name,
    percentage: b.percentage,
    isClass: false,
  }));

  entries.forEach((entry, index) => {
    const angle = (entry.percentage / 100) * 360;
    if (angle <= 0) return;
    const color = CHART_COLORS[index % CHART_COLORS.length];
    gradientStops.push(`${color} ${currentAngle}deg ${currentAngle + angle}deg`);
    currentAngle += angle;
  });

  const totalIssuedPct = entries.reduce((sum, e) => sum + e.percentage, 0);
  if (totalIssuedPct < 100) {
    gradientStops.push(`#e5e7eb ${currentAngle}deg 360deg`);
  }

  // Reserved class coverage as a fraction of the circle (capped at 100 for
  // drawing; individual pool sizes still shown in the legend).
  const totalClassPct = Math.min(
    100,
    classBeneficiaries.reduce((sum, cb) => sum + (cb.percentage || 0), 0)
  );

  const gradient = `conic-gradient(${gradientStops.join(', ')})`;
  const ringGradient = `conic-gradient(rgba(0,0,0,0.35) 0deg ${(totalClassPct / 100) * 360}deg, transparent ${(totalClassPct / 100) * 360}deg 360deg)`;

  return (
    <div className="flex flex-col items-center">
      <div className="relative w-48 h-48">
        <div className="w-48 h-48 rounded-full shadow-inner" style={{ background: gradient }} />
        {classBeneficiaries.length > 0 && (
          <div
            className="absolute inset-1 w-[11.5rem] h-[11.5rem] rounded-full border-2 border-dashed border-navy/50 dark:border-gold/60 pointer-events-none"
            title={`Reserved class pools: ${totalClassPct}%`}
            aria-hidden="true"
          />
        )}
      </div>
      <div className="mt-4 grid grid-cols-2 gap-x-6 gap-y-2 text-sm">
        {entries.slice(0, 6).map((entry, index) => (
          <div key={`${entry.label}-${index}`} className="flex items-center gap-2">
            <div
              className="w-3 h-3 flex-shrink-0"
              style={{ backgroundColor: CHART_COLORS[index % CHART_COLORS.length] }}
            />
            <span className="truncate max-w-[120px]" title={entry.label}>{entry.label}</span>
            <span className="font-mono text-xs text-muted-foreground">{entry.percentage.toFixed(1)}%</span>
          </div>
        ))}
        {entries.length > 6 && (
          <div className="col-span-2 text-muted-foreground text-xs mt-1">+{entries.length - 6} more</div>
        )}
        {totalIssuedPct < 100 && (
          <div className="flex items-center gap-2">
            <div className="w-3 h-3 flex-shrink-0 bg-muted" />
            <span>Unissued</span>
            <span className="font-mono text-xs text-muted-foreground">{(100 - totalIssuedPct).toFixed(1)}%</span>
          </div>
        )}
        {/* Class pools listed separately — reservations, not pie slices */}
        {classBeneficiaries.map(cb => (
          <div key={cb.class_beneficiary_id} className="flex items-center gap-2">
            <div className="w-3 h-3 flex-shrink-0 rounded-full border-2 border-dashed border-navy/50 dark:border-gold/60" />
            <span className="truncate max-w-[120px]" title={cb.class_type_label || cb.class_type}>
              {cb.class_type_label || cb.class_type}
            </span>
            <span className="font-mono text-xs text-muted-foreground">
              {Number(cb.percentage || 0).toFixed(1)}%
              <span className="text-[10px] ml-1 uppercase">res.</span>
            </span>
          </div>
        ))}
      </div>
      {classBeneficiaries.length > 0 && (
        <p className="mt-3 text-[10px] text-muted-foreground text-center max-w-[220px]">
          Dashed ring = reserved class pools. Classes may overlap certificate holders and are not additive to issued shares.
        </p>
      )}
    </div>
  );
};

export default OwnershipPieChart;
