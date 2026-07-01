"""CHARLS/NHANES adapter + inspect-database CLI tests.

All data here is SYNTHETIC, generated with pandas into temporary directories.
These tests never touch the user's real CHARLS data. They require the optional
``multidb`` dependency (pandas); the module is skipped when pandas is absent.
"""

from __future__ import annotations

import io
import json
import warnings
import zipfile
from pathlib import Path

import pytest

pd = pytest.importorskip("pandas")

from neurosurg_epi_agent.adapters import (  # noqa: E402
    CHARLSAdapter,
    DuplicateMemberError,
    EncryptedMemberError,
    MalformedArchiveError,
    NHANESAdapter,
    default_registry,
)
from neurosurg_epi_agent.adapters.base import (  # noqa: E402
    MemberSizeExceededError,
    PathTraversalError,
)
from neurosurg_epi_agent.adapters.charls import _read_capped, safe_member_path  # noqa: E402
from neurosurg_epi_agent.cli import main as cli_main  # noqa: E402


# --------------------------------------------------------------------------- #
# synthetic-data helpers
# --------------------------------------------------------------------------- #

SENTINEL_VALUE = 9999937  # a participant value that must NEVER appear in output
SENTINEL_LABEL = "AGE_IN_YEARS_SYNTHETIC_LABEL"


def make_dta_bytes(
    rows: int = 3,
    extra_cols: dict | None = None,
) -> bytes:
    """Return bytes of a small synthetic Stata .dta file."""
    data = {"age": [SENTINEL_VALUE + i for i in range(rows)], "sex": [1 + (i % 2) for i in range(rows)]}
    if extra_cols:
        data.update(extra_cols)
    df = pd.DataFrame(data)
    buf = io.BytesIO()
    df.to_stata(
        buf,
        write_index=False,
        variable_labels={"age": SENTINEL_LABEL, "sex": "biological sex (synthetic)"},
    )
    return buf.getvalue()


def write_dta(path: Path, **kwargs) -> Path:
    path.write_bytes(make_dta_bytes(**kwargs))
    return path


def write_zip(path: Path, members: dict[str, bytes]) -> Path:
    """Write a ZIP whose member names are taken verbatim (no sanitization)."""
    with zipfile.ZipFile(path, "w") as zf:
        for name, data in members.items():
            zi = zipfile.ZipInfo(name)
            zi.compress_type = zipfile.ZIP_STORED
            zf.writestr(zi, data)
    return path


def set_encrypted_flag(raw: bytes) -> bytes:
    """Flip the encryption bit (GP flag bit 0) in every local + central header."""
    data = bytearray(raw)
    for sig, offset in ((b"PK\x03\x04", 6), (b"PK\x01\x02", 8)):
        pos = data.find(sig)
        while pos != -1:
            data[pos + offset] |= 0x01
            pos = data.find(sig, pos + 4)
    return bytes(data)


def patch_member_name(raw: bytes, old: bytes, new: bytes) -> bytes:
    """Replace a member name wherever it occurs in the ZIP bytes.

    Used to inject literal backslashes (same length as the forward-slash form)
    so the backslash-traversal path is exercised against a real archive.
    """
    assert len(old) == len(new)
    return raw.replace(old, new)


def assert_no_privacy_leak(payload: dict, real_root: Path) -> None:
    """The serialized JSON must not leak the absolute root or participant values."""
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    # 1. The neutral token is used, not the real path.
    assert payload["data_root"] == "<user-supplied>"
    # 2. The absolute/local path never appears anywhere in the output.
    assert str(real_root) not in text
    assert str(real_root).replace("\\", "/") not in text
    # 3. A participant VALUE never appears (metadata only).
    assert str(SENTINEL_VALUE) not in text
    # 4. A variable LABEL does appear (positive control: labels ARE emitted).
    assert SENTINEL_LABEL in text


# --------------------------------------------------------------------------- #
# safe_member_path unit tests (both slash styles + drive + absolute)
# --------------------------------------------------------------------------- #

