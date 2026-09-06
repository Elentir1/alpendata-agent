"""Generate user-systemd units for the AlpenData control plane on a dedicated Linux account."""

import argparse
import re
from pathlib import Path, PurePosixPath


def unit_path(path):
    if (
        not PurePosixPath(path).is_absolute()
        or path != path.strip()
        or ".." in PurePosixPath(path).parts
        or not re.fullmatch(r"[A-Za-z0-9_/. +\-]+", path)
    ):
        raise ValueError("Use an absolute ASCII Linux path without unit expressions")
    return path


def units(*, python, backend, environment, api_port=8080, with_billing=False):
    executable, directory, credentials = map(unit_path, (python, backend, environment))
    if not 1 <= api_port <= 65535:
        raise ValueError("Invalid API port")
    commands = {
        "api": (
            "-m uvicorn alpendata_api.app:from_environment --factory --host 127.0.0.1 "
            f"--port {api_port} --proxy-headers --forwarded-allow-ips 127.0.0.1 --no-access-log"
        ),
        "chat": "-m alpendata_api.chat_worker",
        "scheduler": "-m alpendata_api.schedule_worker",
    }
    if with_billing:
        commands["billing"] = "-m alpendata_api.billing_worker"
    return {
        f"alpendata-{name}.service": f"""[Unit]
Description=AlpenData {name}
StartLimitIntervalSec=60
StartLimitBurst=3

[Service]
Type=exec
WorkingDirectory={directory}
EnvironmentFile={credentials}
ExecStart="{executable}" {command}
Restart=on-failure
RestartSec=5
KillMode=mixed
TimeoutStopSec=1020
UMask=0077
LimitCORE=0
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=default.target
"""
        for name, command in commands.items()
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("python", "backend", "environment", "output"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--api-port", type=int, default=8080)
    parser.add_argument(
        "--with-billing", action="store_true", help="Include the Stripe reconciliation worker"
    )
    arguments = vars(parser.parse_args())
    destination = Path(arguments.pop("output"))
    contents = units(**arguments)
    destination.mkdir(mode=0o700)
    for name, content in contents.items():
        with (destination / name).open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(content)


if __name__ == "__main__":
    main()
