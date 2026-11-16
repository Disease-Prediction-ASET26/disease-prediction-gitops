import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/backup-dev-app-database.py"
spec = importlib.util.spec_from_file_location("dev_backup", SCRIPT)
backup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backup)


class FakeKms:
    def __init__(self):
        self.key = AESGCM.generate_key(bit_length=256)
        self.nonce = os.urandom(12)

    def encrypt(self, details):
        wrapped = AESGCM(self.key).encrypt(self.nonce, backup.unb64(details.plaintext), None)
        return mock.Mock(data=mock.Mock(ciphertext=backup.b64(wrapped)))

    def decrypt(self, details):
        value = AESGCM(self.key).decrypt(self.nonce, backup.unb64(details.ciphertext), None)
        return mock.Mock(data=mock.Mock(plaintext=backup.b64(value)))


class BackupTest(unittest.TestCase):
    def setUp(self):
        self.kms = FakeKms()
        self.dump = b"PGDMP" + b"sensitive-test-database-content"

    def test_encrypted_round_trip_and_tampering(self):
        blob = backup.encrypt_dump(self.dump, self.kms, "fake")
        self.assertNotIn(self.dump, blob)
        self.assertEqual(backup.decrypt_dump(blob, self.kms, "fake"), self.dump)
        envelope = json.loads(blob)
        tampered = bytearray(backup.unb64(envelope["ciphertext"]))
        tampered[0] ^= 1
        envelope["ciphertext"] = backup.b64(tampered)
        with self.assertRaises(InvalidTag):
            backup.decrypt_dump(json.dumps(envelope), self.kms, "fake")

    def test_wrong_key_and_format_are_rejected(self):
        blob = backup.encrypt_dump(self.dump, self.kms, "fake")
        with self.assertRaises(InvalidTag):
            backup.decrypt_dump(blob, FakeKms(), "fake")
        with self.assertRaises(RuntimeError):
            backup.decrypt_dump(b'{"version": 2}', self.kms, "fake")
        with self.assertRaises(RuntimeError):
            backup.encrypt_dump(b"not a postgres archive", self.kms, "fake")

    def test_output_is_private_exclusive_and_preserves_existing_file(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "backup.enc"
            backup.write_new(output, b"ciphertext")
            self.assertEqual(output.stat().st_mode & 0o777, 0o600)
            with self.assertRaises(FileExistsError):
                backup.write_new(output, b"replacement")
            self.assertEqual(output.read_bytes(), b"ciphertext")

    def test_dump_only_queries_selected_dev_database(self):
        cluster = b'{"status":{"currentPrimary":"postgres-1"}}'
        with mock.patch.object(backup, "run", return_value=cluster):
            with mock.patch.object(backup, "bounded_dump", return_value=self.dump) as runner:
                self.assertEqual(backup.dump_dev_database(), self.dump)
        command = runner.call_args.args[0]
        remote = command[-1]
        self.assertIn("SELECT current_database()", remote)
        self.assertIn("--dbname disease_prediction_dev", remote)
        self.assertNotIn("disease_prediction_prod", remote)
        self.assertNotIn("-t", command)

    def test_bad_primary_and_dump_are_rejected(self):
        with mock.patch.object(backup, "run", return_value=b'{"status":{"currentPrimary":"other-1"}}'):
            with self.assertRaises(RuntimeError):
                backup.dump_dev_database()
        with mock.patch.object(backup, "run", return_value=b'{"status":{"currentPrimary":"postgres-1"}}'):
            with mock.patch.object(backup, "bounded_dump", return_value=b"bad"):
                with self.assertRaises(RuntimeError):
                    backup.dump_dev_database()

    def test_dump_size_is_bounded_while_reading(self):
        with mock.patch.object(backup, "MAX_DUMP_SIZE", 100):
            with self.assertRaises(RuntimeError):
                backup.bounded_dump(["python3", "-c", "import sys; sys.stdout.buffer.write(b'x'*101)"])
            self.assertEqual(backup.bounded_dump(["python3", "-c", "print('small')"]), b"small\n")

    def test_restore_is_network_isolated_and_cleans_up_on_failure(self):
        with mock.patch.object(backup, "run", side_effect=[b"container", b"", RuntimeError("failure")]) as runner:
            with mock.patch.object(backup.subprocess, "run", return_value=mock.Mock(returncode=0)) as process:
                with self.assertRaises(RuntimeError):
                    backup.verify_restore(self.dump)
        self.assertIn("none", runner.call_args_list[0].args[0])
        self.assertTrue(any(arg.startswith("/var/lib/postgresql:rw,nosuid,nodev,noexec")
                            for arg in runner.call_args_list[0].args[0]))
        self.assertEqual(process.call_args.args[0][:2], ["docker", "stop"])
        self.assertEqual(runner.call_args_list[-1].kwargs["input_data"], self.dump)


if __name__ == "__main__":
    unittest.main()
