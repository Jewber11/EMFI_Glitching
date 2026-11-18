"""Tests for objdump output parsing."""

import pytest


@pytest.mark.skip(reason="disassembler not yet implemented")
def test_parse_function_header():
    raise NotImplementedError


@pytest.mark.skip(reason="disassembler not yet implemented")
def test_parse_instruction_line():
    raise NotImplementedError


@pytest.mark.skip(reason="disassembler not yet implemented")
def test_parse_with_source_interleaved():
    """objdump -S interleaves C source — parser must keep instructions only."""
    raise NotImplementedError
