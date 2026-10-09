import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import Meta from 'gi://Meta';
import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import {slots} from './layout.js';

const SERVICE = 'org.gnome.Shell.Extensions.Notella';
const PATH = '/org/gnome/Shell/Extensions/Notella';
const INTERFACE = `<node><interface name="${SERVICE}">
    <method name="Pin">
        <arg type="s" direction="in" name="id"/>
        <arg type="i" direction="in" name="order"/>
        <arg type="s" direction="out" name="error"/>
    </method>
    <method name="Unpin">
        <arg type="s" direction="in" name="id"/>
        <arg type="s" direction="out" name="error"/>
    </method>
    <signal name="Released"><arg type="s" name="id"/><arg type="s" name="reason"/></signal>
</interface></node>`;

export default class NotellaDesktop extends Extension {
    enable() {
        this._pins = new Map();
        this._bus = Gio.DBus.session;
        this._object = Gio.DBusExportedObject.wrapJSObject(INTERFACE, this);
        this._object.export(this._bus, PATH);
        this._name = Gio.bus_own_name_on_connection(
            this._bus, SERVICE, Gio.BusNameOwnerFlags.NONE, null, null);
        // Reconcile newly mapped/remapped Qt windows and changed monitor work areas.
        this._timer = GLib.timeout_add(GLib.PRIORITY_DEFAULT, 500, () => {
            this._reconcile();
            return GLib.SOURCE_CONTINUE;
        });
    }

    _slots() {
        const monitor = Main.layoutManager.primaryIndex;
        if (monitor < 0)
            return [];
        return slots(global.workspace_manager.get_active_workspace()
            .get_work_area_for_monitor(monitor));
    }

    PinAsync([id, order], invocation) {
        const reply = error => invocation.return_value(new GLib.Variant('(s)', [error]));
        if (!/^[a-f0-9]{32}$/.test(id) || order < 0) {
            reply('Invalid note identifier or pin order.');
            return;
        }
        const owner = invocation.get_sender();
        const existing = this._pins.get(id);
        if (existing && existing.owner !== owner) {
            reply('This note is already managed by another Notella instance.');
            return;
        }
        if (!existing && this._pins.size >= this._slots().length) {
            reply('The primary desktop is full. Unpin a note to make space.');
            return;
        }
        try {
            const [pid] = this._bus.call_sync(
                'org.freedesktop.DBus', '/org/freedesktop/DBus', 'org.freedesktop.DBus',
                'GetConnectionUnixProcessID', new GLib.Variant('(s)', [owner]),
                new GLib.VariantType('(u)'), Gio.DBusCallFlags.NONE, 2000, null
            ).deep_unpack();
            if (!existing) {
                const entry = {
                    id, order, owner, pid, window: null, signals: [], watcher: 0, lowerSource: 0,
                };
                this._pins.set(id, entry);
                entry.watcher = Gio.bus_watch_name_on_connection(
                    this._bus, owner, Gio.BusNameWatcherFlags.NONE, null,
                    () => this._remove(id));
            } else {
                existing.order = order;
            }
            reply('');
        } catch (error) {
            console.error(`Notella: cannot identify pin requester: ${error}`);
            reply(`Could not identify the Notella process: ${error.message}`);
        }
    }

    UnpinAsync([id], invocation) {
        const entry = this._pins.get(id);
        if (entry && entry.owner !== invocation.get_sender()) {
            invocation.return_value(new GLib.Variant('(s)', ['This pin belongs to another process.']));
            return;
        }
        this._remove(id);
        invocation.return_value(new GLib.Variant('(s)', ['']));
    }

    _detach(entry) {
        if (entry.lowerSource) {
            GLib.Source.remove(entry.lowerSource);
            entry.lowerSource = 0;
        }
        if (!entry.window)
            return;
        for (const signal of entry.signals)
            entry.window.disconnect(signal);
        entry.signals = [];
        entry.window.unstick();
        entry.window = null;
    }

    _remove(id, reason = '') {
        const entry = this._pins.get(id);
        if (!entry)
            return;
        this._pins.delete(id);
        if (entry.watcher)
            Gio.bus_unwatch_name(entry.watcher);
        this._detach(entry);
        if (reason) {
            this._object.emit_signal('Released', new GLib.Variant('(ss)', [id, reason]));
            Main.notify('Notella', reason);
        }
    }

    _reconcile() {
        const positions = this._slots();
        const entries = [...this._pins.values()].sort((a, b) =>
            a.order - b.order || a.id.localeCompare(b.id));
        const windows = global.get_window_actors().map(actor => actor.meta_window);
        for (const [index, entry] of entries.entries()) {
            if (index >= positions.length) {
                this._remove(entry.id, 'The desktop no longer has room for this note. It was unpinned.');
                continue;
            }
            const window = windows.find(candidate =>
                candidate.get_pid() === entry.pid &&
                candidate.get_title()?.endsWith(`[notella:${entry.id}]`));
            if (entry.window !== window) {
                this._detach(entry);
                if (!window)
                    continue;
                entry.window = window;
                entry.signals.push(window.connect_after('raised', () => {
                    // Lower after Mutter finishes the raise, not during its stack update.
                    if (!entry.lowerSource) {
                        entry.lowerSource = GLib.idle_add(GLib.PRIORITY_DEFAULT_IDLE, () => {
                            entry.lowerSource = 0;
                            entry.window?.lower();
                            return GLib.SOURCE_REMOVE;
                        });
                    }
                }));
                entry.signals.push(window.connect('unmanaged', () => {
                    // Qt can recreate a surface when changing its window flags.
                    for (const signal of entry.signals)
                        window.disconnect(signal);
                    entry.signals = [];
                    entry.window = null;
                }));
                window.stick();
                window.unmake_above();
                window.lower();
            }
            if (!window)
                continue;
            const target = positions[index];
            const frame = window.get_frame_rect();
            if (window.get_maximize_flags())
                window.unmaximize(Meta.MaximizeFlags.BOTH);
            if (window.minimized)
                window.unminimize();
            if (frame.x !== target.x || frame.y !== target.y ||
                frame.width !== target.width || frame.height !== target.height) {
                window.move_resize_frame(false, target.x, target.y, target.width, target.height);
            }
        }
    }

    disable() {
        GLib.Source.remove(this._timer);
        for (const id of [...this._pins.keys()])
            this._remove(id);
        Gio.bus_unown_name(this._name);
        this._object.unexport();
        this._pins = null;
        this._object = null;
        this._bus = null;
    }
}
