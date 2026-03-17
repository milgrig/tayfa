// ── Theme Functions ────────────────────────────────────────────────────────

function applyTheme(themeName) {
    document.documentElement.setAttribute('data-theme', themeName);
}

async function changeTheme(newTheme) {
    try {
        const response = await api('POST', '/api/settings', { theme: newTheme });
        if (response.status === 'updated') {
            applyTheme(newTheme);
        }
    } catch (error) {
        alert('Error saving theme: ' + error.message);
        // Revert selector to previous value
        const currentTheme = document.documentElement.getAttribute('data-theme') || 'dark';
        document.getElementById('themeSelect').value = currentTheme;
    }
}

async function loadSettings() {
    try {
        const settings = await api('GET', '/api/settings');

        // Apply theme
        const theme = settings.theme || 'dark';
        applyTheme(theme);

        // Set value in header selector
        const themeSelect = document.getElementById('themeSelect');
        if (themeSelect) themeSelect.value = theme;

        // Set maxConcurrentTasks if available
        const maxInput = document.getElementById('maxConcurrentInput');
        if (maxInput && settings.maxConcurrentTasks) {
            maxInput.value = settings.maxConcurrentTasks;
        }

        // Update settings screen if it exists
        updateSettingsScreen(settings);

        return settings;
    } catch (error) {
        console.warn('Error loading settings:', error.message);
        return {};
    }
}

// ── Settings Dropdown Functions ────────────────────────────────────────────

function toggleSettingsDropdown(event) {
    event.stopPropagation();
    const dropdown = document.getElementById('settingsDropdown');
    dropdown.classList.toggle('show');
}

function closeSettingsDropdown() {
    const dropdown = document.getElementById('settingsDropdown');
    if (dropdown) dropdown.classList.remove('show');
}

// Close when clicking outside menu
document.addEventListener('click', (e) => {
    const dropdown = document.getElementById('settingsDropdown');
    const btn = document.querySelector('.settings-btn');
    if (dropdown && btn && !dropdown.contains(e.target) && !btn.contains(e.target)) {
        dropdown.classList.remove('show');
    }
});
