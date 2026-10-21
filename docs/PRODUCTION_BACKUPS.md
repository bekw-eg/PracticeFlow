# Coordinated production PostgreSQL and private S3 backups

Status: implementation and a reproducible synthetic drill are provided. No
production server, credentials, vault, timer installation or successful
production run has been supplied or verified. Local-volume helpers remain for
LocalStorage only. A PostgreSQL dump never contains S3 document bytes.

## Design and consistency boundary

[production_backup.py](../scripts/production_backup.py) uses the existing
PostgreSQL 16 custom dump/restore approach, the application's pinned boto3 SDK,
the real production service names and the existing API/image/report/DOCX drill
helpers. It copies **every current object** in the dedicated application bucket,
including unreferenced objects. It does not copy old versions, delete markers,
incomplete multipart uploads, IAM policies or provider configuration. Versioning
and replication remain useful additional protection, not this coordinated set.

Each encrypted restic snapshot contains only `database.dump`, numbered object
payloads, `manifest.json` and `manifest.sha256`. The manifest includes UTC time,
format/installation IDs, source identity hashes, PostgreSQL/schema versions,
application image digests, object keys/versions/content types/metadata, every
artifact's SHA-256 and byte size, and database file references from `files`,
successful `export_jobs`, generated `group_review_reports`, student/teacher DOCX
submissions whose originals remain retained, and teaching material objects whose
storage deletion has not completed. Stored DB digests are also compared. A missing referenced object
or incorrect size fails the backup; resolve pending deletion inconsistencies
before retrying. Neither credentials, `.env`, deployment files nor raw logs
are included. Manifest keys and metadata are sensitive and stay encrypted.
The snapshot tree always uses `/bundle`, independently of the temporary
absolute capture path recorded by restic in snapshot metadata.

The consistency procedure is a maintenance window:

1. Fence deployments, cron/manual migration/cleanup/import commands, other hosts
   or projects using this database/bucket, and provider lifecycle/replication
   writers. Configure ingress maintenance behavior. Keep this fence in force
   until the script has resumed the original services. The operator must set
   `external_writers_fenced=true` only after providing these controls; a script
   on one host cannot stop writers on another host. PostgreSQL connection checks
   and two S3 inventories detect several violations but cannot prove fencing.
   For unattended daily runs, enforce this continuously: deployment/migration
   and administrative cron wrappers must acquire the same
   `/var/lib/practiceflow-backup/operation.lock`; deny DB/object writes from
   other hosts/projects and disable live-prefix lifecycle mutation. Do not set
   the flag based only on a one-time manual pause of external automation.
2. Acquire a nonblocking `flock` for the entire operation, including retention.
   Restic also uses its own repository locks. Manual calls and the timer must
   share the same state directory and installation ID.
3. Record exact running container IDs in a private restart journal. Stop all API
   replicas first, then `export-worker`, `document-check-worker` and every other
   running application service in this Compose project, allowing 120 seconds
   per container. Only PostgreSQL, Redis, frontend and Caddy are exempt. Unknown
   writers without matching DB/S3 configuration cause a refusal. Containers
   requiring SIGKILL cause failure without publishing a backup.
4. With all writers stopped and no other DB clients connected, inventory S3,
   read DB references, dump PostgreSQL, stream all objects with conditional GET,
   compare the second inventory and validate every artifact/reference. The API
   remains unavailable throughout the **entire** capture, not just `pg_dump`.
5. In `finally`, start only containers that were originally running; verify their
   running/health status. Originally stopped replicas remain stopped. A restart
   error is a failure and retains the journal. Upload the fixed capture only
   after services resume, then restore the remote snapshot into private staging,
   verify all hashes again and run `restic check` before retention.

Pause duration grows with total live S3 bytes and number of objects. Provision
enough maintenance time and encrypted staging space for the dump plus **two**
complete live object sets during remote readback. Inventories and reference
lists use memory proportional to object count; payloads stream in 1 MiB chunks.
Redis is not backed up: durable job rows live in PostgreSQL; new Redis loses
sessions/guard/notification state and workers recover durable jobs. This is a
logical snapshot, not PITR/WAL archiving or zero-downtime backup.

