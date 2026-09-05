"""Offline diagnostic of upstream profile boundaries, using synthetic data only.

This is an architecture probe, not the Hermes regression suite or a sandbox test.
Run from any directory: python -I -B alpendata/audit/probe_profiles.py
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

REPO = Path(__file__).resolve().parents[2]


def load_module(name: str, relative: str):
    spec = importlib.util.spec_from_file_location(name, REPO / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def inspect_child(own: Path, peer: Path) -> dict:
    os.environ["HERMES_HOME"] = str(own)
    constants = load_module("audit_constants", "hermes_constants.py")
    secrets = load_module("audit_secret_scope", "agent/secret_scope.py")
    resolved = constants.get_hermes_home()
    secrets.set_multiplex_active(True)
    try:
        secrets.get_secret("ALPENDATA_AUDIT_SECRET")
        unscoped_denied = False
    except secrets.UnscopedSecretError:
        unscoped_denied = True

    async def interleaved_scopes():
        ready = asyncio.Event()
        entered = 0

        async def scoped(directory: Path):
            nonlocal entered
            home_token = constants.set_hermes_home_override(directory)
            secret_token = secrets.set_secret_scope({"ALPENDATA_AUDIT_SECRET": directory.name})
            try:
                entered += 1
                if entered == 2:
                    ready.set()
                await ready.wait()
                return {
                    "home_matches": constants.get_hermes_home() == directory,
                    "secret_matches": secrets.get_secret("ALPENDATA_AUDIT_SECRET") == directory.name,
                }
            finally:
                secrets.reset_secret_scope(secret_token)
                constants.reset_hermes_home_override(home_token)

        return await asyncio.gather(scoped(own), scoped(peer))

    scope_results = asyncio.run(interleaved_scopes())
    try:
        peer_readable = (peer / "memories" / "MEMORY.md").read_text(encoding="utf-8") == peer.name
    except PermissionError:
        peer_readable = False
    return {
        "profile": own.name,
        "home_matches": resolved == own,
        "own_memory_matches": (resolved / "memories" / "MEMORY.md").read_text(encoding="utf-8") == own.name,
        "unscoped_secret_denied": unscoped_denied,
        "interleaved_scopes": scope_results,
        "home_restored": constants.get_hermes_home() == own,
        "peer_synthetic_memory_readable_under_same_os_account": peer_readable,
    }


def main():
    if len(sys.argv) == 4 and sys.argv[1] == "--child":
        print(json.dumps(inspect_child(Path(sys.argv[2]), Path(sys.argv[3]))))
        return
    if len(sys.argv) != 1:
        raise SystemExit("Run without arguments.")
    with tempfile.TemporaryDirectory(prefix="alpendata-profile-audit-") as temporary:
        root = Path(temporary).resolve()
        homes = [root / "user-a", root / "user-b"]
        for home in homes:
            (home / "memories").mkdir(parents=True)
            (home / "memories" / "MEMORY.md").write_text(home.name, encoding="utf-8")
        observations = []
        for own, peer in (homes, list(reversed(homes))):
            completed = subprocess.run(
                [sys.executable, "-I", "-B", str(Path(__file__).resolve()), "--child", str(own), str(peer)],
                capture_output=True, text=True, check=True, timeout=30,
            )
            observations.append(json.loads(completed.stdout))
    revision = subprocess.run(
        ["git", "-C", str(REPO), "rev-parse", "HEAD"],
        capture_output=True, text=True, check=True, timeout=10,
    ).stdout.strip()
    print(json.dumps({
        "revision": revision,
        "python": sys.version.split()[0],
        "platform": sys.platform,
        "synthetic_data_only": True,
        "observations": observations,
        "limit": "No HTTP server, Graph call, LLM call or container isolation was exercised.",
    }, indent=2))


if __name__ == "__main__":
    main()
