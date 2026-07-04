# Solmara Lab Agent Notes

This repository is the standalone Republic of Solmara demo lab for Registry
Stack. It consumes published Registry Stack images by digest by default and
must not depend on the `registry-stack` working tree for normal operation.

## Boundaries

- Keep product code changes in `registry-stack`, not here.
- Keep private planning and release evidence in `registry-internal/`, not here.
- Do not commit `.env`, generated secrets, local output, or container state.
- Generated fixtures are intentional artifacts. Regenerate them with the
  documented generator command and review the diff before committing.
- Use `registry-stack@origin/main` as the source for ported lab assets unless
  Jeremi explicitly asks for a different ref.

## Implementation Defaults

- Use `uv` for Python workflows.
- Prefer `pnpm` for portal workflows.
- Prefer `just` recipes over long ad hoc command sequences.
- Use canonical Solmara identifiers and domains:
  `XS`, `XSO`, `*.gov.solmara.example`, and
  `https://id.registrystack.org/solmara/...`.
- Do not reintroduce `demo.example.gov`, `country: ZZ`, Philippine geography,
  or compass districts.
- Raw API tokens live only in generated `.env`. Committed configs use
  fingerprints and `token_env` references.

## Verification

Before calling work complete, run the focused checks for your slice and the
root gates when possible:

```bash
just lint
just test
just smoke
just review
```

If a check cannot run because another workstream has not landed yet, report the
exact missing prerequisite.
