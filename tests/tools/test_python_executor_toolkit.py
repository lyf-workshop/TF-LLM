import time

import pytest

from utu.config import ConfigLoader
from utu.tools import PythonExecutorToolkit

toolkit = PythonExecutorToolkit(ConfigLoader.load_toolkit_config("python_executor"))


async def test_python_executor_toolkit():
    test_code = """
import numpy as np
a = 1
a
"""
    result = await toolkit.execute_python_code(code=test_code)
    print(result)
    assert result["success"]
    assert "1" in result["message"]

    test_code_with_plot = """
import matplotlib.pyplot as plt
import numpy as np

x = np.linspace(0, 10, 100)
y = np.sin(x)

plt.figure(figsize=(8, 6))
plt.plot(x, y, 'b-', label='sin(x)')
plt.title('Sine Function')
plt.grid(True)

print("Image generated")
"""
    result_plot = await toolkit.execute_python_code(code=test_code_with_plot)
    print(result_plot)
    assert result_plot["success"]
    assert "Image generated" in result_plot["message"]
    assert len(result_plot["files"]) == 1
    assert "output_image.png" in result_plot["files"][0]


@pytest.mark.asyncio
async def test_python_executor_timeout_terminates_user_code(tmp_path):
    isolated_toolkit = PythonExecutorToolkit(
        {
            "workspace_root": str(tmp_path),
        }
    )

    started_at = time.monotonic()
    result = await isolated_toolkit.execute_python_code(
        code="while True:\n    pass",
        timeout=1,
    )

    assert result["success"] is False
    assert "timed out" in result["error"]
    assert time.monotonic() - started_at < 5
