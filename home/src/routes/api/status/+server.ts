import { json } from '@sveltejs/kit';
import { readStatus } from '$lib/server/data';
import type { RequestHandler } from './$types';

export const GET: RequestHandler = async ({ fetch }) => {
  return json({ status: await readStatus(fetch) });
};
