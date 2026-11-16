# Expire development Hanko flows

Use this one-off operation to prevent registration flows started under an unsafe
configuration from completing. It expires **all active development flows**,
including login and profile flows. Users must restart those flows. It does not
delete users, credentials, existing sessions or app data. The operation does
not quarantine an existing Hanko account.

Hanko v3.1.0 stores registration flows for up to 24 hours. Disabling signup
stops new email registration actions, but does not cancel an already advanced
flow. This operation updates Hanko's internal database; its admin API does not
provide a flow cancellation endpoint. Use only with Hanko v3.1.0 and after the
checks below. No production database is targeted.

Google callbacks do not use this flow table. They check the active signup
setting before creating a user, so the signup pause and old-pod checks also
apply to those requests.

## Before you start

1. Keep dev signup disabled. Verify that every running `hanko-dev` pod uses a
   ConfigMap with `account.allow_signup: false`, that the rollout completed and
   that no old-config pod or request remains. Do not re-enable signup until the
   quarantine snapshot and verified registration configuration are in place.
2. Verify the most recent encrypted dev database backup and its restore with
   the matching Hanko encryption key. Follow the [backup guide](hanko.md#backup-and-restore).
3. Review the operation and its network policy. Confirm the Job references only
   `hanko-postgres/dev-password` and the `hanko_dev` database role. The Job aborts
   if the connected database or role differs.
4. Choose a quiet period. The Job takes an exclusive lock on the dev `flows`
   table. Ongoing flows finish before the lock is acquired; new flow requests
   wait briefly. It fails if the lock takes more than 15 seconds.

## Preview and run

From the GitOps repository root, inspect the change and check the manifest:

```bash
kubectl --context oracle-k3s diff -f operations/hanko/expire-dev-flows.yaml
kubectl --context oracle-k3s apply --dry-run=server -f operations/hanko/expire-dev-flows.yaml
```

`diff` returns exit code 1 when it finds changes. The file is not included in
Argo CD and will not run when merged. To run it once:

```bash
kubectl --context oracle-k3s apply -f operations/hanko/expire-dev-flows.yaml
kubectl --context oracle-k3s -n auth-system wait --for=condition=complete job/hanko-dev-flow-expiry --timeout=120s
kubectl --context oracle-k3s -n auth-system logs job/hanko-dev-flow-expiry
```

The Job logs SQL command status and the number of expired rows; they must not
contain connection credentials or flow contents. Record the time and count in
the operator's incident record. The Job is retained for one day, then Kubernetes
removes it. The NetworkPolicy remains until it is explicitly removed.

On failure, inspect the Job status and logs. The transaction rolls back if it
cannot acquire the lock or any command fails. Investigate before retrying;
delete the completed or failed Job first because Kubernetes Jobs are immutable.

```bash
kubectl --context oracle-k3s delete --ignore-not-found -f operations/hanko/expire-dev-flows.yaml
```

Keep signup disabled while taking the complete Hanko user snapshot and applying
the app's subject quarantine. Verify the snapshot and access restrictions before
restoring verified signup. Removing a quarantined subject or restoring old flows
can restore unsafe access. Restore a backup only into an isolated database for
recovery review; do not roll the live database back to reactivate old flows.

## Modify or remove

Review any change to the SQL against the exact Hanko version and validate it on
an isolated database. Preview the changed manifest with the commands above.
Run the Job again only for a new, approved maintenance need. Delete the Job and
the temporary NetworkPolicy with the command above after recording the result.