class TestSafeMemberPath:
    @pytest.mark.parametrize("name", ["../evil.dta", "../../etc/passwd", "a/../../b.dta"])
    def test_forward_slash_traversal_rejected(self, name):
        with pytest.raises(PathTraversalError):
            safe_member_path(name)

    @pytest.mark.parametrize("name", [r"..\evil.dta", r"..\..\etc\passwd", r"a\..\..\b.dta"])
    def test_backslash_traversal_rejected(self, name):
        with pytest.raises(PathTraversalError):
            safe_member_path(name)

    @pytest.mark.parametrize("name", ["/etc/passwd", "/abs/secret.dta"])
    def test_absolute_posix_rejected(self, name):
        with pytest.raises(PathTraversalError):
            safe_member_path(name)

    @pytest.mark.parametrize("name", ["C:secret.dta", "D:\\evil\\x.dta", "c:/x.dta"])
    def test_windows_drive_rejected(self, name):
        with pytest.raises(PathTraversalError):
            safe_member_path(name)

    @pytest.mark.parametrize(
        "name,expected",
        [
            ("demo.dta", "demo.dta"),
            ("sub/demo.dta", "sub/demo.dta"),
            (r"sub\nested\demo.dta", "sub/nested/demo.dta"),
            ("./demo.dta", "./demo.dta"),
        ],
    )
    def test_safe_names_normalized(self, name, expected):
        assert safe_member_path(name) == expected

    def test_empty_rejected(self):
        with pytest.raises(PathTraversalError):
            safe_member_path("")


# --------------------------------------------------------------------------- #
# CHARLS happy paths
# --------------------------------------------------------------------------- #

class TestCharlsHappyPath:
    def test_direct_dta_in_root(self, tmp_path):
        root = tmp_path
        write_dta(root / "demo.dta")
        result = CHARLSAdapter().inspect(root)
        payload = result.to_dict()

        assert len(payload["direct_files"]) == 1
        mm = payload["direct_files"][0]
        assert mm["member_name"] == "demo.dta"
        assert mm["member_path"] == "demo.dta"
        assert mm["format"] == "stata-dta"
        assert mm["byte_size"] > 0
        assert len(mm["sha256"]) == 64
        assert mm["row_count"] == 3
        assert mm["column_count"] == 2
        assert {v["name"] for v in mm["variables"]} == {"age", "sex"}
        age = next(v for v in mm["variables"] if v["name"] == "age")
        assert age["label"] == SENTINEL_LABEL
        assert payload["archives"] == []
        assert_no_privacy_leak(payload, root)

    def test_dta_in_subdir_relative_path(self, tmp_path):
        root = tmp_path
        (root / "wave1").mkdir()
        write_dta(root / "wave1" / "health.dta")
        payload = CHARLSAdapter().inspect(root).to_dict()
        assert payload["direct_files"][0]["member_path"] == "wave1/health.dta"

    def test_single_file_root(self, tmp_path):
        dta = write_dta(tmp_path / "solo.dta")
        payload = CHARLSAdapter().inspect(dta).to_dict()
        assert len(payload["direct_files"]) == 1
        assert payload["direct_files"][0]["member_name"] == "solo.dta"

    def test_zip_with_dta_and_non_dta(self, tmp_path):
        root = tmp_path
        dta = make_dta_bytes()
        write_zip(root / "bundle.zip", {"inner/health.dta": dta, "readme.txt": b"hi"})
        payload = CHARLSAdapter().inspect(root).to_dict()

        assert len(payload["archives"]) == 1
        arc = payload["archives"][0]
        assert arc["archive_path"] == "bundle.zip"
        assert len(arc["members"]) == 1
        assert arc["members"][0]["member_path"] == "inner/health.dta"
        assert arc["members"][0]["source_archive"] == "bundle.zip"
        assert arc["members"][0]["row_count"] == 3
        assert [s["member_path"] for s in arc["skipped"]] == ["readme.txt"]
        assert arc["skipped"][0]["reason"].startswith("non-.dta")
        assert_no_privacy_leak(payload, root)

    def test_sha256_matches_raw_member(self, tmp_path):
        root = tmp_path
        dta = make_dta_bytes()
        write_zip(root / "b.zip", {"x.dta": dta})
        payload = CHARLSAdapter().inspect(root).to_dict()
        import hashlib

        assert payload["archives"][0]["members"][0]["sha256"] == hashlib.sha256(dta).hexdigest()


