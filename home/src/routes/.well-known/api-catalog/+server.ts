import { proxyMetadata } from '$lib/server/proxy';
import type { RequestHandler } from './$types';

export const GET: RequestHandler = async ({ fetch }) => {
  return proxyMetadata(fetch, '/.well-known/api-catalog');
};
