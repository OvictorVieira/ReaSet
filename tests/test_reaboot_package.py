#!/usr/bin/env python3
"""Contract tests for ReaSet's ReaPack index and ReaBoot recipe."""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "index.xml"
RECIPE = ROOT / "reaboot.json"
REPO_INDEX_URL = "https://raw.githubusercontent.com/djenttleman/ReaSet/main/index.xml"


def packages(root: ET.Element) -> dict[tuple[str, str], ET.Element]:
    return {
        (category.attrib["name"], package.attrib["name"]): package
        for category in root.findall("category")
        for package in category.findall("reapack")
    }


def test_core_package_installs_script_and_web_interface_from_immutable_tag():
    root = ET.parse(INDEX).getroot()
    core = packages(root)[("ReaSet", "ReaSet")]
    assert core.attrib["type"] == "webinterface"

    version = core.find("version[@name='2.2']")
    assert version is not None
    sources = {source.attrib["file"]: source for source in version.findall("source")}
    assert set(sources) == {"Reaset.lua", "ReaSet.html", "Sortable.min.js"}
    assert sources["Reaset.lua"].attrib == {
        "file": "Reaset.lua",
        "type": "script",
        "main": "main",
    }
    assert "refs/tags/v2.2/" in (sources["Reaset.lua"].text or "")
    assert sources["ReaSet.html"].attrib.get("type", "webinterface") == "webinterface"
    assert sources["Sortable.min.js"].attrib.get("type", "webinterface") == "webinterface"


def test_tools_are_optional_separate_package_and_scripts_are_registered():
    root = ET.parse(INDEX).getroot()
    tools = packages(root)[("ReaSet", "ReaSet Tools")]
    assert tools.attrib["type"] == "script"
    version = tools.find("version[@name='2.2']")
    assert version is not None
    sources = version.findall("source")
    assert {source.attrib["file"] for source in sources} == {
        "Lyrics_Tapper.lua",
        "ReaSet_Diagnose.lua",
    }
    assert all(source.attrib.get("main") == "main" for source in sources)
    assert all("refs/tags/v2.2/" in (source.text or "") for source in sources)


def test_every_source_is_reachable_and_avoids_reaboot_1_2_hash_bug():
    root = ET.parse(INDEX).getroot()
    for source in root.findall("./category/reapack/version/source"):
        # ReaBoot 1.2.0 consumes each download chunk before hashing it, so any
        # legitimate ReaPack multihash is compared with SHA-256(empty) and the
        # install is rejected. Keep immutable tag URLs and omit hash until a
        # fixed ReaBoot release is the public installer.
        assert "hash" not in source.attrib
        url = (source.text or "").strip()
        assert url.startswith("https://raw.githubusercontent.com/")
        with urllib.request.urlopen(url, timeout=30) as response:
            assert response.status == 200
            assert response.read()


def test_reaboot_recipe_requires_core_and_exposes_expected_features():
    recipe = json.loads(RECIPE.read_text())
    assert recipe["name"] == "ReaSet"
    assert recipe["website"] == "https://github.com/djenttleman/ReaSet"
    assert recipe["skip_additional_packages"] is True
    assert recipe["required_packages"] == [
        f"{REPO_INDEX_URL}#p=ReaSet/ReaSet&v=latest"
    ]

    features = recipe["features"]
    assert set(features) == {"tools", "sws"}
    assert features["tools"]["packages"][0] == (
        f"{REPO_INDEX_URL}#p={urllib.parse.quote('ReaSet/ReaSet Tools')}&v=latest"
    )
    # Lyrics Tapper is part of Tools, so ReaImGui must be selected atomically
    # with that feature rather than exposed as an independent checkbox.
    assert "reaper_imgui.ext" in features["tools"]["packages"][1]
    assert features["sws"]["default"] is True
    assert "ReaTeam/Extensions" in features["sws"]["packages"][0]


def test_readme_contains_reaboot_recipe_install_link():
    readme = (ROOT / "README.md").read_text()
    encoded_recipe_url = urllib.parse.quote(
        "https://raw.githubusercontent.com/djenttleman/ReaSet/main/reaboot.json",
        safe="",
    )
    expected = f"https://www.reaboot.com/install/{encoded_recipe_url}"
    assert expected in readme