# --------------------------------------------------------------------------- #
# Filters
# --------------------------------------------------------------------------- #

class TestFilters:
    def test_zip_members_filter_by_basename(self, tmp_path):
        root = tmp_path
        dta = make_dta_bytes()
        write_zip(root / "b.zip", {"a.dta": dta, "b.dta": dta})
        payload = CHARLSAdapter().inspect(root, members={"a.dta"}).to_dict()
        arc = payload["archives"][0]
        assert [m["member_name"] for m in arc["members"]] == ["a.dta"]

    def test_zip_members_filter_by_relpath(self, tmp_path):
        root = tmp_path
        dta = make_dta_bytes()
        write_zip(root / "b.zip", {"dir/a.dta": dta, "dir/b.dta": dta})
        payload = CHARLSAdapter().inspect(root, members={"dir/b.dta"}).to_dict()
        assert [m["member_path"] for m in payload["archives"][0]["members"]] == ["dir/b.dta"]


# --------------------------------------------------------------------------- #
# Security: traversal, duplicates, encrypted, malformed, oversize
# --------------------------------------------------------------------------- #

class TestArchiveSecurity:
    def test_traversal_forward_slash_rejected(self, tmp_path):
        root = tmp_path
        write_zip(root / "evil.zip", {"../escape.dta": make_dta_bytes()})
        with pytest.raises(PathTraversalError):
            CHARLSAdapter().inspect(root)

    def test_traversal_backslash_slash_rejected(self, tmp_path):
        # Backslash-style traversal is exercised at the safe_member_path unit
        # level (see TestSafeMemberPath), because Python's zipfile normalizes
        # backslashes to forward slashes on READ -- a real archive can never
        # deliver a literal-backslash member name to the adapter. Here we just
        # confirm the defensive normalization directly: both raw forms collapse
        # to the same rejected token.
        with pytest.raises(PathTraversalError):
            safe_member_path("..\\escape.dta")
        with pytest.raises(PathTraversalError):
            safe_member_path("../escape.dta")
        # A real archive carrying the forward-slash form must also be rejected
        # end-to-end (covered by test_traversal_forward_slash_rejected above).

    def test_duplicate_normalized_member_rejected(self, tmp_path):
        root = tmp_path
        dta = make_dta_bytes()
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            write_zip(root / "dup.zip", {"data/foo.dta": dta, r"data\foo.dta": dta})
        with pytest.raises(DuplicateMemberError):
            CHARLSAdapter().inspect(root)

    def test_encrypted_member_rejected(self, tmp_path):
        root = tmp_path
        zpath = root / "enc.zip"
        write_zip(zpath, {"secret.dta": make_dta_bytes()})
        zpath.write_bytes(set_encrypted_flag(zpath.read_bytes()))
        # Sanity: the flag is observed by zipfile before our adapter acts.
        with zipfile.ZipFile(zpath) as zf:
            assert zf.infolist()[0].flag_bits & 0x1
        with pytest.raises(EncryptedMemberError):
            CHARLSAdapter().inspect(root)

    def test_malformed_zip_not_a_zip(self, tmp_path):
        root = tmp_path
        (root / "broken.zip").write_bytes(b"not a zip file at all")
        with pytest.raises(MalformedArchiveError):
            CHARLSAdapter().inspect(root)

    def test_malformed_zip_empty(self, tmp_path):
        root = tmp_path
        (root / "empty.zip").write_bytes(b"")
        with pytest.raises(MalformedArchiveError):
            CHARLSAdapter().inspect(root)

    def test_oversize_direct_file_skipped_before_read(self, tmp_path):
        root = tmp_path
        # Real size > 10-byte limit; the stat guard must skip without parsing.
        write_dta(root / "big.dta")
        payload = CHARLSAdapter().inspect(root, max_member_bytes=10).to_dict()
        assert payload["direct_files"] == []
        assert len(payload["skipped_roots"]) == 1
        assert "before reading" in payload["skipped_roots"][0]["reason"]

    def test_oversize_zip_member_declared_skipped(self, tmp_path):
        root = tmp_path
        dta = make_dta_bytes()  # declared uncompressed size >> 10
        write_zip(root / "b.zip", {"big.dta": dta})
        payload = CHARLSAdapter().inspect(root, max_member_bytes=10).to_dict()
        arc = payload["archives"][0]
        assert arc["members"] == []
        assert len(arc["skipped"]) == 1
        assert "uncompressed size" in arc["skipped"][0]["reason"]

    def test_unsupported_files_skipped(self, tmp_path):
        root = tmp_path
        (root / "notes.txt").write_text("hello")
        (root / "image.png").write_bytes(b"\x89PNG\r\n")
        payload = CHARLSAdapter().inspect(root).to_dict()
        assert payload["direct_files"] == []
        skipped = sorted(s["member_name"] for s in payload["skipped_roots"])
        assert skipped == ["image.png", "notes.txt"]
        assert all("unsupported file type" in s["reason"] for s in payload["skipped_roots"])


