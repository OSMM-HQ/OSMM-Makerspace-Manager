# Printing kernel cutover (B4)

`cutover_printing_kernel --makerspace <id>` is the deterministic, idempotent
backfill and reconciliation gate. It writes kernel provenance keys only; it
does not alter legacy printing history. Inspect `PrintingCutoverRepair` for any
invalid source, missing object, collision, warranty, or reconciliation entry.

Run `cutover_printing_kernel --makerspace <id> --reconcile-only` after a
repair. Use `--flip` only after a successful reconciliation. That marks the
makerspace kernel-authoritative, makes legacy printing models read-only, and
keeps old endpoints as compatibility readers/adapters through B6.

## Forward repair and rollback boundary

Rollback is safe only before `--flip`. After a kernel write, consumable-ledger
adjustment, or attachment has been accepted, copying it back would break the
append-only ledger/audit trail and storage accounting. Do not restore legacy
writes or edit imported immutable history. Instead, add the required kernel
record or ledger correction, retain the repair row and its audit link, rerun
the idempotent command, and reconcile the affected makerspace again. Missing
objects stay explicit repair records; no replacement attachment is fabricated.
