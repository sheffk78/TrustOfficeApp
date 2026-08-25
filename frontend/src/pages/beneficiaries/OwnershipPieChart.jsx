import { CHART_COLORS } from './constants';

// ========== OWNERSHIP DISTRIBUTION CHART ==========
// Accepts beneficiaries (person/org holders) and optional classBeneficiaries.
//
// Semantics: certificates are ISSUED ownership — they sum toward 100%.
// Class beneficiaries are RESERVED pools that may OVERLAP with issued
// certificates (a contingent "Descendants" class can include members who
// already hold certificates). They are therefore NOT rendered as additional
// slices/segments (that would double-count past 100%); instead reserved
// class coverage is drawn as a dashed-ring overlay, and both layers are
// listed in the legend.
//
// Visualization by holder count:
//   - 1 holder: "seal / stamp" — solid circle with the holder's name and
//     percentage in the center, wrapped in decorative rings.
//   - 2 holders: horizontal proportional split bar.
//   - 3+ holders: conic-gradient pie chart.

const Legend = ({ entries, totalIssuedPct, classBeneficiaries }) => (
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
    {/* Class pools listed separately — reservations, not chart segments */}
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
);

const ClassRingNote = ({ classBeneficiaries }) =>
  classBeneficiaries.length > 0 ? (
    <p className="mt-3 text-[10px] text-muted-foreground text-center max-w-[220px]">
      Dashed ring = reserved class pools. Classes may overlap certificate holders and are not additive to issued shares.
    </p>
  ) : null;

// --- Single holder: seal/stamp visualization ---
const SealChart = ({ entry, totalIssuedPct, classBeneficiaries }) => {
  const color = CHART_COLORS[0];
  const partial = totalIssuedPct < 100;
  return (
    <div className="flex flex-col items-center">
      <div className="relative w-48 h-48 flex items-center justify-center">
        {/* Outer decorative ring */}
        <div
          className="absolute inset-0 rounded-full border-4 opacity-30"
          style={{ borderColor: color }}
          aria-hidden="true"
        />
        {/* Dotted inner accent ring */}
        <div
          className="absolute inset-2 rounded-full border border-dotted opacity-40"
          style={{ borderColor: color }}
          aria-hidden="true"
        />
        {/* Solid seal face */}
        <div
          className={`absolute inset-5 rounded-full shadow-inner flex flex-col items-center justify-center text-center px-4 ${partial ? 'opacity-80' : ''}`}
          style={{ backgroundColor: color }}
        >
          <span className="font-serif text-lg leading-tight text-white break-words line-clamp-3 max-w-full drop-shadow-sm">
            {entry.label}
          </span>
          <span className="font-mono text-2xl font-bold text-white mt-1 tracking-wider drop-shadow-sm">
            {totalIssuedPct.toFixed(0)}%
          </span>
          <span className="text-[9px] uppercase tracking-widest font-mono text-white/80 mt-0.5">
            {partial ? 'Partially Issued' : 'Sole Holder'}
          </span>
        </div>
        {classBeneficiaries.length > 0 && (
          <div
            className="absolute inset-1 w-[11.5rem] h-[11.5rem] rounded-full border-2 border-dashed border-navy/50 dark:border-gold/60 pointer-events-none"
            title={`Reserved class pools: ${Math.min(100, classBeneficiaries.reduce((s, cb) => s + (cb.percentage || 0), 0))}%`}
            aria-hidden="true"
          />
        )}
      </div>
      <Legend entries={[entry]} totalIssuedPct={totalIssuedPct} classBeneficiaries={classBeneficiaries} />
      <ClassRingNote classBeneficiaries={classBeneficiaries} />
    </div>
  );
};