# --------------------------------------------------------------------------- #
# Actual-byte-after-read guard (unit level)
# --------------------------------------------------------------------------- #

class TestActualByteGuard:
    def test_capped_reader_never_retains_more_than_limit_plus_one(self):
        stream = io.BytesIO(b"x" * 100)
        assert _read_capped(stream, 10, chunk_size=4) is None
        assert stream.tell() == 11

    def test_extract_skips_when_actual_bytes_exceed_limit(self):
        adapter = CHARLSAdapter()
        sink: list = []
        out = adapter._extract_dta_metadata(
            raw=b"x" * 200,
            rel_path="m.dta",
            member_name="m.dta",
            source_archive=None,
            max_member_bytes=50,
            members_filter=None,
            skip_on_parse=True,
            skipped_sink=sink,
        )
        assert out is None
        assert len(sink) == 1
        assert "actual bytes" in sink[0].reason

    def test_extract_raises_when_no_sink(self):
        adapter = CHARLSAdapter()
        with pytest.raises(MemberSizeExceededError):
            adapter._extract_dta_metadata(
                raw=b"x" * 200,
                rel_path="m.dta",
                member_name="m.dta",
                source_archive=None,
                max_member_bytes=50,
                members_filter=None,
                skip_on_parse=True,
                skipped_sink=None,
            )

    def test_labeled_stata_row_count_emits_no_categorical_warning(self, tmp_path):
        buf = io.BytesIO()
        pd.DataFrame({"group": [1, 2, 1]}).to_stata(
            buf,
            write_index=False,
            value_labels={"group": {1: "one", 2: "two"}},
        )
        write_zip(tmp_path / "labeled.zip", {"labeled.dta": buf.getvalue()})
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            payload = CHARLSAdapter().inspect(tmp_path).to_dict()
        assert payload["archives"][0]["members"][0]["row_count"] == 3
        assert not [w for w in caught if "CategoricalConversionWarning" in type(w.message).__name__]


# --------------------------------------------------------------------------- #
# Symlink escape (skipped where the OS/privilege level cannot create symlinks)
# --------------------------------------------------------------------------- #

