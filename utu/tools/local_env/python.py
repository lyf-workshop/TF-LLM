"""
- [ ] polish _execute_python_code_sync
"""

import asyncio
import base64
import contextlib
import glob
import io
import multiprocessing
import os
import re
import time
import traceback
from typing import TYPE_CHECKING

try:
    import matplotlib
    import matplotlib.pyplot as plt
    from IPython.core.interactiveshell import InteractiveShell
    from traitlets.config.loader import Config

    matplotlib.use("Agg")
except ImportError:
    pass

if TYPE_CHECKING:
    from IPython.core.history import HistoryManager
    from traitlets.config.loader import Config as BaseConfig

    class Config(BaseConfig):
        HistoryManager: HistoryManager


# Used to clean ANSI escape sequences
ANSI_ESCAPE = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]")
try:
    MAX_MEMORY_GB = max(1, min(8, int(os.getenv("UTU_PYTHON_TOOL_MEMORY_GB", "2"))))
except ValueError:
    MAX_MEMORY_GB = 2
CODE_HEADER = f"""
try:
    import resource
    memory_limit_bytes = {MAX_MEMORY_GB * 1024 * 1024 * 1024}
    resource.setrlimit(resource.RLIMIT_AS, (memory_limit_bytes, memory_limit_bytes))
except (ImportError, ValueError, OSError):
    pass
"""


def execute_python_code_sync(code: str, workdir: str):
    """
    Synchronous execution of Python code.
    This function is intended to be run in a separate thread.
    """
    original_dir = os.getcwd()
    try:
        # Clean up code format
        code_clean = code.strip()
        if code_clean.startswith("```python"):
            code_clean = code_clean.split("```python")[1].split("```")[0].strip()
        code_clean = CODE_HEADER + code_clean

        # Create and change to working directory
        os.makedirs(workdir, exist_ok=True)
        os.chdir(workdir)

        # Get file list before execution
        files_before = set(glob.glob("*"))

        # Create a new IPython shell instance
        InteractiveShell.clear_instance()

        config = Config()
        config.HistoryManager.enabled = False
        config.HistoryManager.hist_file = ":memory:"

        shell = InteractiveShell.instance(config=config)

        if hasattr(shell, "history_manager"):
            shell.history_manager.enabled = False

        output = io.StringIO()
        error_output = io.StringIO()

        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(error_output):
            execution_result = shell.run_cell(code_clean)

            execution_error = getattr(execution_result, "error_in_exec", None)
            if execution_error is None:
                execution_error = getattr(execution_result, "error_before_exec", None)
            if execution_error is not None:
                traceback.print_exception(
                    type(execution_error),
                    execution_error,
                    execution_error.__traceback__,
                    file=error_output,
                )

            if plt.get_fignums():
                img_buffer = io.BytesIO()
                plt.savefig(img_buffer, format="png")
                img_base64 = base64.b64encode(img_buffer.getvalue()).decode("utf-8")
                plt.close()

                image_name = "output_image.png"
                counter = 1
                while os.path.exists(image_name):
                    image_name = f"output_image_{counter}.png"
                    counter += 1

                with open(image_name, "wb") as f:
                    f.write(base64.b64decode(img_base64))

        stdout_result = output.getvalue()
        stderr_result = error_output.getvalue()

        stdout_result = ANSI_ESCAPE.sub("", stdout_result)
        stderr_result = ANSI_ESCAPE.sub("", stderr_result)

        files_after = set(glob.glob("*"))
        new_files = list(files_after - files_before)
        new_files = [os.path.join(workdir, f) for f in new_files]

        try:
            shell.atexit_operations = lambda: None
            if hasattr(shell, "history_manager") and shell.history_manager:
                shell.history_manager.enabled = False
                shell.history_manager.end_session = lambda: None
            InteractiveShell.clear_instance()
        except Exception:  # pylint: disable=broad-except
            pass

        success = execution_error is None
        if "Error" in stderr_result or ("Error" in stdout_result and "Traceback" in stdout_result):
            success = False
        message = "Code execution completed, no output"
        if stdout_result.strip():
            message = f"Code execution completed\nOutput:\n{stdout_result.strip()}"

        return {
            "workdir": workdir,
            "success": success,
            "message": message,
            "status": True,
            "files": new_files,
            "error": stderr_result.strip(),
        }
    except Exception as e:  # pylint: disable=broad-except
        return {
            "workdir": workdir,
            "success": False,
            "message": f"Code execution failed, error message:\n{str(e)},\nTraceback:{traceback.format_exc()}",
            "status": False,
            "files": [],
            "error": str(e),
        }
    finally:
        os.chdir(original_dir)


def _execute_python_code_worker(code: str, workdir: str, connection) -> None:
    """Run user code in a child process and return a serializable result."""

    try:
        connection.send(execute_python_code_sync(code, workdir))
    except BaseException as exc:  # pragma: no cover - exercised through process failures
        connection.send(
            {
                "success": False,
                "message": f"Code execution failed: {exc}",
                "status": False,
                "files": [],
                "error": repr(exc),
            }
        )
    finally:
        connection.close()


async def execute_python_code_async(code: str, workdir: str, timeout: int = 30) -> dict:
    """Execute code in an isolated process so timeout can terminate user code.

    Cancelling a coroutine backed by ``run_in_executor`` does not stop the
    worker thread.  A user program that loops or blocks would therefore keep
    consuming memory and executor capacity after its timeout.  A process can
    be terminated and reaped reliably on both Linux and Windows.
    """

    context = multiprocessing.get_context("spawn")
    parent_connection, child_connection = context.Pipe(duplex=False)
    process = context.Process(
        target=_execute_python_code_worker,
        args=(code, str(workdir), child_connection),
        daemon=True,
    )

    started = False
    try:
        process.start()
        started = True
        child_connection.close()
        deadline = time.monotonic() + max(0.0, float(timeout))

        while True:
            if parent_connection.poll():
                result = parent_connection.recv()
                process.join(timeout=1)
                return result
            if not process.is_alive():
                process.join(timeout=1)
                return {
                    "success": False,
                    "message": "Code execution process exited without a result",
                    "status": False,
                    "files": [],
                    "error": f"child process exit code: {process.exitcode}",
                }
            if time.monotonic() >= deadline:
                process.terminate()
                process.join(timeout=1)
                if process.is_alive():
                    process.kill()
                    process.join(timeout=1)
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "",
                    "status": False,
                    "output": "",
                    "files": [],
                    "error": f"Code execution timed out ({timeout} seconds)",
                }
            await asyncio.sleep(0.02)
    except Exception as exc:
        if started and process.is_alive():
            process.terminate()
        if started:
            process.join(timeout=1)
        return {
            "success": False,
            "message": f"Code execution process failed: {exc}",
            "status": False,
            "files": [],
            "error": repr(exc),
        }
    finally:
        child_connection.close()
        parent_connection.close()
        if started and process.is_alive():
            process.terminate()
            process.join(timeout=1)
