# Scoped PII encryption operator runbook

> **Opt-in only.** Both self-hosted and managed deployments remain OFF until an
> operator explicitly sets `PII_ENCRYPTION_ENABLED=True`. Managed PostgreSQL or
> storage does not opt a deployment in. Turning this flag off after rollout is
> **not** a rollback: ciphertext will no longer be readable by the application.
> Run the fenced `decrypt_scoped_pii` rollback below before disabling it.

This runbook is for an operator with Django management-command access, a
protected secret store, database backup/restore access, and an active
superuser ID (`$ACTOR_ID`). Do not put keys in shell history, tickets, logs, or
command output. Use a secure secret manager in production; the root-owned
files below are an example protected sink for a self-hosted host.

## Configure secrets and a broker

Create independent 32-byte Fernet master and HMAC search secrets without
printing them. The command text contains no secret and writes files readable
only by root; replace this sink with your Vault/KMS/secret-manager write API
where available.

```sh
install -d -m 0700 /etc/inventory-manager/secrets
python -c "from cryptography.fernet import Fernet; open('/etc/inventory-manager/secrets/pii_master_key','wb').write(Fernet.generate_key()+b'\n')"
python -c "import base64,secrets; open('/etc/inventory-manager/secrets/pii_search_hash_key','wb').write(base64.urlsafe_b64encode(secrets.token_bytes(32))+b'\n')"
chmod 0600 /etc/inventory-manager/secrets/pii_master_key /etc/inventory-manager/secrets/pii_search_hash_key
```

Back up both secrets in the restricted operator vault before enabling the
feature. Losing the master/KEK makes data unreadable; losing the search key
makes search indexes unrebuildable. Never reuse either value for
`API_CLIENT_ENC_KEY` or another application secret.

Self-hosted local wrapping uses the following environment (load values from the
secret sink, rather than exporting literal values in an interactive shell):

```dotenv
PII_ENCRYPTION_ENABLED=False
PII_ENCRYPTION_DUAL_READ=True
PII_KEY_BROKER=local
PII_MASTER_KEY=<contents of protected pii_master_key>
PII_MASTER_KEY_PREVIOUS=
PII_SEARCH_HASH_KEY=<contents of protected pii_search_hash_key>
PII_DEK_CACHE_TTL_SECONDS=300
```

Managed or self-hosted AWS KMS wrapping remains opt-in too. Install
`backend/requirements-kms.txt`, give the process identity KMS encrypt/decrypt
access, and use a KMS alias where possible:

```dotenv
PII_ENCRYPTION_ENABLED=False
PII_ENCRYPTION_DUAL_READ=True
PII_KEY_BROKER=aws_kms
PII_AWS_KMS_KEY_ID=alias/inventory-manager-pii
PII_AWS_KMS_REGION=ap-south-1
PII_AWS_KMS_ENDPOINT_URL=
PII_SEARCH_HASH_KEY=<contents of protected pii_search_hash_key>
```

`PII_AWS_KMS_REGION` and `PII_AWS_KMS_ENDPOINT_URL` are optional (the latter is
normally only for an approved KMS-compatible endpoint). `PII_MASTER_KEY` and
`PII_MASTER_KEY_PREVIOUS` are unused by the KMS broker. Do not enable a mixed
old/new fleet.

## Preflight and initial binding

With the feature still disabled, deploy all code and run ordinary health/check
validation. Create or verify the active DEK for each makerspace only with the
future enabled configuration available to the command process; unwrap every
retained DEK version as part of the enabled readiness preflight. Startup and
readiness fail closed when a broker, wrapped DEK, active search generation, or
search-key fingerprint is unavailable or mismatched.

During the fenced enable-transition window described below, bind generation 1:

```sh
cd backend
python manage.py bind_pii_search_key --initial --actor-id "$ACTOR_ID"
python manage.py check
```

The command is idempotent only for the same fingerprint and sole active
generation. Treat any mismatch as an incident: keep the fence closed, restore
the intended secret, and rerun readiness. Exercise an all-DEK preflight on a
restored copy before production: enable the intended broker settings and run
the application readiness/health probe so each existing key version is
unwrapped, without displaying key material.

## Fence operations and platform log redaction

All maintenance writes require a persistent fence operation. Stop intake and
drain workers first. Capture the UUID printed by the close command as
`$OPERATION`; it is also the resume token after a crash. The supported kinds
are `enable_transition`, `decrypt_rollback`, and `search_rotation`.

```sh
# Global enable, rollback, or search-key maintenance (also closes every tenant)
python manage.py close_pii_write_fence --global --all-makerspaces \
  --operation-kind enable_transition --actor-id "$ACTOR_ID"

# A makerspace-only maintenance operation
python manage.py close_pii_write_fence --makerspace "$MAKERSPACE_ID" \
  --operation-kind decrypt_rollback --actor-id "$ACTOR_ID"

# Reopen only after the operation's verification gate has passed
python manage.py open_pii_write_fence --operation "$OPERATION" --actor-id "$ACTOR_ID"
```

