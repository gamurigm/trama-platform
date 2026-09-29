import os
import subprocess
import sys

import pytest

from trama_platform.lifecycle import _is_running


@pytest.mark.skipif(os.name != "nt", reason="Windows process probing regression")
def test_windows_liveness_probe_does_not_terminate_the_process():
    process = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(20)"])
    try:
        assert _is_running(process.pid)
        with pytest.raises(subprocess.TimeoutExpired):
            process.wait(timeout=0.3)
    finally:
        process.terminate()
        process.wait(timeout=5)