## Independent private vault and keys

Before installing the timer, supply these **real deployment parameters**:

- Production Linux host, checkout/image revision, explicit Compose project,
  Compose files (including actual overrides), protected production env-file
  path, and a maintenance window/ingress policy covering all writers.
- Source HTTPS S3 endpoint, dedicated bucket, region, addressing style, trusted
  CA and a separate read-only backup credential: bucket listing/head and object
  reads. Do not reuse the application's write credential for this reader.
  The provider must guarantee strongly consistent listing and object reads
  after acknowledged writes. An eventually consistent compatible store needs
  a provider-specific snapshot/settling barrier before this workflow can be
  considered complete; two equal inventories alone cannot establish that.
- A private S3 vault on an independent server/account/failure domain, different
  endpoint from the source, bucket/prefix, region and separate credentials.
  Restrict the vault policy to its custodians and this backup role. Explicitly
  deny anonymous/public reads and insecure transport. Verify account ownership,
  independent placement, provider encryption-at-rest and recovery access before
  setting `offsite_private_confirmed=true`. Distinct DNS names alone do not prove
  off-site storage. The script enforces HTTPS with certificate validation in
  production, different endpoint hosts, and a pinned restic repository ID.
- A strong restic password file, stable random installation ID, repository ID,
  retention days, minimum snapshot count, staging capacity, and alert destination.
- An isolated restore PostgreSQL/Redis project and new private bucket, with
  target-only write/read/list/version-list credentials and an application route
  reachable only by drill operators.

Restic provides authenticated client-side encryption before bytes reach the
vault; HTTPS protects transfer. Keep its password separate from repository
access keys. The host state directory must reside on an encrypted filesystem
(for example LUKS) or an appropriately sized private encrypted ephemeral volume:
it contains temporary plaintext. Root mode `0700`, umask `0077` and systemd's
restricted writable path protect staging access. Successful and ordinary failed
runs remove their own staging directories. Hard power loss/SIGKILL can leave
private `capture-*`/`restore-*` directories; after recovering the journal and
confirming no operation holds the lock, inspect and remove only those directories
created by this mechanism. Never recursively clean the checkout or bucket.

Use a dedicated restic prefix/repository. Vault permissions cover listing,
encrypted object reads/writes and deletions inside that prefix, including restic
locks and retention. The source credential has no delete permission. For
ransomware protection, independently administer an immutable secondary copy or
append-only service and test its recovery. Do not blindly apply Object Lock to
the writable restic prefix: lock cleanup/prune may fail. This workflow does not
claim WORM protection or protection from a fully compromised backup custodian.

Maintain a separate access-controlled recovery escrow/password manager containing:

- restic password, vault access/recovery keys and any vault KMS recovery rights;
- application `MFA_TOTP_ENCRYPTION_KEY`, `MFA_RECOVERY_CODE_PEPPER`, audit hash
  pepper, break-glass custodian material/hashes and JWT key/rotation policy;
- reviewed runtime configuration, deployment/image digests, database role setup,
  S3 policies, private CA certificates and any source SSE-KMS decryption rights.

Keep this escrow outside the bundle, server and Git. Test access by authorized
recovery custodians. Without the original MFA/audit encryption/pepper material,
restoring rows alone cannot recover their meaning. Rotate infrastructure keys
for a new environment and decide whether to rotate JWT/sign out all sessions.
Do not re-enable outbound SMTP, public ingress or seed in a real-data drill.

## Linux installation and schedule

Install a maintained restic package (the test runner uses restic 0.18.1),
Docker Compose v2 with `!override` support for the test fixture, and Python 3.12+.
The production backend image and application dependencies are unchanged.
The auxiliary runner uses the same immutable Python base digest, an allowlisted
build context, the pinned boto3 input and current Alpine restic/Docker packages.
CI audits the backup SDK separately. The runner needs root/Docker-socket access
to create its disposable namespaces; it is trusted operator tooling, never an
application service or a production API image. Existing production image
SBOM/CVE gates remain unchanged; host restic/Docker security updates belong to
the server operator.

