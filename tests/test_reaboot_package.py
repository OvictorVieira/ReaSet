#!/usr/bin/env python3
"""Contract tests for ReaSet's ReaPack index and ReaBoot recipe."""

from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "index.xml"
RECIPE = ROOT / "reaboot.json"
REPO_INDEX_URL = "https://raw.githubusercontent.com/djenttleman/ReaSet/main/index.xml"
RELEASE_VERSION = "3.0"
RELEASE_COMMIT = "dea2bbda162a16750ca65bcb82ad684f84079629"


def packages(root: ET.Element) -> dict[tuple[str, str], ET.Element]:
    return {
        (category.attrib["name"], package.attrib["name"]): package
        for category in root.findall("category")
        for package in category.findall("reapack")
    }


def test_core_package_installs_current_release_from_immutable_commit():
    root = ET.parse(INDEX).getroot()
    core = packages(root)[("ReaSet", "ReaSet")]
    assert core.attrib["type"] == "webinterface"

    version = core.find(f"version[@name='{RELEASE_VERSION}']")
    assert version is not None
    sources = {source.attrib["file"]: source for source in version.findall("source")}
    assert set(sources) == {"Reaset.lua", "ReaSet.html", "Sortable.min.js"}
    assert sources["Reaset.lua"].attrib == {
        "file": "Reaset.lua",
        "type": "script",
        "main": "main",
    }
    assert all(
        f"/{RELEASE_COMMIT}/" in (source.text or "")
        for source in sources.values()
    )
    assert sources["ReaSet.html"].attrib.get("type", "webinterface") == "webinterface"
    assert sources["Sortable.min.js"].attrib.get("type", "webinterface") == "webinterface"


def test_tools_are_optional_separate_package_and_scripts_are_registered():
    root = ET.parse(INDEX).getroot()
    tools = packages(root)[("ReaSet", "ReaSet Tools")]
    assert tools.attrib["type"] == "script"
    version = tools.find(f"version[@name='{RELEASE_VERSION}']")
    assert version is not None
    sources = version.findall("source")
    assert {source.attrib["file"] for source in sources} == {
        "Lyrics_Tapper.lua",
        "ReaSet_Diagnose.lua",
        "ReaSet_LibraryDoctor.lua",
        "Text to MIDI Bitmap.lua",
    }
    assert all(source.attrib.get("main") == "main" for source in sources)
    assert all(f"/{RELEASE_COMMIT}/Tools/" in (source.text or "") for source in sources)


def test_every_source_is_reachable_and_avoids_reaboot_1_2_hash_bug():
    root = ET.parse(INDEX).getroot()
    for source in root.findall("./category/reapack/version/source"):
        # ReaBoot 1.2.0 consumes each download chunk before hashing it, so any
        # legitimate ReaPack multihash is compared with SHA-256(empty) and the
        # install is rejected. Keep full-commit URLs and omit hash until a
        # fixed ReaBoot release is the public installer. A full commit SHA is
        # immutable, unlike a tag reference that can be moved.
        assert "hash" not in source.attrib
        url = (source.text or "").strip()
        match = re.match(
            r"^https://raw\.githubusercontent\.com/djenttleman/ReaSet/([0-9a-f]{40})/",
            url,
        )
        assert match, f"source is not pinned to a full commit SHA: {url}"
        with urllib.request.urlopen(url, timeout=30) as response:
            assert response.status == 200
            assert response.read()


def test_reapack_destination_contract_matches_documentation():
    root = ET.parse(INDEX).getroot()
    index_name = root.attrib["name"]
    core = packages(root)[("ReaSet", "ReaSet")]
    version = core.find(f"version[@name='{RELEASE_VERSION}']")
    assert version is not None

    destinations = set()
    for source in version.findall("source"):
        package_type = source.attrib.get("type", core.attrib["type"])
        file_name = source.attrib["file"]
        if package_type == "script":
            destinations.add(f"Scripts/{index_name}/ReaSet/{file_name}")
        elif package_type == "webinterface":
            destinations.add(f"reaper_www_root/{file_name}")

    assert destinations == {
        "Scripts/ReaSet/ReaSet/Reaset.lua",
        "reaper_www_root/ReaSet.html",
        "reaper_www_root/Sortable.min.js",
    }


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


def test_readme_header_contains_logo_and_graphical_reaboot_button():
    readme = (ROOT / "README.md").read_text()
    install_url = (
        "https://www.reaboot.com/install/"
        "https%3A%2F%2Fraw.githubusercontent.com%2Fdjenttleman%2FReaSet%2F"
        "main%2Freaboot.json"
    )
    header = readme.split("##### 🇬🇧 ENGLISH", 1)[0]

    assert '<img src="assets/reaset-logo.png" alt="ReaSet" width="560">' in header
    assert f'<a href="{install_url}">' in header
    assert (
        '<img src="assets/install-via-reaboot.svg" '
        'alt="Install via ReaBoot" height="52">'
    ) in header

    logo = ROOT / "assets/reaset-logo.png"
    button = ROOT / "assets/install-via-reaboot.svg"
    assert logo.is_file() and logo.stat().st_size > 0
    assert button.is_file() and button.stat().st_size > 0
    button_xml = ET.parse(button).getroot()
    assert button_xml.tag.endswith("svg")
    assert "Install via ReaBoot" in "".join(button_xml.itertext())


def test_readme_contains_reaboot_recipe_install_link():
    readme = (ROOT / "README.md").read_text()
    encoded_recipe_url = urllib.parse.quote(
        "https://raw.githubusercontent.com/djenttleman/ReaSet/main/reaboot.json",
        safe="",
    )
    expected = f"https://www.reaboot.com/install/{encoded_recipe_url}"
    assert expected in readme
