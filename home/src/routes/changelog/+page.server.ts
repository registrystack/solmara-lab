import { readChangelog } from '$lib/server/data';
import { runtime } from '$lib/server/runtime';
import type { PageServerLoad } from './$types';

export const load: PageServerLoad = async () => {
  return { entries: await readChangelog(), repoUrl: runtime.repoUrl };
};
