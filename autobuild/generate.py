import os
import shutil
import sys
import time
from argparse import ArgumentParser
from os import path
from pathlib import Path

import yaml

import build_util
import generate_autofit

parser = ArgumentParser()
parser.add_argument("project", type=str, help="The project to generate notebooks for")
parser.add_argument(
    "--report-dir",
    type=str,
    default=None,
    help="Directory to write structured JSON generation results to",
)

args = parser.parse_args()

WORKSPACE_PATH = Path.cwd()
CONFIG_PATH = WORKSPACE_PATH.parent / "PyAutoBuild/autobuild/config"

project = args.project

with open(path.join(CONFIG_PATH, "copy_files.yaml"), "r+") as f:
    copy_files_dict = yaml.safe_load(f)

copy_files_list = copy_files_dict[project] or []


def is_copy_file(file_path):
    return any(str(file_path).endswith(copy_file) for copy_file in copy_files_list)


def notebook_path_(script_path_):
    return Path(str(script_path_).replace("/scripts/", "/notebooks/"))


def copy_to_notebooks(source):
    target = notebook_path_(source)
    os.makedirs(target.parent, exist_ok=True)
    shutil.copy(source, target)
    os.system(f"git add -f {target}")


if __name__ == "__main__":
    report = None
    if args.report_dir:
        from result_collector import RunReport
        report = RunReport(
            project=project,
            directory="",
            run_type="generate",
        )

    generate_autofit.generate_project_folders()

    p = Path(".")

    start_here_files = [
        f for f in p.glob("start_here*.py")
        if f.name != "welcome.py"
    ]

    for old_notebook in p.glob("start_here*.ipynb"):
        os.remove(old_notebook)

    for start_here_file in start_here_files:
        start = time.time()
        try:
            notebook = build_util.py_to_notebook(start_here_file)
            os.system(f"git add -f {notebook}")
            if report is not None:
                from result_collector import ScriptResult, Status
                report.results.append(ScriptResult(
                    file=str(start_here_file),
                    status=Status.PASSED,
                    duration_seconds=time.time() - start,
                ))
        except Exception as e:
            if report is not None:
                from result_collector import ScriptResult, Status
                report.results.append(ScriptResult(
                    file=str(start_here_file),
                    status=Status.FAILED,
                    duration_seconds=time.time() - start,
                    error_message=str(e),
                ))
            else:
                raise

    scripts_path = Path(f"{WORKSPACE_PATH}/scripts")
    notebooks_path = notebook_path_(scripts_path)

    shutil.rmtree(WORKSPACE_PATH / "notebooks", ignore_errors=True)

    for script_path in scripts_path.rglob("*.py"):
        if script_path.name == "__init__.py":
            continue
        start = time.time()
        if is_copy_file(script_path):
            try:
                copy_to_notebooks(script_path)
                if report is not None:
                    from result_collector import ScriptResult, Status
                    report.results.append(ScriptResult(
                        file=str(script_path),
                        status=Status.PASSED,
                        duration_seconds=time.time() - start,
                    ))
            except Exception as e:
                if report is not None:
                    from result_collector import ScriptResult, Status
                    report.results.append(ScriptResult(
                        file=str(script_path),
                        status=Status.FAILED,
                        duration_seconds=time.time() - start,
                        error_message=str(e),
                    ))
                else:
                    raise
        else:
            try:
                source_path = build_util.py_to_notebook(script_path)
                copy_to_notebooks(source_path)
                os.remove(source_path)
                if report is not None:
                    from result_collector import ScriptResult, Status
                    report.results.append(ScriptResult(
                        file=str(script_path),
                        status=Status.PASSED,
                        duration_seconds=time.time() - start,
                    ))
            except Exception as e:
                if report is not None:
                    from result_collector import ScriptResult, Status
                    report.results.append(ScriptResult(
                        file=str(script_path),
                        status=Status.FAILED,
                        duration_seconds=time.time() - start,
                        error_message=str(e),
                    ))
                else:
                    raise

    for read_me_path in scripts_path.rglob("*.rst"):
        copy_to_notebooks(read_me_path)

    for read_me_path in scripts_path.rglob("*.md"):
        copy_to_notebooks(read_me_path)

    if report is not None:
        report_path = report.write(Path(args.report_dir))
        print(f"Generation results written to {report_path}")
        if report.has_failures:
            sys.exit(1)