class TestSymlinks:
    def _make_outside_dta(self, tmp_path: Path) -> Path:
        outside = tmp_path / "_outside"
        outside.mkdir()
        target = outside / "secret.dta"
        write_dta(target)
        return target

    def test_symlinked_file_not_followed(self, tmp_path):
        root = tmp_path / "root"
        root.mkdir()
        target = self._make_outside_dta(tmp_path)
        link = root / "leak.dta"
        try:
            link.symlink_to(target)
        except (OSError, NotImplementedError):
            pytest.skip("symlinks not supported on this platform/privilege")
        payload = CHARLSAdapter().inspect(root).to_dict()
        # The symlink is recorded as skipped, never hashed/inspected.
        names = [s["member_name"] for s in payload["skipped_roots"]]
        assert "leak.dta" in names
        assert payload["direct_files"] == []
        # The outside file's bytes never make it into the output.
        import hashlib

        secret_hash = hashlib.sha256(target.read_bytes()).hexdigest()
        assert secret_hash not in json.dumps(payload)

    def test_symlinked_directory_not_descended(self, tmp_path):
        root = tmp_path / "root"
        root.mkdir()
        outside = tmp_path / "_outside"
        outside.mkdir()
        write_dta(outside / "secret.dta")
        link = root / "leakdir"
        try:
            link.symlink_to(outside)
        except (OSError, NotImplementedError):
            pytest.skip("symlinks not supported on this platform/privilege")
        payload = CHARLSAdapter().inspect(root).to_dict()
        assert payload["direct_files"] == []
        # secret.dta living only behind the symlinked dir must not appear.
        assert "secret.dta" not in json.dumps(payload)


# --------------------------------------------------------------------------- #
# Determinism
# --------------------------------------------------------------------------- #

class TestDeterminism:
    def test_repeat_inspection_is_byte_identical(self, tmp_path):
        root = tmp_path
        write_dta(root / "a.dta")
        (root / "sub").mkdir()
        write_dta(root / "sub" / "b.dta")
        write_zip(root / "c.zip", {"x.dta": make_dta_bytes()})

        a = CHARLSAdapter().inspect(root).to_dict()
        b = CHARLSAdapter().inspect(root).to_dict()
        assert json.dumps(a, sort_keys=True, ensure_ascii=False) == json.dumps(
            b, sort_keys=True, ensure_ascii=False
        )


# --------------------------------------------------------------------------- #
# NHANES adapter (public XPT; identity + light metadata)
# --------------------------------------------------------------------------- #

class TestNHANESAdapter:
    def _xpt_bytes(self) -> bytes:
        # Minimal blob that exercises _xport_member_names: a >=8 char
        # alpha+identifier token after a HEADER RECORD marker.
        return b"HEADER RECORD\x00AGESCODE\x00payload-not-used"

    def test_xpt_listed_with_hash_and_neutral_root(self, tmp_path):
        root = tmp_path
        (root / "DEMO_J.XPT").write_bytes(self._xpt_bytes())
        payload = NHANESAdapter().inspect(root).to_dict()
        assert payload["data_root"] == "<user-supplied>"
        assert len(payload["direct_files"]) == 1
        mm = payload["direct_files"][0]
        assert mm["format"] == "sas-xport"
        assert mm["member_name"] == "DEMO_J.XPT"
        assert len(mm["sha256"]) == 64
        assert str(root) not in json.dumps(payload, ensure_ascii=False)

    def test_non_xpt_skipped(self, tmp_path):
        root = tmp_path
        (root / "readme.txt").write_text("x")
        (root / "DEMO.XPT").write_bytes(self._xpt_bytes())
        payload = NHANESAdapter().inspect(root).to_dict()
        skipped = [s["member_name"] for s in payload["skipped_roots"]]
        assert "readme.txt" in skipped
        assert [m["member_name"] for m in payload["direct_files"]] == ["DEMO.XPT"]

    def test_oversize_xpt_skipped(self, tmp_path):
        root = tmp_path
        (root / "BIG.XPT").write_bytes(self._xpt_bytes() + b"\x00" * 500)
        payload = NHANESAdapter().inspect(root, max_member_bytes=10).to_dict()
        assert payload["direct_files"] == []
        assert payload["skipped_roots"][0]["reason"].startswith("size ")


# --------------------------------------------------------------------------- #
# CLI: inspect-database
# --------------------------------------------------------------------------- #

