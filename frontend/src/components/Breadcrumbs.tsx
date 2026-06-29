/**
 * Shared breadcrumb navigation. Each page passes its trail, root → current;
 * every item except the last is a link, so users can step back up the
 * hierarchy (Network → Site → Projections, etc.).
 */

import { Link } from "react-router-dom";

export type Crumb = { label: string; to?: string };

export function Breadcrumbs({ items }: { items: Crumb[] }) {
  return (
    <nav className="mb-4 text-sm text-slate-500" aria-label="Breadcrumb">
      <ol className="flex flex-wrap items-center gap-1">
        {items.map((c, i) => {
          const last = i === items.length - 1;
          return (
            <li key={`${c.label}-${i}`} className="flex items-center gap-1">
              {i > 0 && (
                <span className="text-slate-400" aria-hidden>
                  /
                </span>
              )}
              {c.to && !last ? (
                <Link to={c.to} className="hover:underline">
                  {c.label}
                </Link>
              ) : (
                <span
                  className={last ? "font-medium text-slate-800" : undefined}
                  aria-current={last ? "page" : undefined}
                >
                  {c.label}
                </span>
              )}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
