# PyAutoBuild

📖 **Full documentation → <https://pyautoscientist.readthedocs.io>** — the whole PyAutoScientist organism, including how to fork and run your own.

The Hands of the PyAuto organism: the executor that packages, tags, builds
notebooks, and releases the PyAuto libraries (PyAutoConf, PyAutoFit,
PyAutoArray, PyAutoGalaxy, PyAutoLens) and their workspaces to PyPI. It
runs no readiness checks and makes no gate decisions — those belong to
[PyAutoHeart](https://github.com/PyAutoLabs/PyAutoHeart), whose verdict the
[PyAutoBrain](https://github.com/PyAutoLabs/PyAutoBrain) release agent
reads before dispatching a release here.

Every operation is reachable through one dispatcher:

```bash
bash bin/autobuild help                # list every subcommand
bash bin/autobuild help <subcommand>   # full docstring for one
bash bin/autobuild pre_build [minor]   # format, generate notebooks, bump, push
bash bin/autobuild run_all             # run the workspace validation scripts
```

The release pipeline (`.github/workflows/release.yml`) packages to
TestPyPI, verifies the install, runs the workspace scripts, and on success
releases to PyPI and tags the workspaces — nightly, when there is new
activity to ship.

Boundary and agent guidance: [AGENTS.md](AGENTS.md). The organism:
[PyAutoBrain/ORGANISM.md](https://github.com/PyAutoLabs/PyAutoBrain/blob/main/ORGANISM.md),
documented in full at <https://pyautoscientist.readthedocs.io>.