For the initial transition, while the global `enable_transition` fence is
closed and the old fleet is stopped, inspect then irreversibly redact platform
mail logs:

```sh
python manage.py redact_platform_email_logs --dry-run --actor-id "$ACTOR_ID" \
  --fence-operation "$OPERATION"
python manage.py redact_platform_email_logs --apply --actor-id "$ACTOR_ID" \
  --fence-operation "$OPERATION"
```

This command is enabled-transition-only; redacted platform recipient/body data
cannot be recovered, including by decrypt rollback. A failed process restart
leaves the persisted fence closed: correct the cause, resume the same operation
and command checkpoint, validate, then reopen. Do not bypass the fence with ORM
or SQL writes.

## Dual-read rollout sequence

1. Deploy H1-H4 everywhere with `PII_ENCRYPTION_ENABLED=False` and `PII_ENCRYPTION_DUAL_READ=True`; verify byte-for-byte legacy source storage and new platform EmailLog persistence/field-value behavior, compatible report/public-policy outputs, the documented search/sort/`__str__` changes, open fence rows, green tests, and zero pre-existing envelope markers. Mutating backfill/reindex commands must refuse to run in this state.
2. Generate independent `PII_MASTER_KEY` and `PII_SEARCH_HASH_KEY` secrets (or provision KMS and install the optional dependency). Back them up in the operator secret store; losing either makes data unreadable or search unrebuildable.
3. Run non-mutating wrapping/search preflight and create/verify one active DEK per makerspace; unwrap every existing DEK version. Do not redact platform logs or bind a search key while normal flag-off writers are running.
4. Enter a brief maintenance/drain window: stop intake, drain jobs, close the global write fence (which waits for in-flight mapped writers), and stop every flag-off web, worker, scheduler, and long-running command process. While the fence remains closed, run `bind_pii_search_key --initial`, then `redact_platform_email_logs --dry-run` and `--apply`; verify generation 1's fingerprint matches the configured key and every existing platform row has empty recipient/text/HTML plus a fixed non-PII subject/event label. Keep `PII_ENCRYPTION_DUAL_READ=True`, set `PII_ENCRYPTION_ENABLED=True`, start the replacement fleet, and require readiness from every process against the persisted search generation and every DEK version. Only after the enabled fleet is exclusively ready may the operator reopen the global fence and restore traffic/jobs. This single fleet switch activates authenticated envelope reads, legacy plaintext reads, encryption-on-write, generation-bound Bloom/exact-index-on-write, enabled platform-log minimization, and indexed lookup. A rolling mixed-flag restart is forbidden because an old process could read a new envelope as plaintext. Do not start backfill until the enabled fleet is exclusively active.
5. Before mutation, record database size, free disk/WAL headroom, replica lag, and autovacuum health; require capacity for the measured rewrite/WAL amplification plus a fresh encrypted backup. Benchmark a conservative batch size on a restored production-like database for both self-hosted PostgreSQL and the managed transaction-pooler profile, and start production at or below the tested managed-platform size. Run `backfill_scoped_pii` and then the H3-revised `reindex_scoped_pii` for every makerspace/model in throttled, bounded row-locked batches. Pause on disk/WAL/lag thresholds, avoid long transactions, and schedule/observe post-rewrite `VACUUM (ANALYZE)` rather than assuming space is immediately reclaimed. Concurrent normal writes remain encrypted/indexed and serialize with each command's lock. Rerun both commands idempotently to close interrupted batches, then verify counts and sample authorized reads without printing PII.
6. Run strict verify-only plus the expanded leak sweep. Confirm zero nonempty plaintext mapped values, zero missing/stale/wrong-generation Bloom/exact/event hashes, the configured key fingerprint matches the sole active generation, no plaintext makerspace EmailLog/Notification/audit/log copies, no unredacted enabled-mode platform logs, no corrupt envelopes, one active DEK per makerspace, no mapped-field DB expressions, and unchanged report totals/API shapes.
7. Optionally set `PII_ENCRYPTION_DUAL_READ=False` and restart all processes. This is the desired steady state. Keep it true only for a time-boxed compatibility window.

For each makerspace/model, use a measured, conservative batch and record each
printed `checkpoint` before continuing. These commands have `--batch-size` and
`--resume-after-pk`, not built-in WAL/disk/lag thresholds; monitor those outside
the command and pause before the agreed thresholds. Use `--dry-run` and
`--verify-only` first, keep transactions bounded, and schedule `VACUUM (ANALYZE)`
after the rewrite.

