#!/usr/bin/env python3
"""Encrypted operator backup and isolated restore check for the dev app database."""

import argparse
import base64
import json
import hmac
import os
import resource
import selectors
import stat
import subprocess
import sys
import time
from pathlib import Path

import oci
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

CONTEXT = "proxmox-k3s"
NAMESPACE = "postgres"
DATABASE = "disease_prediction_dev"
KEY_NAME = "disease-prediction-secrets-key"
AAD = b"pocket-doc.dev-app-database.v1"
MAX_DUMP_SIZE = 128 * 1024 * 1024
IMAGE = "postgres:18.6-alpine@sha256:9ba53c7d41ea093baf5c1ba635ba5434c4f979880527d49bb7d9237d3193085b"


def run(args, *, input_data=None, timeout=120):
    result = subprocess.run(args, input=input_data, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, timeout=timeout, check=False)
    if result.returncode:
        raise RuntimeError("a required command failed")
    return result.stdout


def b64(data):
    return base64.b64encode(data).decode("ascii")


def unb64(data):
    return base64.b64decode(data, validate=True)


def make_kms(terraform_dir, profile):
    vault_id = run(["terraform", f"-chdir={terraform_dir}", "output", "-raw", "secrets_vault_id"]).decode().strip()
    config = oci.config.from_file(profile_name=profile)
    vault = oci.key_management.KmsVaultClient(config).get_vault(vault_id).data
    manager = oci.key_management.KmsManagementClient(config, vault.management_endpoint)
    keys = oci.pagination.list_call_get_all_results(manager.list_keys, vault.compartment_id).data
    keys = [key for key in keys if key.display_name == KEY_NAME and key.lifecycle_state == "ENABLED" and key.algorithm == "AES"]
    if len(keys) != 1:
        raise RuntimeError("expected one enabled project backup key")
    return oci.key_management.KmsCryptoClient(config, vault.crypto_endpoint), keys[0].id


def dump_dev_database():
    cluster = json.loads(run(["kubectl", "--context", CONTEXT, "-n", NAMESPACE,
                              "get", "cluster", "postgres", "-o", "json"]))
    primary = cluster["status"]["currentPrimary"]
    if not primary or not primary.startswith("postgres-") or not primary[9:].isdigit():
        raise RuntimeError("cannot determine PostgreSQL primary")
    # Check the actual connection target before streaming the one permitted database.
    remote = ("set -eu; db=$(psql -X -v ON_ERROR_STOP=1 -d disease_prediction_dev -Atc "
              "'SELECT current_database()'); [ \"$db\" = disease_prediction_dev ]; "
              "exec pg_dump --format=custom --no-owner --no-acl --dbname disease_prediction_dev")
    command = ["kubectl", "--context", CONTEXT, "-n", NAMESPACE, "exec", primary,
               "--", "sh", "-c", remote]
    dump = bounded_dump(command)
    if not dump.startswith(b"PGDMP"):
        raise RuntimeError("invalid PostgreSQL archive")
    return dump


def bounded_dump(command):
    # Bound memory while reading, and discard stderr because it may contain identifiers.
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    data = bytearray()
    deadline = time.monotonic() + 600
    try:
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ)
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise RuntimeError("database export timed out")
                if not selector.select(remaining):
                    raise RuntimeError("database export timed out")
                chunk = os.read(process.stdout.fileno(), 256 * 1024)
                if not chunk:
                    break
                data.extend(chunk)
                if len(data) > MAX_DUMP_SIZE:
                    raise RuntimeError("database export exceeds size limit")
        if process.wait(timeout=max(0.1, deadline - time.monotonic())):
            raise RuntimeError("database export failed")
        return bytes(data)
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()
        process.stdout.close()


def generate_data_key(kms, key_id):
    key = AESGCM.generate_key(bit_length=256)
    wrapped = kms.encrypt(oci.key_management.models.EncryptDataDetails(
        key_id=key_id, plaintext=b64(key), encryption_algorithm="AES_256_GCM")).data.ciphertext
    check = kms.decrypt(oci.key_management.models.DecryptDataDetails(
        key_id=key_id, ciphertext=wrapped, encryption_algorithm="AES_256_GCM")).data.plaintext
    if not hmac.compare_digest(key, unb64(check)):
        raise RuntimeError("cannot verify backup key")
    return key, wrapped


