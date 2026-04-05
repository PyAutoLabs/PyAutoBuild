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

args = parser.parse_args()

project = args.project
directory = args.directory
visualise = args.visualise

CONFIG_PATH = Path(__file__).parent / "config"

with open(CONFIG_PATH / "no_run.yaml") as f:
    no_run_dict = yaml.safe_load(f)

if visualise:
    with open(CONFIG_PATH / "visualise_notebooks.yaml") as f:
        visualise_dict = yaml.safe_load(f)[project]
else:
    visualise_dict = None

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
        skip_reasons = parse_no_run_reasons(CONFIG_PATH / "no_run.yaml", project)

    build_util.execute_notebooks_in_folder(
        no_run_list=no_run_dict[project],
        visualise_dict=visualise_dict,
        directory=directory,
        report=report,
        skip_reasons=skip_reasons,
    )

    if report is not None:
        report_path = report.write(Path(args.report_dir))
        print(f"Results written to {report_path}")
        if report.has_failures:
            sys.exit(1)