```sh
python manage.py backfill_scoped_pii --makerspace "$MAKERSPACE_ID" \
  --model hardware_requests.HardwareRequest --batch-size 100 --resume-after-pk 0
python manage.py reindex_scoped_pii --makerspace "$MAKERSPACE_ID" \
  --model hardware_requests.HardwareRequest --batch-size 100 --resume-after-pk 0
python manage.py reindex_scoped_pii --makerspace "$MAKERSPACE_ID" \
  --model hardware_requests.HardwareRequest --verify-only
```

## Fenced decrypt rollback and schema reversal

Rollback is global. Keep the global and every makerspace fence closed from the
first decrypt batch through proof, fleet replacement, and disabled-mode
verification. Do not reopen between those phases.

```sh
python manage.py close_pii_write_fence --global --all-makerspaces \
  --operation-kind decrypt_rollback --actor-id "$ACTOR_ID"
# Save printed UUID as $OPERATION; repeat for every makerspace and model.
python manage.py decrypt_scoped_pii --makerspace "$MAKERSPACE_ID" \
  --model hardware_requests.HardwareRequest --batch-size 100 \
  --actor-id "$ACTOR_ID" --confirm-makerspace "$MAKERSPACE_ID" \
  --fence-operation "$OPERATION"
python manage.py decrypt_scoped_pii --makerspace "$MAKERSPACE_ID" \
  --model hardware_requests.HardwareRequest --verify-only --actor-id "$ACTOR_ID"
python manage.py decrypt_scoped_pii --global --verify-only --actor-id "$ACTOR_ID"
```

The command authenticates envelopes, validates legacy sizes/emails/uniqueness,
removes index artifacts atomically, and is resumable with `--resume-after-pk`.
Keep keys available through verification. After the global zero-envelope,
zero-index, zero-event-hash and platform-redaction proof, stop the enabled
fleet, set `PII_ENCRYPTION_ENABLED=False`, start only the disabled fleet, and
run read-only behavior/readiness checks. Only then reopen `$OPERATION`.

Only after that proof and disabled-fleet verification may a separately reviewed
schema migration restore bounded legacy fields or drop nullable event-hash and
blind-index schema. Retain wrapped DEK rows, broker authority, and search
material until encrypted backup retention expires.

## Key rotation, backup, and incident recovery

- **Per-makerspace DEK:** rotate through the audited service, then re-save/backfill
  that makerspace's mapped rows in batches. New envelopes use N+1 and old N
  envelopes remain readable by their embedded version. Verify no envelope
  references N before retaining it for backup retention or disabling it. No
  blind-index rebuild is needed because the search key is unchanged.
- **Local KEK:** configure new `PII_MASTER_KEY` plus old
  `PII_MASTER_KEY_PREVIOUS`, restart, rewrap every DEK, verify each unwrap with
  the new fingerprint, then remove the previous secret and restart. Rewrap
  changes only wrapped DEKs/broker metadata, not application envelopes or blind
  indexes.
- **AWS KMS:** use a rotating alias when possible. A move to another key
  re-encrypts wrapped DEKs and updates `broker_key_id`; verify unwrap before
  retiring old KMS authority. KMS outage is fail-closed: restore KMS access,
  not plaintext fallback.
- **Search HMAC:** stop intake/jobs, close a global `search_rotation` fence,
  stop the old fleet, retain the old vault secret, build N+1, reindex every
  generic Bloom/exact and EventRegistration hash, prove complete N+1 coverage,
  then atomically retire N/activate N+1. Replace `PII_SEARCH_HASH_KEY`, start
  an exclusively N+1-ready fleet, and only then reopen the same fence. Never
  run mixed-key traffic; preserve the old secret until relevant backups expire.

Maintain encrypted database backups and separately escrow broker/search
authority under least privilege. Regularly restore a production-like backup to
an isolated environment, restore the matching master/KMS permissions and search
secret, unwrap every retained DEK version, decrypt authorized samples, verify
the active fingerprint, and rehearse both a resume checkpoint and fenced
rollback. A restore missing wrapped-key rows, external KEK/KMS authority, or
search material must fail clearly and remain unavailable.

DEKs are cached in-process for `PII_DEK_CACHE_TTL_SECONDS` (default 300).
Rotation, rewrap, and disable invalidate the relevant cache; restart processes
after external authority changes. A generic HTTP 503 / “temporarily unavailable”
is expected for missing keys, unavailable KMS, corrupt/authentication-failed
envelopes, readiness fingerprint mismatch, or a closed write fence. Do not
expose internal cryptographic errors to callers. Preserve the fence, collect
non-secret timestamps/operation IDs, restore the correct authority from the
vault or backup, preflight all DEKs, and resume only after verification.
