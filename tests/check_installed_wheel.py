import os
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEMP_ROOT = Path("/var/folders/2c/23by97c10_382f_zbcl83v100000gn/T/opencode")


def main() -> None:
    with tempfile.TemporaryDirectory(dir=TEMP_ROOT) as temporary_directory:
        temporary = Path(temporary_directory)
        wheelhouse = temporary / "wheelhouse"
        target = temporary / "target"
        outside = temporary / "outside"
        wheelhouse.mkdir()
        target.mkdir()
        outside.mkdir()

        subprocess.run(
            ["uv", "build", "--wheel", "--out-dir", str(wheelhouse)],
            cwd=ROOT,
            check=True,
        )
        wheel = next(wheelhouse.glob("*.whl"))
        subprocess.run(
            ["uv", "pip", "install", "--target", str(target), "--no-deps", str(wheel)],
            cwd=ROOT,
            check=True,
        )

        environment = os.environ.copy()
        environment["PYTHONPATH"] = str(target)
        subprocess.run(
            [
                sys.executable,
                "-c",
                """
import os
from pathlib import Path

from fastapi.testclient import TestClient
import voice_interviewer
from voice_interviewer.api import app

assert Path(voice_interviewer.__file__).is_relative_to(Path(os.environ["PYTHONPATH"]))
client = TestClient(app)
assert client.get('/').status_code == 200
assert client.get('/app.js').status_code == 200
assert client.get('/styles.css').status_code == 200
""",
            ],
            cwd=outside,
            env=environment,
            check=True,
        )


if __name__ == "__main__":
    main()
