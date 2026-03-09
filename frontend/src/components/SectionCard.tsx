import type { PropsWithChildren, ReactNode } from 'react';

interface SectionCardProps extends PropsWithChildren {
  title: string;
  subtitle?: string;
  action?: ReactNode;
}

export function SectionCard({ title, subtitle, action, children }: SectionCardProps) {
  return (
    <section className="section-card">
      <div className="section-card__header">
        <div>
          <h2>{title}</h2>
          {subtitle ? <p>{subtitle}</p> : null}
        </div>
        {action ? <div className="section-card__action">{action}</div> : null}
      </div>
      {children}
    </section>
  );
}
