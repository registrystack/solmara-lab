import { loadCountryData } from '$lib/server/data';
import type { PageServerLoad } from './$types';

export const load: PageServerLoad = async ({ fetch }) => {
  return { home: await loadCountryData(fetch) };
};
