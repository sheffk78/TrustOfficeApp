import { CHART_COLORS } from './constants';

// ========== PIE CHART COMPONENT ==========
// Accepts beneficiaries (person/org holders) and optional classBeneficiaries.
// Renders both on the same pie chart so the full allocation picture is visible.
export const OwnershipPieChart = ({ beneficiaries, totalAuthorized, classBeneficiaries = [] }) => {
  let gradientStops = [];
  let currentAngle = 0;

  // Combine person/org holders with class beneficiaries into one chart.
  // Person/org entries use `percentage`; class entries use `percentage` as a
  // reserved pool. We render them in order: persons first, then classes.
  const allEntries = [
    ...beneficiaries.map(b => ({
      label: b.holder_name,
      percentage: b.percentage,
      isClass: false,
    })),
    ...classBeneficiaries.map(cb => ({
      label: cb.class_type_label || cb.class_type,
      percentage: cb.percentage,
      isClass: true,
    })),
  ];

  allEntries.forEach((entry, index) => {
    const angle = (entry.percentage / 100) * 360;
    if (angle <= 0) return;
    const color = CHART_COLORS[index % CHART_COLORS.length];
    gradientStops.push(`${color} ${currentAngle}deg ${currentAngle + angle}deg`);
    currentAngle += angle;
  });

  const totalShown = allEntries.reduce((sum, e) => sum + e.percentage, 0);
  if (totalShown < 100) {
    gradientStops.push(`#e5e7eb ${currentAngle}deg 360deg`);
  }

  const gradient = `conic-gradient(${gradientStops.join(', ')})`;

  return (
    <div className="flex flex-col items-center">
      <div className="w-48 h-48 rounded-full shadow-inner" style={{ background: gradient }} />
      <div className="mt-4 grid grid-cols-2 gap-x-6 gap-y-2 text-sm">
        {allEntries.slice(0, 6).map((entry, index) => (
          <div key={`${entry.label}-${index}`} className="flex items-center gap-2">
            <div
              className="w-3 h-3 flex-shrink-0"
              style={{ backgroundColor: CHART_COLORS[index % CHART_COLORS.length] }}
            />
            <span className="truncate max-w-[120px]" title={entry.label}>{entry.label}</span>
            <span className="font-mono text-xs text-muted-foreground">{entry.percentage.toFixed(1)}%</span>
          </div>
        ))}
        {allEntries.length > 6 && (
          <div className="col-span-2 text-muted-foreground text-xs mt-1">+{allEntries.length - 6} more</div>
        )}
        {totalShown < 100 && (
          <div className="flex items-center gap-2">
            <div className="w-3 h-3 flex-shrink-0 bg-muted" />
            <span>Unissued</span>
            <span className="font-mono text-xs text-muted-foreground">{(100 - totalShown).toFixed(1)}%</span>
          </div>
        )}
      </div>
    </div>
  );
};

export default OwnershipPieChart;