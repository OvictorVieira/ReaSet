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
INDEX = ROOT / "reaboot/index.xml"
RECIPE = ROOT / "reaboot.json"
REPO_INDEX_URL = "https://raw.githubusercontent.com/djenttleman/ReaSet/main/reaboot/index.xml"
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


def test_readme_header_contains_brand_assets_and_graphical_reaboot_button():
    readme = (ROOT / "README.md").read_text()
    spanish_readme = (ROOT / "README.es.md").read_text()
    install_url = (
        "https://www.reaboot.com/install/"
        "https%3A%2F%2Fraw.githubusercontent.com%2Fdjenttleman%2FReaSet%2F"
        "main%2Freaboot.json"
    )

    logo = '<img src="assets/reaset-logo-transparent.svg" alt="ReaSet" width="520">'
    assert logo in readme
    assert logo in spanish_readme
    assert '<img src="assets/readme-hero-v2.svg"' in readme
    assert f'<a href="{install_url}">' in readme
    assert (
        '<img src="assets/install-via-reaboot.svg" '
        'alt="Install via ReaBoot" height="52">'
    ) in readme
    assert install_url in spanish_readme

    assets = [
        ROOT / "assets/reaset-logo.png",  # compatibility endpoint
        ROOT / "assets/reaset-logo.svg",  # previous SVG compatibility endpoint
        ROOT / "assets/reaset-logo-transparent.svg",
        ROOT / "assets/install-via-reaboot.svg",
        ROOT / "assets/readme-hero-v2.svg",
    ]
    assert all(asset.is_file() and asset.stat().st_size > 0 for asset in assets)
    for asset in assets:
        if asset.suffix == ".svg":
            svg = ET.parse(asset).getroot()
            assert svg.tag.endswith("svg")


def test_readme_logo_uses_a_transparent_note_cutout():
    svg = ET.parse(ROOT / "assets/reaset-logo-transparent.svg").getroot()
    namespace = "{http://www.w3.org/2000/svg}"
    mask = svg.find(f".//{namespace}mask[@id='note-cutout']")

    assert mask is not None
    assert "transparent musical-note cutout" in svg.findtext(f"{namespace}desc", "")
    visible_circle = svg.find(f"{namespace}circle")
    assert visible_circle is not None
    assert visible_circle.attrib["mask"] == "url(#note-cutout)"

    # Black geometry subtracts alpha only inside the mask; it must never be a
    # visible sibling painted over the green circle.
    masked_elements = set(mask.iter())
    black_elements = [
        element for element in svg.iter() if element.attrib.get("fill") == "#000000"
    ]
    assert black_elements
    assert all(element in masked_elements for element in black_elements)


def test_readme_is_digestible_and_full_manuals_are_preserved():
    readme = (ROOT / "README.md").read_text()
    spanish_readme = (ROOT / "README.es.md").read_text()
    guide = (ROOT / "docs/USER_GUIDE.md").read_text()
    spanish_guide = (ROOT / "docs/USER_GUIDE.es.md").read_text()

    assert len(readme.splitlines()) < 250
    assert len(spanish_readme.splitlines()) < 250
    assert len(guide) > 40_000
    assert len(spanish_guide) > 40_000
    assert "## 8) Usage Manual" in guide
    assert "## 8) Manual de uso" in spanish_guide
    assert "docs/USER_GUIDE.md" in readme
    assert "docs/USER_GUIDE.es.md" in spanish_readme


def test_public_tree_excludes_retired_legacy_and_roadmap_content():
    assert not (ROOT / "Legacy").exists()
    assert not (ROOT / "ROADMAP.md").exists()

    searchable = [
        ROOT / "README.md",
        ROOT / "README.es.md",
        ROOT / "docs/USER_GUIDE.md",
        ROOT / "docs/USER_GUIDE.es.md",
        ROOT / "CHANGELOG.md",
        ROOT / "LICENSE",
        ROOT / "Reaset.lua",
        ROOT / "ReaSet.html",
    ]
    for path in searchable:
        content = path.read_text()
        assert "Legacy/" not in content, f"retired Legacy path remains in {path}"
        assert "ROADMAP.md" not in content, f"retired roadmap remains in {path}"


def test_reaboot_distribution_files_are_grouped_without_breaking_recipe_url():
    assert RECIPE.is_file(), "root recipe is the stable public installer endpoint"
    assert INDEX.is_file()
    assert (ROOT / "reaboot/README.md").is_file()
    compatibility_index = ROOT / "index.xml"
    assert compatibility_index.is_file(), "existing ReaPack remotes need the old URL"
    assert compatibility_index.read_bytes() == INDEX.read_bytes()
    assert not (ROOT / "docs/REABOOT.md").exists()


def test_local_markdown_links_resolve():
    import re

    documents = [
        ROOT / "README.md",
        ROOT / "README.es.md",
        ROOT / "docs/USER_GUIDE.md",
        ROOT / "docs/USER_GUIDE.es.md",
        ROOT / "reaboot/README.md",
    ]
    for document in documents:
        text = document.read_text()
        for target in re.findall(r"\[[^]]+\]\(([^)]+)\)", text):
            if target.startswith(("http://", "https://", "#", "mailto:")):
                continue
            file_target = target.split("#", 1)[0]
            if not file_target:
                continue
            resolved = (document.parent / urllib.parse.unquote(file_target)).resolve()
            assert resolved.exists(), f"broken local link in {document}: {target}"


def test_readme_contains_reaboot_recipe_install_link():
    readme = (ROOT / "README.md").read_text()
    encoded_recipe_url = urllib.parse.quote(
        "https://raw.githubusercontent.com/djenttleman/ReaSet/main/reaboot.json",
        safe="",
    )
    expected = f"https://www.reaboot.com/install/{encoded_recipe_url}"
    assert expected in readme
