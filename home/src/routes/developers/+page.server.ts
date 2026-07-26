import { loadDeveloperData } from '$lib/server/data';
import type { PageServerLoad } from './$types';

export const load: PageServerLoad = async () => {
  return { home: await loadDeveloperData() };
};
