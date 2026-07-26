import { loadHomeData } from '$lib/server/data';
import type { PageServerLoad } from './$types';

export const load: PageServerLoad = async ({ fetch }) => {
  return { home: await loadHomeData(fetch) };
};
