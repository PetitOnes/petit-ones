"""Tests for notes-mcp server."""

import asyncio
import tempfile
from pathlib import Path
from unittest.mock import patch

from notes_mcp.server import _safe_name, call_tool


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


class TestSafeName:
    def test_adds_md_extension(self):
        assert _safe_name("hello") == "hello.md"

    def test_keeps_md_extension(self):
        assert _safe_name("hello.md") == "hello.md"

    def test_strips_whitespace(self):
        assert _safe_name("  hello  ") == "hello.md"

    def test_replaces_slashes(self):
        assert _safe_name("a/b\\c") == "a_b_c.md"

    def test_replaces_dotdot(self):
        assert _safe_name("../etc/passwd") == "__etc_passwd.md"

    def test_empty_becomes_untitled(self):
        assert _safe_name("") == "untitled.md"


class TestListNotes:
    def test_empty_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("notes_mcp.server.NOTES_DIR", Path(tmpdir)):
                result = _run(call_tool("list_notes", {}))
                assert "空です" in result[0].text

    def test_lists_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            d = Path(tmpdir)
            (d / "light.md").write_text("test", encoding="utf-8")
            (d / "sounds.md").write_text("test2", encoding="utf-8")
            with patch("notes_mcp.server.NOTES_DIR", d):
                result = _run(call_tool("list_notes", {}))
                assert "light" in result[0].text
                assert "sounds" in result[0].text
                assert "2 ノート" in result[0].text


class TestReadNote:
    def test_read_existing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            d = Path(tmpdir)
            (d / "test.md").write_text("# Hello\nWorld", encoding="utf-8")
            with patch("notes_mcp.server.NOTES_DIR", d):
                result = _run(call_tool("read_note", {"name": "test"}))
                assert "Hello" in result[0].text
                assert "World" in result[0].text

    def test_read_missing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("notes_mcp.server.NOTES_DIR", Path(tmpdir)):
                result = _run(call_tool("read_note", {"name": "nope"}))
                assert "見つかりません" in result[0].text


class TestWriteNote:
    def test_create_new(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            d = Path(tmpdir)
            with patch("notes_mcp.server.NOTES_DIR", d):
                result = _run(call_tool("write_note", {"name": "test", "content": "hello"}))
                assert "作成" in result[0].text
                assert (d / "test.md").read_text() == "hello"

    def test_overwrite_existing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            d = Path(tmpdir)
            (d / "test.md").write_text("old", encoding="utf-8")
            with patch("notes_mcp.server.NOTES_DIR", d):
                result = _run(call_tool("write_note", {"name": "test", "content": "new"}))
                assert "更新" in result[0].text
                assert (d / "test.md").read_text() == "new"


class TestAppendNote:
    def test_append_to_existing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            d = Path(tmpdir)
            (d / "log.md").write_text("line1", encoding="utf-8")
            with patch("notes_mcp.server.NOTES_DIR", d):
                result = _run(call_tool("append_note", {"name": "log", "content": "line2"}))
                assert "追記" in result[0].text
                assert (d / "log.md").read_text() == "line1\nline2"

    def test_append_creates_new(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            d = Path(tmpdir)
            with patch("notes_mcp.server.NOTES_DIR", d):
                result = _run(call_tool("append_note", {"name": "new", "content": "first"}))
                assert "作成" in result[0].text
                assert (d / "new.md").read_text() == "first"


class TestDeleteNote:
    def test_delete_existing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            d = Path(tmpdir)
            (d / "bye.md").write_text("gone", encoding="utf-8")
            with patch("notes_mcp.server.NOTES_DIR", d):
                result = _run(call_tool("delete_note", {"name": "bye"}))
                assert "削除" in result[0].text
                assert not (d / "bye.md").exists()

    def test_delete_missing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("notes_mcp.server.NOTES_DIR", Path(tmpdir)):
                result = _run(call_tool("delete_note", {"name": "nope"}))
                assert "見つかりません" in result[0].text
