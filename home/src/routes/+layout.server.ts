import { analyticsConfig } from '$lib/server/analytics';

export const load = async () => {
  return {
    analytics: analyticsConfig()
  };
};
