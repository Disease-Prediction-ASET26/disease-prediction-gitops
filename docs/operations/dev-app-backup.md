# Back up the development app database before a reset

Use this one-off procedure before deleting dev application records. It exports only
`disease_prediction_dev` from the Proxmox CloudNativePG primary. It does not back up
Hanko, production, the backend encryption key, or other services. This is not a
scheduled backup or a production recovery plan.

## Requirements

- Stop the dev app writers before creating the backup and keep them stopped until the
  reset and checks finish. Confirm the correct cluster and database separately.
- Use a trusted workstation with enough memory and no unencrypted swap access for the
  backup process or its restore container. The compressed
  PostgreSQL archive is limited to 128 MiB. The program holds the dump and encryption
  buffers in memory; an isolated restore also uses temporary memory-backed storage.
  Core dumps are disabled. The commands below prevent swap use on the current Linux
  workstation; a hypervisor may still page memory outside the guest.
- Have `kubectl` access to context `proxmox-k3s`, Terraform access to the existing Oracle
  configuration and state, and an OCI profile allowed to use the project's Vault key.
  The existing OCI CLI Python environment includes the OCI SDK and `cryptography`.
- Docker must be available for the isolated restore check. The check starts a local
  PostgreSQL container with no network, a read-only root filesystem and tmpfs database
  storage. It removes the container after the check.
- Preserve the matching `data_encryption_key` in OCI Vault. The database dump contains
  encrypted application fields, so restoring the database without that key is not enough
  to recover those fields. Keep access to the OCI KMS key and the encryption key in the
  recovery plan.

## Create and verify

Run from the GitOps repository root. Set `OCI_PYTHON` to the Python interpreter used by
the installed OCI CLI, and set `ORACLE_TERRAFORM_DIR` to the Oracle Terraform directory.
The OCI CLI's executable begins with a shebang containing its Python path. For the
current Linuxbrew installation, these commands obtain that path without displaying
credentials:

```bash
OCI_PYTHON="$(head -n 1 "$(command -v oci)" | cut -c 3-)"
ORACLE_TERRAFORM_DIR="../disease-prediction-infra/terraform/oracle"
systemd-run --user --scope -p MemoryMax=512M -p MemorySwapMax=0 \
  "$OCI_PYTHON" scripts/backup-dev-app-database.py create \
  /secure/path/dev-app-before-reset.enc --terraform-dir "$ORACLE_TERRAFORM_DIR"
systemd-run --user --scope -p MemoryMax=512M -p MemorySwapMax=0 \
  "$OCI_PYTHON" scripts/backup-dev-app-database.py verify \
  /secure/path/dev-app-before-reset.enc --terraform-dir "$ORACLE_TERRAFORM_DIR"
```

The `systemd-run` limits require a user systemd session with cgroup v2 and delegated
memory controls. They prevent the Python process and its child commands from using
swap; they do not apply to containers started by the Docker daemon. The restore
container has its own 512 MiB memory limit and no swap. If these controls are not
available, use another verified method that prevents unencrypted swap access. If the
backup exceeds the process memory limit, stop and select an appropriate larger limit;
do not proceed with the reset.

Use `--profile NAME` if the OCI profile is not `DEFAULT`. The program queries the
existing Terraform output for the Vault, locates `disease-prediction-secrets-key`,
and checks KMS access before exporting. Each backup uses a fresh AES-256-GCM data
key wrapped by that KMS key. It creates a new file with mode `0600` and refuses to
overwrite an existing path. Use a protected directory outside Git. The program does
not print database contents, credentials, key IDs or the backup path.

The `verify` command decrypts the archive in memory and restores it to a temporary,
network-isolated local PostgreSQL container. It checks that the restore succeeds and
that the Flyway history table can be read. It does not check application-level login
or decrypt the app's protected fields. It does not update the live database.

If either command fails, do not start the reset. Check the workstation's OCI profile,
KMS permissions, Terraform state, cluster access, Docker and available memory. Error
messages are intentionally limited so they cannot expose credentials or data.

## Keep and remove the backup

Keep the encrypted file on reliable local storage outside the cluster, restricted to
the operator. Keep it until the reset has been validated and the team has agreed on
a retention period. Record its location privately. Deleting or disabling the OCI KMS
key makes the backup unreadable; changing the backend data-encryption key can also
make restored application fields unreadable. Confirm the required keys are recoverable
before deleting the backup. Remove the file through the workstation's normal secure
data-retention process when it is no longer needed.

For a recovery into an application database, perform a separately reviewed restore
into a new isolated database, use the matching backend encryption key, verify the app
and only then consider a cutover. This script's `verify` action is an isolated restore
check, not a live restore command.
