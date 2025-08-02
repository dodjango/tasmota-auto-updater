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
            
            try {
                const response = await fetch('/api/devices');
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
                this.error = `Failed to load devices: ${error.message}`;
            } finally {
                this.isLoading = false;
            }
        },
        
        async fetchLatestRelease() {
            try {
                const response = await fetch('/api/releases/latest');
                if (!response.ok) {
                    throw new Error(`Failed to fetch latest release: ${response.statusText}`);
                }
                
                this.latestRelease = await response.json();
            } catch (error) {
                console.error('Error fetching latest release:', error);
                // Don't show an error notification for this, just log it
            }
        },
        
        async fetchDeviceStatus(device) {
            device.isChecking = true;
            
            try {
                const response = await fetch(`/api/devices/${device.ip}`, {
                    timeout: device.timeout || 60
                });
                if (!response.ok) {
                    throw new Error(`Failed to fetch device status: ${response.statusText}`);
                }
                
                device.status = await response.json();
                
                // Now check if update is needed
                await this.checkDeviceUpdate(device);
            } catch (error) {
                console.error(`Error fetching status for ${device.ip}:`, error);
                device.status = null;
            } finally {
                device.isChecking = false;
            }
        },
        
        async checkDeviceUpdate(device) {
            if (!device.status) return;
            
            try {
                const response = await fetch('/api/update', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({
                        ip: device.ip,
                        check_only: true
                    })
                });
                
                if (!response.ok) {
                    throw new Error(`Failed to check update: ${response.statusText}`);
                }
                
                device.update_status = await response.json();
            } catch (error) {
                console.error(`Error checking update for ${device.ip}:`, error);
                device.update_status = null;
            }
        },
        
        async updateDevice(device) {
            device.isUpdating = true;
            
            // Set update in progress flags for UI indicator
            device.update_in_progress = true;
            device.update_message = 'Pending update...';
            
            try {
                const response = await fetch('/api/update', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({
                        ip: device.ip,
                        check_only: false
                    })
                });
                
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
                    device.update_message = device.update_status.message || 'Update completed';
                    
                    // Refresh device status after a delay
                    setTimeout(() => this.fetchDeviceStatus(device), 5000);
                } else {
                    // Update failed
                    device.update_message = device.update_status.message || 'Update failed';
                }
            } catch (error) {
                console.error(`Error updating ${device.ip}:`, error);
                this.error = `Failed to update ${device.ip}: ${error.message}`;
                device.update_message = `Error: ${error.message}`;
            } finally {
                device.isUpdating = false;
                device.update_in_progress = false;
            }
        },
        
        async updateAllDevices() {
            this.isUpdatingAll = true;
            this.updateProgress = {
                total: 0,
                completed: 0,
                inProgress: 0,
                failed: 0,
                percentage: 0
            };
            
            // Get user preference for update filtering
            const updateOnlyNeeded = localStorage.getItem('update_only_needed') !== 'false';
            
            try {
                // First, mark all devices as pending update
                this.devices.forEach(device => {
                    if (updateOnlyNeeded && !device.update_status?.needs_update) {
                        return;
                    }
                    device.update_in_progress = true;
                    device.update_completed = false;
                    device.update_message = 'Pending update...';
                    this.updateProgress.total++;
                });
                
                const response = await fetch('/api/update/all', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({
                        check_only: false,
                        update_only_needed: updateOnlyNeeded
                    })
                });
                
                if (!response.ok) {
                    throw new Error(`Failed to update devices: ${response.statusText}`);
                }
                
                const result = await response.json();
                
                // Update progress information
                // Get the count of devices that need updates or are being updated
                this.updateProgress.total = result.summary.needs_update > 0 ? result.summary.needs_update : this.updateProgress.total;
                
                this.updateProgress = {
                    total: this.updateProgress.total, // Use the count of devices that need updates
                    completed: result.summary.updated,
                    inProgress: result.results.filter(r => r.update_started && !r.update_completed).length,
                    failed: result.results.filter(r => r.update_started && !r.success).length,
                    percentage: this.updateProgress.total > 0 ? 
                        Math.round((result.summary.updated / this.updateProgress.total) * 100) : 0
                };
                
                // Update the status of each device
                result.results.forEach(updateResult => {
                    const device = this.devices.find(d => d.ip === updateResult.ip);
                    if (device) {
                        device.update_status = updateResult;
                        device.update_in_progress = updateResult.update_started && !updateResult.update_completed;
                        device.update_completed = updateResult.update_completed;
                        device.update_message = updateResult.message;
                        
                        // Add timeout information
                        if (updateResult.timeout_seconds) {
                            device.timeout_seconds = updateResult.timeout_seconds;
                        }
                    }
                });
                
                // Show success message with summary
                this.success = `Update completed: ${result.summary.updated} devices updated, ` + 
                              `${result.summary.needs_update - result.summary.updated} devices failed or timed out.`;
                
                // Refresh device statuses after a delay
                setTimeout(() => this.refreshDevices(), 5000);
            } catch (error) {
                console.error('Error updating all devices:', error);
                this.error = `Failed to update devices: ${error.message}`;
                
                // Reset update progress status for all devices
                this.devices.forEach(device => {
                    device.update_in_progress = false;
                });
            } finally {
                this.isUpdatingAll = false;
            }
        },
        
        async checkAllDevices() {
            this.isCheckingAll = true;
            
            // Set all devices to checking state
            this.devices.forEach(device => {
                device.isChecking = true;
            });
            
            try {
                const response = await fetch('/api/update/all', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({
                        check_only: true
                    })
                });
                
                if (!response.ok) {
                    throw new Error(`Failed to check devices: ${response.statusText}`);
                }
                
                const result = await response.json();
                const currentTime = new Intl.DateTimeFormat(navigator.language, {
                    hour: '2-digit',
                    minute: '2-digit',
                    second: '2-digit'
                }).format(new Date());
                
                // Update the status of each device
                result.results.forEach(updateResult => {
                    const device = this.devices.find(d => d.ip === updateResult.ip);
                    if (device) {
                        device.update_status = updateResult;
                        device.lastChecked = currentTime;
                    }
                });
                
                // Set success indicator for all devices
                this.devices.forEach(device => {
                    device.checkSuccess = true;
                });
                
                // Clear success indicator after delay
                setTimeout(() => {
                    this.devices.forEach(device => {
                        device.checkSuccess = false;
                    });
                }, 2000);
                
            } catch (error) {
                console.error('Error checking all devices:', error);
                this.error = `Failed to check devices: ${error.message}`;
            } finally {
                // Clear checking state for all devices
                this.devices.forEach(device => {
                    device.isChecking = false;
                });
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
