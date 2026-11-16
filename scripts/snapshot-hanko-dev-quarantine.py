#!/usr/bin/env python3
"""Store the dev Hanko subjects in OCI Vault without writing them locally."""

import argparse
import base64
import json
import logging
import subprocess
import sys
import uuid
from pathlib import Path

SECRET_NAME = "hanko-dev-quarantine"
MAX_PAYLOAD_BYTES = 24_000  # OCI Vault secret bundles have a 25 KB limit.


def command_json(command):
    return json.loads(subprocess.check_output(command, stderr=subprocess.DEVNULL, timeout=60))


def read_subjects(context):
    command = [
        "kubectl", "--context", context, "-n", "auth-system", "exec",
        "deployment/hanko-postgres", "-c", "postgres", "--", "psql",
        "-U", "postgres", "-d", "hanko_dev", "-X", "-A", "-t",
        "-v", "ON_ERROR_STOP=1", "-c",
        "SELECT COALESCE(public_id::text, 'NULL') FROM public.users ORDER BY public_id;",
    ]
    rows = subprocess.check_output(command, stderr=subprocess.DEVNULL, timeout=30).decode().splitlines()
    if not rows or any(str(uuid.UUID(value)) != value for value in rows):
        raise ValueError("Snapshot is empty or contains an invalid subject")
    if len(rows) != len(set(rows)):
        raise ValueError("Snapshot contains duplicate subjects")
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--terraform-dir", required=True, type=Path,
                        help="Initialized OCI Terraform directory for this cluster")
    parser.add_argument("--context", default="oracle-k3s", help="Kubernetes context")
    parser.add_argument("--signup-paused-and-drained", action="store_true",
                        help="Confirm dev signup is disabled and in-flight requests drained")
    args = parser.parse_args()
    if not args.signup_paused_and_drained:
        parser.error("Confirm dev signup is disabled and in-flight requests have drained")
    if not args.terraform_dir.is_dir():
        parser.error("Terraform directory does not exist")

    # Ensure SDK diagnostics cannot print secret content or request bodies.
    logging.disable(logging.CRITICAL)
    import oci

    first = read_subjects(args.context)
    if first != read_subjects(args.context):
        raise RuntimeError("The two snapshots differ")
    payload = json.dumps({"subjects": "\n".join(first) + "\n"}, separators=(",", ":")).encode()
    if len(payload) > MAX_PAYLOAD_BYTES:
        raise ValueError("Snapshot exceeds the supported Vault size")

    terraform = ["terraform", "-chdir=" + str(args.terraform_dir)]
    outputs = command_json(terraform + ["output", "-json"])
    state = command_json(terraform + ["show", "-json"])
    resources = state["values"]["root_module"]["resources"]
    key = next(r["values"] for r in resources if r["address"] == "oci_kms_key.secrets")
    vault_id = outputs["secrets_vault_id"]["value"]
    compartment_id = key["compartment_id"]
    vault = oci.vault.VaultsClient(oci.config.from_file())
    existing = oci.pagination.list_call_get_all_results(
        vault.list_secrets, compartment_id=compartment_id, vault_id=vault_id, name=SECRET_NAME
    ).data
    if any(item.secret_name == SECRET_NAME and item.lifecycle_state != "DELETED" for item in existing):
        raise RuntimeError("A quarantine secret already exists")

    details = oci.vault.models.CreateSecretDetails(
        compartment_id=compartment_id, vault_id=vault_id, key_id=key["id"],
        secret_name=SECRET_NAME, description="Previously unverified Hanko dev identities",
        secret_content=oci.vault.models.Base64SecretContentDetails(
            content=base64.b64encode(payload).decode(), stage="CURRENT"
        ),
    )
    vault.create_secret(details)
    print("Quarantine snapshot stored in OCI Vault. Subjects:", len(first))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        # An SDK or command error may include sensitive values; do not print it.
        print("Snapshot failed (" + type(exc).__name__ + "); inspect Vault and cluster state before retrying.",
              file=sys.stderr)
        sys.exit(1)
