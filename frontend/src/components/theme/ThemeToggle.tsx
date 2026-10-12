"use client";

import { useTheme } from "./ThemeProvider";

export default function ThemeToggle({ className = "" }: { className?: string }) {
  const { theme, setTheme } = useTheme();
  const nextTheme = theme === "light" ? "dark" : "light";

  return (
    <button
      type="button"
      className={`theme-toggle ${className}`.trim()}
      aria-label={`Switch to ${nextTheme} mode`}
      title={`Switch to ${nextTheme} mode`}
      onClick={() => setTheme(nextTheme)}
    >
      <svg viewBox="0 0 24 24" width="18" height="18" fill="none" aria-hidden="true">
        {theme === "light" ? (
          <>
            <circle cx="12" cy="12" r="3.7" />
            <path d="M12 2.5v2M12 19.5v2M4.4 4.4l1.4 1.4m12.4 12.4 1.4 1.4M2.5 12h2m15 0h2M4.4 19.6l1.4-1.4M18.2 5.8l1.4-1.4" />
          </>
        ) : (
          <path d="M20.2 15.1A8.6 8.6 0 0 1 8.9 3.8 8.7 8.7 0 1 0 20.2 15.1Z" />
        )}
      </svg>
      <span className="theme-toggle-label">{theme === "light" ? "Dark" : "Light"}</span>
    </button>
  );
}
