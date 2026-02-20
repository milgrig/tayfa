// ── Init ───────────────────────────────────────────────────────────────────

(async () => {
    // Load settings (including theme) on startup
    const _initSettings = await loadSettings();

    // Check if there is an open project
    try {
        const status = await api('GET', '/api/status');

        if (!status.has_project) {
            // No current project — show project-picker
            showProjectPicker();
            return;
        }

        // Set document.title to project name
        if (status.current_project && status.current_project.name) {
            document.title = status.current_project.name + ' — Tayfa';
        }

        // Disable project switching UI when locked_project is set
        if (status.locked_project) {
            disableProjectSwitching();
        }
    } catch (e) {
        console.warn('Failed to check project status:', e.message);
        // On error show project-picker
        showProjectPicker();
        return;
    }

    // Project exists — load main application
    await Promise.all([checkStatus(), loadEmployees(), loadAgents(), fetchRunningTasks(), loadSprints(), loadGitStatus()]);
    updateRunningTasksIndicator();
    setInterval(checkStatus, 10000);
    startGlobalRunningPoll();
    startGitAutoRefresh();

    // Start auto-launch loop if setting is enabled
    if (_initSettings && _initSettings.autoLaunchSprints) {
        startAutoLaunchLoop();
    }

    // Ping server every 5 seconds (for auto-shutdown on tab close)
    // Use keepalive for background tab
    let pingFailCount = 0;
    const MAX_PING_FAILS = 3;

    setInterval(() => {
        fetch('/api/ping', {
            method: 'POST',
            keepalive: true,  // Allows request to complete even if tab is in background
            headers: { 'Content-Type': 'application/json' }
        })
        .then(response => {
            if (response.ok) {
                pingFailCount = 0;  // Reset counter on success
            } else {
                pingFailCount++;
                if (pingFailCount >= MAX_PING_FAILS) {
                    console.warn(`[PING] Ping failed ${pingFailCount} times`);
                }
            }
        })
        .catch(err => {
            pingFailCount++;
            if (pingFailCount >= MAX_PING_FAILS) {
                console.error(`[PING] Connection error (${pingFailCount} fails):`, err.message);
            }
        });
    }, 5000);

    // Additional ping on visibility change event (switching from background to active tab)
    document.addEventListener('visibilitychange', () => {
        if (!document.hidden) {
            // Tab became active — send ping immediately
            fetch('/api/ping', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' }
            }).catch(() => {});
        }
    });
})();
