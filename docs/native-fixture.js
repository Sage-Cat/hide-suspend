import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import Shell from 'gi://Shell';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';
export default class Fixture extends Extension {
 enable() {
  if (!GLib.get_user_runtime_dir().startsWith('/tmp/power-menu-docs-')) throw new Error('Private runtime required');
  this.dbus = Gio.DBusExportedObject.wrapJSObject('<node><interface name="org.example.PowerMenuDocumentation"><method name="Control"><arg type="s" direction="in"/><arg type="s" direction="out"/></method></interface></node>', {Control: value => JSON.stringify(this.control(JSON.parse(value)))});
  this.dbus.export(Gio.DBus.session, '/org/example/PowerMenuDocumentation');
 }
 disable() {this.dbus?.unexport();}
 control(request) {
  if (request.action === 'setup') Main.overview.hide();
  if (request.action === 'menu') {
   const owner = Main.panel.statusArea.quickSettings._system._systemItem.menu.sourceActor;
   owner._systemActions.forceUpdate = () => {};
   for (const action of ['suspend','restart','power-off','logout']) {owner._systemActions._actions.get(action).available = true; owner._systemActions.notify('can-' + action);}
   const suspend = owner._items.find(item => item.label?.text === 'Suspend');
   if (!suspend || suspend.visible || !owner._systemActions.canSuspend)
    throw new Error('Expected available Suspend action to be hidden by the extension');
   Main.panel.statusArea.quickSettings.menu.open();
   Main.panel.statusArea.quickSettings._system._systemItem.menu.open();
  }
  if (request.action === 'screenshot') {
   if (!request.path.startsWith(GLib.get_user_runtime_dir() + '/'))
    throw new Error('Screenshot must remain in the disposable runtime');
   const actor = Main.panel.statusArea.quickSettings._system._systemItem.menu.actor;
   const [x,y] = actor.get_transformed_position();
   const [w,h] = actor.get_transformed_size();
   const stream = Gio.File.new_for_path(request.path).replace(null,false,Gio.FileCreateFlags.PRIVATE,null);
   this.capture = {done:false};
   new Shell.Screenshot().screenshot_area(Math.floor(x),Math.floor(y),Math.ceil(w),Math.ceil(h),stream,(o,r)=>{
    try {o.screenshot_area_finish(r);stream.close(null);this.capture={done:true};} catch(e) {this.capture={done:true,error:e.message};}
   });
  }
  return {ready:!Main.layoutManager._startingUp,overview:Main.overview.visible,capture:this.capture};
 }
}
