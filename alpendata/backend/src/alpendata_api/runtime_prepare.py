"""Initialize a pinned image under the service UID before admitting executions."""

import argparse
import json
import subprocess
from pathlib import Path
from uuid import uuid4

from .runtime import ContainerRuntime, RuntimeSettings, engine_environment


def prepare(image):
    runtime = ContainerRuntime(RuntimeSettings(Path("/var/empty"), image))
    name = "alpendata-image-check-" + uuid4().hex
    command = runtime.command(name, Path("/var/empty"))
    # No state mount, service credentials, network, or provider call is needed.
    volume = command.index("--volume")
    del command[volume : volume + 2]
    command[-1:-1] = ["--entrypoint=/bin/true"]
    environment = engine_environment()
    try:
        result = subprocess.run(
            command,
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=600,
        )
        if result.returncode:
            raise ValueError("runtime_image_not_ready")
    finally:
        subprocess.run(
            [runtime.settings.executable, "--cgroup-manager=cgroupfs", "rm", "--force", name],
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=30,
            check=False,
        )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True)
    args = parser.parse_args()
    try:
        prepare(args.image)
    except (ValueError, OSError, subprocess.SubprocessError):
        print(json.dumps({"status": "not_ready"}))
        return 1
    print(json.dumps({"status": "ready", "image": args.image}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
