# ReaBoot and ReaPack release maintenance

ReaBoot installs ReaSet through the ReaPack-compatible repository described by
[`index.xml`](index.xml). The branded installer configuration intentionally
remains at [`../reaboot.json`](../reaboot.json): that root URL is the stable
public endpoint already used by the website, README buttons and existing links.

The root [`../index.xml`](../index.xml) is an identical compatibility copy.
Existing ReaPack installations store that URL as their remote, and raw GitHub
URLs cannot redirect. Contract tests require both index files to remain byte-for-byte
identical; edit `reaboot/index.xml`, then synchronize the root copy in the same
commit.

## Public links

- ReaPack repository: `https://raw.githubusercontent.com/djenttleman/ReaSet/main/reaboot/index.xml`
- ReaBoot recipe: `https://raw.githubusercontent.com/djenttleman/ReaSet/main/reaboot.json`
- ReaBoot installer page:
  `https://www.reaboot.com/install/https%3A%2F%2Fraw.githubusercontent.com%2Fdjenttleman%2FReaSet%2Fmain%2Freaboot.json`

## Package layout

- `ReaSet/ReaSet` is required. It installs:
  - `Reaset.lua` as `Scripts/ReaSet/ReaSet/Reaset.lua` and records it as a
    Main Action List script in ReaPack's registry. REAPER/ReaPack completes
    Action List registration when REAPER starts.
  - `ReaSet.html` and `Sortable.min.js` in `reaper_www_root`.
- `ReaSet/ReaSet Tools` is optional. The ReaBoot recipe selects ReaImGui with
  it because Lyrics Tapper requires that extension.
- SWS is recommended but optional. ReaSet transport works without it, while
  lyrics/chords Item Notes need it.

ReaBoot and ReaPack intentionally do not change user preferences. Users still
need to run `Reaset` once and optionally configure it as a Startup Action.

## Adding a release

1. Release and tag ReaSet first. Never point a published `<source>` at `main`.
2. Resolve the tag to its full 40-character commit SHA, then add a new
   `<version>` to both packages in `index.xml`. Source URLs must use
   `https://raw.githubusercontent.com/djenttleman/ReaSet/<commit-sha>/...`.
3. Do **not** add the optional ReaPack `hash` attribute while ReaBoot 1.2.0 is
   the public installer. Its downloader consumes each chunk before feeding it
   to the verifier, so every legitimate checksum is compared against the hash
   of empty content and the installation is rejected. Because Git tags can be
   moved, immutable full-commit URLs are mandatory during this exception. This
   limitation is enforced by the contract tests.
4. If file locations changed in the release, use those paths in the source
   URLs. The v2.2 tools are at the repository root; v3.0 and later keep
   them under `Tools/`.
5. Run the contract tests:

   ```sh
   uvx pytest tests/test_reaboot_package.py -q
   ```

6. Test installation into a temporary portable REAPER resource directory before
   merging the index update.

`latest` selects the highest stable version in the index. Use a pre-release
version and `latest-pre` only when deliberately exposing a testing channel.
