"""Real age encryption through a complete PostgreSQL + owner-files recovery."""

import io
import json
import os
import subprocess
import sys
import tarfile
from pathlib import Path

import pytest
from sqlalchemy import select
from test_backup import backup_host as backup_host
from test_backup import empty_target
from test_routines import connected_service as connected_service
from test_routines import routine_service as routine_service

from alpendata_api.backup import BackupFailure, checksum, create_bundle
from alpendata_api.backup_encryption import seal_bundle, unseal_bundle
from alpendata_api.backup_restore import restore_bundle, verify_bundle
from alpendata_api.models import AuthSession, MicrosoftConnection, User

pytestmark = pytest.mark.linux_only


@pytest.fixture
def encryption(routine_service, backup_host, request):
    configured = request.config.getoption("--age-bin")
    if not configured:
        pytest.skip("Requires --age-bin for real encryption")
    executable = Path(configured)
    app, _, _, _, _, org, _, owner = routine_service
    root, runtime, binaries = backup_host
    pairs = []
    for number in range(3):
        identity = root / f"identity-{number}.txt"
        subprocess.run(
            [str(executable.with_name("age-keygen")), "-o", str(identity)],
            capture_output=True,
            check=True,
            timeout=10,
        )
        result = subprocess.run(
            [str(executable.with_name("age-keygen")), "-y", str(identity)],
            capture_output=True,
            check=True,
            timeout=10,
            text=True,
        )
        pairs.append((identity, result.stdout.strip()))
    with runtime.owner_state(org, owner[0]) as state:
        (state / "private.txt").write_bytes(b"Private coaching data\n" * 16000)
    bundle = root / "bundle"
    create_bundle(app.state.engine, runtime, bundle, binaries, "a" * 40)
    return root, executable, pairs, bundle


def test_multiple_recovery_keys_and_cli_decryption_restore_only_verified_private_stores(
    routine_service,
    backup_host,
    encryption,
):
    app, _, _, _, _, org, _, owner = routine_service
    _, _, binaries = backup_host
    root, executable, pairs, bundle = encryption
    encrypted = root / "snapshot.age"
    receipt = seal_bundle(bundle, encrypted, [pairs[0][1], pairs[1][1]], executable)
    assert encrypted.stat().st_mode & 0o077 == 0
    assert b"Private coaching data" not in encrypted.read_bytes()
    assert receipt["sha256"] == checksum(encrypted) and receipt["bytes"] == encrypted.stat().st_size
    opened = root / "opened"
    environment = {key: os.environ[key] for key in ("PATH", "HOME") if key in os.environ}
    cli = subprocess.run(
        [
            sys.executable,
            "-m",
            "alpendata_api.backup_encryption",
            "--age-bin",
            str(executable),
            "unseal",
            "--input",
            str(encrypted),
            "--destination",
            str(opened),
            "--identity",
            str(pairs[0][0]),
            "--expected-sha256",
            receipt["sha256"],
        ],
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    )
    assert json.loads(cli.stdout) == {"backup_id": receipt["backup_id"], "status": "decrypted_verified"}
    assert "AGE-SECRET-KEY" not in cli.stdout + cli.stderr
    assert verify_bundle(opened) == verify_bundle(bundle)
    alternative = root / "alternative"
    assert (
        unseal_bundle(encrypted, alternative, pairs[1][0], receipt["sha256"], executable)["backup_id"]
        == receipt["backup_id"]
    )
    assert checksum(alternative / "database.dump") == checksum(bundle / "database.dump")
    target_engine, factory = empty_target(app.state.engine)
    try:
        restored = root / "restored"
        assert (
            restore_bundle(target_engine, factory, opened, restored, binaries)["status"]
            == "restored_suspended"
        )
        assert (restored / org / owner[0] / "private.txt").read_bytes() == b"Private coaching data\n" * 16000
        with factory() as db:
            assert db.get(User, owner[0]).display_name
            assert all(session.revoked for session in db.scalars(select(AuthSession)))
            assert all(
                connection.encrypted_cache is None for connection in db.scalars(select(MicrosoftConnection))
            )
    finally:
        target_engine.dispose()
    with pytest.raises(BackupFailure, match="backup_plaintext_destination_exists"):
        unseal_bundle(encrypted, opened, pairs[0][0], receipt["sha256"], executable)
    assert not list(root.glob(".alpendata-*-*"))


def test_wrong_keys_truncation_and_hostile_envelopes_never_publish_plaintext(encryption):
    root, executable, pairs, bundle = encryption
    encrypted = root / "snapshot.age"
    receipt = seal_bundle(bundle, encrypted, [pairs[0][1]], executable)
    with pytest.raises(BackupFailure, match="backup_encrypted_destination_exists"):
        seal_bundle(bundle, encrypted, [pairs[1][1]], executable)
    assert checksum(encrypted) == receipt["sha256"]
    with pytest.raises(BackupFailure, match="backup_decryption_failed"):
        unseal_bundle(encrypted, root / "wrong-key", pairs[2][0], receipt["sha256"], executable)
    assert not (root / "wrong-key").exists()
    truncated = root / "truncated.age"
    truncated.write_bytes(encrypted.read_bytes()[:-12])
    with pytest.raises(BackupFailure, match="backup_encrypted_integrity_failed"):
        unseal_bundle(truncated, root / "bad-digest", pairs[0][0], receipt["sha256"], executable)
    # Matching a supplied digest does not bypass age's final authentication check.
    with pytest.raises(BackupFailure, match="backup_decryption_failed"):
        unseal_bundle(truncated, root / "truncated", pairs[0][0], checksum(truncated), executable)
    assert not (root / "truncated").exists()
    damaged = root / "damaged.age"
    data = bytearray(encrypted.read_bytes())
    data[len(data) // 2] ^= 1
    damaged.write_bytes(data)
    with pytest.raises(BackupFailure, match="backup_decryption_failed"):
        unseal_bundle(damaged, root / "damaged", pairs[0][0], checksum(damaged), executable)
    assert not (root / "damaged").exists()
    pairs[0][0].chmod(0o644)
    with pytest.raises(BackupFailure, match="backup_identity_permissions_invalid"):
        unseal_bundle(encrypted, root / "exposed-key", pairs[0][0], receipt["sha256"], executable)
    pairs[0][0].chmod(0o600)
    hostile = root / "hostile.tar"
    with tarfile.open(hostile, "w") as archive:
        info = tarfile.TarInfo("../outside")
        info.size = 7
        archive.addfile(info, io.BytesIO(b"outside"))
    with hostile.open("rb") as source, (root / "hostile.age").open("xb") as output:
        subprocess.run(
            [str(executable), "--encrypt", "--recipient", pairs[0][1]],
            stdin=source,
            stdout=output,
            stderr=subprocess.PIPE,
            timeout=10,
            check=True,
        )
    with pytest.raises(BackupFailure, match="backup_envelope_invalid"):
        unseal_bundle(
            root / "hostile.age",
            root / "hostile-output",
            pairs[0][0],
            checksum(root / "hostile.age"),
            executable,
        )
    assert not (root / "outside").exists() and not (root / "hostile-output").exists()
    with (bundle / "states.tar").open("ab") as stream:
        stream.write(b"incomplete source")
    with pytest.raises(BackupFailure, match="backup_integrity_failed"):
        seal_bundle(bundle, root / "incomplete.age", [pairs[0][1]], executable)
    assert not (root / "incomplete.age").exists()
    assert not list(root.glob(".alpendata-*-*"))
