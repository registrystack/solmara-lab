import { loadHomeData } from '$lib/server/data';

export const load = async ({ fetch }) => {
  return {
    home: await loadHomeData(fetch)
  };
};
