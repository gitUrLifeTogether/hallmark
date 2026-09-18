/* Light or dark, chosen by the viewer or by their system.
 *
 * The tokens for both themes already existed and nothing ever set `data-theme`, so the
 * dark palette only appeared for someone whose system asked for it and could not be
 * chosen at all. That matters more here than on most pages: this console is recorded, and
 * a recording happens in whichever theme reads better on the day.
 *
 * "system" is a real third state, not a default that silently becomes light. Dropping it
 * would mean a viewer who never touches the control is answered once and then ignored when
 * their system changes.
 */

import { useEffect, useState } from "react";

export type Theme = "system" | "light" | "dark";

const KEY = "hallmark.theme";

function stored(): Theme {
  try {
    const raw = localStorage.getItem(KEY);
    return raw === "light" || raw === "dark" ? raw : "system";
  } catch {
    // Private windows and blocked storage both land here; neither is worth failing over.
    return "system";
  }
}

function apply(theme: Theme): void {
  const root = document.documentElement;
  if (theme === "system") root.removeAttribute("data-theme");
  else root.setAttribute("data-theme", theme);
}

export function useTheme(): [Theme, (next: Theme) => void] {
  const [theme, setTheme] = useState<Theme>(stored);

  useEffect(() => {
    apply(theme);
    try {
      if (theme === "system") localStorage.removeItem(KEY);
      else localStorage.setItem(KEY, theme);
    } catch {
      // The choice still applies to this page; only remembering it failed.
    }
  }, [theme]);

  return [theme, setTheme];
}
