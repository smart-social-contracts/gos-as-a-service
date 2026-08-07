import { browser } from "$app/environment";
import { init, register, isLoading, locale } from "svelte-i18n";

export const supportedLocales = [
  { id: "en", name: "English" },
  { id: "es", name: "Español" },
  { id: "de", name: "Deutsch" },
  { id: "fr", name: "Français" },
  { id: "zh-CN", name: "中文 (简体)" },
  { id: "it", name: "Italiano" }
];

register("en", () => import("./locales/en.json"));
register("es", () => import("./locales/es.json"));
register("de", () => import("./locales/de.json"));
register("fr", () => import("./locales/fr.json"));
register("zh-CN", () => import("./locales/zh-CN.json"));
register("it", () => import("./locales/it.json"));

export function waitLocale(): Promise<void> {
  return new Promise<void>((resolve) => {
    const unsubscribe = isLoading.subscribe(($isLoading) => {
      if (!$isLoading) {
        unsubscribe();
        resolve();
      }
    });
  });
}

function getPreferredLocale(): string {
  if (!browser) return "en";
  
  const targetLanguages = ["en", "de", "fr", "es", "zh-CN", "it"];
  
  // Check URL parameters first
  try {
    const urlParams = new URLSearchParams(window.location.search);
    const urlLocale = urlParams.get('locale');
    if (urlLocale && targetLanguages.includes(urlLocale)) {
      return urlLocale;
    }
  } catch (e) {
    console.error('Error reading URL parameters:', e);
  }
  
  // Check localStorage
  try {
    const storedLocale = localStorage.getItem('registryPreferredLocale');
    if (storedLocale && targetLanguages.includes(storedLocale)) {
      return storedLocale;
    }
  } catch (e) {
    console.error('Error accessing localStorage:', e);
  }
  
  // Fall back to browser language preferences
  const browserLanguages = navigator.languages || [navigator.language];
  
  for (const browserLang of browserLanguages) {
    if (targetLanguages.includes(browserLang)) {
      return browserLang;
    }
    
    const langCode = browserLang.split('-')[0];
    if (langCode === 'zh') return 'zh-CN';
    if (targetLanguages.includes(langCode)) {
      return langCode;
    }
  }
  
  return "en";
}

export function setLocale(newLocale: string) {
  if (browser) {
    try {
      localStorage.setItem('registryPreferredLocale', newLocale);
    } catch (e) {
      console.error('Error saving locale to localStorage:', e);
    }
  }
  locale.set(newLocale);
}

export async function initI18n() {
  init({
    fallbackLocale: "en",
    initialLocale: browser ? getPreferredLocale() : "en"
  });
  
  // Wait for the locale to finish loading
  await waitLocale();
}
