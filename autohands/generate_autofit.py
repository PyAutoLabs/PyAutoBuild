import glob
import os
from pathlib import Path

import build_util

WORKSPACE_PATH = f"{os.getcwd()}/../autofit_workspace"
PROJECTS_ROOT_PATH = f"{WORKSPACE_PATH}/projects"

PROJECTS_FOLDERS_OMIT = ["config", "dataset", "src"]


def generate_project_folders():
    for project_path in map(Path, glob.glob(f"{PROJECTS_ROOT_PATH}/*/")):
        try:
            os.remove(project_path / "temp.py")
        except FileNotFoundError:
            pass

        for f in glob.glob(f"{project_path}/*.ipynb*"):
            os.remove(project_path / f)

        for python_file in map(Path, glob.glob(f"{project_path}/*.py")):
            if python_file.name == "__init__.py":
                continue

            new_filename = build_util.py_to_notebook(python_file)
            build_util.inject_colab_setup(new_filename, "autofit")
            os.system(f"git add -f {new_filename}")
