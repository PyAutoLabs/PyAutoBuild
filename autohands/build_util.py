import datetime
import logging
import os
import re
import subprocess
import sys
import time
import traceback
from pathlib import Path
from typing import List

TIMEOUT_SECS = int(os.environ.get("BUILD_SCRIPT_TIMEOUT", "300"))
BUILD_PATH = Path(__file__).parent

BUILD_PYTHON_INTERPRETER = os.environ.get("BUILD_PYTHON_INTERPRETER", "python3")


def py_to_notebook(filename: Path):
    subprocess.run(
        ["python3", f"{BUILD_PATH}/add_notebook_quotes.py", filename, "temp.py"],
        check=True,
    )
    new_filename = filename.with_suffix(".ipynb")
    subprocess.run(
        ["ipynb-py-convert", "temp.py", new_filename],
        check=True,
    )
    os.remove("temp.py")
    uncomment_jupyter_magic(new_filename)
    return new_filename


# Projects whose generated notebooks receive the Colab setup cell, mapped to
# the public package through which local users access ``setup_colab``. The keys
# must stay in sync with the `_PROJECTS` registry in PyAutoNerves's
# `autonerves/setup_colab.py`.
COLAB_PROJECTS = {
    "autofit": "autofit",
    "autogalaxy": "autogalaxy",
    "autolens": "autolens",
    "howtofit": "autofit",
    "howtogalaxy": "autogalaxy",
    "howtolens": "autolens",
}

COLAB_SETUP_MARKDOWN = """__Google Colab Setup__

This cell sets up the environment when the notebook is run on Google Colab: it installs the
required PyAuto packages, clones the workspace (configuration files and example datasets) and
points the configuration at it. If you are running the notebook elsewhere (e.g. locally via
your own installation) it does nothing, and you can run it safely.

Colab tip: model-fits run much faster on a GPU — enable one via "Runtime" -> "Change runtime
type" -> "Hardware accelerator" before running the notebook."""

COLAB_SETUP_CODE = '''try:
    import google.colab
except ImportError:
    from {package} import setup_colab as _setup_colab
else:
    import importlib
    import subprocess
    import sys

    subprocess.check_call(
        [sys.executable, "-m", "pip", "install", "autonerves", "--no-deps"]
    )
    _setup_colab = importlib.import_module("autonerves.setup_colab")

_setup_colab.setup("{project}")'''


def inject_colab_setup(notebook_path, project: str):
    """
    Prepend the standard Google Colab setup cell pair (markdown explainer +
    code cell) to a generated notebook, so every published notebook can
    bootstrap itself on Colab.

    The cells are inserted after the notebook's leading markdown cell (the
    script's intro docstring) so the title stays on top. Notebooks whose
    source already calls ``setup_colab`` (hand-written setup sections) are
    left untouched. Returns True if cells were injected.
    """
    import json

    if project not in COLAB_PROJECTS:
        raise ValueError(
            f"inject_colab_setup: unknown project '{project}' — add it to "
            f"COLAB_PROJECTS here and to the _PROJECTS registry in "
            f"PyAutoNerves's autonerves/setup_colab.py. Known: {sorted(COLAB_PROJECTS)}"
        )

    with open(notebook_path, "r") as f:
        notebook = json.load(f)

    cells = notebook["cells"]

    for cell in cells:
        if "setup_colab" in "".join(cell.get("source", [])):
            return False

    markdown_cell = {
        "cell_type": "markdown",
        "metadata": {},
        "source": COLAB_SETUP_MARKDOWN.splitlines(keepends=True),
    }
    code_cell = {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": COLAB_SETUP_CODE.format(
            project=project, package=COLAB_PROJECTS[project]
        ).splitlines(keepends=True),
    }

    insert_at = 1 if cells and cells[0]["cell_type"] == "markdown" else 0
    cells[insert_at:insert_at] = [markdown_cell, code_cell]

    with open(notebook_path, "w") as f:
        json.dump(notebook, f, indent=1)

    return True


def uncomment_jupyter_magic(f):
    with open(f, "r") as sources:
        lines = sources.readlines()
    with open(f, "w") as sources:
        for line in lines:
            line = re.sub(
                r"# from autonerves import setup_notebook; setup_notebook\(\)",
                "from autonerves import setup_notebook; setup_notebook()",
                line,
            )
            sources.write(line)


