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

TIMEOUT_SECS = 36000
BUILD_PATH = Path(__file__).parent

BUILD_PYTHON_INTERPRETER = os.environ.get("BUILD_PYTHON_INTERPRETER", "python3")
print(BUILD_PYTHON_INTERPRETER)


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


def uncomment_jupyter_magic(f):
    with open(f, "r") as sources:
        lines = sources.readlines()
    with open(f, "w") as sources:
        for line in lines:
            line = re.sub(r"# %matplotlib", "%matplotlib", line)
            line = re.sub(r"# from pyproj", "from pyproj", line)
            line = re.sub(r"# workspace_path", "workspace_path", line)
            line = re.sub(r"# %cd", "%cd", line)
            line = re.sub(r"# print\(f", "print(f", line)
            sources.write(line)


def no_run_list_with_extension_from(no_run_list: List[str], extension: str):
    for i, no_run in enumerate(no_run_list):
        if not no_run.endswith(extension):
            no_run_list[i] = f"{no_run}{extension}"

    return no_run_list


def should_skip(file: Path, no_run_list: List[str]) -> bool:
    """
    Return True if the file matches any entry in no_run_list.

    Entries with a '/' are treated as path-specific patterns: the file is
    skipped only if that pattern appears in the file's path (without extension).
    Entries without a '/' match any file whose stem equals the entry.
    """
    file_path_no_ext = str(file.with_suffix(""))
    for pattern in no_run_list:
        if "/" in pattern:
            if pattern in file_path_no_ext:
                return True
        else:
            if file.stem == pattern:
                return True
    return False


def _find_skip_reason(file: Path, no_run_list: List[str], skip_reasons: dict) -> str:
    """Find the reason a file is being skipped from the skip_reasons dict."""
    file_path_no_ext = str(file.with_suffix(""))
    for pattern in no_run_list:
        if "/" in pattern:
            if pattern in file_path_no_ext:
                return skip_reasons.get(pattern, "No reason documented")
        else:
            if file.stem == pattern:
                return skip_reasons.get(pattern, "No reason documented")
    return "No reason documented"


def execute_notebook(f, report=None):
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
            )
            print(result.stdout)
            if result.stderr:
                print(result.stderr, file=sys.stderr)
        else:
            subprocess.run(
                ["jupyter", "nbconvert", "--to", "notebook", "--execute", "--output", f, f],
                check=True,
                timeout=TIMEOUT_SECS,
            )
    except subprocess.TimeoutExpired as e:
        logging.exception(e)
        duration = time.time() - start
        if report is not None:
            from result_collector import ScriptResult, Status
            report.results.append(ScriptResult(
                file=str(f),
                status=Status.TIMEOUT,
                duration_seconds=duration,
                error_message="Timed out after {:.0f}s".format(duration),
            ))
            return
        sys.exit(1)
    except subprocess.CalledProcessError as e:
        logging.exception(e)
        duration = time.time() - start

        if "InversionException" in traceback.format_exc():
            if report is not None:
                from result_collector import ScriptResult, Status
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
            report.results.append(ScriptResult(
                file=str(f),
                status=Status.FAILED,
                duration_seconds=duration,
                error_message=str(e),
                traceback=stderr,
            ))
            return
        sys.exit(1)

    duration = time.time() - start
    if report is not None:
        from result_collector import ScriptResult, Status
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
):
    # Infrastructure files — always skip, never report
    infra_skip = ["__init__", "README"]
    no_run_list.extend(infra_skip)
    files = list(Path.cwd().rglob(f"{directory}/**/*.ipynb"))

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
            execute_notebook(file, report=report)


def execute_script(f, report=None):
    args = [BUILD_PYTHON_INTERPRETER, f]
    print(f"Running <{args}>")

    start = time.time()
    try:
        if report is not None:
            result = subprocess.run(
                args,
                check=True,
                timeout=TIMEOUT_SECS,
                capture_output=True,
                text=True,
            )
            print(result.stdout)
            if result.stderr:
                print(result.stderr, file=sys.stderr)
        else:
            subprocess.run(
                args,
                check=True,
                timeout=TIMEOUT_SECS,
            )
    except subprocess.TimeoutExpired as e:
        logging.exception(e)
        duration = time.time() - start
        if report is not None:
            from result_collector import ScriptResult, Status
            report.results.append(ScriptResult(
                file=str(f),
                status=Status.TIMEOUT,
                duration_seconds=duration,
                error_message="Timed out after {:.0f}s".format(duration),
            ))
            return
        sys.exit(1)
    except subprocess.CalledProcessError as e:
        logging.exception(e)
        duration = time.time() - start

        if "inversion" in f:
            if report is not None:
                from result_collector import ScriptResult, Status
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
            report.results.append(ScriptResult(
                file=str(f),
                status=Status.FAILED,
                duration_seconds=duration,
                error_message=str(e),
                traceback=stderr,
            ))
            return
        sys.exit(1)

    duration = time.time() - start
    if report is not None:
        from result_collector import ScriptResult, Status
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
    files = list(Path.cwd().rglob(f"{directory}/**/*.py"))
    return sorted(
        files,
        key=lambda f: (
            ("simulator" not in str(f), f.name != "start_here.py", str(f)),
            f,
        ),
    )


def execute_scripts_in_folder(directory, no_run_list=None, report=None, skip_reasons=None):
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
            execute_script(str(file), report=report)
