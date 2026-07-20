from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

from blender_git_manager.services.history_diff_parser import (
    HistoryDiffParseError,
    combine_diff_records,
    parse_commit_diff_z,
    parse_name_status_z,
    parse_numstat_z,
)


class HistoryDiffParserTests(unittest.TestCase):
    def test_parses_normal_binary_and_unusual_numstat_paths(self):
        output = (
            "12\t3\tfolder/file with spaces.txt\0"
            "-\t-\tassets/textura-árbol.bin\0"
            "1\t0\tline\nbreak\tand-tab.txt\0"
        )

        records = parse_numstat_z(output)

        self.assertEqual(len(records), 3)
        self.assertEqual(records[0].path, "folder/file with spaces.txt")
        self.assertEqual((records[0].added_lines, records[0].deleted_lines), (12, 3))
        self.assertTrue(records[1].is_binary)
        self.assertEqual(records[1].path, "assets/textura-árbol.bin")
        self.assertEqual(records[2].path, "line\nbreak\tand-tab.txt")

    def test_parses_numstat_rename_and_copy_shape(self):
        # numstat uses the same three-path shape for renames and copies; their
        # distinction comes from the independently parsed name-status output.
        output = (
            "4\t2\t\0old scene.blend\0new\nscene.blend\0"
            "0\t0\t\0source.txt\0copia-ñ.txt\0"
        )

        records = parse_numstat_z(output)

        self.assertEqual(
            [(record.old_path, record.path) for record in records],
            [
                ("old scene.blend", "new\nscene.blend"),
                ("source.txt", "copia-ñ.txt"),
            ],
        )

    def test_parses_name_status_including_rename_copy_and_type_change(self):
        output = (
            "M\0plain file.txt\0"
            "R87\0old\nname.txt\0new\nname.txt\0"
            "C100\0origen-ñ.txt\0copia-ñ.txt\0"
            "T\0linked asset\0"
        )

        records = parse_name_status_z(output)

        self.assertEqual([record.status_token for record in records], ["M", "R087", "C100", "T"])
        self.assertTrue(records[1].is_rename)
        self.assertEqual(records[1].similarity, 87)
        self.assertEqual(records[1].old_path, "old\nname.txt")
        self.assertTrue(records[2].is_copy)
        self.assertEqual(records[2].path, "copia-ñ.txt")

    def test_combines_outputs_in_order_and_preserves_binary_marker(self):
        records = parse_commit_diff_z(
            "2\t1\tnormal.txt\0-\t-\t\0old.bin\0new.bin\0",
            "M\0normal.txt\0R100\0old.bin\0new.bin\0",
        )

        self.assertEqual(len(records), 2)
        self.assertEqual(records[0].status, "M")
        self.assertEqual((records[0].added_lines, records[0].deleted_lines), (2, 1))
        self.assertEqual(records[1].status_token, "R100")
        self.assertEqual(records[1].original_path, "old.bin")
        self.assertTrue(records[1].is_binary)

    def test_bytes_are_decoded_losslessly_with_surrogateescape(self):
        record = parse_numstat_z(b"1\t0\tinvalid-\xff-name.txt\0")[0]

        self.assertEqual(record.path.encode("utf-8", errors="surrogateescape"), b"invalid-\xff-name.txt")

    def test_empty_outputs_return_empty_lists(self):
        self.assertEqual(parse_numstat_z(""), [])
        self.assertEqual(parse_name_status_z(b""), [])
        self.assertEqual(parse_commit_diff_z("", ""), [])

    def test_rejects_truncated_or_malformed_numstat(self):
        malformed = (
            "1\t0\tfile.txt",
            "1\t0\0old.txt\0new.txt\0",
            "1\t-\tfile.bin\0",
            "one\t0\tfile.txt\0",
            "1\t0\t\0only-old.txt\0",
        )
        for output in malformed:
            with self.subTest(output=output):
                with self.assertRaises(HistoryDiffParseError):
                    parse_numstat_z(output)

    def test_rejects_truncated_or_malformed_name_status(self):
        malformed = (
            "M\0file.txt",
            "M100\0file.txt\0",
            "R\0old.txt\0new.txt\0",
            "R101\0old.txt\0new.txt\0",
            "R0000\0old.txt\0new.txt\0",
            "R80\0only-old.txt\0",
            "Q\0file.txt\0",
        )
        for output in malformed:
            with self.subTest(output=output):
                with self.assertRaises(HistoryDiffParseError):
                    parse_name_status_z(output)

    def test_rejects_mismatched_parallel_outputs(self):
        numstat = parse_numstat_z("1\t0\tfirst.txt\0")
        statuses = parse_name_status_z("M\0second.txt\0")

        with self.assertRaisesRegex(HistoryDiffParseError, "paths differ"):
            combine_diff_records(numstat, statuses)

        with self.assertRaisesRegex(HistoryDiffParseError, "different number"):
            combine_diff_records(numstat, [])

    def test_rejects_non_text_input(self):
        with self.assertRaises(TypeError):
            parse_numstat_z(None)  # type: ignore[arg-type]


class HistoryDiffGitIntegrationTests(unittest.TestCase):
    def _git(self, root: Path, *arguments: str) -> bytes:
        return subprocess.run(
            ["git", *arguments],
            cwd=root,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        ).stdout

    def test_parses_real_git_rename_unicode_spaces_and_binary_file(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._git(root, "init", "-q")
            self._git(root, "config", "user.name", "History Parser Test")
            self._git(root, "config", "user.email", "history-parser@example.invalid")

            old_path = root / "old scene.txt"
            old_path.write_text("".join(f"line {index}\n" for index in range(80)), encoding="utf-8")
            copy_source = root / "copy source.txt"
            copy_source.write_text(
                "".join(f"unique copy line {index}\n" for index in range(80)),
                encoding="utf-8",
            )
            (root / "binary.dat").write_bytes(b"\0first binary version")
            self._git(root, "add", ".")
            self._git(root, "commit", "-qm", "initial")

            new_relative_path = "escena nueva á.txt"
            old_path.rename(root / new_relative_path)
            copy_relative_path = "copia exacta β.txt"
            (root / copy_relative_path).write_bytes(copy_source.read_bytes())
            (root / "binary.dat").write_bytes(b"\0second binary version")
            (root / "notes with spaces.txt").write_text("uno\ndos\n", encoding="utf-8")
            self._git(root, "add", "-A")
            self._git(root, "commit", "-qm", "rename and modify")

            common_arguments = (
                "--find-renames",
                "--find-copies",
                "--find-copies-harder",
                "HEAD^",
                "HEAD",
            )
            numstat_output = self._git(root, "diff", "--numstat", "-z", *common_arguments)
            status_output = self._git(root, "diff", "--name-status", "-z", *common_arguments)

        records = parse_commit_diff_z(numstat_output, status_output)
        by_path = {record.path: record for record in records}
        self.assertEqual(by_path[new_relative_path].status, "R")
        self.assertEqual(by_path[new_relative_path].old_path, "old scene.txt")
        self.assertEqual(by_path[copy_relative_path].status, "C")
        self.assertEqual(by_path[copy_relative_path].old_path, "copy source.txt")
        self.assertTrue(by_path["binary.dat"].is_binary)
        self.assertEqual(by_path["notes with spaces.txt"].status, "A")


if __name__ == "__main__":
    unittest.main()
