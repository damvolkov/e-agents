"""Tests for the agnostic module scanner."""

from __future__ import annotations

import dataclasses
import inspect
from pathlib import Path

import pytest

from e_agents.shared.helpers.scan import Scanner, ScanResult

##### SCAN RESULT MODEL #####


async def test_scan_result_is_frozen_dataclass() -> None:
    result = ScanResult()
    assert dataclasses.is_dataclass(result)
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.classes = {}  # type: ignore[misc]


##### CLASS DISCOVERY #####


async def test_scan_discovers_subclasses(scanner: Scanner, fake_pkg: Path, gadget_base: type) -> None:
    result = await scanner.scan(fake_pkg, bases=(gadget_base,))

    assert set(result.classes) == {"Phone", "Tablet", "Thermometer", "Barometer"}
    for cls in result.classes.values():
        assert isinstance(cls, type)


async def test_scan_excludes_base_itself(scanner: Scanner, fake_pkg: Path, gadget_base: type) -> None:
    result = await scanner.scan(fake_pkg, bases=(gadget_base,))

    assert "Gadget" not in result.classes


async def test_scan_excludes_private_classes(scanner: Scanner, fake_pkg: Path, gadget_base: type) -> None:
    result = await scanner.scan(fake_pkg, bases=(gadget_base,))

    assert "_SecretGadget" not in result.classes


async def test_scan_traverses_nested_directories(scanner: Scanner, fake_pkg: Path, gadget_base: type) -> None:
    result = await scanner.scan(fake_pkg, bases=(gadget_base,))

    assert "Thermometer" in result.classes
    assert "Barometer" in result.classes


##### INSTANCE DISCOVERY #####


async def test_scan_discovers_instances(scanner: Scanner, fake_pkg: Path, wrapper_base: type) -> None:
    result = await scanner.scan(fake_pkg, bases=(wrapper_base,))

    assert set(result.functions) == {"tool_search", "tool_fetch"}
    for fn in result.functions.values():
        assert isinstance(fn, wrapper_base)


async def test_scan_excludes_private_instances(scanner: Scanner, fake_pkg: Path, wrapper_base: type) -> None:
    result = await scanner.scan(fake_pkg, bases=(wrapper_base,))

    assert "_private_tool" not in result.functions


##### MULTIPLE BASES #####


async def test_scan_multiple_bases(
    scanner: Scanner, fake_pkg: Path, gadget_base: type, wrapper_base: type,
) -> None:
    result = await scanner.scan(fake_pkg, bases=(gadget_base, wrapper_base))

    assert set(result.classes) == {"Phone", "Tablet", "Thermometer", "Barometer"}
    assert set(result.functions) == {"tool_search", "tool_fetch"}


##### NAME FILTER #####


@pytest.mark.parametrize(
    "name_filter, expected",
    [
        (["search"], {"tool_search"}),
        (["fetch"], {"tool_fetch"}),
        (["tool"], {"tool_search", "tool_fetch"}),
        (["nonexistent"], set()),
    ],
    ids=["search-only", "fetch-only", "both-tools", "no-match"],
)
async def test_scan_func_filter_name(
    scanner: Scanner,
    fake_pkg: Path,
    wrapper_base: type,
    name_filter: list[str],
    expected: set[str],
) -> None:
    result = await scanner.scan(fake_pkg, bases=(wrapper_base,), func_filter_name=name_filter)

    assert set(result.functions) == expected


##### KWARGS FILTER #####


@pytest.mark.parametrize(
    "kwargs_filter, expected",
    [
        (["query"], {"tool_search"}),
        (["url"], {"tool_fetch"}),
        (["limit", "timeout"], {"tool_search", "tool_fetch"}),
        (["nonexistent"], set()),
    ],
    ids=["query-param", "url-param", "limit-or-timeout", "no-match"],
)
async def test_scan_func_filter_kwargs(
    scanner: Scanner,
    fake_pkg: Path,
    wrapper_base: type,
    kwargs_filter: list[str],
    expected: set[str],
) -> None:
    result = await scanner.scan(fake_pkg, bases=(wrapper_base,), func_filter_kwargs=kwargs_filter)

    assert set(result.functions) == expected


##### COMBINED FILTERS #####


async def test_scan_combined_filters_are_and(scanner: Scanner, fake_pkg: Path, wrapper_base: type) -> None:
    result = await scanner.scan(
        fake_pkg,
        bases=(wrapper_base,),
        func_filter_name=["tool"],
        func_filter_kwargs=["query"],
    )

    assert set(result.functions) == {"tool_search"}


async def test_scan_combined_filters_no_overlap(scanner: Scanner, fake_pkg: Path, wrapper_base: type) -> None:
    result = await scanner.scan(
        fake_pkg,
        bases=(wrapper_base,),
        func_filter_name=["search"],
        func_filter_kwargs=["url"],
    )

    assert not result.functions


##### EDGE CASES #####


async def test_scan_empty_directory(scanner: Scanner, tmp_path: Path) -> None:
    empty = tmp_path / "empty_dir"
    empty.mkdir()
    result = await scanner.scan(empty, bases=(int,))

    assert not result.classes
    assert not result.functions


async def test_scan_no_matching_members(scanner: Scanner, fake_pkg: Path) -> None:
    class Alien:
        pass

    result = await scanner.scan(fake_pkg, bases=(Alien,))

    assert not result.classes
    assert not result.functions


async def test_scan_nonexistent_directory_raises(scanner: Scanner, tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        await scanner.scan(tmp_path / "ghost", bases=(int,))


async def test_scan_excludes_out_of_scope_imports(
    scanner: Scanner, fake_pkg: Path, gadget_base: type, wrapper_base: type,
) -> None:
    """Imported symbols from outside the scan scope must not leak into results."""
    result = await scanner.scan(fake_pkg, bases=(gadget_base, wrapper_base))

    all_names = set(result.classes) | set(result.functions)
    for name in all_names:
        obj = result.classes.get(name) or result.functions.get(name)
        obj_mod = getattr(obj, "__module__", "")
        assert obj_mod.startswith("scantest_pkg"), f"{name} leaked from {obj_mod}"


##### REAL APP — LIVEKIT FUNCTION TOOLS #####


async def test_scan_real_tools_discovers_function_tools(
    scanner: Scanner, real_tools_dir: Path, function_tool_cls: type,
) -> None:
    result = await scanner.scan(real_tools_dir, bases=(function_tool_cls,))

    if not result.functions:
        pytest.skip("tools modules could not be imported (missing env?)")

    expected = {"web_search"}
    assert result.functions.keys() == expected
    assert all(isinstance(v, function_tool_cls) for v in result.functions.values())
    assert not result.classes


async def test_scan_real_tools_with_name_filter(
    scanner: Scanner, real_tools_dir: Path, function_tool_cls: type,
) -> None:
    result = await scanner.scan(real_tools_dir, bases=(function_tool_cls,), func_filter_name=["web"])

    if not result.functions:
        pytest.skip("tools modules could not be imported (missing env?)")

    assert set(result.functions) == {"web_search"}


async def test_scan_real_tools_with_kwargs_filter(
    scanner: Scanner, real_tools_dir: Path, function_tool_cls: type,
) -> None:
    result = await scanner.scan(real_tools_dir, bases=(function_tool_cls,), func_filter_kwargs=["query"])

    if not result.functions:
        pytest.skip("tools modules could not be imported (missing env?)")

    assert all(
        "query" in inspect.signature(getattr(v, "__wrapped__", v)).parameters
        for v in result.functions.values()
    )
