# Source and volume recovery

Relay V2 reads authority-owned SQLite publications and owns no source truth.
Evidence reads either a named immutable extract or a Relay response. Recovery
therefore preserves publication identity and runtime bindings, not a shared
application database.

For a mutable Relay source, stop its authority publisher before snapshotting the
database. Restore into a new volume, verify the governed schema fingerprint and
read-only binding, then restart only that Relay. For an immutable extract,
restore the exact file under its original name or publish a reviewed replacement
under a new name. Never modify an active extract in place.

Audit sinks, Mint state, signer state, and source publications are separate
recovery units. Record exact artifact digests, runtime configuration revisions,
public JWKs, and volume identities with each backup. Do not copy private
recovery evidence into this public repository.

During the reset, superseded service volumes remain detached and recoverable.
Deleting them is outside the reset delivery and requires separate approval.
