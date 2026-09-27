# Hide Suspend

GNOME Shell 46 extension that hides **Suspend** in the Quick Settings power menu.
Disabling it restores GNOME's normal menu behavior.

This changes only the menu. System suspend, lid-switch settings, and other ways
of requesting suspend remain available.

![Power menu with Suspend hidden](docs/screenshots/power-menu.png)

Native menu in a disposable session with synthetic power capabilities.
[Capture details](docs/visual-guide.md).

## Install and use

Requires GNOME Shell **46**, Make, Node.js, `jq`, and ESLint.
CI uses Node 20 and Ubuntu 24.04 lint tools.

```sh
make check
make install
gnome-extensions enable hide-suspend@sagecat.local
```

On Wayland, log out and back in if GNOME has not discovered the extension or still
runs an older version. For a workspace-state-managed install, use its next-login deployment.

To disable:

```sh
gnome-extensions disable hide-suspend@sagecat.local
```

## Diagnose

Read the loaded policy and build identity:

```sh
gdbus call --session --dest org.gnome.Shell \
  --object-path /org/sagecat/HideSuspend \
  --method org.sagecat.HideSuspend.GetState
```

## Documentation

- [Diagnostics and screenshots](docs/visual-guide.md)
- [Design diagram](docs/architecture.svg) · [PlantUML source](docs/architecture.puml)
- [Releases](https://github.com/Sage-Cat/hide-suspend/releases)
