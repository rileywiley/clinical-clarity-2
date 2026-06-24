/** Small effect that mirrors a string into document.title for each page. */

import { useEffect } from "react";

const SUFFIX = " · VFP";

export function useDocumentTitle(title: string | undefined | null) {
  useEffect(() => {
    if (!title) return;
    const prev = document.title;
    document.title = `${title}${SUFFIX}`;
    return () => {
      document.title = prev;
    };
  }, [title]);
}
