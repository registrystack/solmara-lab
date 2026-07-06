import { proxyMetadata } from '$lib/server/proxy';
import type { RequestHandler } from './$types';

export const GET: RequestHandler = async ({ fetch, params }) => {
  return proxyMetadata(fetch, `/metadata/${params.path}`);
};
