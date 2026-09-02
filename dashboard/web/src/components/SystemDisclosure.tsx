import type { ReactNode } from "react";

type Props = {
  title: string;
  summary: string;
  status?: string;
  children: ReactNode;
};

export function SystemDisclosure({ title, summary, status, children }: Props) {
  return (
    <details className="system-disclosure">
      <summary>
        <span>
          <strong>{title}</strong>
          <small>{summary}</small>
        </span>
        {status ? <em>{status}</em> : null}
        <i aria-hidden="true">+</i>
      </summary>
      <div className="system-disclosure-body">{children}</div>
    </details>
  );
}
