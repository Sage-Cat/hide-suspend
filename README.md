# Hide Suspend

This GNOME Shell 46 extension removes **Suspend** from the power submenu. It
keeps the menu item hidden when GNOME refreshes power capabilities and restores
GNOME's normal Suspend visibility when the extension is disabled.

```sh
make check
make install
gnome-extensions enable hide-suspend@sagecat.local
```

The GNOME 46 adapter verifies the native SystemActions owner and a unique translated
Suspend action label. Menu reordering is supported; missing or ambiguous identity
fails without hiding another action. Diagnostics are read-only:

```sh
gdbus call --session --dest org.gnome.Shell --object-path /org/sagecat/HideSuspend --method org.sagecat.HideSuspend.GetState
```

`build` reports the loaded UUID/version/import-time revision. `development` means
unstamped source identity; installing new files does not reload a cached module.

## Checks and releases

```sh
make check
```

The [CI workflow](.github/workflows/ci.yml) verifies each change. Successful pushes
to the default branch publish a commit-addressed `build-<full-commit-SHA>` release
with a source archive, applicable extension bundles, and SHA-256 checksums.
See the [release process](https://github.com/Sage-Cat/workspace-state/blob/main/docs/publication.md) for artifact and verification details.

The local pre-commit privacy gate blocks private files before they enter a commit.
Enable it in a fresh clone with `git config core.hooksPath .githooks`.
CI repeats the privacy check before building or publishing.
