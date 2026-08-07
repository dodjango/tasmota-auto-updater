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
            } catch (err) {
                this.error = `Konfiguration konnte nicht geladen werden: ${err.message}`;
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

        removeDevice(index) {
            const device = this.devices[index];
            const label = device.dns_name || device.ip || 'dieses Gerät';
            if (!confirm(`${label} aus der Konfiguration entfernen?`)) return;
            this.devices.splice(index, 1);
        },

        clearPassword(device) {
            device.remove_password = true;
            device.password = '';
            device.has_password = false;
        },

        _payload() {
            return this.devices.map(device => {
                const entry = { ip: (device.ip || '').trim() };
                if (device.username) entry.username = device.username;
                if (device.dns_name) entry.dns_name = device.dns_name;
                if (device.timeout) entry.timeout = Number(device.timeout);
                if (device.password) entry.password = device.password;
                if (device.remove_password) entry.remove_password = true;
                return entry;
            });
        },

        async save() {
            this.saving = true;
            this.error = '';
            this.saved = false;
            try {
                const response = await fetch('/api/config/devices', {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ devices: this._payload() }),
                });
                const payload = await response.json();
                if (!response.ok) {
                    throw new Error(payload.details || `HTTP ${response.status}`);
                }
                this.devices = payload.devices.map(device => ({
                    ...device, password: '', remove_password: false,
                }));
                this.saved = true;
                setTimeout(() => { this.saved = false; }, 4000);
            } catch (err) {
                this.error = `Speichern fehlgeschlagen: ${err.message}`;
            } finally {
                this.saving = false;
            }
        },
    };
}
