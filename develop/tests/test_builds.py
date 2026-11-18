"""Tests for build subprocess pipeline."""

import pytest


@pytest.mark.skip(reason="build pipeline not yet implemented")
def test_build_sha_deterministic():
    """Same source + same toolchain → same SHA."""
    raise NotImplementedError


@pytest.mark.skip(reason="build pipeline not yet implemented")
def test_c_build_produces_elf_bin_lst():
    raise NotImplementedError


@pytest.mark.skip(reason="build pipeline not yet implemented")
def test_failed_build_returns_log_tail():
    raise NotImplementedError
