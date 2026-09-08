export type ThemePreference = "obsidian" | "ledger";
export type DensityPreference = "comfortable" | "compact";

export interface PresentationPreferences {
  theme: ThemePreference;
  density: DensityPreference;
  highContrast: boolean;
}

export const defaultPresentationPreferences: PresentationPreferences = {
  theme: "obsidian",
  density: "comfortable",
  highContrast: false,
};

const storageKey = "airbench.presentation-preferences.v1";

function isThemePreference(value: unknown): value is ThemePreference {
  return value === "obsidian" || value === "ledger";
}

function isDensityPreference(value: unknown): value is DensityPreference {
  return value === "comfortable" || value === "compact";
}

export function parsePresentationPreferences(raw: string | null): PresentationPreferences {
  if (!raw) return defaultPresentationPreferences;

  try {
    const candidate: unknown = JSON.parse(raw);
    if (!candidate || typeof candidate !== "object") return defaultPresentationPreferences;
    const value = candidate as Partial<PresentationPreferences>;
    return {
      theme: isThemePreference(value.theme) ? value.theme : defaultPresentationPreferences.theme,
      density: isDensityPreference(value.density) ? value.density : defaultPresentationPreferences.density,
      highContrast: typeof value.highContrast === "boolean" ? value.highContrast : defaultPresentationPreferences.highContrast,
    };
  } catch {
    return defaultPresentationPreferences;
  }
}

export function loadPresentationPreferences(): PresentationPreferences {
  if (typeof window === "undefined") return defaultPresentationPreferences;

  try {
    return parsePresentationPreferences(window.localStorage.getItem(storageKey));
  } catch {
    return defaultPresentationPreferences;
  }
}

export function savePresentationPreferences(preferences: PresentationPreferences): void {
  if (typeof window === "undefined") return;

  try {
    window.localStorage.setItem(storageKey, JSON.stringify(preferences));
  } catch {
    // The desktop shell remains usable when the operating-system profile is read-only.
  }
}
