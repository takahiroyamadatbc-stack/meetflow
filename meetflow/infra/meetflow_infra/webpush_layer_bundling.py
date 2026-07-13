import subprocess
import sys
import tempfile
from pathlib import Path

import jsii
from aws_cdk import ILocalBundling

# NotificationLambdaのWeb Push送信(Lambda設計書v1.2 §9.3b)には
# `pywebpush`が必要で、これは`cryptography`というネイティブ(Rust/C)拡張を
# 引き込む -- これはmeetflow_commonと同じようにソースファイルをコピー
# するだけ(meetflow_compute_stack.pyの`Code.from_asset`で`bundling`無し)
# ではバンドルできない。標準的なCDKの解法はDockerバンドルassetだが、
# この開発環境にはDockerが無い。代わりに: `cryptography`(および
# pywebpushが引き込む他の全てのネイティブ依存)はPyPIにmanylinuxホイールを
# 公開しているため、`pip install --platform manylinux2014_x86_64
# --only-binary=:all:`で、ローカルで何もコンパイルせずにコンパイル済みの
# Linuxバイナリを取得できる -- このWindows開発マシンから動作することを
# 確認済み。唯一の例外は`http-ece`(pywebpushのペイロード暗号化用の依存)で、
# ソースディストリビューションしか公開していない。これは純粋なPythonなので
# ホストOSに関わらずローカルビルドしても安全であり、1回だけホイール
# ビルドして`--find-links`経由で戻すことで、pywebpushの依存ツリーの
# 残りが単一のpip呼び出し内で自動的に解決されるようにしている。
_MANYLINUX_PLATFORM = "manylinux2014_x86_64"
_PYTHON_VERSION = "3.13"  # meetflow_compute_stack.pyのlambda_.Runtime.PYTHON_3_13と一致させる


@jsii.implements(ILocalBundling)
class WebpushLayerLocalBundling:
    """webpush Lambda Layer asset用の`local`バンドリングフック
    (meetflow_compute_stack.pyの`_build_notification_lambda`のILocalBundling
    を参照)。CDKは`cdk synth`/`cdk deploy`中に`try_bundle`を呼び出し、
    Trueを返すとDockerベースの`image`/`command`フォールバックを完全に
    スキップする。
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
