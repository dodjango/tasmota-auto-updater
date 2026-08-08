/**
 * Devices editor — edits the configuration behind /api/config/devices.
 *
 * The password is write-only: the server never sends it, an empty field means
 * "keep", and removal is explicit. Changing a device's IP makes it a new device,
 * so its password cannot follow.
 */
function devicesEditor() {
    return {
        devices: [],
        writable: true,
        devicesFile: '',
        loading: false,
        saving: false,
        error: '',
        saved: false,
        // Only a successful GET may set this true. Save is gated on it so a
        // failed load (expired session, proxy hiccup, 500) shows an empty,
        // disabled table instead of an empty, saveable one — a Save click
        // against that would submit `{devices: []}`, which is a perfectly
        // legal request, and wipe the real configuration on disk.
        loaded: false,
        // The last successfully loaded device count, so save() can tell "the
        // user really emptied the list" apart from "the list was never loaded".
        loadedDeviceCount: 0,

        async init() {
            await this.load();
        },

        async load() {
            this.loading = true;
            this.error = '';
            try {
                const response = await fetch('/api/config/devices');
                if (!response.ok) throw new Error(`HTTP ${response.status}`);
                const payload = await response.json();
                this.devices = payload.devices.map(device => ({
                    ...device,
                    password: '',
                    remove_password: false,
                }));
                this.writable = payload.writable;
                this.devicesFile = payload.devices_file;
                this.loadedDeviceCount = this.devices.length;
                this.loaded = true;
            } catch (err) {
                this.error = `Could not load the configuration: ${err.message}`;
                this.loaded = false;
            } finally {
                this.loading = false;
            }
        },

        addDevice() {
            this.devices.push({
                ip: '', username: '', dns_name: '', timeout: null,
                password: '', has_password: false, remove_password: false,
            });
        },

        /**
         * Take findings from the discovery modal as unsaved rows.
         *
         * Deliberately additive and deliberately unsaved: the user still has to
         * add credentials and press Save, so PUT /api/config/devices remains the
         * only path that writes the file.
         *
         * Gated on `loaded` for the same reason addDevice() is. Appending to a
         * list that never loaded and saving it would submit those rows as the
         * entire configuration and wipe everything else on disk.
         */
        adoptDiscovered(devices) {
            if (!this.loaded || !this.writable) return;
            const known = new Set(this.devices.map(device => (device.ip || '').trim()));
            (devices || [])
                .filter(device => device.ip && !known.has(device.ip))
                .forEach(device => {
                    this.devices.push({
                        ip: device.ip,
                        username: '',
                        dns_name: device.dns_name || '',
                        timeout: null,
                        password: '',
                        has_password: false,
                        remove_password: false,
                    });
                });
        },

        removeDevice(index) {
            const device = this.devices[index];
            const label = device.dns_name || device.ip || 'this device';
            if (!confirm(`Remove ${label} from the configuration?`)) return;
            this.devices.splice(index, 1);
        },

        clearPassword(device) {
            const label = device.dns_name || device.ip || 'this device';
            if (!confirm(`Remove the stored password for ${label}? It will be contacted without credentials until a new password is entered and saved.`)) return;
            device.remove_password = true;
            device.password = '';
            device.has_password = false;
        },

        _payload() {
            return this.devices.map(device => {
                const entry = { ip: (device.ip || '').trim() };
                const username = (device.username || '').trim();
                const dnsName = (device.dns_name || '').trim();
                if (username) entry.username = username;
                if (dnsName) entry.dns_name = dnsName;
                if (device.timeout) entry.timeout = Number(device.timeout);
                if (device.password) entry.password = device.password;
                if (device.remove_password) entry.remove_password = true;
                return entry;
            });
        },

        async save() {
            const submitted = this._payload();
            if (submitted.length === 0 && this.loadedDeviceCount > 0) {
                const confirmed = confirm(
                    `This removes all ${this.loadedDeviceCount} device(s) from the ` +
                    'configuration. Continue?'
                );
                if (!confirmed) return;
            }

            this.saving = true;
            this.error = '';
            this.saved = false;
            try {
                const response = await fetch('/api/config/devices', {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ devices: submitted }),
                });
                const payload = await response.json();
                if (!response.ok) {
                    const message = payload.details || `HTTP ${response.status}`;
                    if (response.status === 409) {
                        // Not writable (or unreadable) — re-derive `writable` from the
                        // server instead of letting the user retry against a file that
                        // will keep rejecting. load() clears `error`, so re-apply it.
                        await this.load();
                        this.error = `Save failed: ${message}`;
                        return;
                    }
                    throw new Error(message);
                }
                this.devices = payload.devices.map(device => ({
                    ...device, password: '', remove_password: false,
                }));
                this.loadedDeviceCount = this.devices.length;
                this.saved = true;
                // Tell the operational device list (the cards above) to
                // refresh — otherwise it keeps showing the pre-save devices.
                this.$dispatch('devices-changed');
                setTimeout(() => { this.saved = false; }, 4000);
            } catch (err) {
                this.error = `Save failed: ${err.message}`;
            } finally {
                this.saving = false;
            }
        },
    };
}
