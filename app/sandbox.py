"""Run the agent's analysis code in an isolated Docker container.

The container gets: no network, capped memory/CPU/processes, a read-only mount,
and a non-root user. It receives the dataset, runs the code (which must set
`result`), and prints a JSON result. Nothing else leaves the box."""
import json
import subprocess
import tempfile
from pathlib import Path

from . import config

_HARNESS = '''import json, pandas as pd
_d = json.load(open("/work/dataset.json"))
df = pd.DataFrame(_d["rows"], columns=_d["columns"])
try:
{code}
    print(json.dumps({{"ok": True, "result": result}}, default=str))
except Exception as e:
    print(json.dumps({{"ok": False, "error": "{{}}: {{}}".format(type(e).__name__, e)}}))
'''


def build_image() -> str:
    """Build the sandbox image (idempotent). Returns docker's output."""
    root = Path(__file__).resolve().parent.parent
    r = subprocess.run(
        ["docker", "build", "-t", config.SANDBOX_IMAGE, "-f", "Dockerfile.sandbox", "."],
        cwd=root, capture_output=True, text=True,
    )
    return (r.stdout + r.stderr).strip()


def run(code: str, dataset: dict, timeout: int = 35) -> dict:
    """dataset = {"columns": [...], "rows": [...]}. Returns {ok, result|error}."""
    indented = "\n".join("    " + ln for ln in code.strip().splitlines()) or "    result = {}"
    with tempfile.TemporaryDirectory() as td:
        p = Path(td)
        (p / "dataset.json").write_text(json.dumps({"columns": dataset["columns"], "rows": dataset["rows"]}))
        (p / "main.py").write_text(_HARNESS.format(code=indented))
        cmd = [
            "docker", "run", "--rm", "--network", "none",
            "--memory", "512m", "--cpus", "1", "--pids-limit", "128",
            "-v", f"{td}:/work:ro", config.SANDBOX_IMAGE,
            "python", "/work/main.py",
        ]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            return {"ok": False, "error": "sandbox timed out"}
        except FileNotFoundError:
            return {"ok": False, "error": "docker not available"}
        out = (r.stdout or "").strip().splitlines()
        for line in reversed(out):
            try:
                return json.loads(line)
            except Exception:
                continue
        return {"ok": False, "error": (r.stderr or "no output from sandbox").strip()[:300]}
