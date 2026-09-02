import { useState } from "react";
import { faviconUrl, initials } from "../lib/format";

type Props = { company: string; domain?: string | null; url?: string | null; size?: "sm" | "md" };

export function CompanyLogo({ company, domain, url, size = "md" }: Props) {
  const src = url || faviconUrl(domain ?? null);
  const [failed, setFailed] = useState(false);
  const cls = `logo ${size === "sm" ? "sm" : ""}`;
  if (!src || failed) {
    return <span className={cls}>{initials(company)}</span>;
  }
  return (
    <span className={cls}>
      <img src={src} alt="" loading="lazy" onError={() => setFailed(true)} />
    </span>
  );
}
