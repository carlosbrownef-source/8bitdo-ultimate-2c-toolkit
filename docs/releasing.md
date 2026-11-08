# Releasing a new version

1. Bump the version in `pyproject.toml`, `u2c_customfw/__init__.py` and `tests/test_smoke.py`, and run the tests.
2. Commit, tag and push: `git tag -a vX.Y.Z -m "U2C Firmware Toolkit X.Y.Z"`, then `git push origin main vX.Y.Z`.
3. Build the app and its zip for each architecture: `macos/build.sh` (writes `dist/firmware-toolkit-X.Y.Z-macos-arm64.zip`) and `macos/build.sh x86_64` (writes `dist/firmware-toolkit-X.Y.Z-macos-x86_64.zip`).
4. Publish the release with both zips attached, not as a prerelease:
   `gh release create vX.Y.Z --title "U2C Firmware Toolkit X.Y.Z" dist/firmware-toolkit-X.Y.Z-macos-arm64.zip dist/firmware-toolkit-X.Y.Z-macos-x86_64.zip`

## Homebrew

Publishing the release runs `.github/workflows/homebrew.yml`, which points the formula and cask in
[carlosbrownef-source/homebrew-tap](https://github.com/carlosbrownef-source/homebrew-tap) at the new tag and zip
(version, and the SHA-256 of each zip: the cask picks the arm64 or x86_64 one) and commits them as `github-actions[bot]`. Nothing has to be edited by hand.

- Check that it ran: the **homebrew** run under Actions, and a commit "firmware-toolkit X.Y.Z" in the tap.
- If it failed (for example, the zip was attached more than about five minutes after publishing), run it again from
  Actions → homebrew → Run workflow; the tag field is optional and defaults to the latest release. A rerun on a tag the
  tap already has changes nothing.
- It writes to the tap with a deploy key (read-write, on `homebrew-tap`) whose private half is the `TAP_DEPLOY_KEY`
  secret of this repository. If the key is removed, make a new ed25519 key pair, add the public half as a write deploy
  key on the tap (`gh repo deploy-key add --allow-write`) and store the private half with `gh secret set TAP_DEPLOY_KEY`.
- After the bump, `brew update && brew upgrade firmware-toolkit` and `brew upgrade --cask firmware-toolkit` should install it.