```sh
sudo python3 -m venv /opt/practiceflow-backup-venv
sudo /opt/practiceflow-backup-venv/bin/pip install -r /opt/practiceflow/deployment/backup/requirements.txt
sudo install -d -m 0700 /etc/practiceflow /var/lib/practiceflow-backup
sudo install -m 0600 deployment/backup/config.example.json /etc/practiceflow/backup.json
sudo install -m 0600 deployment/backup/credentials.example /etc/practiceflow/backup-credentials
```

Replace placeholders privately; create `/etc/practiceflow/backup-password` with
a strong random password and mode `0600`. Use root-owned files; never turn on
shell tracing. Initialize the **new dedicated vault** once, using its separate
credentials, then record its ID in `backup.json`:

```sh
sudo -i
set -a
. /etc/practiceflow/backup-credentials
set +a
export RESTIC_REPOSITORY='s3:https://backup.example.invalid/practiceflow-vault/restic'
export RESTIC_PASSWORD_FILE=/etc/practiceflow/backup-password
export AWS_ACCESS_KEY_ID="$PF_VAULT_ACCESS_KEY"
export AWS_SECRET_ACCESS_KEY="$PF_VAULT_SECRET_KEY"
export AWS_DEFAULT_REGION='replace-with-vault-region'
restic init
restic cat config
# Record only the repository id, never passwords, in the private backup config.
```

Run one manual backup with the maintenance fence and verify its success before
enabling the schedule. Load the protected credential environment as above.

```sh
/opt/practiceflow-backup-venv/bin/python /opt/practiceflow/scripts/production_backup.py \
  --config /etc/practiceflow/backup.json backup
sudo install -m 0644 deployment/backup/practiceflow-backup.service /etc/systemd/system/
sudo install -m 0644 deployment/backup/practiceflow-backup.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now practiceflow-backup.timer
sudo systemctl list-timers practiceflow-backup.timer
```

The template schedules daily **02:00 UTC** plus up to 10 minutes jitter; missed
runs catch up after boot. `Type=oneshot` and flock prevent overlap. A local
timer drop-in can change the owner-approved maintenance window. `ExecStopPost`
attempts journal recovery even after failure/termination. After host power loss,
run the `resume` command **before** starting a new backup; the journal refuses
changed/missing container identities rather than starting an unintended stack.
For a journal-related startup refusal, restore the original containers manually
under incident control before removing the verified obsolete journal.

Every failed subprocess/check/restart returns nonzero. Logs expose fixed status,
snapshot ID, object count and timings, never raw SDK/restic/Compose output or
document bytes. Check `systemctl status` and `journalctl -u practiceflow-backup`.
Wire a local `OnFailure=` drop-in to the existing on-call transport and an
independent backup-age monitor (alert if no successful snapshot within the
approved RPO). A timer existing or an empty journal is not proof of success.
Alerting transport/contacts are deployment inputs and are not provisioned here.

Retention defaults to 30 days with at least seven snapshots. Expiration runs
only after a new remote snapshot passes full readback. It selects only the
reserved engine+installation tags and matching host in the pinned repository,
preserves the current snapshot and minimum count, and passes exact expired IDs
to `restic forget`. `prune` removes unreferenced encrypted data and preserves
data referenced by other snapshots; `check` runs afterwards. Foreign snapshots
are never selected for deletion. Do not use bucket-wide lifecycle deletion on
restic data: it can invalidate retained snapshots.

## Restore into an isolated empty target

1. Retrieve the exact 64-character snapshot ID from a successful backup result
   or a protected `restic snapshots --json` listing. Restore never accepts
   `latest`. Provision a new PostgreSQL/Redis project and private S3 bucket.
   Keep API/workers stopped and external writers fenced throughout recovery.
2. Create a protected restore config with the **same** installation/repository
   identity and vault/password, a different project/state directory, the new
   target endpoint/bucket and target-only S3 credential environment. Configure
   all eventual API/worker replicas to that target. Source bucket/project are
   rejected; any user DB relations, live objects, versions or delete markers in
   the target are rejected. The target must support version listing.
