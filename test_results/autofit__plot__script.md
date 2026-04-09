# Test Report: autofit / plot (script)

**5 scripts** | 1 failed | 1 passed | 3 skipped

| Status | Count |
|--------|-------|
| failed | 1 |
| passed | 1 |
| skipped | 3 |

## Failures

### `/home/jammy/Code/PyAutoLabs/autofit_workspace/scripts/plot/EmceePlotter.py` — FAILED (2.3s)

Command '['/home/jammy/venv/PyAuto/bin/python3', '/home/jammy/Code/PyAutoLabs/autofit_workspace/scripts/plot/EmceePlotter.py']' returned non-zero exit status 1.

```
Traceback (most recent call last):
  File "/home/jammy/Code/PyAutoLabs/autofit_workspace/scripts/plot/EmceePlotter.py", line 156, in <module>
    for walker_index in range(search_internal.get_log_prob().shape[1]):
                              ^^^^^^^^^^^^^^^^^^^^^^^^^^^^
AttributeError: 'NoneType' object has no attribute 'get_log_prob'
```

## Skipped

| Script | Reason |
|--------|--------|
| `DynestyPlotter.py` | Test Model Iniitalization no good. |
| `GetDist.py` | Cant get it to install, even in optional requirements. |
| `ZeusPlotter.py` | Test Model Iniitalization no good. |

## Passed

- `/home/jammy/Code/PyAutoLabs/autofit_workspace/scripts/plot/NautilusPlotter.py` (1.8s)
