export function formatPercent(value: number, digits = 0): string {
  return `${(value * 100).toFixed(digits)}%`;
}

export function formatSignedPoints(value: number): string {
  const points = (value * 100).toFixed(1);
  return `${value >= 0 ? '+' : ''}${points} pts`;
}

export function formatDateTime(value: string | null | undefined): string {
  if (!value) {
    return '—';
  }

  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }

  return new Intl.DateTimeFormat(undefined, {
    year: 'numeric',
    month: 'short',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(parsed);
}

export function titleCase(value: string): string {
  return value.charAt(0).toUpperCase() + value.slice(1);
}

export function labelizeFeature(name: string): string {
  return name
    .split('_')
    .map((segment) => titleCase(segment))
    .join(' ');
}
