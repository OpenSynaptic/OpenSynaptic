# Test Suite

- `tests/unit/test_core_algorithms.py`: Base62/CRC/packet encode-decode checks.
- `tests/integration/test_pipeline_e2e.py`: end-to-end flow from virtual sensors to packet decode.

Run locally:

```powershell
py -3 -m pip install -e .[dev]
py -3 -m pytest --cov=opensynaptic tests
```

Windows PowerShell (execution policy-safe, no activation required):

```powershell
.\scripts\venv-python.cmd -m pip install -e .[dev]
.\scripts\venv-python.cmd -m pytest --cov=opensynaptic tests
```

