export const UMAMI_SCRIPT_URL = 'https://stats.registrystack.org/script.js';

export type AnalyticsConfig = {
  scriptUrl: typeof UMAMI_SCRIPT_URL;
  websiteId: string;
};

export function analyticsConfig(env: NodeJS.ProcessEnv = process.env): AnalyticsConfig | null {
  const websiteId = env.UMAMI_WEBSITE_ID?.trim();
  if (!websiteId) return null;

  return {
    scriptUrl: UMAMI_SCRIPT_URL,
    websiteId
  };
}
