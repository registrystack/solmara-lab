import { fetchScenarios } from '$lib/server/data';
import { buildPurposeViews, readPurposes } from '$lib/server/purposes';
import type { PageServerLoad } from './$types';

export const load: PageServerLoad = async ({ fetch }) => {
  const [purposes, scenarioResult] = await Promise.all([readPurposes(), fetchScenarios(fetch)]);
  return { purposes: buildPurposeViews(purposes, scenarioResult.scenarios) };
};
