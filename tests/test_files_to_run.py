import os
from pathlib import Path

from autohands.build_util import find_scripts_in_folder


def test_script_order():
    os.chdir(Path(__file__).parent)
    directory = "scripts_folder"
    scripts = [
        str(path.relative_to(Path.cwd() / directory))
        for path in find_scripts_in_folder(directory)
    ]

    assert scripts == [
        "simulators/simulator_script.py",
        "sub_directory/simulator.py",
        "sub_directory/simulators.py",
        "start_here.py",
        "a.py",
        "sub_directory/sub.py",
        "top_level.py",
    ]
