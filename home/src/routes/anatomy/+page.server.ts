import { runtime } from '$lib/server/runtime';
import { topologyGroups } from '$lib/server/services';
import { readComposeServices } from '$lib/server/data';
import type { PageServerLoad } from './$types';

export const load: PageServerLoad = async () => {
  // The compose service list is parsed server-side; the topology table maps each
  // service to its authority or purpose and its in-repo config paths.
  const composeServices = await readComposeServices();
  return {
    groups: topologyGroups(runtime.repoUrl),
    composeServiceCount: composeServices.length,
    repoUrl: runtime.repoUrl
  };
};
