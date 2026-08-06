import { CHART_COLORS } from './constants';

// ========== PIE CHART COMPONENT ==========
export const OwnershipPieChart = ({ beneficiaries, totalAuthorized }) => {
  let gradientStops = [];
  let currentAngle = 0;

  beneficiaries.forEach((ben, index) => {
    const angle = (ben.percentage / 100) * 360;
    const color = CHART_COLORS[index % CHART_COLORS.length];
    gradientStops.push(`${color} ${currentAngle}deg ${currentAngle + angle}deg`);
    currentAngle += angle;
  });

  const totalIssued = beneficiaries.reduce((sum, b) => sum + b.percentage, 0);
  if (totalIssued < 100) {
    gradientStops.push(`#e5e7eb ${currentAngle}deg 360deg`);
  }

  const gradient = `conic-gradient(${gradientStops.join(', ')})`;

  return (
    <div className="flex flex-col items-center">
      <div className="w-48 h-48 rounded-full shadow-inner" style={{ background: gradient }} />
      <div className="mt-4 grid grid-cols-2 gap-x-6 gap-y-2 text-sm">
        {beneficiaries.slice(0, 6).map((ben, index) => (
          <div key={ben.holder_name} className="flex items-center gap-2">
            <div className="w-3 h-3 flex-shrink-0" style={{ backgroundColor: CHART_COLORS[index % CHART_COLORS.length] }} />
            <span className="truncate max-w-[120px]" title={ben.holder_name}>{ben.holder_name}</span>
            <span className="font-mono text-xs text-muted-foreground">{ben.percentage.toFixed(1)}%</span>
          </div>
        ))}
        {beneficiaries.length > 6 && (
          <div className="col-span-2 text-muted-foreground text-xs mt-1">+{beneficiaries.length - 6} more holders</div>
        )}
        {totalIssued < 100 && (
          <div className="flex items-center gap-2">
            <div className="w-3 h-3 flex-shrink-0 bg-muted" />
            <span>Unissued</span>
            <span className="font-mono text-xs text-muted-foreground">{(100 - totalIssued).toFixed(1)}%</span>
          </div>
        )}
      </div>
    </div>
  );
};

export default OwnershipPieChart;