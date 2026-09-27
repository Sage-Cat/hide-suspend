#!/usr/bin/env python3
"""Capture the native power submenu in a disposable GNOME Shell."""
from __future__ import annotations

import argparse
import ast
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import time

FIXTURE = 'power-menu-documentation@example.invalid'



def stop(process):
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=3)


def inside(root, output):
    if Path(os.environ['XDG_RUNTIME_DIR']) != root / 'runtime' or str(root / 'runtime') not in os.environ.get('DBUS_SESSION_BUS_ADDRESS', ''):
        raise RuntimeError('private runtime and private bus required')
    deadline = time.monotonic() + 100

    def control(action='state', **kwargs):
        value = subprocess.run(['gdbus', 'call', '--session', '--dest', 'org.gnome.Shell',
                                '--object-path', '/org/example/PowerMenuDocumentation', '--method',
                                'org.example.PowerMenuDocumentation.Control', json.dumps({'action': action, **kwargs})],
                               capture_output=True, text=True, timeout=3, check=True)
        return json.loads(ast.literal_eval(value.stdout)[0])

    def until(predicate, timeout=8):
        end = min(deadline, time.monotonic() + timeout)
        last = None
        while time.monotonic() < end:
            try:
                last = control()
                if predicate(last):
                    return last
            except subprocess.CalledProcessError:
                pass
            time.sleep(.1)
        raise RuntimeError(f'disposable Shell did not become ready: {last}')

    with (root / 'shell.log').open('w') as log:
        shell = subprocess.Popen(['gnome-shell', '--headless', '--wayland', '--no-x11', '--sm-disable',
                                  '--wayland-display=power-menu-docs', '--virtual-monitor=1400x1100'],
                                 stdout=log, stderr=subprocess.STDOUT)
        try:
            until(lambda state: state.get('ready'), timeout=35)
            control('setup')
            until(lambda state: not state.get('overview'))
            for name, interface in [('hide-suspend', 'HideSuspend')]:
                value = subprocess.run(['gdbus', 'call', '--session', '--dest', 'org.gnome.Shell', '--object-path', '/org/sagecat/' + interface, '--method', 'org.sagecat.' + interface + '.GetState'], capture_output=True, text=True, check=True)
                (output / (name + '.json')).write_text(json.dumps(json.loads(ast.literal_eval(value.stdout)[0]), indent=2))
            control('menu')
            time.sleep(.7)
            target = root / 'runtime/power-menu.png'
            control('screenshot', path=str(target))
            status = until(lambda state: (state.get('capture') or {}).get('done'))
            if status['capture'].get('error'):
                raise RuntimeError(status['capture']['error'])
            shutil.copyfile(target, output / target.name)
        except Exception:
            print((root / 'shell.log').read_text()[-7000:], file=sys.stderr)
            raise
        finally:
            stop(shell)
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', action='store_true', help='explicitly opt in to a disposable compositor')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--inside', type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.inside:
        return inside(args.inside, args.output)
    if not args.run:
        parser.error('--run is required; nothing is installed into the active desktop')
    for binary in ['gnome-shell', 'dbus-run-session', 'gdbus', 'glib-compile-schemas']:
        if not shutil.which(binary):
            raise RuntimeError(f'missing prerequisite: {binary}')
    source = Path(__file__).resolve().parent.parent
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='power-menu-docs-', dir='/tmp') as temporary:
        root = Path(temporary)
        for name in ['runtime', 'config', 'data', 'cache', 'state', 'schemas']:
            (root / name).mkdir(mode=0o700)
        base = root / 'data/gnome-shell/extensions'
        base.mkdir(parents=True)
        extension_names = ['hide-suspend']
        uuids = []
        for name in extension_names:
            project = source
            metadata = json.loads((project / 'metadata.json').read_text())
            uuids.append(metadata['uuid'])
            dest = base / metadata['uuid']
            dest.mkdir()
            for path in project.iterdir():
                if path.suffix == '.js' or path.name == 'metadata.json':
                    shutil.copyfile(path, dest / path.name)
        fixture = base / FIXTURE
        fixture.mkdir()
        shutil.copyfile(source / 'docs/native-fixture.js', fixture / 'extension.js')
        (fixture / 'metadata.json').write_text(json.dumps({'uuid': FIXTURE, 'name': 'Disposable documentation controller',
                                                         'description': 'Screenshot driver', 'shell-version': ['46'], 'version': 1}))
        for schema in Path('/usr/share/glib-2.0/schemas').iterdir():
            if schema.name.endswith(('.xml', '.override')):
                (root / 'schemas' / schema.name).symlink_to(schema)
        (root / 'schemas/zz-power-menu-docs.gschema.override').write_text(f'''[org.gnome.shell]
enabled-extensions={uuids + [FIXTURE]}
disable-user-extensions=false
[org.gnome.mutter]
dynamic-workspaces=false
[org.gnome.desktop.wm.preferences]
num-workspaces=1
[org.gnome.desktop.interface]
color-scheme='prefer-dark'
''')
        subprocess.run(['glib-compile-schemas', '--strict', str(root / 'schemas')], check=True, timeout=10)
        bus = root / 'session-bus.conf'
        bus.write_text(f'''<!DOCTYPE busconfig PUBLIC "-//freedesktop//DTD D-Bus Bus Configuration 1.0//EN" "http://www.freedesktop.org/standards/dbus/1.0/busconfig.dtd">
<busconfig><type>session</type><listen>unix:tmpdir={root / 'runtime'}</listen><auth>EXTERNAL</auth>
<policy context="default"><allow send_destination="*"/><allow receive_sender="*"/><allow own="*"/></policy></busconfig>''')
        env = dict(os.environ, XDG_RUNTIME_DIR=str(root / 'runtime'),
                   XDG_CONFIG_HOME=str(root / 'config'), XDG_DATA_HOME=str(root / 'data'),
                   XDG_CACHE_HOME=str(root / 'cache'), XDG_STATE_HOME=str(root / 'state'),
                   XDG_CONFIG_DIRS=str(root / 'config'), XDG_DATA_DIRS='/usr/local/share:/usr/share',
                   WAYLAND_DISPLAY='power-menu-docs', DISPLAY='', GDK_BACKEND='wayland',
                   LANG='C.UTF-8', LC_ALL='C.UTF-8', GSETTINGS_BACKEND='memory', GSETTINGS_SCHEMA_DIR=str(root / 'schemas'),
                   GIO_USE_VFS='local', GVFS_DISABLE_FUSE='1', NO_AT_BRIDGE='1', GTK_A11Y='none',
                   IBUS_ADDRESS='unix:path=' + str(root / 'runtime/no-ibus'), GTK_IM_MODULE='gtk-im-context-simple',
                   LIBGL_ALWAYS_SOFTWARE='1', GALLIUM_DRIVER='llvmpipe', GNOME_SHELL_SESSION_MODE='gnome',
                   XDG_SESSION_TYPE='wayland', XDG_CURRENT_DESKTOP='GNOME')
        for name in ['DBUS_SESSION_BUS_ADDRESS', 'GNOME_SETUP_DISPLAY', 'SESSION_MANAGER',
                     'DESKTOP_AUTOSTART_ID', 'WSCTL_OPERATION_CONTEXT']:
            env.pop(name, None)
        process = subprocess.Popen(['dbus-run-session', '--config-file', str(bus), '--', sys.executable,
                                    str(Path(__file__).resolve()), '--inside', str(root), '--output', str(output)],
                                   env=env, start_new_session=True)
        try:
            result = process.wait(timeout=115)
        finally:
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=3)
        if result:
            return result
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