def no_run_list_with_extension_from(no_run_list: List[str], extension: str):
    for i, no_run in enumerate(no_run_list):
        if not no_run.endswith(extension):
            no_run_list[i] = f"{no_run}{extension}"

    return no_run_list


def should_skip(file: Path, no_run_list: List[str]) -> bool:
    """
    Return True if the file matches any entry in no_run_list.

    Entries with a '/' are treated as path-specific patterns and are
    substring-matched against the file's full path **including extension** —
    so a pattern may include ``.py`` to anchor against the script form (e.g.
    ``imaging/visualization.py`` matches ``scripts/imaging/visualization.py``
    but not ``scripts/imaging/visualization_jax.py``).
    Entries without a '/' match any file whose stem equals the entry.
    """
    file_str = str(file)
    for pattern in no_run_list:
        if "/" in pattern:
            if pattern in file_str:
                return True
        else:
            if file.stem == pattern:
                return True
    return False


def _find_skip_reason(file: Path, no_run_list: List[str], skip_reasons: dict) -> str:
    """Find the reason a file is being skipped from the skip_reasons dict."""
    file_str = str(file)
    for pattern in no_run_list:
        if "/" in pattern:
            if pattern in file_str:
                return skip_reasons.get(pattern, "No reason documented")
        else:
            if file.stem == pattern:
                return skip_reasons.get(pattern, "No reason documented")
    return "No reason documented"


def execute_notebook(f, report=None, env=None):
    print(f"Running <{f}> at {datetime.datetime.now().isoformat()}")

    start = time.time()
    try:
        if report is not None:
            result = subprocess.run(
                ["jupyter", "nbconvert", "--to", "notebook", "--execute", "--output", f, f],
                check=True,
                timeout=TIMEOUT_SECS,
                capture_output=True,
                text=True,
                env=env,
            )
        else:
            subprocess.run(
                ["jupyter", "nbconvert", "--to", "notebook", "--execute", "--output", f, f],
                check=True,
                timeout=TIMEOUT_SECS,
                env=env,
            )
    except subprocess.TimeoutExpired as e:
        duration = time.time() - start
        if report is not None:
            from result_collector import ScriptResult, Status
            print(f"  TIMEOUT ({duration:.0f}s)")
            report.results.append(ScriptResult(
                file=str(f),
                status=Status.TIMEOUT,
                duration_seconds=duration,
                error_message="Timed out after {:.0f}s".format(duration),
            ))
            return
        logging.exception(e)
        sys.exit(1)
    except subprocess.CalledProcessError as e:
        duration = time.time() - start

        if "InversionException" in traceback.format_exc():
            if report is not None:
                from result_collector import ScriptResult, Status
                print(f"  PASS (InversionException, {duration:.1f}s)")
                report.results.append(ScriptResult(
                    file=str(f),
                    status=Status.PASSED,
                    duration_seconds=duration,
                    error_message="InversionException (ignored)",
                ))
            return

        if report is not None:
            from result_collector import ScriptResult, Status
            stderr = getattr(e, 'stderr', '') or ''
            last_line = stderr.strip().splitlines()[-1] if stderr.strip() else str(e)
            print(f"  FAIL ({duration:.1f}s) {last_line}")
            report.results.append(ScriptResult(
                file=str(f),
                status=Status.FAILED,
                duration_seconds=duration,
                error_message=str(e),
                traceback=stderr,
            ))
            return
        logging.exception(e)
        sys.exit(1)

    duration = time.time() - start
    if report is not None:
        from result_collector import ScriptResult, Status
        print(f"  PASS ({duration:.1f}s)")
        report.results.append(ScriptResult(
            file=str(f),
            status=Status.PASSED,
            duration_seconds=duration,
        ))


def execute_notebooks_in_folder(
    directory,
    no_run_list,
    visualise_dict=None,
    report=None,
    skip_reasons=None,
    env_config=None,
):
    # Infrastructure files — always skip, never report
    infra_skip = ["__init__", "README"]
    no_run_list.extend(infra_skip)
    files = list((Path.cwd() / directory).rglob("*.ipynb"))

    print(f"Found {len(files)} notebooks")

    for file in sorted(files):
        if file.stem in infra_skip:
            continue
        if visualise_dict is not None:
            without_suffix = str(file.with_suffix(""))
            if not any(
                map(
                    without_suffix.endswith,
                    visualise_dict,
                )
            ):
                continue
        if should_skip(file, no_run_list):
            if report is not None:
                from result_collector import ScriptResult, Status
                reason = _find_skip_reason(file, no_run_list, skip_reasons or {})
                report.results.append(ScriptResult(
                    file=str(file),
                    status=Status.SKIPPED,
                    skip_reason=reason,
                ))
        else:
            from env_config import build_env_for_script
            env = build_env_for_script(file, env_config)
            execute_notebook(file, report=report, env=env)


