import sys
import yaml
from pathlib import Path

import build_util

from argparse import ArgumentParser


parser = ArgumentParser()

parser.add_argument("project", type=str, help="The project to build")
parser.add_argument("directory", type=str, help="The directory to build")
parser.add_argument(
    "--visualise",
    action="store_true",
    help="Only run notebooks for which we want to create visualisations",
)
parser.add_argument(
    "--report-dir",
    type=str,
    default=None,
    help="Directory to write structured JSON results to",
)
parser.add_argument(
    "--env-config",
    type=str,
    default=None,
    help="Path to env_vars.yaml for per-script environment configuration",
)

args = parser.parse_args()

project = args.project
directory = args.directory
visualise = args.visualise

WORKSPACE_BUILD_CONFIG = Path.cwd() / "config" / "build"

# Each workspace owns its build config in config/build/. There is no
# autohands-level fallback: the keyed-dict fallbacks were removed once every
# build target owned its own files, so a missing config is a workspace bug and
# is reported as one rather than silently resolving to someone else's rules.
no_run_path = WORKSPACE_BUILD_CONFIG / "no_run.yaml"
if not no_run_path.exists():
    raise FileNotFoundError(
        f"{no_run_path} not found. Every workspace must own its "
        f"config/build/no_run.yaml (an empty file is valid and skips nothing). "
        f"Run from the workspace root, not from PyAutoHands."
    )

with open(no_run_path) as f:
    no_run_list = yaml.safe_load(f) or []

if visualise:
    # A workspace with no visualise_notebooks.yaml has nothing marked for
    # visualisation; that is not an error, it just selects nothing.
    workspace_visualise = WORKSPACE_BUILD_CONFIG / "visualise_notebooks.yaml"
    if workspace_visualise.exists():
        with open(workspace_visualise) as f:
            visualise_dict = yaml.safe_load(f) or []
    else:
        print(
            f"--visualise: no {workspace_visualise} in this workspace; "
            f"no notebooks are marked for visualisation."
        )
        visualise_dict = []
else:
    visualise_dict = None

# env_vars.yaml: explicit flag > workspace config/build/ > none
env_config_path = None
if args.env_config:
    env_config_path = Path(args.env_config)
elif (WORKSPACE_BUILD_CONFIG / "env_vars.yaml").exists():
    env_config_path = WORKSPACE_BUILD_CONFIG / "env_vars.yaml"

if __name__ == "__main__":
    report = None
    skip_reasons = None

    if args.report_dir:
        from result_collector import RunReport, parse_no_run_reasons

        report = RunReport(
            project=project,
            directory=directory,
            run_type="notebook",
        )
        skip_reasons = parse_no_run_reasons(no_run_path, project)

    env_config = None
    if env_config_path:
        from env_config import load_env_config
        env_config = load_env_config(env_config_path)

    build_util.execute_notebooks_in_folder(
        no_run_list=no_run_list,
        visualise_dict=visualise_dict,
        directory=directory,
        report=report,
        skip_reasons=skip_reasons,
        env_config=env_config,
    )

    if report is not None:
        report_path = report.write(Path(args.report_dir))
        print(f"Results written to {report_path}")
        if report.has_failures:
            sys.exit(1)
