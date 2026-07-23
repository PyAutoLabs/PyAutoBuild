import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "autohands"))

import build_util


def make_notebook(path, cells):
    notebook = {
        "cells": cells,
        "metadata": {},
        "nbformat": 4,
        "nbformat_minor": 4,
    }
    path.write_text(json.dumps(notebook))
    return path


def markdown_cell(text):
    return {"cell_type": "markdown", "metadata": {}, "source": [text]}


def code_cell(text):
    return {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": [text],
    }


def test_injects_after_leading_markdown(tmp_path):
    nb_path = make_notebook(
        tmp_path / "example.ipynb",
        [markdown_cell("Title\n====="), code_cell("import autolens as al")],
    )

    assert build_util.inject_colab_setup(nb_path, "autolens") is True

    cells = json.loads(nb_path.read_text())["cells"]
    assert len(cells) == 4
    assert cells[0]["source"] == ["Title\n====="]
    assert cells[1]["cell_type"] == "markdown"
    assert "Google Colab Setup" in "".join(cells[1]["source"])
    assert cells[2]["cell_type"] == "code"
    assert 'setup_colab.setup("autolens")' in "".join(cells[2]["source"])
    assert cells[3]["source"] == ["import autolens as al"]


def test_injects_at_top_when_no_leading_markdown(tmp_path):
    nb_path = make_notebook(
        tmp_path / "example.ipynb", [code_cell("import autofit as af")]
    )

    assert build_util.inject_colab_setup(nb_path, "autofit") is True

    cells = json.loads(nb_path.read_text())["cells"]
    assert cells[0]["cell_type"] == "markdown"
    assert 'setup_colab.setup("autofit")' in "".join(cells[1]["source"])


def test_skips_notebook_with_hand_written_setup(tmp_path):
    original = [
        markdown_cell("Title"),
        code_cell("from autonerves import setup_colab\nsetup_colab.for_autolens()"),
    ]
    nb_path = make_notebook(tmp_path / "start_here.ipynb", original)

    assert build_util.inject_colab_setup(nb_path, "autolens") is False
    assert json.loads(nb_path.read_text())["cells"] == original


def test_idempotent(tmp_path):
    nb_path = make_notebook(
        tmp_path / "example.ipynb", [markdown_cell("Title"), code_cell("x = 1")]
    )

    assert build_util.inject_colab_setup(nb_path, "howtolens") is True
    once = nb_path.read_text()
    assert build_util.inject_colab_setup(nb_path, "howtolens") is False
    assert nb_path.read_text() == once


def test_all_projects_accepted(tmp_path):
    for project in sorted(build_util.COLAB_PROJECTS):
        nb_path = make_notebook(tmp_path / f"{project}.ipynb", [code_cell("x = 1")])
        assert build_util.inject_colab_setup(nb_path, project) is True
        cells = json.loads(nb_path.read_text())["cells"]
        assert f'setup_colab.setup("{project}")' in "".join(cells[1]["source"])


def test_unknown_project_raises(tmp_path):
    nb_path = make_notebook(tmp_path / "example.ipynb", [code_cell("x = 1")])
    with pytest.raises(ValueError, match="unknown project 'euclid'"):
        build_util.inject_colab_setup(nb_path, "euclid")


def test_output_is_valid_notebook_json(tmp_path):
    nb_path = make_notebook(
        tmp_path / "example.ipynb", [markdown_cell("Title"), code_cell("x = 1")]
    )
    build_util.inject_colab_setup(nb_path, "autogalaxy")

    notebook = json.loads(nb_path.read_text())
    assert notebook["nbformat"] == 4
    for cell in notebook["cells"]:
        assert isinstance(cell["source"], list)
        assert all(isinstance(line, str) for line in cell["source"])
    code = notebook["cells"][2]
    assert code["outputs"] == []
    assert code["execution_count"] is None
