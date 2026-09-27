import assert from 'node:assert/strict';
import test from 'node:test';
import fs from 'node:fs';
import vm from 'node:vm';
import {findSuspendAction, SuspendVisibilityPolicy} from '../suspendAction.js';

function item(label) {
    let visible = true;
    const callbacks = new Map();
    return {label: {text: label}, callbacks,
        get visible() { return visible; },
        set visible(value) { visible = value; for (const cb of callbacks.values()) cb(); },
        hide() { this.visible = false; },
        connect(_name, cb) { callbacks.set(1, cb); return 1; },
        disconnect(id) { callbacks.delete(id); },
    };
}
function menu(items) {
    return {sourceActor: {_items: items, _systemActions: {activateSuspend() {}, canSuspend: true}}};
}

test('localized Suspend identity survives native menu reordering', () => {
    const restart = item('Restart'); const suspend = item('Призупинити');
    const result = findSuspendAction(menu([restart, suspend]), 'Призупинити');
    assert.equal(result.item, suspend);
    const policy = new SuspendVisibilityPolicy(result.item, result.actions);
    policy.enable();
    assert.equal(suspend.visible, false); assert.equal(restart.visible, true);
    suspend.visible = true; assert.equal(suspend.visible, false);
    result.actions.canSuspend = false;
    policy.disable(); assert.equal(suspend.visible, false);
    assert.equal(suspend.callbacks.size, 0);
});

test('missing, duplicate or foreign action identity fails without hiding anything', () => {
    const first = item('Power Off'); const second = item('Suspend');
    assert.throws(() => findSuspendAction(menu([first]), 'Suspend'));
    assert.throws(() => findSuspendAction(menu([second, item('Suspend')]), 'Suspend'));
    assert.throws(() => findSuspendAction({sourceActor: {_items: [second]}}, 'Suspend'));
    assert.equal(first.visible, true); assert.equal(second.visible, true);
});

test('disable restores current capability and partial enable removes its connection', () => {
    const suspend = item('Suspend'); const actions = {canSuspend: true};
    const policy = new SuspendVisibilityPolicy(suspend, actions);
    policy.enable(); policy.disable(); assert.equal(suspend.visible, true);
    suspend.hide = () => { throw new Error('injected failure'); };
    assert.throws(() => policy.enable(), /injected failure/);
    assert.equal(suspend.callbacks.size, 0);
});

// Execute the production lifecycle adapter with an initially unavailable menu.
test('startup waits for Quick Settings and disable cancels deferred activation', () => {
    const callbacks = new Map();
    const Main = {layoutManager: {_startingUp: true,
        connect(name, callback) { assert.equal(name, 'startup-complete'); callbacks.set(1, callback); return 1; },
        disconnect(id) { callbacks.delete(id); }}, panel: {statusArea: {quickSettings: {}}}};
    let exports = 0;
    const context = {Main, Extension: class {}, findSuspendAction, SuspendVisibilityPolicy,
        Gettext: {domain: () => ({gettext: value => value})}, BUILD_REVISION: 'test',
        Gio: {DBus: {session: {}}, DBusExportedObject: {wrapJSObject: () => ({
            export() { exports++; }, unexport() { exports--; },
        })}}};
    const source = fs.readFileSync(new URL('../extension.js', import.meta.url), 'utf8')
        .replace(/^import .*;\n/gm, '').replace('export default class', 'globalThis.Adapter = class');
    vm.runInNewContext(source, context);
    const extension = new context.Adapter();
    extension.enable();
    assert.equal(exports, 0);
    extension.disable();
    assert.equal(callbacks.size, 0);
    extension.enable();
    const suspend = item('Suspend');
    Main.panel.statusArea.quickSettings._system = {_systemItem: {menu: menu([suspend])}};
    Main.layoutManager._startingUp = false;
    callbacks.get(1)();
    assert.equal(callbacks.size, 0);
    assert.equal(suspend.visible, false);
    assert.equal(exports, 1);
    extension.disable();
    assert.equal(suspend.visible, true);
    assert.equal(exports, 0);
});