def execute_script(f, report=None, env=None, extra_args=None):
    args = [BUILD_PYTHON_INTERPRETER, f]
    if extra_args:
        args.extend(extra_args)
    script_name = Path(f).relative_to(Path.cwd()) if Path(f).is_relative_to(Path.cwd()) else Path(f).name
    print(f"  {script_name} ...", end=" ", flush=True)

    start = time.time()
    try:
        if report is not None:
            result = subprocess.run(
                args,
                check=True,
                timeout=TIMEOUT_SECS,
                capture_output=True,
                text=True,
                env=env,
            )
        else:
            subprocess.run(
                args,
                check=True,
                timeout=TIMEOUT_SECS,
                env=env,
            )
    except subprocess.TimeoutExpired as e:
        duration = time.time() - start
        if report is not None:
            from result_collector import ScriptResult, Status
            print(f"  TIMEOUT ({duration:.0f}s)")
            report.results.append(ScriptResult(
                file=str(f),
                status=Status.TIMEOUT,
                duration_seconds=duration,
                error_message="Timed out after {:.0f}s".format(duration),
            ))
            return
        logging.exception(e)
        sys.exit(1)
    except subprocess.CalledProcessError as e:
        duration = time.time() - start

        if "inversion" in f:
            if report is not None:
                from result_collector import ScriptResult, Status
                print(f"  PASS (inversion, {duration:.1f}s)")
                report.results.append(ScriptResult(
                    file=str(f),
                    status=Status.PASSED,
                    duration_seconds=duration,
                    error_message="Inversion script failure (ignored)",
                ))
            return

        if report is not None:
            from result_collector import ScriptResult, Status
            stderr = getattr(e, 'stderr', '') or ''
            # One-line console summary; full details go to the report file
            last_line = stderr.strip().splitlines()[-1] if stderr.strip() else str(e)
            print(f"  FAIL ({duration:.1f}s) {last_line}")
            report.results.append(ScriptResult(
                file=str(f),
                status=Status.FAILED,
                duration_seconds=duration,
                error_message=str(e),
                traceback=stderr,
            ))
            return
        logging.exception(e)
        sys.exit(1)

    duration = time.time() - start
    if report is not None:
        from result_collector import ScriptResult, Status
        print(f"  PASS ({duration:.1f}s)")
        report.results.append(ScriptResult(
            file=str(f),
            status=Status.PASSED,
            duration_seconds=duration,
        ))


def find_scripts_in_folder(directory: str) -> List[Path]:
    """
    Find all the Python scripts in a folder recursively.

    Order the scripts such that:
    - Any script with "simulator" in the path comes first
    - Any script named "start_here.py" comes next
    - Any other script comes last

    Parameters
    ----------
    directory
        The directory to search in

    Returns
    -------
    A list of paths to the scripts
    """
    files = list((Path.cwd() / directory).rglob("*.py"))
    return sorted(
        files,
        key=lambda f: (
            ("simulator" not in str(f), f.name != "start_here.py", str(f)),
            f,
        ),
    )


def execute_scripts_in_folder(directory, no_run_list=None, report=None, skip_reasons=None, env_config=None):
    no_run_list = no_run_list or []
    # Infrastructure files — always skip, never report
    infra_skip = ["__init__", "README"]
    no_run_list.extend(infra_skip)

    files = find_scripts_in_folder(directory)
    print(f"Found {len(files)} scripts")

    for file in files:
        if file.stem in infra_skip:
            continue
        if should_skip(file, no_run_list):
            if report is not None:
                from result_collector import ScriptResult, Status
                reason = _find_skip_reason(file, no_run_list, skip_reasons or {})
                report.results.append(ScriptResult(
                    file=str(file),
                    status=Status.SKIPPED,
                    skip_reason=reason,
                ))
        else:
            from env_config import build_env_for_script, args_for_script
            env = build_env_for_script(file, env_config)
            extra_args = args_for_script(file, env_config)
            execute_script(str(file), report=report, env=env, extra_args=extra_args)
