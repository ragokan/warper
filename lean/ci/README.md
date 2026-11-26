# Warper macOS release

Warper ships for macOS on Apple silicon only. Releases are built, packaged and uploaded from
ragmini; the `Lean release` workflow is disabled (no GitHub Actions) and only kept as a record of
the same steps.

1. Build: `lean/build.sh` builds `warp-oss` with `--no-default-features`, an explicit terminal
   feature list and the `lean` Cargo profile exactly as defined in `Cargo.toml`: ThinLTO, its
   default codegen units, no debug symbols, and stripped symbols. It prints the binary path.
2. Package: `GIT_RELEASE_TAG=lean-vX.Y.Z lean/ci/bundle-macos.sh target/lean/warp-oss dist` writes
   `warper-macos-arm64.zip` and `.dmg`. Tags must use `lean-vX.Y.Z` with an optional nonempty
   `-prerelease` or `+build` suffix; a malformed tag fails packaging. `GIT_RELEASE_TAG` is set
   only during packaging, for the plist and bundled `version.json`; it is unset during compilation.
   Packaging does not invoke the private channel config installer or use Warp secrets.
3. Checksums: `(cd dist && shasum -a 256 warper-macos-arm64.zip warper-macos-arm64.dmg > SHA256SUMS)`.
   The in-app **Check for Updates…** command runs `warper-update`, which refuses an archive
   without a matching `SHA256SUMS` entry.
4. Publish: push `lean`, push an annotated `lean-vX.Y.Z` tag, then
   `gh release create lean-vX.Y.Z --repo ragokan/warper --verify-tag --title lean-vX.Y.Z
   --notes-file <notes> dist/warper-macos-arm64.zip dist/warper-macos-arm64.dmg dist/SHA256SUMS`.
   Check that `gh run list --repo ragokan/warper` shows no new run.

Packaging signs the app ad hoc, verifies the signature, checks the bundle with
`verify-bundle.py` (plist, URL scheme, document types, usage descriptions, terminal services,
authorized client, arm64 Mach-O header, Cow icon, Dock tile plug-in, resources, settings schema,
licenses, the bundled `warper-update`, no `Resources/bin` CLI entry point, and `strings -a` finding
no embedded `lean-ci` or `lean-v<digit>` marker), then extracts the zip into a fresh directory and
checks it again. `codesign -dv --verbose=4` is printed. Packaging checks do not establish
successful GUI startup.

The Oz and skill documentation under `resources/bundled/skills` is inert in the lean build. It
remains bundled with the other resources; verification requires the `bundled/` directory.

Workflows introduced by a future upstream sync can arrive enabled. After each sync, list all
workflows and disable every enabled one:

```bash
gh workflow list --all --repo ragokan/warper
gh workflow disable <workflow-id> --repo ragokan/warper
```

## Installing a release

Extract `warper-macos-arm64.zip`, or mount the DMG, and move `Warper.app` to Applications. The
app is ad-hoc signed, **not notarized**. On macOS 15+, try opening it once, then use **System
Settings → Privacy & Security → Open Anyway** if you trust the downloaded build. See
[Apple's Gatekeeper instructions](https://support.apple.com/en-us/102445). Alternatively, remove
its quarantine attribute:

```bash
xattr -dr com.apple.quarantine /Applications/Warper.app
```

## Local packaging checks

```bash
for script in lean/ci/bundle-macos.sh lean/warper-update; do bash -n "$script"; done
python3 -m unittest discover -s lean/ci -p '*_tests.py'
python3 lean/ci/verify-bundle.py /path/to/Warper.app
```
