"""Tests for generate_markdown.py — config parsing, path mapping, output cleaning."""

import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

AUTOHANDS_DIR = Path(__file__).parent.parent / "autohands"
sys.path.insert(0, str(AUTOHANDS_DIR))

import generate_markdown  # noqa: E402


def _write_config(workspace: Path, entries) -> None:
    config_path = workspace / generate_markdown.CONFIG_RELATIVE_PATH
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(yaml.safe_dump(entries))


def _make_script(workspace: Path, rel: str, docstring: str = "Title\n=====") -> None:
    script = workspace / rel
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text(f'"""\n{docstring}\n"""\nprint("hi")\n')


class TestLoadExamples:
    def test_dict_and_string_entries(self, tmp_path):
        _make_script(tmp_path, "scripts/imaging/modeling.py")
        _make_script(tmp_path, "start_here.py")
        _write_config(
            tmp_path,
            [
                {"script": "scripts/imaging/modeling.py", "max_minutes": 120},
                "start_here.py",
            ],
        )
        examples = generate_markdown.load_examples(tmp_path)
        assert examples[0]["script"] == Path("scripts/imaging/modeling.py")
        assert examples[0]["max_minutes"] == 120
        assert examples[1]["script"] == Path("start_here.py")
        assert examples[1]["max_minutes"] == generate_markdown.DEFAULT_MAX_MINUTES

    def test_features_folder_rejected(self, tmp_path):
        _make_script(tmp_path, "scripts/imaging/features/no_lens_light/modeling.py")
        _write_config(
            tmp_path, ["scripts/imaging/features/no_lens_light/modeling.py"]
        )
        with pytest.raises(ValueError, match="features/"):
            generate_markdown.load_examples(tmp_path)

    def test_missing_script_rejected(self, tmp_path):
        _write_config(tmp_path, ["scripts/imaging/nope.py"])
        with pytest.raises(FileNotFoundError):
            generate_markdown.load_examples(tmp_path)

    def test_non_py_rejected(self, tmp_path):
        _make_script(tmp_path, "scripts/imaging/modeling.py")
        (tmp_path / "scripts/imaging/modeling.ipynb").write_text("{}")
        _write_config(tmp_path, ["scripts/imaging/modeling.ipynb"])
        with pytest.raises(ValueError, match="not a .py"):
            generate_markdown.load_examples(tmp_path)

    def test_missing_config_reported(self, tmp_path):
        with pytest.raises(FileNotFoundError, match="markdown_examples.yaml"):
            generate_markdown.load_examples(tmp_path)


class TestMarkdownDestination:
    def test_scripts_prefix_stripped(self):
        assert generate_markdown.markdown_destination(
            Path("scripts/imaging/modeling.py")
        ) == Path("markdown/imaging")

    def test_root_script(self):
        assert generate_markdown.markdown_destination(
            Path("start_here.py")
        ) == Path("markdown")

    def test_nested_guides(self):
        assert generate_markdown.markdown_destination(
            Path("scripts/guides/tracer.py")
        ) == Path("markdown/guides")


class TestStreamCleaning:
    def test_ansi_stripped(self):
        assert generate_markdown._clean_stream_text("\x1b[1mBold\x1b[0m") == "Bold"

    def test_carriage_return_progress_resolved(self):
        assert (
            generate_markdown._clean_stream_text("it 1/100\rit 50/100\rit 100/100")
            == "it 100/100"
        )

    def test_long_output_truncated(self):
        text = "\n".join(f"line {i}" for i in range(200))
        cleaned = generate_markdown._clean_stream_text(text)
        lines = cleaned.split("\n")
        assert len(lines) == (
            generate_markdown.STREAM_HEAD_LINES
            + generate_markdown.STREAM_TAIL_LINES
            + 1
        )
        assert "truncated" in cleaned
        assert lines[0] == "line 0"
        assert lines[-1] == "line 199"

    def test_short_output_untouched(self):
        assert generate_markdown._clean_stream_text("a\nb") == "a\nb"

    def test_local_paths_redacted(self):
        redactions = generate_markdown._redactions_for(
            Path("/home/user/wt/autolens_workspace")
        )
        cleaned = generate_markdown._clean_stream_text(
            "Working Directory has been set to `/home/user/wt/autolens_workspace`\n"
            "/home/user/wt/PyAutoArray/autoarray/operators/convolver.py:1415: UserWarning",
            redactions=redactions,
        )
        assert "Working Directory has been set to `autolens_workspace`" in cleaned
        assert ".../PyAutoArray/autoarray/operators/convolver.py:1415" in cleaned
        assert "/home/user" not in cleaned

    def test_clean_notebook_outputs(self, tmp_path):
        notebook = {
            "cells": [
                {
                    "cell_type": "code",
                    "outputs": [
                        {"output_type": "stream", "text": ["a\r", "b\x1b[0m"]},
                        {"output_type": "display_data", "data": {}},
                    ],
                }
            ]
        }
        path = tmp_path / "nb.ipynb"
        path.write_text(json.dumps(notebook))
        generate_markdown.clean_notebook_outputs(path)
        cleaned = json.loads(path.read_text())
        assert cleaned["cells"][0]["outputs"][0]["text"] == "b"
        assert cleaned["cells"][0]["outputs"][1] == {
            "output_type": "display_data",
            "data": {},
        }


