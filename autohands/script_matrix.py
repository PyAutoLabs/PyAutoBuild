#!/usr/bin/env python
import json
import os
import sys
from pathlib import Path


def make_script_matrix(project):
    return [
        {
            "name": project,
            "directory": path.name,
        }
        for path in (Path(project) / "scripts").glob("*/")
        if path.is_dir()
    ]


def make_combined_script_matrix(projects):
    return [item for project in projects for item in make_script_matrix(project)]


if __name__ == "__main__":
    projects = sys.argv[1:]

    output = make_combined_script_matrix(projects)
    print(json.dumps(output))
