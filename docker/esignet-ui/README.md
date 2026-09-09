# Native eSignet UI build

The image builds the exact eSignet source pinned in `versions.env`, applies
`default-locale.patch` and `dependencies.patch`, then uses `npm ci` to produce a
static UI. Both patches must apply cleanly. The Dockerfile verifies the patched
lockfile SHA256 and records it as `io.registry.esignet.ui.lock.sha256` in the
image. Node and test tools are not copied into the nginx runtime.

The dependency patch retains Thunder React 0.11.2 and its existing API. It
updates compatible Axios, React Router, CSS/browser-data and test dependencies.
An exact DOMPurify 3.4.15 override replaces the sanitizer version pinned by that
Thunder release. Remove the override when a compatible Thunder update supplies
an appropriate sanitizer itself.

## Validate or refresh

Use a disposable checkout of the exact upstream commit from `versions.env`.
Apply both patches from this directory at that checkout's root, then run these
commands in its `oidc-ui` directory:

```sh
npm ci
npm test
npm run build
npm run lint
npm audit --package-lock-only
npm audit --omit=dev --package-lock-only
```

The pinned upstream source has existing lint diagnostics. Compare the exact
file/rule/location set before and after a dependency update; do not hide or
reclassify diagnostics. Tests and production build must pass.

Generate dependency changes with npm 12.0.2, which supports the Node version
used by this build. npm 10.9.8 can install the resulting lockfile but its peer
resolver fails when updating this graph. Keep the update within compatible
versions, regenerate `dependencies.patch` from only `oidc-ui/package.json` and
`oidc-ui/package-lock.json`, and update `ESIGNET_UI_LOCK_SHA256` in the Dockerfile.
The image build still uses its pinned Node image's `npm ci`.

Finally rebuild the local fixture UI and edge images and repeat the login and
protocol checks described in [the native integration guide](../../docs/esignet.md).
Review metadata and the real browser journey before any separate publication.
