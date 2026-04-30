PyAutoBuild: PyAuto Build Server
================================

This project performs automatic building, testing and deployment of projects in the PyAuto software family:

- `PyAutoConf <https://github.com/PyAutoLabs/PyAutoConf>`_
- `PyAutoFit <https://github.com/PyAutoLabs/PyAutoFit>`_
- `PyAutoArray <https://github.com/PyAutoLabs/PyAutoArray>`_
- `PyAutoGalaxy <https://github.com/PyAutoLabs/PyAutoGalay>`_
- `PyAutoLens <https://github.com/PyAutoLabs/PyAutoLens>`_
- `PyAutoCTI <https://github.com/PyAutoLabs/PyAutoCTI>`_

It uses their associated workspaces:

- `autofit_workspace <https://github.com/PyAutoLabs/autofit_workspace>`_
- `autogalaxy_workspace <https://github.com/PyAutoLabs/autogalaxy_workspace>`_
- `autolens_workspace <https://github.com/PyAutoLabs/autolens_workspace>`_

And their test workspaces:

- `autofit_workspace_test <https://github.com/PyAutoLabs/autofit_workspace_test>`_
- `autogalaxy_workspace_test <https://github.com/PyAutoLabs/autogalaxy_workspace_test>`_
- `autolens_workspace_test <https://github.com/PyAutoLabs/autolens_workspace_test>`_

The build pipeline includes the following tasks:

- Package and release all projects to the test_pypi server.
- Install all test packages via pip.
- Run all project unit tests.
- Run all workspace integration test scripts.
- If successful, release packages to pypi.
- Update workspaces with new test scripts.

This automatically runs every 24 hours.

CLI Usage
---------

Every operation is invokable from the shell via the ``autobuild`` dispatcher::

    bash bin/autobuild help                    # list every subcommand
    bash bin/autobuild help <subcommand>       # full docstring for one
    bash bin/autobuild pre_build [minor]       # full pre-build flow
    bash bin/autobuild verify_install          # release-readiness gate

Recommended alias for ``~/.bashrc``::

    alias autobuild-help='$HOME/Code/PyAutoLabs/PyAutoBuild/bin/autobuild help'

The dispatcher wraps both bash scripts and Python tools, so any operation in
this repo is reachable from a single entry point with consistent ``--help``
documentation.