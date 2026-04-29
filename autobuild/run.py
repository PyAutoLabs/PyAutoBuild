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

AUTOBUILD_CONFIG = Path(__file__).parent / "config"
WORKSPACE_BUILD_CONFIG = Path.cwd() / "config" / "build"

# no_run.yaml: prefer workspace config/build/, fall back to autobuild config
no_run_path = WORKSPACE_BUILD_CONFIG / "no_run.yaml"
if not no_run_path.exists():
    no_run_path = AUTOBUILD_CONFIG / "no_run.yaml"

with open(no_run_path) as f:
    no_run_data = yaml.safe_load(f)

# Support both flat list (workspace) and keyed dict (legacy autobuild)
if isinstance(no_run_data, dict):
    no_run_list = no_run_data[project]
else:
    no_run_list = no_run_data or []

if visualise:
    # visualise_notebooks.yaml: prefer workspace config/build/ (flat list),
    # fall back to autobuild's keyed dict indexed by project.
    workspace_visualise = WORKSPACE_BUILD_CONFIG / "visualise_notebooks.yaml"
    if workspace_visualise.exists():
        with open(workspace_visualise) as f:
            visualise_dict = yaml.safe_load(f) or []
    else:
        with open(AUTOBUILD_CONFIG / "visualise_notebooks.yaml") as f:
            visualise_dict = yaml.safe_load(f).get(project) or []
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
