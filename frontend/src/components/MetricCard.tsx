import type { ReactNode } from 'react';

interface MetricCardProps {
  label: string;
  value: string;
  detail?: string;
  accent?: ReactNode;
}

export function MetricCard({ label, value, detail, accent }: MetricCardProps) {
  return (
    <article className="metric-card">
      <div className="metric-card__header">
        <p className="metric-card__label">{label}</p>
        {accent ? <div className="metric-card__accent">{accent}</div> : null}
      </div>
      <p className="metric-card__value">{value}</p>
      {detail ? <p className="metric-card__detail">{detail}</p> : null}
    </article>
  );
}
