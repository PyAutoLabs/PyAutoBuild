import os
import shutil
from os import path
from pathlib import Path
from sys import argv

import yaml

import build_util
import generate_autofit

WORKSPACE_PATH = Path.cwd()
CONFIG_PATH = WORKSPACE_PATH.parent / "PyAutoBuild/autobuild/config"

project = argv[1]

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
    generate_autofit.generate_project_folders()

    path = Path(".")

    start_here_files = [
        f for f in path.glob("start_here*.py")
        if f.name != "welcome.py"
    ]

    for old_notebook in path.glob("start_here*.ipynb"):
        os.remove(old_notebook)

    for start_here_file in start_here_files:

        notebook = build_util.py_to_notebook(start_here_file)
        os.system(f"git add -f {notebook}")

    scripts_path = Path(f"{WORKSPACE_PATH}/scripts")
    notebooks_path = notebook_path_(scripts_path)

    shutil.rmtree(WORKSPACE_PATH / "notebooks", ignore_errors=True)

    for script_path in scripts_path.rglob("*.py"):
        if script_path.name == "__init__.py":
            continue
        if is_copy_file(script_path):
            copy_to_notebooks(script_path)
        else:
            source_path = build_util.py_to_notebook(script_path)
            copy_to_notebooks(source_path)
            os.remove(source_path)

    for read_me_path in scripts_path.rglob("*.rst"):
        copy_to_notebooks(read_me_path)

    for read_me_path in scripts_path.rglob("*.md"):
        copy_to_notebooks(read_me_path)
