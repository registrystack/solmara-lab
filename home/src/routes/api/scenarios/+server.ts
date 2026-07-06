import { json, error } from '@sveltejs/kit';
import { joinedUrl, runtime } from '$lib/server/runtime';
import type { RequestHandler } from './$types';

export const GET: RequestHandler = async ({ fetch }) => {
  const response = await fetch(joinedUrl(runtime.scenarioRunnerUrl, '/v1/scenarios'));
  if (!response.ok) {
    throw error(503, 'scenario runner unavailable');
  }
  return json(await response.json());
};