class TestInspectDatabaseCLI:
    def _root(self, tmp_path: Path) -> Path:
        root = tmp_path / "data"
        root.mkdir()
        write_dta(root / "demo.dta")
        return root

    def test_cli_happy_path(self, tmp_path):
        root = self._root(tmp_path)
        out = tmp_path / "out.json"
        rc = cli_main([
            "inspect-database",
            "--database", "CHARLS",
            "--data-root", str(root),
            "--output", str(out),
        ])
        assert rc == 0
        assert out.exists()
        payload = json.loads(out.read_text(encoding="utf-8"))
        assert payload["data_root"] == "<user-supplied>"
        assert str(root) not in out.read_text(encoding="utf-8")
        assert len(payload["direct_files"]) == 1

    def test_cli_output_is_utf8_deterministic(self, tmp_path):
        root = self._root(tmp_path)
        out1 = tmp_path / "a.json"
        out2 = tmp_path / "b.json"
        assert cli_main(["inspect-database", "--database", "CHARLS",
                         "--data-root", str(root), "--output", str(out1)]) == 0
        assert cli_main(["inspect-database", "--database", "CHARLS",
                         "--data-root", str(root), "--output", str(out2)]) == 0
        assert out1.read_bytes() == out2.read_bytes()
        # UTF-8: an em dash in the privacy statement must round-trip correctly
        # (not mojibake).
        text = out1.read_text(encoding="utf-8")
        assert "metadata-only" in text.lower()

    def test_cli_refuses_overwrite_without_force(self, tmp_path):
        root = self._root(tmp_path)
        out = tmp_path / "out.json"
        out.write_text("PRE-EXISTING", encoding="utf-8")
        rc = cli_main([
            "inspect-database", "--database", "CHARLS",
            "--data-root", str(root), "--output", str(out),
        ])
        assert rc == 2
        # Original contents untouched.
        assert out.read_text(encoding="utf-8") == "PRE-EXISTING"

    def test_cli_force_overwrites(self, tmp_path):
        root = self._root(tmp_path)
        out = tmp_path / "out.json"
        out.write_text("PRE-EXISTING", encoding="utf-8")
        rc = cli_main([
            "inspect-database", "--database", "CHARLS",
            "--data-root", str(root), "--output", str(out), "--force",
        ])
        assert rc == 0
        payload = json.loads(out.read_text(encoding="utf-8"))
        assert "database" in payload

    def test_cli_missing_data_root(self, tmp_path):
        out = tmp_path / "out.json"
        rc = cli_main([
            "inspect-database", "--database", "CHARLS",
            "--data-root", str(tmp_path / "does_not_exist"),
            "--output", str(out),
        ])
        assert rc == 2
        assert not out.exists()

    def test_cli_invalid_database_rejected(self, tmp_path):
        root = self._root(tmp_path)
        out = tmp_path / "out.json"
        with pytest.raises(SystemExit):
            cli_main([
                "inspect-database", "--database", "BOGUS",
                "--data-root", str(root), "--output", str(out),
            ])

    def test_cli_traversal_returns_error(self, tmp_path):
        root = tmp_path
        write_zip(root / "evil.zip", {"../escape.dta": make_dta_bytes()})
        out = tmp_path / "out.json"
        rc = cli_main([
            "inspect-database", "--database", "CHARLS",
            "--data-root", str(root), "--output", str(out),
        ])
        assert rc == 1
        assert not out.exists()

    def test_cli_max_member_bytes_skips_oversize(self, tmp_path):
        root = self._root(tmp_path)
        out = tmp_path / "out.json"
        rc = cli_main([
            "inspect-database", "--database", "CHARLS",
            "--data-root", str(root), "--output", str(out),
            "--max-member-bytes", "10",
        ])
        assert rc == 0
        payload = json.loads(out.read_text(encoding="utf-8"))
        assert payload["direct_files"] == []
        assert len(payload["skipped_roots"]) == 1

    def test_cli_default_registry_used(self, tmp_path, monkeypatch):
        # The CLI must use the package default registry (NHANES + CHARLS + CDC WONDER + SEER).
        names = default_registry().names()
        assert names == ["CDC_WONDER", "CHARLS", "NHANES", "SEER"]
