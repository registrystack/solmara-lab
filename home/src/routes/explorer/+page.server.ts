import { fetchMetadata } from '$lib/server/data';
import { buildPublicUrlMap, mapPublicUrl } from '$lib/server/urlmap';
import type { PageServerLoad } from './$types';

export const load: PageServerLoad = async ({ fetch }) => {
  const metadata = await fetchMetadata(fetch);
  const metadataBase = mapPublicUrl('http://static-metadata:8080', buildPublicUrlMap());
  return { metadata, metadataBase };
};
