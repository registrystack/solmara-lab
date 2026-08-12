import { fireEvent, render, screen } from '@testing-library/svelte';
import { describe, expect, it } from 'vitest';
import ProofInspector from './ProofInspector.svelte';
import type { ProofTrace } from '$lib/types';

const trace: ProofTrace = {
  id: 'proof-1',
  seq: 1,
  fieldId: 'farmer-registered',
  authority: 'agri',
  headline: 'Confirmed by NAgDI',
  answered: 'National Agricultural Data Institute answered: farmer-registered = true',
  notDisclosed: 'source rows and selector values',
  status: 'ok',
  ts: '2026-06-21T12:04:09.000Z',
  purpose: 'voucher-eligibility-review',
  resultState: 'verified',
  responseStatus: 200,
  presentations: [{
    authority: 'National Agricultural Data Institute',
    issuer: 'did:web:id.registrystack.org:solmara:authority:nagdi',
    serviceId: 'nagdi-evidence',
    source: 'Relay lookup'
  }],
  proof: {
    signedBy: 'National Agricultural Data Institute',
    algorithm: 'Flattened JWS, ES256, verified server-side',
    issuerKey: 'Authority JWKS',
    holderBound: 'Reviewed request',
    credential: 'Signed minimum-disclosure Evidence assertion'
  }
};

describe('ProofInspector', () => {
  it('renders the resident-facing result without exposing evidence internals', () => {
    const { container } = render(ProofInspector, { traces: [trace] });

    expect(screen.getByText('Confirmed by NAgDI')).toBeInTheDocument();
    expect(screen.getByText(/source rows and selector values/)).toBeInTheDocument();
    expect(container.textContent).not.toMatch(/requestNonce|subjects|protected|payload|signature|Bearer|FR-\d+/);
  });

  it('expands canonical authority, issuer, service, and exact source metadata only', async () => {
    const { container } = render(ProofInspector, { traces: [trace] });
    await fireEvent.click(screen.getByRole('button', { name: /Authority evidence/ }));

    expect(screen.getAllByText('National Agricultural Data Institute')).toHaveLength(2);
    expect(screen.getByText('did:web:id.registrystack.org:solmara:authority:nagdi')).toBeInTheDocument();
    expect(screen.getByText('nagdi-evidence')).toBeInTheDocument();
    expect(screen.getByText('Relay lookup')).toBeInTheDocument();
    expect(container.textContent).not.toMatch(/raw wire|audit id|compact JWS|request body/i);
  });

  it('states when authorization prevented any authority call', async () => {
    const denied = { ...trace, id: 'denied', status: 'denied' as const, resultState: 'error' as const, presentations: [] };
    render(ProofInspector, { traces: [denied] });
    await fireEvent.click(screen.getByRole('button', { name: /Authority evidence/ }));
    expect(screen.getByText('No authority Evidence service was called.')).toBeInTheDocument();
  });

  it('shows reconnecting state without removing existing proofs', () => {
    render(ProofInspector, { traces: [trace], connected: false });
    expect(screen.getByRole('status')).toHaveTextContent('Reconnecting to proof feed');
    expect(screen.getByText('Confirmed by NAgDI')).toBeInTheDocument();
  });
});
