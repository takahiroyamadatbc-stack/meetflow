import subprocess
import sys
import tempfile
from pathlib import Path

import jsii
from aws_cdk import ILocalBundling

# NotificationLambda's Web Push send (Lambda設計書v1.2 §9.3b) needs
# `pywebpush`, which pulls in `cryptography` -- a native (Rust/C) extension
# that can't be bundled by copying source files the way meetflow_common is
# (meetflow_compute_stack.py's `Code.from_asset` with no `bundling`). The
# standard CDK answer is a Docker-bundled asset, but this dev environment
# has no Docker. Instead: `cryptography` (and every other native dependency
# pywebpush pulls in) publishes manylinux wheels on PyPI, so `pip install
# --platform manylinux2014_x86_64 --only-binary=:all:` fetches
# already-compiled Linux binaries without compiling anything locally --
# verified to work from this Windows dev machine. The one exception is
# `http-ece` (pywebpush's payload-encryption dependency), which only
# publishes a source distribution; since it's pure Python, building it
# locally is safe regardless of host OS, so it's wheel-built once and fed
# back in via `--find-links` so the rest of pywebpush's dependency tree
# still resolves automatically in a single pip invocation.
_MANYLINUX_PLATFORM = "manylinux2014_x86_64"
_PYTHON_VERSION = "3.12"  # matches lambda_.Runtime.PYTHON_3_12 in meetflow_compute_stack.py


@jsii.implements(ILocalBundling)
class WebpushLayerLocalBundling:
    """`local` bundling hook for the webpush Lambda Layer asset (see
    ILocalBundling in meetflow_compute_stack.py's `_build_notification_lambda`).
    CDK calls `try_bundle` during `cdk synth`/`cdk deploy`; returning True
    skips the Docker-based `image`/`command` fallback entirely.
    """

    def __init__(self, requirements_path: Path):
        self._requirements_path = requirements_path

    def try_bundle(self, output_dir: str, options) -> bool:
        python_dir = Path(output_dir) / "python"
        python_dir.mkdir(parents=True, exist_ok=True)

        with tempfile.TemporaryDirectory() as tmp_wheel_dir:
            wheel_result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pip",
                    "wheel",
                    "--no-deps",
                    "--wheel-dir",
                    tmp_wheel_dir,
                    "http-ece",
                ],
                capture_output=True,
                text=True,
            )
            if wheel_result.returncode != 0:
                print(wheel_result.stdout)
                print(wheel_result.stderr)
                return False

            install_result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pip",
                    "install",
                    "--platform",
                    _MANYLINUX_PLATFORM,
                    "--python-version",
                    _PYTHON_VERSION,
                    "--implementation",
                    "cp",
                    "--only-binary=:all:",
                    "--find-links",
                    tmp_wheel_dir,
                    "--target",
                    str(python_dir),
                    "-r",
                    str(self._requirements_path),
                ],
                capture_output=True,
                text=True,
            )
            if install_result.returncode != 0:
                print(install_result.stdout)
                print(install_result.stderr)
                return False

        return True
