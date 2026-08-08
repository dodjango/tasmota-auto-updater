/**
 * Find Tasmota devices on the network and hand the picks to the editor.
 *
 * This component never writes configuration. Adopted devices leave here as a
 * `discovery-adopt` event and become unsaved rows in the editor, so the single
 * save path through PUT /api/config/devices stays the only writer.
 *
 * The editor and this modal talk through window events in both directions
 * rather than through $refs: they are separate x-data scopes, and reaching
 * into another scope's methods by DOM reference breaks the moment the markup
 * is nested differently.
 */
function discoveryModal() {
    return {
        isOpen: false,
        method: null,          // 'mdns' | 'scan' while a job runs
        network: '',
        limits: { max_prefix: 22, max_hosts: 1024 },
        jobId: null,
        status: null,          // 'pending' | 'running' | 'completed' | 'error'
        completed: 0,
        total: null,
        results: [],
        selected: [],
        notice: null,
        error: null,
        pollTimer: null,

        async open() {
            this.isOpen = true;
            this.reset();
            try {
                const response = await fetch('/api/discovery');
                if (response.ok) {
                    const body = await response.json();
                    this.limits = body.limits || this.limits;
                    this.network = (body.suggested_networks || [])[0] || '';
                }
            } catch (err) {
                // A missing suggestion is not worth an error banner — the user
                // can type the network. Only a failed search is worth shouting about.
            }
        },

        close() {
            // Stops the polling, not the job. The server finishes on its own
            // within ~25s; cancelling it would be extra state for nothing.
            this.isOpen = false;
            this.stopPolling();
        },

        reset() {
            // Drop any timer first. Without this, re-opening the dialog while a
            // poll is still ticking leaves an orphaned interval that then polls
            // a jobId of null and writes its 404 into a fresh dialog's error.
            this.stopPolling();
            this.jobId = null;
            this.status = null;
            this.completed = 0;
            this.total = null;
            this.results = [];
            this.selected = [];
            this.notice = null;
            this.error = null;
        },

        get isRunning() {
            return this.status === 'pending' || this.status === 'running';
        },

        get progressLabel() {
            if (this.method === 'mdns') return 'Listening for announcements…';
            if (this.total) return `Probed ${this.completed} of ${this.total} addresses`;
            return 'Starting…';
        },

        get selectableCount() {
            return this.results.filter(device => !device.already_configured).length;
        },

        async start(method) {
            this.reset();
            this.method = method;
            const payload = method === 'scan'
                ? { method, network: this.network }
                : { method };

            try {
                const response = await fetch('/api/discovery', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload),
                });
                const body = await response.json();
                if (!response.ok) {
                    this.error = body.details || body.error || 'Discovery could not be started.';
                    return;
                }
                this.jobId = body.job_id;
                this.status = 'pending';
                this.poll();
            } catch (err) {
                this.error = 'Discovery could not be started.';
            }
        },

        poll() {
            this.stopPolling();
            this.pollTimer = setInterval(async () => {
                try {
                    const response = await fetch(`/api/jobs/${this.jobId}`);
                    if (!response.ok) {
                        this.error = 'Lost track of the discovery job.';
                        this.stopPolling();
                        return;
                    }
                    const job = await response.json();
                    this.status = job.status;
                    this.completed = job.completed || 0;
                    this.total = job.total;
                    this.results = job.results || [];
                    this.notice = job.notice;
                    if (job.status === 'completed' || job.status === 'error') {
                        this.error = job.error;
                        this.stopPolling();
                    }
                } catch (err) {
                    this.error = 'Lost track of the discovery job.';
                    this.stopPolling();
                }
            }, 1000);
        },

        stopPolling() {
            if (this.pollTimer) {
                clearInterval(this.pollTimer);
                this.pollTimer = null;
            }
        },

        toggle(ip) {
            const index = this.selected.indexOf(ip);
            if (index === -1) this.selected.push(ip);
            else this.selected.splice(index, 1);
        },

        adopt() {
            const picks = this.results
                .filter(device => this.selected.includes(device.ip))
                .map(device => ({ ip: device.ip, dns_name: device.hostname || '' }));
            this.$dispatch('discovery-adopt', { devices: picks });
            this.close();
        },
    };
}
