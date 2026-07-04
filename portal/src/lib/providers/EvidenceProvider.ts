import type { ClaimResult, Field, ProofTrace, RailEvent } from '$lib/types';
import type { MockEvaluation, EvaluateOptions } from '$lib/providers/mock';

// Context the BFF passes to a provider for one evaluation.
export type EvaluateContext = {
  subject: string;            // session-bound applicant national id (server-side only)
  selectedSubject?: string;   // server-selected story persona, never client supplied
  delegatedTarget?: string;   // a verified dependent, for delegated fields
};

// The single seam both the mock and the live build implement (spec section 5.6).
// "mock then wire" must never become "mock then rewrite".
export interface EvidenceProvider {
  evaluate(field: Field, ctx: EvaluateContext): Promise<ClaimResult>;
}

export interface DetailedEvidenceProvider extends EvidenceProvider {
  evaluateDetailed(field: Field, ctx: EvaluateContext, opts?: EvaluateOptions): Promise<MockEvaluation>;
}

// The reactive feeds the UI subscribes to. The provider/BFF layer pushes into
// these; proof + rail components only read. Implemented in src/lib/server +
// client stores; the interfaces live here so feature agents agree without
// depending on each other's code.
export interface ProofFeed {
  readonly traces: ProofTrace[];
}
export interface RailFeed {
  readonly events: RailEvent[];
}
