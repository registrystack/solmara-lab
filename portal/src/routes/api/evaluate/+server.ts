// POST /api/evaluate : proxy a single field's claim to its Notary (Phase 0: the
// MockEvidenceProvider).
//
// Body: { slug, fieldId, scenarioKey?, delegated? }
//   - slug / fieldId identify a field in the server-side form catalogue.
//   - scenarioKey is accepted only for the server-owned set pieces that need a
//     field/scenario alias. It never gives the browser a free target selector.
//   - delegated.guardianLinkVerified gates the two-hop civil reads.
//
// The session subject and selected story persona are resolved SERVER-SIDE
// (never trust a client-supplied target), the provider is called, a REDACTED
// trace is teed to the proof feed, and the ClaimResult is returned.

import { error, json } from '@sveltejs/kit';
import type { RequestHandler } from './$types';
import type { Field } from '$lib/types';
import { getForm } from '$lib/forms/descriptors';
import { teeToFeeds } from '$lib/server/bff';
import { getSession, getSessionId } from '$lib/server/session';
import { getProvider } from '$lib/server/provider';
import { PERSONA } from '$lib/providers/mock';

type EvaluateBody = {
  slug?: string;
  fieldId?: string;
  scenarioKey?: string;
  delegated?: { guardianLinkVerified?: boolean; selectedChild?: string };
};

export const POST: RequestHandler = async ({ request, cookies }) => {
  const session = getSession(cookies);
  const sessionId = getSessionId(cookies);
  if (!session || !sessionId) {
    throw error(401, 'not signed in');
  }

  let body: EvaluateBody;
  try {
    body = (await request.json()) as EvaluateBody;
  } catch {
    throw error(400, 'invalid JSON body');
  }

  const fieldId = body.fieldId;
  if (!fieldId || typeof fieldId !== 'string') {
    throw error(400, 'fieldId is required');
  }
  const slug = body.slug;
  if (!slug || typeof slug !== 'string') {
    throw error(400, 'slug is required');
  }

  const form = getForm(slug);
  if (!form) {
    throw error(400, 'unknown service');
  }

  const field = resolveAllowedField(form, fieldId, body.scenarioKey);

  // The actor subject is always the signed-in session subject. Wave 1 also has
  // server-selected story personas so the three demo journeys can exercise their
  // named fixture rows without accepting a browser-supplied target id.
  const ctx = {
    subject: session.subject,
    selectedSubject: selectedStorySubject(form.slug),
    delegatedTarget: form.slug === 'child-benefit' ? PERSONA.mateo : undefined
  };

  const provider = getProvider();
  try {
    const evaluation = await provider.evaluateDetailed(field, ctx, {
      scenarioKey: body.scenarioKey,
      guardianLinkVerified: body.delegated?.guardianLinkVerified
    });

    // Tee a REDACTED trace + rail event to the feeds (the SSE stream replays it).
    teeToFeeds(evaluation, { sessionId, fieldId });

    // Return only the portal-facing ClaimResult; raw wire stays server-side.
    return json(evaluation.result);
  } catch (err) {
    // No silent failure: surface a scoped 422 with a safe message (no identifiers).
    const message = err instanceof Error ? err.message : 'evaluation failed';
    throw error(422, message);
  }
};

function resolveAllowedField(
  form: NonNullable<ReturnType<typeof getForm>>,
  fieldId: string,
  scenarioKey: string | undefined
): Field {
  const field = form.fields.find((candidate) => candidate.id === fieldId);
  if (!scenarioKey) {
    if (!field) throw error(400, 'unknown field for service');
    return field;
  }

  if (form.slug === 'child-benefit' && fieldId === 'guardian-link-verified' && scenarioKey === 'caregiver-link') {
    return {
      id: fieldId,
      label: 'Guardian link verified',
      kind: 'verify',
      notary: 'social'
    };
  }

  if (form.slug === 'pension-survivor' && fieldId === 'denial' && scenarioKey === 'denial') {
    return {
      id: fieldId,
      label: 'Cross-person denial',
      kind: 'verify',
      notary: 'civil'
    };
  }

  throw error(400, 'scenario override is not allowed for this service field');
}

function selectedStorySubject(slug: string): string | undefined {
  if (slug === 'farmer-voucher') return PERSONA.aminaFarmer;
  if (slug === 'pension-survivor') return PERSONA.rafael;
  return undefined;
}
