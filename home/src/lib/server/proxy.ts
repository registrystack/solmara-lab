import { error } from '@sveltejs/kit';
import { joinedUrl, runtime } from './runtime';

export async function proxyMetadata(fetcher: typeof fetch, path: string): Promise<Response> {
  const response = await fetcher(joinedUrl(runtime.staticMetadataUrl, path));
  if (!response.ok) {
    throw error(response.status, 'metadata artifact unavailable');
  }
  const headers = new Headers();
  const contentType = response.headers.get('Content-Type');
  headers.set('Content-Type', contentType ?? contentTypeFor(path));
  headers.set('Cache-Control', 'no-store');
  return new Response(await response.arrayBuffer(), { status: response.status, headers });
}

function contentTypeFor(path: string): string {
  if (path.endsWith('.jsonld')) return 'application/ld+json; charset=utf-8';
  if (path.endsWith('.yaml')) return 'application/yaml; charset=utf-8';
  if (path.endsWith('.json') || path.endsWith('api-catalog') || path.endsWith('cpsv-ap')) {
    return 'application/json; charset=utf-8';
  }
  return 'application/octet-stream';
}
