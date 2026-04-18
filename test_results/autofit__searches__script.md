# Test Report: autofit / searches (script)

**11 scripts** | 6 passed | 5 skipped

| Status | Count |
|--------|-------|
| passed | 6 |
| skipped | 5 |

## Skipped

| Script | Reason |
|--------|--------|
| `Zeus.py` | Test Model Iniitalization no good. |
| `PySwarmsGlobal.py` | PySwarms does not support JAX. |
| `PySwarmsLocal.py` | PySwarms does not support JAX. |
| `UltraNest.py` | UltraNest does not support JAX. |
| `start_point.py` | bug https://github.com/rhayes777/PyAutoFit/issues/1017 |

## Passed

- `/home/jammy/Code/PyAutoLabs/autofit_workspace/scripts/searches/mcmc/Emcee.py` (2.3s)
- `/home/jammy/Code/PyAutoLabs/autofit_workspace/scripts/searches/mle/Drawer.py` (1.4s)
- `/home/jammy/Code/PyAutoLabs/autofit_workspace/scripts/searches/mle/LBFGS.py` (1.6s)
- `/home/jammy/Code/PyAutoLabs/autofit_workspace/scripts/searches/nest/DynestyDynamic.py` (1.6s)
- `/home/jammy/Code/PyAutoLabs/autofit_workspace/scripts/searches/nest/DynestyStatic.py` (1.6s)
- `/home/jammy/Code/PyAutoLabs/autofit_workspace/scripts/searches/nest/Nautilus.py` (1.8s)
