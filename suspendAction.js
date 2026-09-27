// GNOME 46 binds these menu entries to SystemActions, but exposes no action ID.
// Match the unique Shell-translated action label and verify its native owner;
// never use item ordering or an English-only label as identity.
export function findSuspendAction(menu, suspendLabel) {
    const owner = menu?.sourceActor;
    const actions = owner?._systemActions;
    if (!Array.isArray(owner?._items) || typeof actions?.activateSuspend !== 'function')
        throw new Error('Unsupported GNOME Suspend action owner');
    const matches = owner._items.filter(item => item.label?.text === suspendLabel &&
        typeof item.connect === 'function' && typeof item.disconnect === 'function' &&
        typeof item.hide === 'function');
    if (matches.length !== 1)
        throw new Error(`Expected one native Suspend action; found ${matches.length}`);
    return {item: matches[0], actions};
}

export class SuspendVisibilityPolicy {
    constructor(item, actions) {
        this.item = item;
        this.actions = actions;
        this.signal = 0;
    }

    enable() {
        try {
            this.signal = this.item.connect('notify::visible', () => {
                if (this.item.visible)
                    this.item.hide();
            });
            this.item.hide();
        } catch (error) {
            this.disable();
            throw error;
        }
    }

    disable() {
        if (this.signal) {
            this.item.disconnect(this.signal);
            this.signal = 0;
        }
        this.item.visible = this.actions.canSuspend ?? false;
    }
}
