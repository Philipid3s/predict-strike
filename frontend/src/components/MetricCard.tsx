import type { ReactNode } from 'react';

interface MetricCardProps {
  label: string;
  value: string;
  detail?: string;
  accent?: ReactNode;
  action?: ReactNode;
}

export function MetricCard({ label, value, detail, accent, action }: MetricCardProps) {
  return (
    <article className="metric-card">
      <div className="metric-card__header">
        <p className="metric-card__label">{label}</p>
        <div className="metric-card__header-right">
          {action ? <div className="metric-card__action">{action}</div> : null}
          {accent ? <div className="metric-card__accent">{accent}</div> : null}
        </div>
      </div>
      <p className="metric-card__value">{value}</p>
      {detail ? <p className="metric-card__detail">{detail}</p> : null}
    </article>
  );
}
