# Contributing

Solmara Lab changes should be small, reviewable, and tied to a story or
verification need.

## Commit Rules

- Use DCO sign-off: `git commit -s`.
- Keep generated fixtures in the same change as the generator logic that
  produced them.
- Do not mix unrelated cleanup into feature work.
- Do not commit secrets, `.env`, local outputs, or hosted deployment evidence.

## Local Verification

Run focused checks for the files you touched. Before a PR, run:

```bash
just lint
just test
just smoke
just review
```

If services are not available, explain exactly which checks were skipped and
why.

## Security Review

Changes touching auth, authorization, scopes, credential issuance, disclosure,
redaction, audit, replay, config trust, or signing need explicit notes in the
PR. Configs must reference raw tokens through environment variables only.
