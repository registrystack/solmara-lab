import { error } from '@sveltejs/kit';
import { loadScenario } from '$lib/server/data';
import type { PageServerLoad } from './$types';

export const load: PageServerLoad = async ({ params, fetch }) => {
  const scenario = await loadScenario(params.id, fetch);
  if (!scenario) {
    throw error(404, 'Unknown story');
  }
  return { scenario };
};
