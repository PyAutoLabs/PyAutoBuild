import os
import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "autobuild" / "bump_colab_urls.sh"


def run(directory, tag):
    return subprocess.run(
        ["bash", str(SCRIPT), tag],
        capture_output=True,
        text=True,
        cwd=directory,
    )


def test_bumps_workspace_tag(tmp_path):
    f = tmp_path / "README.rst"
    f.write_text(
        "https://colab.research.google.com/github/PyAutoLabs/autolens_workspace/blob/2026.4.13.6/start_here.ipynb"
    )
    result = run(tmp_path, "2026.5.0.0")
    assert result.returncode == 0, result.stderr
    assert (
        f.read_text()
        == "https://colab.research.google.com/github/PyAutoLabs/autolens_workspace/blob/2026.5.0.0/start_here.ipynb"
    )


def test_bumps_all_three_workspaces(tmp_path):
    contents = (
        "autofit:    https://colab.research.google.com/github/PyAutoLabs/autofit_workspace/blob/2026.1.0.0/a.ipynb\n"
        "autogalaxy: https://colab.research.google.com/github/PyAutoLabs/autogalaxy_workspace/blob/2026.2.0.0/b.ipynb\n"
        "autolens:   https://colab.research.google.com/github/PyAutoLabs/autolens_workspace/blob/2026.3.0.0/c.ipynb\n"
    )
    f = tmp_path / "all.md"
    f.write_text(contents)
    result = run(tmp_path, "2026.5.0.0")
    assert result.returncode == 0, result.stderr
    out = f.read_text()
    assert out.count("/blob/2026.5.0.0/") == 3
    assert "2026.1.0.0" not in out
    assert "2026.2.0.0" not in out
    assert "2026.3.0.0" not in out


def test_idempotent(tmp_path):
    f = tmp_path / "README.rst"
    original = (
        "https://colab.research.google.com/github/PyAutoLabs/autolens_workspace/blob/2026.5.0.0/start_here.ipynb"
    )
    f.write_text(original)
    run(tmp_path, "2026.5.0.0")
    run(tmp_path, "2026.5.0.0")
    assert f.read_text() == original


def test_leaves_jammy2211_alone(tmp_path):
    """Owner cleanup is the URL sweep PR's job, not the bumper's."""
    original = (
        "https://colab.research.google.com/github/Jammy2211/autolens_workspace/blob/2026.1.0.0/start_here.ipynb"
    )
    f = tmp_path / "README.rst"
    f.write_text(original)
    result = run(tmp_path, "2026.5.0.0")
    assert result.returncode == 0
    assert f.read_text() == original


def test_leaves_release_ref_alone(tmp_path):
    """Branch refs are not date-tagged, so the bumper skips them — url_check.sh catches these instead."""
    original = (
        "https://colab.research.google.com/github/PyAutoLabs/autolens_workspace/blob/release/start_here.ipynb"
    )
    f = tmp_path / "README.rst"
    f.write_text(original)
    result = run(tmp_path, "2026.5.0.0")
    assert result.returncode == 0
    assert f.read_text() == original


def test_leaves_non_workspace_urls_alone(tmp_path):
    original = (
        "https://colab.research.google.com/github/PyAutoLabs/PyAutoFit/blob/2026.1.0.0/some.ipynb"
    )
    f = tmp_path / "README.rst"
    f.write_text(original)
    result = run(tmp_path, "2026.5.0.0")
    assert result.returncode == 0
    assert f.read_text() == original


def test_rejects_non_date_tag(tmp_path):
    result = run(tmp_path, "v1.15.2")
    assert result.returncode == 2
    assert "YYYY.M.D.B" in result.stderr


def test_rejects_missing_arg(tmp_path):
    result = subprocess.run(
        ["bash", str(SCRIPT)], capture_output=True, text=True, cwd=tmp_path
    )
    assert result.returncode == 2


def test_handles_empty_directory(tmp_path):
    result = run(tmp_path, "2026.5.0.0")
    assert result.returncode == 0


def test_recurses_into_subdirectories(tmp_path):
    nested = tmp_path / "docs" / "howto"
    nested.mkdir(parents=True)
    f = nested / "intro.rst"
    f.write_text(
        "https://colab.research.google.com/github/PyAutoLabs/autofit_workspace/blob/2026.1.0.0/a.ipynb"
    )
    result = run(tmp_path, "2026.5.0.0")
    assert result.returncode == 0
    assert "/blob/2026.5.0.0/" in f.read_text()


def test_leaves_unscanned_extensions(tmp_path):
    f = tmp_path / "data.txt"
    original = (
        "https://colab.research.google.com/github/PyAutoLabs/autolens_workspace/blob/2026.1.0.0/x.ipynb"
    )
    f.write_text(original)
    result = run(tmp_path, "2026.5.0.0")
    assert result.returncode == 0
    assert f.read_text() == original
