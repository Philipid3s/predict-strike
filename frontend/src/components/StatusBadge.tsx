interface StatusBadgeProps {
  tone: 'neutral' | 'info' | 'positive' | 'warning' | 'danger';
  children: string;
}

export function StatusBadge({ tone, children }: StatusBadgeProps) {
  return <span className={`status-badge status-badge--${tone}`}>{children}</span>;
}
