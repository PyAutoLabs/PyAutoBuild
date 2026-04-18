import argparse
import os
import subprocess

WORKSPACE = "../"

LIB_PROJECTS = ["PyAutoConf", "PyAutoFit", "PyAutoArray", "PyAutoLens", "PyAutoGalaxy"]


def main(version):
    for project in LIB_PROJECTS:
        print(f"Tagging {project}")
        old_dir = os.getcwd()
        os.chdir(os.path.join(WORKSPACE, project))
        subprocess.run(
            ["git", "commit", "-a", "-m", f"Update version to {version}"], check=True
        )
        subprocess.run(["git", "tag", f"v{version}"], check=True)
        os.chdir(old_dir)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Tag library projects for release")
    parser.add_argument("--version", type=str, required=True, help="Version to use")

    args = parser.parse_args()
    main(args.version)