3. Start only the empty target PostgreSQL and Redis services using its explicit
   project and protected env file. Load recovery credentials without tracing.

```sh
/opt/practiceflow-backup-venv/bin/python /opt/practiceflow/scripts/production_backup.py \
  --config /etc/practiceflow/restore.json restore \
  --snapshot REPLACE_WITH_FULL_64_CHARACTER_SNAPSHOT_ID --confirm-empty-target
```

4. The script reads back/decrypts and validates the entire manifest before any
   target write, conditionally creates each object, reads it back and checks its
   SHA-256, verifies the exact object set, then restores the database in one
   transaction with `--exit-on-error`, `--no-owner`, `--no-acl`. It verifies DB
   references after restore and leaves application services stopped. Restore
   DB role ownership/grants separately from the escrow; no role passwords are
   archived. Use the PostgreSQL major version and application image/schema
   recorded in the manifest. Do not run a newer incompatible migration blindly.
5. Start the matching application image and workers privately, with original
   MFA/audit keys, seed disabled, fresh Redis and outbound notifications disabled.
   Check readiness and both worker heartbeats; log in as an authorized drill
   account, download a known image via `/api/v1/files/{id}`, compare its bytes,
   open its report document and generate/download a DOCX containing its media.
   Test MFA/audit and any required PDF/PPTX/material paths separately for the
   installation. Only then consider an approved traffic cutover.
6. A failure after object creation leaves a partial target intentionally. Do
   not rerun against it or auto-delete it: provision another empty bucket/DB.
   Cleanup must use only the drill's verified project/bucket identities.

## Reproducible drill and measured evidence

Run from a checkout with Docker Engine available (Windows PowerShell or Linux).
The test runner mounts the Docker socket, so run only trusted repository code.
It creates fresh UUID source/restore Compose projects, no host ports, synthetic
E2E users/documents, separate MinIO live/vault instances and independent target
DB/storage. It reuses the production app/worker images and existing API helpers.

```sh
docker build -t practiceflow-backup-test-runner -f testing/backup/Dockerfile .
docker run --rm -v "$PWD:/workspace:ro" -v /var/run/docker.sock:/var/run/docker.sock \
  practiceflow-backup-test-runner python -m unittest discover -s scripts/tests -v
docker run --rm -v "$PWD:/workspace:ro" -v /var/run/docker.sock:/var/run/docker.sock \
  practiceflow-backup-test-runner
```

In PowerShell use `${PWD}:/workspace:ro` for the first mount. Cleanup verifies
UUID namespaces were unused before creation and removes only those projects
and volumes. Generic failure diagnostics deliberately do not dump app logs.

The drill checks real custom dump/restore, all current objects including an
orphan, hashes, authenticated image download, report reference, DOCX embedded
image, API and **both workers** resuming after success and missing-object
failure, wrong repository refusal, nonempty/source restore refusal, removal
of an expired owned snapshot, preservation of an unrelated snapshot, anonymous
object access denial and a full `restic check --read-data`.

Each successful run prints measured `pause_seconds`, `total_seconds`, dump/object
byte counts, `restore_seconds`, application verification time and total recovery
time as a final JSON result. These results persist in the PR's **PostgreSQL and
S3 backup restore drill** CI job log; the associated PR records the actual
successful measurements and runner context, not estimates. This fixture uses
HTTP on private disposable Docker networks and puts its independent containers
on one Docker host; production mode rejects these insecure endpoints. The drill
does not establish production throughput, network durability, KMS/escrow/MFA
recovery, provider policies, systemd execution on a real server, public ingress
or production RPO/RTO. No production backup is claimed until an actual remote
run, target restore and alert/age monitoring have been verified.

Implementation references: [restic repository setup](https://restic.readthedocs.io/en/stable/030_preparing_a_new_repo.html),
[restic restore](https://restic.readthedocs.io/en/stable/050_restore.html),
[retention and prune](https://restic.readthedocs.io/en/stable/060_forget.html),
[systemd timers](https://www.freedesktop.org/software/systemd/man/260/systemd.timer.html).