class TestMarkdownHeader:
    def test_scripts_page_links(self):
        header = generate_markdown._markdown_header(
            Path("scripts/imaging/modeling.py"), Path("markdown/imaging")
        )
        assert "../../scripts/imaging/modeling.py" in header
        assert "../../notebooks/imaging/modeling.ipynb" in header
        assert "auto-generated" in header

    def test_root_page_links(self):
        header = generate_markdown._markdown_header(
            Path("start_here.py"), Path("markdown")
        )
        assert "(../start_here.py)" in header
        assert "(../start_here.ipynb)" in header


class TestScriptTitle:
    def test_docstring_title(self, tmp_path):
        _make_script(tmp_path, "s.py", docstring="Modeling: Start Here\n====")
        assert generate_markdown.script_title(tmp_path / "s.py") == "Modeling: Start Here"

    def test_emphasis_markers_stripped(self, tmp_path):
        _make_script(tmp_path, "s.py", docstring="__Log Likelihood Function__")
        assert (
            generate_markdown.script_title(tmp_path / "s.py")
            == "Log Likelihood Function"
        )

    def test_no_docstring_falls_back_to_stem(self, tmp_path):
        script = tmp_path / "bare.py"
        script.write_text("print('hi')\n")
        assert generate_markdown.script_title(script) == "bare"


class TestTrackedFileProtection:
    def _git_workspace(self, tmp_path):
        subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
        subprocess.run(
            ["git", "config", "user.email", "t@t"], cwd=tmp_path, check=True
        )
        subprocess.run(["git", "config", "user.name", "t"], cwd=tmp_path, check=True)
        (tmp_path / "dataset.txt").write_text("original")
        subprocess.run(["git", "add", "dataset.txt"], cwd=tmp_path, check=True)
        subprocess.run(
            ["git", "commit", "-qm", "init"], cwd=tmp_path, check=True
        )
        return tmp_path

    def test_modified_tracked_file_restored(self, tmp_path):
        workspace = self._git_workspace(tmp_path)
        (workspace / "dataset.txt").write_text("clobbered by simulator")
        restored = generate_markdown.restore_tracked_files(workspace)
        assert restored == ["dataset.txt"]
        assert (workspace / "dataset.txt").read_text() == "original"

    def test_pre_dirty_files_excluded(self, tmp_path):
        workspace = self._git_workspace(tmp_path)
        (workspace / "dataset.txt").write_text("hand edit before build")
        restored = generate_markdown.restore_tracked_files(
            workspace, exclude=frozenset(["dataset.txt"])
        )
        assert restored == []
        assert (workspace / "dataset.txt").read_text() == "hand edit before build"

    def test_markdown_and_untracked_left_alone(self, tmp_path):
        workspace = self._git_workspace(tmp_path)
        md = workspace / "markdown"
        md.mkdir()
        (md / "page.md").write_text("new page")
        (workspace / "output.log").write_text("untracked")
        assert generate_markdown.restore_tracked_files(workspace) == []
        assert (md / "page.md").read_text() == "new page"
        assert (workspace / "output.log").exists()
