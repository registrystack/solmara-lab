import { fetchScenarios } from '$lib/server/data';
import { readPurposes } from '$lib/server/purposes';
import { assembleProblemCodes } from '$lib/server/problemcodes';
import type { PageServerLoad } from './$types';

export const load: PageServerLoad = async ({ fetch }) => {
  const [purposes, scenarioResult] = await Promise.all([readPurposes(), fetchScenarios(fetch)]);
  return { codes: assembleProblemCodes(purposes, scenarioResult.scenarios) };
};
