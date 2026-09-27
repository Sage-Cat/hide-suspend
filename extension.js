/* exported default */
import Gio from 'gi://Gio';
import Gettext from 'gettext';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';
import {findSuspendAction, SuspendVisibilityPolicy} from './suspendAction.js';
import {BUILD_REVISION} from './buildInfo.js';

const XML = '<node><interface name="org.sagecat.HideSuspend"><method name="GetState"><arg type="s" direction="out"/></method></interface></node>';

export default class HideSuspendExtension extends Extension {
    enable() {
        try {
            const menu = Main.panel.statusArea.quickSettings?._system?._systemItem?.menu;
            const label = Gettext.domain('gnome-shell').gettext('Suspend');
            const {item, actions} = findSuspendAction(menu, label);
            this._policy = new SuspendVisibilityPolicy(item, actions);
            this._policy.enable();
            this._dbus = Gio.DBusExportedObject.wrapJSObject(XML, {
                GetState: () => JSON.stringify({enabled: Boolean(this._policy), build: {
                    uuid: this.uuid, version: this.metadata.version, revision: BUILD_REVISION,
                    sourceIdentityKnown: BUILD_REVISION !== 'development',
                }}),
            });
            this._dbus.export(Gio.DBus.session, '/org/sagecat/HideSuspend');
        } catch (error) {
            this.disable();
            throw error;
        }
    }

    disable() {
        try {
            this._dbus?.unexport();
        } finally {
            this._dbus = null;
            this._policy?.disable();
            this._policy = null;
        }
    }
}
