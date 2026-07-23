<p align="center">
  <img src="logo.png" alt="PyAutoHands" width="400">
</p>

# PyAutoHands

> **Formerly PyAutoBuild.** The repository is being renamed PyAutoBuild →
> PyAutoHands; see [MIGRATION.md](MIGRATION.md). The `autohands` command and
> Python package keep their names for now — only the repository and its
> branding change.

🧬 **PyAutoScientist → <https://github.com/PyAutoLabs/PyAutoScientist>** — this repo is one organ of the PyAuto organism.

📖 **Full documentation → <https://pyautoscientist.readthedocs.io>** — the whole PyAutoScientist organism, including how to fork and run your own.

PyAutoHands is the **Hands** of the PyAuto organism: the executor that packages,
tags, builds notebooks, and releases the PyAuto libraries (PyAutoNerves, PyAutoFit,
PyAutoArray, PyAutoGalaxy, PyAutoLens) and their workspaces to PyPI. **PyAutoHands
executes work on behalf of PyAutoBrain** — the Brain decides, the Hands do. It
runs no readiness checks and makes no gate decisions — those belong to
[PyAutoHeart](https://github.com/PyAutoLabs/PyAutoHeart), whose verdict the
[PyAutoBrain](https://github.com/PyAutoLabs/PyAutoBrain) release agent
reads before dispatching a release here.

Every operation is reachable through one dispatcher:

```bash
bash bin/autohands help                # list every subcommand
bash bin/autohands help <subcommand>   # full docstring for one
bash bin/autohands pre_build [minor]   # format, generate notebooks, bump, push
bash bin/autohands run_all             # run the workspace validation scripts
```

The release pipeline (`.github/workflows/release.yml`) packages to
TestPyPI, verifies the install, runs the workspace scripts, and on success
releases to PyPI and tags the workspaces — nightly, when there is new
activity to ship.

Boundary and agent guidance: [AGENTS.md](AGENTS.md). The organism:
[PyAutoBrain/ORGANISM.md](https://github.com/PyAutoLabs/PyAutoBrain/blob/main/ORGANISM.md),
documented in full at <https://pyautoscientist.readthedocs.io>.
