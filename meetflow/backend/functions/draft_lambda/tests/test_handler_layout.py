"""Lambdaランタイムと同じsys.pathでhandler.pyがimportできることを確かめる。

実際のLambdaでsys.pathに入るのは関数ルート（/var/task）と共有Layer
（/opt/python）だけで、`handlers/` 自体は入らない。そのため handlers 配下の
モジュールを `import repository` のようにトップレベル参照すると、テストでは
通っても実行時にImportErrorで落ちる（一度これを作り込んだ）。

テスト側のsys.pathが汚れていると意味が無いので、別プロセスで検証する。
"""

import json
import subprocess
import sys
from pathlib import Path

_DRAFT_LAMBDA_DIR = Path(__file__).resolve().parent.parent
_COMMON_LAYER_DIR = _DRAFT_LAMBDA_DIR.parent.parent / "layers" / "common" / "python"

# site-packages（boto3等）はLambdaランタイムが提供するので残す。
# 落とすのは「handlers配下をトップレベル名として見せうるパス」だけ、つまり
# functions/ と layers/ の下にあるエントリ。リポジトリ配下を丸ごと落とすと、
# backend/.venv のsite-packagesまで消えてboto3が見つからなくなる。
_SCRIPT = """
import json, os, sys
_exposes_handlers = lambda p: "/functions/" in p or "/layers/" in p
sys.path = [%r, %r] + [p for p in sys.path if p and not _exposes_handlers(p)]
os.environ["TABLE_NAME"] = "dummy"
os.environ["DRAFT_TABLE_NAME"] = "dummy"
os.environ["AWS_DEFAULT_REGION"] = "ap-northeast-1"
import handler
print(json.dumps(sorted("%%s %%s" %% route for route in handler._ROUTES)))
""" % (str(_DRAFT_LAMBDA_DIR), str(_COMMON_LAYER_DIR))


def test_関数ルートとLayerだけでhandlerをimportできる():
    result = subprocess.run(
        [sys.executable, "-c", _SCRIPT], capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr
    routes = json.loads(result.stdout.strip().splitlines()[-1])
    # 代表的なルートが登録されていること（数だけ見ると足し忘れに気づけない）
    assert "POST /drafts/{draftId}/picks" in routes
    assert "POST /drafts/{draftId}/standings/refresh" in routes
    assert len(routes) == len(set(routes))
