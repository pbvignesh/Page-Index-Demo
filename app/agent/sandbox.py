"""Run the agent's analysis code in an isolated Docker container.

The container gets: no network, capped memory/CPU/processes, a read-only mount,
and a non-root user. It receives the dataset, runs the code (which must set
`result`), and prints a JSON result. Nothing else leaves the box."""
import json
import subprocess
import tempfile
from pathlib import Path

from .. import config

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
    repo_root = Path(__file__).resolve().parents[2]
    completed = subprocess.run(
        ["docker", "build", "-t", config.SANDBOX_IMAGE, "-f", "Dockerfile.sandbox", "."],
        cwd=repo_root, capture_output=True, text=True,
    )
    return (completed.stdout + completed.stderr).strip()


def run(code: str, dataset: dict, timeout: int = 35) -> dict:
    """dataset = {"columns": [...], "rows": [...]}. Returns {ok, result|error}."""
    indented_code = "\n".join("    " + line for line in code.strip().splitlines()) or "    result = {}"

    with tempfile.TemporaryDirectory() as work_dir:
        work_path = Path(work_dir)
        (work_path / "dataset.json").write_text(
            json.dumps({"columns": dataset["columns"], "rows": dataset["rows"]})
        )
        (work_path / "main.py").write_text(_HARNESS.format(code=indented_code))

        command = [
            "docker", "run", "--rm", "--network", "none",
            "--memory", "512m", "--cpus", "1", "--pids-limit", "128",
            "-v", f"{work_dir}:/work:ro", config.SANDBOX_IMAGE,
            "python", "/work/main.py",
        ]
        try:
            completed = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            return {"ok": False, "error": "sandbox timed out"}
        except FileNotFoundError:
            return {"ok": False, "error": "docker not available"}

        # the result is the last JSON line the harness printed
        for line in reversed((completed.stdout or "").strip().splitlines()):
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                continue
        return {"ok": False, "error": (completed.stderr or "no output from sandbox").strip()[:300]}
