/**
 * Tiny wrapper around `window.print()`. The browser's PDF generator does the
 * actual rendering — works in Chromium, Safari, Firefox without any new dep.
 *
 * The print stylesheet (src/print.css) handles layout: hides app chrome,
 * forces utilization colors, expands tables.
 */

import { useCallback } from "react";

export function usePrintToPdf() {
  return useCallback(() => {
    window.print();
  }, []);
}