// --- Two holders: proportional split bar ---
const SplitBarChart = ({ entries, totalIssuedPct, classBeneficiaries }) => {
  const issuedEntries = entries.filter(e => e.percentage > 0);
  const unissued = Math.max(0, 100 - totalIssuedPct);
  return (
    <div className="flex flex-col items-center w-full">
      <div
        className="relative w-full h-16 flex overflow-hidden shadow-inner border border-border"
        role="img"
        aria-label={`Ownership split: ${entries.map(e => `${e.label} ${e.percentage.toFixed(1)}%`).join(', ')}`}
      >
        {issuedEntries.map((entry, index) => (
          <div
            key={`${entry.label}-${index}`}
            className="h-full flex items-center justify-center transition-all"
            style={{
              width: `${entry.percentage}%`,
              backgroundColor: CHART_COLORS[index % CHART_COLORS.length],
            }}
            title={`${entry.label}: ${entry.percentage.toFixed(1)}%`}
          >
            <span className="px-2 text-xs font-medium text-white truncate max-w-full drop-shadow-sm">
              {entry.label}
            </span>
          </div>
        ))}
        {unissued > 0 && (
          <div
            className="h-full flex items-center justify-center bg-muted"
            style={{ width: `${unissued}%` }}
            title={`Unissued: ${unissued.toFixed(1)}%`}
          >
            <span className="px-2 text-xs text-muted-foreground">Unissued</span>
          </div>
        )}
        {/* Divider ticks at the boundary for a crisp two-party read */}
        {issuedEntries.length === 2 && unissued === 0 && (
          <div className="absolute top-0 bottom-0 left-1/2 w-px bg-background/70" aria-hidden="true" />
        )}
      </div>
      <Legend entries={entries} totalIssuedPct={totalIssuedPct} classBeneficiaries={classBeneficiaries} />
      <ClassRingNote classBeneficiaries={classBeneficiaries} />
    </div>
  );
};

export const OwnershipPieChart = ({ beneficiaries, totalAuthorized, classBeneficiaries = [] }) => {
  const entries = beneficiaries.map(b => ({
    label: b.holder_name,
    percentage: b.percentage,
    isClass: false,
  }));

  const totalIssuedPct = entries.reduce((sum, e) => sum + e.percentage, 0);

  // Reserved class coverage as a fraction of the circle (capped at 100 for
  // drawing; individual pool sizes still shown in the legend).
  const totalClassPct = Math.min(
    100,
    classBeneficiaries.reduce((sum, cb) => sum + (cb.percentage || 0), 0)
  );

  // Pick visualization by holder count. 1 → seal/stamp, 2 → split bar, 3+ → pie.
  if (entries.length <= 1) {
    const sole = entries[0] || { label: 'Unallocated', percentage: 0 };
    return (
      <SealChart
        entry={sole}
        totalIssuedPct={entries.length ? totalIssuedPct : 0}
        classBeneficiaries={classBeneficiaries}
      />
    );
  }

  if (entries.length === 2) {
    return (
      <SplitBarChart
        entries={entries}
        totalIssuedPct={totalIssuedPct}
        classBeneficiaries={classBeneficiaries}
      />
    );
  }

  // --- Pie chart (3+ holders) ---
  let gradientStops = [];
  let currentAngle = 0;

  entries.forEach((entry, index) => {
    const angle = (entry.percentage / 100) * 360;
    if (angle <= 0) return;
    const color = CHART_COLORS[index % CHART_COLORS.length];
    gradientStops.push(`${color} ${currentAngle}deg ${currentAngle + angle}deg`);
    currentAngle += angle;
  });

  if (totalIssuedPct < 100) {
    gradientStops.push(`#e5e7eb ${currentAngle}deg 360deg`);
  }

  const gradient = `conic-gradient(${gradientStops.join(', ')})`;

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
      <Legend entries={entries} totalIssuedPct={totalIssuedPct} classBeneficiaries={classBeneficiaries} />
      <ClassRingNote classBeneficiaries={classBeneficiaries} />
    </div>
  );
};

export default OwnershipPieChart;
