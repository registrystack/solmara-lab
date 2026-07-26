import { loadLandingData } from '$lib/server/data';

export const load = async ({ fetch }) => {
  return {
    home: await loadLandingData(fetch)
  };
};
