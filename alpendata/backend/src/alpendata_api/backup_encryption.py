"""Encrypt complete operator bundles with age; expose plaintext only after full verification."""

import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
from contextlib import contextmanager
from pathlib import Path

from .backup import BackupFailure, checksum
from .backup_restore import verify_bundle

FILES = ("database.dump", "states.tar", "manifest.json")
PUBLIC_KEY = re.compile(r"age1[023456789acdefghjklmnpqrstuvwxyz]{58}")
PRIVATE_KEY = re.compile(r"AGE-SECRET-KEY-1[023456789ACDEFGHJKLMNPQRSTUVWXYZ]{58}")


@contextmanager
def regular_file(path):
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, "rb") as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise BackupFailure("backup_regular_file_required")
        yield stream


def age(executable, arguments, source, output, *, identity=None):
    if sys.platform != "linux" or not executable.is_absolute():
        raise BackupFailure("backup_age_requires_linux_absolute_path")
    descriptors = ()
    if identity is not None:
        info = os.fstat(identity.fileno())
        if info.st_mode & 0o077 or info.st_size > 16384:
            raise BackupFailure("backup_identity_permissions_invalid")
        lines = identity.read().decode("ascii").splitlines()
        keys = [line.strip() for line in lines if line.strip() and not line.startswith("#")]
        if not keys or any(not PRIVATE_KEY.fullmatch(key) for key in keys):
            raise BackupFailure("backup_native_identity_required")
        identity.seek(0)
        arguments = [*arguments, "--identity", f"/proc/self/fd/{identity.fileno()}"]
        descriptors = (identity.fileno(),)
    try:
        result = subprocess.run(
            [str(executable), *arguments],
            stdin=source,
            stdout=output,
            stderr=subprocess.DEVNULL,
            env={"PATH": "/usr/bin:/bin"},
            pass_fds=descriptors,
            timeout=3600,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        raise BackupFailure("backup_age_unavailable") from None
    if result.returncode:
        raise BackupFailure(
            "backup_encryption_failed" if "--encrypt" in arguments else "backup_decryption_failed"
        )
    output.flush()
    os.fsync(output.fileno())


def seal_bundle(bundle, output, recipients, executable=Path("/usr/bin/age"), *, scratch=Path("/var/tmp")):
    if not recipients or len(recipients) > 16 or any(not PUBLIC_KEY.fullmatch(key) for key in recipients):
        raise BackupFailure("backup_native_recipients_required")
    manifest = verify_bundle(bundle)
    output = output.absolute()
    if output.exists() or output.is_symlink():
        raise BackupFailure("backup_encrypted_destination_exists")
    if output.resolve().is_relative_to(bundle.resolve()):
        raise BackupFailure("backup_destination_overlaps_bundle")
    if not scratch.is_absolute():
        raise BackupFailure("backup_scratch_path_invalid")
    with (
        tempfile.TemporaryDirectory(prefix=".alpendata-plaintext-", dir=scratch) as temporary,
        tempfile.TemporaryDirectory(prefix=".alpendata-ciphertext-", dir=output.parent) as ciphertext,
    ):
        staging = Path(temporary)
        # A bounded file stream keeps large databases out of Python memory.
        with tarfile.open(staging / "bundle.tar", "w") as archive:
            for name in FILES:
                with regular_file(bundle / name) as source:
                    info = tarfile.TarInfo(name)
                    info.size, info.mode = os.fstat(source.fileno()).st_size, 0o600
                    archive.addfile(info, source)
        # Check the bytes actually packed, so a source modified during copying cannot
        # become an apparently successful encrypted backup with mismatched inner hashes.
        with tarfile.open(staging / "bundle.tar", "r:") as archive:
            if json.load(archive.extractfile("manifest.json")) != manifest:
                raise BackupFailure("backup_source_changed")
            for name in FILES[:2]:
                with archive.extractfile(name) as packed:
                    if hashlib.file_digest(packed, "sha256").hexdigest() != manifest["files"][name]["sha256"]:
                        raise BackupFailure("backup_source_changed")
        encrypted = Path(ciphertext) / "bundle.age"
        with (staging / "bundle.tar").open("rb") as source, encrypted.open("xb") as target:
            arguments = ["--encrypt"]
            for recipient in dict.fromkeys(recipients):
                arguments.extend(["--recipient", recipient])
            age(executable, arguments, source, target)
        encrypted.chmod(0o600)
        receipt = {
            "backup_id": manifest["backup_id"],
            "sha256": checksum(encrypted),
            "bytes": encrypted.stat().st_size,
            "status": "encrypted",
        }
        # Same-filesystem hard-link publication is atomic and refuses an existing name.
        os.link(encrypted, output)
    return receipt


def unseal_bundle(
    encrypted,
    destination,
    identity_path,
    expected_sha256,
    executable=Path("/usr/bin/age"),
    *,
    scratch=Path("/var/tmp"),
):
    if not re.fullmatch(r"[0-9a-f]{64}", expected_sha256):
        raise BackupFailure("backup_expected_digest_required")
    destination = destination.absolute()
    if destination.exists() or destination.is_symlink():
        raise BackupFailure("backup_plaintext_destination_exists")
    if not scratch.is_absolute():
        raise BackupFailure("backup_scratch_path_invalid")
    with tempfile.TemporaryDirectory(prefix=".alpendata-unseal-", dir=scratch) as temporary:
        staging = Path(temporary)
        with regular_file(encrypted) as source, regular_file(identity_path) as identity:
            if hashlib.file_digest(source, "sha256").hexdigest() != expected_sha256:
                raise BackupFailure("backup_encrypted_integrity_failed")
            source.seek(0)
            with (staging / "bundle.tar").open("xb") as plaintext:
                age(executable, ["--decrypt"], source, plaintext, identity=identity)
        # age may emit verified prefixes before reporting a truncated final chunk.
        # Parse/extract nothing until the process has authenticated the entire input.
        unpacked = staging / "unpacked"
        unpacked.mkdir(mode=0o700)
        with tarfile.open(staging / "bundle.tar", "r:") as archive:
            seen = set()
            for info in archive:
                if info.name not in FILES or info.name in seen or not info.isfile():
                    raise BackupFailure("backup_envelope_invalid")
                seen.add(info.name)
                with archive.extractfile(info) as source, (unpacked / info.name).open("xb") as target:
                    shutil.copyfileobj(source, target, length=1024 * 1024)
                (unpacked / info.name).chmod(0o600)
            if seen != set(FILES):
                raise BackupFailure("backup_envelope_invalid")
        manifest = verify_bundle(unpacked)
        destination.mkdir(mode=0o700, parents=False, exist_ok=False)
        for name in FILES:  # The completion manifest is published last.
            with (unpacked / name).open("rb") as source, (destination / name).open("xb") as target:
                shutil.copyfileobj(source, target, length=1024 * 1024)
                target.flush()
                os.fsync(target.fileno())
            (destination / name).chmod(0o600)
    return {"backup_id": manifest["backup_id"], "status": "decrypted_verified"}


def main():
    parser = argparse.ArgumentParser(description="AlpenData age backup encryption")
    parser.add_argument("--age-bin", type=Path, default=Path("/usr/bin/age"))
    parser.add_argument("--scratch", type=Path, default=Path("/var/tmp"))
    commands = parser.add_subparsers(dest="action", required=True)
    seal = commands.add_parser("seal")
    seal.add_argument("--bundle", type=Path, required=True)
    seal.add_argument("--output", type=Path, required=True)
    seal.add_argument("--recipient", action="append", required=True)
    unseal = commands.add_parser("unseal")
    unseal.add_argument("--input", type=Path, required=True)
    unseal.add_argument("--destination", type=Path, required=True)
    unseal.add_argument("--identity", type=Path, required=True)
    unseal.add_argument("--expected-sha256", required=True)
    args = parser.parse_args()
    try:
        if sys.platform != "linux":
            raise BackupFailure("backup_encryption_requires_linux")
        os.umask(0o077)
        if args.action == "seal":
            receipt = seal_bundle(
                args.bundle, args.output, args.recipient, args.age_bin, scratch=args.scratch
            )
        else:
            receipt = unseal_bundle(
                args.input,
                args.destination,
                args.identity,
                args.expected_sha256,
                args.age_bin,
                scratch=args.scratch,
            )
        print(json.dumps(receipt))
    except BackupFailure as error:
        print(json.dumps({"status": "refused", "error": str(error)}))
        return 1
    except (OSError, ValueError, KeyError, tarfile.TarError):
        print(json.dumps({"status": "refused", "error": "backup_encryption_operation_failed"}))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