def encrypt_dump(dump, kms, key_id, material=None):
    if not dump.startswith(b"PGDMP") or len(dump) > MAX_DUMP_SIZE:
        raise RuntimeError("invalid PostgreSQL archive")
    key, wrapped = material if material is not None else generate_data_key(kms, key_id)
    nonce = os.urandom(12)
    ciphertext = AESGCM(key).encrypt(nonce, dump, AAD)
    return json.dumps({"version": 1, "wrapped_key": wrapped, "nonce": b64(nonce),
                       "ciphertext": b64(ciphertext)}, separators=(",", ":")).encode()


def decrypt_dump(envelope, kms, key_id):
    if len(envelope) > (MAX_DUMP_SIZE * 2):
        raise RuntimeError("backup exceeds size limit")
    parsed = json.loads(envelope)
    if set(parsed) != {"version", "wrapped_key", "nonce", "ciphertext"} or parsed["version"] != 1:
        raise RuntimeError("unsupported backup format")
    result = kms.decrypt(oci.key_management.models.DecryptDataDetails(
        key_id=key_id, ciphertext=parsed["wrapped_key"], encryption_algorithm="AES_256_GCM"))
    key = unb64(result.data.plaintext)
    nonce = unb64(parsed["nonce"])
    if len(key) != 32 or len(nonce) != 12:
        raise RuntimeError("invalid backup parameters")
    dump = AESGCM(key).decrypt(nonce, unb64(parsed["ciphertext"]), AAD)
    if len(dump) > MAX_DUMP_SIZE or not dump.startswith(b"PGDMP"):
        raise RuntimeError("invalid PostgreSQL archive")
    return dump


def write_new(path, contents):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(contents)
            stream.flush()
            os.fsync(stream.fileno())
        directory_fd = os.open(str(Path(path).parent), os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except BaseException:
        Path(path).unlink(missing_ok=True)
        raise


def read_backup(path):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_DUMP_SIZE * 2:
            raise RuntimeError("invalid backup file")
        data = stream.read(MAX_DUMP_SIZE * 2 + 1)
        if len(data) > MAX_DUMP_SIZE * 2:
            raise RuntimeError("backup exceeds size limit")
        return data


def verify_restore(dump):
    container = None
    try:
        container = run(["docker", "run", "--detach", "--rm", "--network", "none",
                         "--read-only", "--user", "70:70", "--cap-drop", "ALL",
                         "--security-opt", "no-new-privileges", "--memory", "512m",
                         "--memory-swap", "512m",
                         "--pids-limit", "64",
                         "--tmpfs", "/var/lib/postgresql:rw,nosuid,nodev,noexec,uid=70,gid=70,mode=700,size=1g",
                         "--tmpfs", "/var/run/postgresql:rw,nosuid,nodev,uid=70,gid=70,mode=700",
                         "--tmpfs", "/tmp:rw,nosuid,nodev,size=64m",
                         "-e", "POSTGRES_HOST_AUTH_METHOD=trust", IMAGE], timeout=120).decode().strip()
        for _ in range(60):
            result = subprocess.run(["docker", "exec", container, "pg_isready", "-U", "postgres"],
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
            if result.returncode == 0:
                break
            time.sleep(1)
        else:
            raise RuntimeError("isolated PostgreSQL did not become ready")
        run(["docker", "exec", container, "createdb", "-U", "postgres", "restore_check"])
        run(["docker", "exec", "-i", container, "pg_restore", "-U", "postgres", "-d", "restore_check",
             "--no-owner", "--no-acl", "--exit-on-error"], input_data=dump, timeout=600)
        run(["docker", "exec", container, "psql", "-U", "postgres", "-d", "restore_check", "-v",
             "ON_ERROR_STOP=1", "-c", "SELECT count(*) FROM public.flyway_schema_history"], timeout=30)
    finally:
        if container:
            subprocess.run(["docker", "stop", "--time", "3", container], stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, check=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("create", "verify"))
    parser.add_argument("file", type=Path, help="new encrypted file, or file to verify")
    parser.add_argument("--terraform-dir", required=True, help="path to the Oracle Terraform directory")
    parser.add_argument("--profile", default="DEFAULT", help="OCI CLI configuration profile")
    args = parser.parse_args()
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    try:
        kms, key_id = make_kms(args.terraform_dir, args.profile)
        if args.action == "create":
            material = generate_data_key(kms, key_id)
            write_new(args.file, encrypt_dump(dump_dev_database(), kms, key_id, material))
            print("Encrypted dev database backup created.")
        else:
            verify_restore(decrypt_dump(read_backup(args.file), kms, key_id))
            print("Encrypted dev database backup restored in an isolated temporary database.")
    except Exception as exc:
        # Provider, subprocess and database errors can contain secrets or identifiers.
        print(f"Backup operation failed ({type(exc).__name__}); check access and prerequisites.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
