/** Theme (light / dark / follow system) — persisted to localStorage and driven by the html.dark class. */

export type Theme = "light" | "dark" | "system";
export const THEMES: readonly Theme[] = ["light", "dark", "system"];

const STORAGE_KEY = "terrane.theme";

function systemMedia(): MediaQueryList | null {
  return typeof window.matchMedia === "function"
    ? window.matchMedia("(prefers-color-scheme: dark)")
    : null;
}

export function storedTheme(): Theme {
  const value = localStorage.getItem(STORAGE_KEY);
  return value === "light" || value === "dark" || value === "system" ? value : "system";
}

function render(theme: Theme): void {
  const dark = theme === "dark" || (theme === "system" && (systemMedia()?.matches ?? false));
  document.documentElement.classList.toggle("dark", dark);
}

export function applyTheme(theme: Theme): void {
  localStorage.setItem(STORAGE_KEY, theme);
  render(theme);
}

export function initTheme(): void {
  render(storedTheme());
  systemMedia()?.addEventListener("change", () => {
    if (storedTheme() === "system") render("system");
  });
}
