/**
 * Tasmota Updater Web Application
 * Main JavaScript file for the frontend
 */

function tasmotaApp() {
    return {
        // Data
        devices: [],
        latestRelease: null,
        isLoading: true,
        isCheckingAll: false,
        isUpdatingAll: false,
        error: '',
        success: '',
        showUpdateModal: false,
        selectedDevice: null,
        updateProgress: {
            total: 0,
            completed: 0,
            inProgress: 0,
            failed: 0,
            percentage: 0
        },
        updateSettings: {
            updateOnlyNeeded: localStorage.getItem('update_only_needed') !== 'false'
        },
        
        // Helper functions
        getDeviceUrl(device) {
            // Use DNS name if available, otherwise use IP
            const host = device.dns_name || device.ip;
            return `http://${host}`;
        },
        
        // Computed properties
        get hasUpdatableDevices() {
            return this.devices.some(device => 
                device.update_status && device.update_status.needs_update
            );
        },
        
        // Lifecycle methods
        init() {
            this.fetchLatestRelease();
            this.fetchDevices();
        },
        
        // Methods
        async fetchDevices() {
            this.isLoading = true;
            this.error = '';
            
            const timeoutValue = 60; // Default to 60 seconds for device listing
            try {
                // Create an AbortController
                const controller = new AbortController();
                
                // Set up timeout
                const timeoutId = setTimeout(() => controller.abort(), timeoutValue * 1000);
                
                const response = await fetch('/api/devices', {
                    signal: controller.signal
                });
                
                // Clear timeout since fetch completed
                clearTimeout(timeoutId);
                
                if (!response.ok) {
                    throw new Error(`Failed to fetch devices: ${response.statusText}`);
                }
                
                const data = await response.json();
                this.devices = data.devices.map(device => ({
                    ...device,
                    status: null,
                    update_status: null,
                    isChecking: false,
                    isUpdating: false,
                    checkSuccess: false,
                    lastChecked: null
                }));
                
                // If we have devices, check their status
                if (this.devices.length > 0) {
                    this.devices.forEach(device => this.fetchDeviceStatus(device));
                }
            } catch (error) {
                console.error('Error fetching devices:', error);
                
                if (error.name === 'AbortError') {
                    console.error(`Device listing request timed out after ${timeoutValue}s`);
                    this.error = `Failed to load devices: Request timed out after ${timeoutValue}s`;
                } else {
                    this.error = `Failed to load devices: ${error.message}`;
                }
            } finally {
                this.isLoading = false;
            }
        },
        
        async fetchLatestRelease() {
            const timeoutValue = 10; // Default to 10 seconds for release info
            try {
                // Create an AbortController
                const controller = new AbortController();
                
                // Set up timeout
                const timeoutId = setTimeout(() => controller.abort(), timeoutValue * 1000);
                
                const response = await fetch('/api/releases/latest', {
                    signal: controller.signal
                });
                
                // Clear timeout since fetch completed
                clearTimeout(timeoutId);
                
                if (!response.ok) {
                    throw new Error(`Failed to fetch latest release: ${response.statusText}`);
                }
                
                this.latestRelease = await response.json();
            } catch (error) {
                console.error('Error fetching latest release:', error);
                if (error.name === 'AbortError') {
                    console.error(`Release info request timed out after ${timeoutValue}s`);
                }
                // Don't show an error notification for this, just log it
            }
        },
        
        async fetchDeviceStatus(device) {
            device.isChecking = true;
            
            try {
                // Create an AbortController
                const controller = new AbortController();
                const timeoutValue = device.timeout || 60; // Default to 60 seconds
                
                // Set up timeout
                const timeoutId = setTimeout(() => controller.abort(), timeoutValue * 1000);
                
                const response = await fetch(`/api/devices/${device.ip}`, {
                    signal: controller.signal
                });
                
                // Clear timeout since fetch completed
                clearTimeout(timeoutId);
                
                if (!response.ok) {
                    throw new Error(`Failed to fetch device status: ${response.statusText}`);
                }
                
                device.status = await response.json();
                
                // Now check if update is needed
                await this.checkDeviceUpdate(device);
            } catch (error) {
                console.error(`Error fetching status for ${device.ip}:`, error);
                if (error.name === 'AbortError') {
                    console.error(`Request timed out for ${device.ip} after ${device.timeout || 60}s`);
                }
                device.status = null;
            } finally {
                device.isChecking = false;
            }
        },
        
        async checkDeviceUpdate(device) {
            if (!device.status) return;
            console.log(`Checking update status for ${device.ip}`);
            const timeoutValue = device.timeout || 60; // Default to 60 seconds
            try {
                // Create an AbortController
                const controller = new AbortController();
                
                // Set up timeout
                const timeoutId = setTimeout(() => controller.abort(), timeoutValue * 1000);
                
                const response = await fetch('/api/update', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({
                        ip: device.ip,
                        check_only: true
                    }),
                    signal: controller.signal
                });
                
                // Clear timeout since fetch completed
                clearTimeout(timeoutId);
                
                if (!response.ok) {
                    throw new Error(`Failed to check update: ${response.statusText}`);
                }
                
                device.update_status = await response.json();
            } catch (error) {
                console.error(`Error checking update for ${device.ip}:`, error);
                if (error.name === 'AbortError') {
                    console.error(`Update check timed out for ${device.ip} after ${timeoutValue}s`);
                }
                device.update_status = null;
            }
        },
        
        async updateDevice(device) {
            device.isUpdating = true;
            
            // Set update in progress flags for UI indicator
            device.update_in_progress = true;
            device.update_message = 'Pending update...';
            
            try {
                // Create an AbortController
                const controller = new AbortController();
                const timeoutValue = device.timeout || 60; // Default to 60 seconds for firmware updates
                
                // Set up timeout
                const timeoutId = setTimeout(() => controller.abort(), timeoutValue * 1000);
                
                const response = await fetch('/api/update', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({
                        ip: device.ip,
                        check_only: false
                    }),
                    signal: controller.signal
                });
                
                // Clear timeout since fetch completed
                clearTimeout(timeoutId);
                
                if (!response.ok) {
                    throw new Error(`Failed to update device: ${response.statusText}`);
                }
                
                device.update_status = await response.json();
                
                // Set timeout value from API response
                if (device.update_status.timeout_seconds) {
                    device.timeout_seconds = device.update_status.timeout_seconds;
                }
                
                if (device.update_status.success) {
                    // Update was successful, set completed status
                    device.update_completed = true;
                    // if update_status.message is not empty, use it, otherwise use default message, always append "Pending restart..."
                    device.update_message = device.update_status.message ? device.update_status.message + ', pending restart...' : 'Update completed, pending restart...';
                    // if it is a fake device, sleep 3 seconds
                    if (device.fake) {
                        await new Promise(resolve => setTimeout(resolve, 3000));
                    }
                    // Check update status again
                    await this.checkDeviceUpdate(device);
                } else {
                    // Update failed
                    device.update_message = device.update_status.message || 'Update failed';
                }
            } catch (error) {
                console.error(`Error updating ${device.ip}:`, error);
                
                if (error.name === 'AbortError') {
                    const timeoutValue = device.timeout || 60;
                    console.error(`Update timed out for ${device.ip} after ${timeoutValue}s`);
                    this.error = `Update timed out for ${device.ip} after ${timeoutValue}s`;
                    device.update_message = `Error: Update timed out after ${timeoutValue}s`;
                } else {
                    this.error = `Failed to update ${device.ip}: ${error.message}`;
                    device.update_message = `Error: ${error.message}`;
                }
            } finally {
                device.isUpdating = false;
                device.update_in_progress = false;
            }
        },
        
        // Poll a background job until it reaches a terminal state, invoking
        // onProgress(job) on each tick. Returns the final job snapshot.
        async _pollJob(jobId, onProgress) {
            while (true) {
                const resp = await fetch(`/api/jobs/${jobId}`);
                if (!resp.ok) {
                    throw new Error(`Failed to poll job status: ${resp.statusText}`);
                }
                const job = await resp.json();
                if (onProgress) onProgress(job);
                if (job.status === 'completed' || job.status === 'error') {
                    return job;
                }
                await new Promise(resolve => setTimeout(resolve, 1500));
            }
        },

        async updateAllDevices() {
            this.isUpdatingAll = true;
            this.error = '';
            this.updateProgress = { total: 0, completed: 0, inProgress: 0, failed: 0, percentage: 0 };

            const updateOnlyNeeded = localStorage.getItem('update_only_needed') !== 'false';
            try {
                // Mark candidate devices as pending update
                this.devices.forEach(device => {
                    if (updateOnlyNeeded && !device.update_status?.needs_update) return;
                    device.update_in_progress = true;
                    device.update_completed = false;
                    device.update_message = 'Pending update...';
                });

                // Start the background job (returns 202 + job id immediately)
                const startResp = await fetch('/api/update/all', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ check_only: false, update_only_needed: updateOnlyNeeded })
                });
                if (startResp.status === 409) {
                    throw new Error('A batch operation is already in progress.');
                }
                if (startResp.status !== 202 && !startResp.ok) {
                    throw new Error(`Failed to start update: ${startResp.statusText}`);
                }
                const { job_id } = await startResp.json();

                // Poll for real server-side progress
                const job = await this._pollJob(job_id, (j) => {
                    const total = j.total || 0;
                    const completed = j.completed || 0;
                    this.updateProgress = {
                        total,
                        completed,
                        inProgress: Math.max(0, total - completed),
                        failed: j.failed || 0,
                        percentage: total > 0 ? Math.round((completed / total) * 100) : 0
                    };
                    (j.results || []).forEach(r => {
                        const device = this.devices.find(d => d.ip === r.ip);
                        if (device) {
                            device.update_status = r;
                            device.update_in_progress = r.update_started && !r.update_completed;
                            device.update_completed = r.update_completed;
                            device.update_message = r.message;
                        }
                    });
                });

                if (job.status === 'error') {
                    throw new Error(job.error || 'Batch update failed');
                }
                const summary = job.summary || { updated: 0, needs_update: 0 };
                const failed = Math.max(0, (summary.needs_update || 0) - (summary.updated || 0));
                this.success = `Update completed: ${summary.updated || 0} device(s) updated`
                    + (failed ? `, ${failed} failed or skipped.` : '.');

                setTimeout(() => this.refreshDevices(), 3000);
            } catch (error) {
                console.error('Error updating all devices:', error);
                this.error = `Failed to update devices: ${error.message}`;
                this.devices.forEach(device => { device.update_in_progress = false; });
            } finally {
                this.isUpdatingAll = false;
            }
        },

        async checkAllDevices() {
            this.isCheckingAll = true;
            this.error = '';
            this.devices.forEach(device => { device.isChecking = true; });

            try {
                const startResp = await fetch('/api/update/all', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ check_only: true })
                });
                if (startResp.status === 409) {
                    throw new Error('A batch operation is already in progress.');
                }
                if (startResp.status !== 202 && !startResp.ok) {
                    throw new Error(`Failed to start check: ${startResp.statusText}`);
                }
                const { job_id } = await startResp.json();

                const job = await this._pollJob(job_id);
                if (job.status === 'error') {
                    throw new Error(job.error || 'Batch check failed');
                }

                const currentTime = new Intl.DateTimeFormat(navigator.language, {
                    hour: '2-digit', minute: '2-digit', second: '2-digit'
                }).format(new Date());
                (job.results || []).forEach(r => {
                    const device = this.devices.find(d => d.ip === r.ip);
                    if (device) {
                        device.update_status = r;
                        device.lastChecked = currentTime;
                    }
                });

                this.devices.forEach(device => { device.checkSuccess = true; });
                setTimeout(() => {
                    this.devices.forEach(device => { device.checkSuccess = false; });
                }, 2000);
            } catch (error) {
                console.error('Error checking all devices:', error);
                this.error = `Failed to check devices: ${error.message}`;
            } finally {
                this.devices.forEach(device => { device.isChecking = false; });
                this.isCheckingAll = false;
            }
        },
        
        // UI interaction methods
        refreshDevices() {
            this.fetchDevices();
        },
        
        async checkDevice(device) {
            if (device.isChecking) return; // Prevent multiple simultaneous checks
            
            // The fetchDeviceStatus function already handles setting isChecking to true/false
            await this.fetchDeviceStatus(device);
            
            // Add visual feedback when check completes
            device.lastChecked = new Intl.DateTimeFormat(navigator.language, {
                hour: '2-digit',
                minute: '2-digit',
                second: '2-digit'
            }).format(new Date());
            
            // Optional: Flash a brief success indicator
            device.checkSuccess = true;
            setTimeout(() => {
                device.checkSuccess = false;
            }, 2000);
        },
        
        confirmUpdateDevice(device) {
            this.selectedDevice = device;
            this.showUpdateModal = true;
        },
        
        confirmUpdateAll() {
            this.selectedDevice = null;
            this.showUpdateModal = true;
        },
        
        updateConfirmed() {
            this.showUpdateModal = false;
            
            // Save update settings to localStorage
            localStorage.setItem('update_only_needed', this.updateSettings.updateOnlyNeeded.toString());
            
            if (this.selectedDevice) {
                this.updateDevice(this.selectedDevice);
            } else {
                this.updateAllDevices();
            }
        }
    };
}
