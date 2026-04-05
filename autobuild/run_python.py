#!/usr/bin/env python

import sys
import yaml
from argparse import ArgumentParser
from pathlib import Path

import build_util

parser = ArgumentParser()
parser.add_argument("project", type=str, help="The project to run scripts for")
parser.add_argument("directory", type=str, help="The directory containing scripts")
parser.add_argument(
    "--report-dir",
    type=str,
    default=None,
    help="Directory to write structured JSON results to",
)

args = parser.parse_args()

project = args.project
directory = args.directory

CONFIG_PATH = Path(__file__).parent / "config"

with open(CONFIG_PATH / "no_run.yaml") as f:
    no_run_dict = yaml.safe_load(f)

if __name__ == "__main__":
    report = None
    skip_reasons = None

    if args.report_dir:
        from result_collector import RunReport, parse_no_run_reasons

        report = RunReport(
            project=project,
            directory=directory,
            run_type="script",
        )
        skip_reasons = parse_no_run_reasons(CONFIG_PATH / "no_run.yaml", project)

    build_util.execute_scripts_in_folder(
        no_run_list=no_run_dict[project],
        directory=directory,
        report=report,
        skip_reasons=skip_reasons,
    )

    if report is not None:
        report_path = report.write(Path(args.report_dir))
        print(f"Results written to {report_path}")
        if report.has_failures:
            sys.exit(1)
