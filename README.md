# Hide Suspend

GNOME Shell 46 extension that hides **Suspend** in the Quick Settings power menu.
Disabling it restores GNOME's normal menu behavior.

This changes only the menu. System suspend, lid-switch settings, and other ways
of requesting suspend remain available.

![Power menu with Suspend hidden](docs/screenshots/power-menu.png)

Native menu in a disposable session with synthetic capabilities; [capture details](docs/visual-guide.md).

## Install and use

Requires GNOME Shell **46**, Make, Node.js, `jq`, and ESLint (CI: Node 20, Ubuntu 24.04).

```sh
make check  # Metadata, syntax, ESLint and lifecycle tests
make install
gnome-extensions enable hide-suspend@sagecat.local
```

To restore the normal menu: `gnome-extensions disable hide-suspend@sagecat.local`.

On Wayland, log out and back in if GNOME has not discovered the extension or still
runs an older version. For a workspace-state-managed install, use its next-login deployment.

## Documentation

- [Diagnostics and screenshots](docs/visual-guide.md)
- [Design diagram](docs/architecture.svg) · [PlantUML source](docs/architecture.puml)
- [Releases](https://github.com/Sage-Cat/hide-suspend/releases)
- [Full desktop lifecycle validation](https://github.com/Sage-Cat/desktop-workspace/blob/main/docs/validation.md) documents integration tests and their limits, not VM coverage of every power action.
