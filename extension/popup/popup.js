/**
 * Scaler Companion - Popup Script
 * Handles UI interactions and communication with background worker
 */

// Constants
const BACKEND_URL = 'http://localhost:8000';
const API_ENDPOINTS = {
    health: `${BACKEND_URL}/health`,
    download: `${BACKEND_URL}/api/download`,
    process: `${BACKEND_URL}/api/process`,
    status: `${BACKEND_URL}/api/status`,
};

// DOM Elements
const elements = {
    statusIndicator: document.getElementById('statusIndicator'),
    statusDot: document.querySelector('.status-dot'),
    statusText: document.querySelector('.status-text'),
    detectionSection: document.getElementById('detectionSection'),
    lectureTitle: document.getElementById('lectureTitle'),
    lectureInfo: document.getElementById('lectureInfo'),
    controlsSection: document.getElementById('controlsSection'),
    downloadBtn: document.getElementById('downloadBtn'),
    progressContainer: document.getElementById('progressContainer'),
    progressFill: document.getElementById('progressFill'),
    progressText: document.getElementById('progressText'),
    processingSection: document.getElementById('processingSection'),
    processBtn: document.getElementById('processBtn'),
    recentSection: document.getElementById('recentSection'),
    recentList: document.getElementById('recentList'),
    backendStatus: document.getElementById('backendStatus'),
    settingsBtn: document.getElementById('settingsBtn'),
    // Developer Mode
    devModeToggle: document.getElementById('devModeToggle'),
    devModeBadge: document.getElementById('devModeBadge'),
    devModeOptions: document.getElementById('devModeOptions'),
    startTimeInput: document.getElementById('startTime'),
    endTimeInput: document.getElementById('endTime'),
};

// State
let currentLecture = null;
let isDownloading = false;
let isProcessing = false;
let devModeEnabled = false;

// ============================================
// Initialization
// ============================================

document.addEventListener('DOMContentLoaded', async () => {
    await init();
});

async function init() {
    // Check backend status
    await checkBackendHealth();

    // Check current tab for lectures
    await detectLecture();

    // Load recent downloads
    await loadRecentDownloads();

    // Load developer mode settings
    await loadDevModeSettings();

    // Setup event listeners
    setupEventListeners();

    // Start periodic health check
    setInterval(checkBackendHealth, 30000);
}

// ============================================
// Backend Communication
// ============================================

async function checkBackendHealth() {
    try {
        const response = await fetch(API_ENDPOINTS.health, {
            method: 'GET',
            headers: { 'Content-Type': 'application/json' }
        });

        if (response.ok) {
            updateBackendStatus(true);
            return true;
        }
    } catch (error) {
        console.error('Backend health check failed:', error);
    }

    updateBackendStatus(false);
    return false;
}

function updateBackendStatus(isOnline) {
    const dot = elements.backendStatus.querySelector('.status-dot');

    if (isOnline) {
        dot.classList.remove('offline');
        elements.backendStatus.title = 'Backend is running';
    } else {
        dot.classList.add('offline');
        elements.backendStatus.title = 'Backend is offline. Start the server with: python -m backend.server';
    }
}

// ============================================
// Lecture Detection
// ============================================

async function detectLecture() {
    try {
        // Get current active tab
        const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });

        if (!tab || !tab.url) {
            showNoLecture();
            return;
        }

        // Check if we're on Scaler
        if (!tab.url.includes('scaler.com')) {
            showNoLecture('Not on Scaler Academy');
            return;
        }

        // Send message to content script to get lecture info
        try {
            const response = await chrome.tabs.sendMessage(tab.id, { action: 'getLectureInfo' });

            if (response && response.hasLecture) {
                showLecture(response);
            } else {
                // Content script responded but no lecture detected
                // Try fallback URL-based detection
                fallbackDetection(tab);
            }
        } catch (error) {
            // Content script not loaded yet, use fallback
            console.log('Content script not responding, using fallback detection');
            fallbackDetection(tab);
        }
    } catch (error) {
        console.error('Error detecting lecture:', error);
        showNoLecture();
    }
}

function fallbackDetection(tab) {
    const url = tab.url;
    const title = tab.title || '';

    // Check URL patterns
    const isClassPage = /\/class\/\d+/.test(url);
    const isSessionPage = url.includes('/session');
    const isRecordingPage = url.includes('/recording');

    if (isClassPage || isSessionPage || isRecordingPage) {
        // Extract title from page title
        let lectureTitle = 'Scaler Class';
        const titleMatch = title.match(/^(?:Lecture\s*\|\s*)?([^|\-]+)/);
        if (titleMatch && !titleMatch[1].toLowerCase().includes('scaler')) {
            lectureTitle = titleMatch[1].trim();
        }

        showLecture({
            hasLecture: true,
            title: lectureTitle,
            url: url,
            streamInfo: null,
            fallbackMode: true
        });

        updateStatus('Manual Capture Mode', 'ready');
    } else {
        showNoLecture('Navigate to a class or recording page');
    }
}

function showNoLecture(message = 'No Lecture Detected') {
    currentLecture = null;
    elements.lectureTitle.textContent = message;
    elements.lectureInfo.textContent = 'Navigate to a Scaler lecture page';
    elements.controlsSection.style.display = 'none';
    elements.processingSection.style.display = 'none';

    updateStatus('Ready', 'ready');
}

function showLecture(lectureInfo) {
    currentLecture = lectureInfo;
    elements.lectureTitle.textContent = lectureInfo.title || 'Lecture Found';

    // Handle live sessions differently
    if (lectureInfo.isLiveSession && !lectureInfo.streamInfo?.baseUrl) {
        elements.lectureInfo.textContent = '🔴 Live Session - Recording available after class';
        elements.controlsSection.style.display = 'block';
        elements.downloadBtn.innerHTML = '<span class="btn-icon">⏳</span>Recording Not Ready';
        elements.downloadBtn.disabled = true;
        elements.downloadBtn.title = 'This is a live session. Download the recording after class ends.';
        updateStatus('Live Session', 'processing');
    } else if (lectureInfo.streamInfo?.baseUrl) {
        // Stream URL captured - ready to download
        elements.lectureInfo.textContent = lectureInfo.duration
            ? `Duration: ${formatDuration(lectureInfo.duration)}`
            : '✅ Stream captured - Ready to download';
        elements.controlsSection.style.display = 'block';
        elements.downloadBtn.innerHTML = '<span class="btn-icon">⬇️</span>Download Lecture';
        elements.downloadBtn.disabled = false;
        updateStatus('Ready to Download', 'ready');
    } else {
        // Lecture detected but no stream yet
        elements.lectureInfo.textContent = '⏳ Play the video to capture stream...';
        elements.controlsSection.style.display = 'block';
        elements.downloadBtn.innerHTML = '<span class="btn-icon">⬇️</span>Download Lecture';
        elements.downloadBtn.disabled = false;
        elements.downloadBtn.title = 'Play the video first, then click to download';
        updateStatus('Lecture Detected', 'ready');
    }
}

// ============================================
// Download Functionality
// ============================================

function setupEventListeners() {
    elements.downloadBtn.addEventListener('click', handleDownload);
    elements.processBtn.addEventListener('click', handleProcess);
    elements.settingsBtn.addEventListener('click', openSettings);

    // Developer mode toggle
    elements.devModeToggle.addEventListener('change', handleDevModeToggle);
}

async function handleDownload() {
    if (!currentLecture || isDownloading) return;

    const backendOnline = await checkBackendHealth();
    if (!backendOnline) {
        alert('Backend server is not running.\n\nStart it with:\npython -m backend.server');
        return;
    }

    isDownloading = true;
    elements.downloadBtn.disabled = true;
    elements.progressContainer.style.display = 'block';
    updateStatus('Downloading...', 'processing');

    try {
        // CRITICAL: Fetch FRESH streamInfo from content script before downloading
        // The currentLecture.streamInfo might be stale if set when popup opened
        const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
        let freshStreamInfo = currentLecture.streamInfo;

        try {
            const freshLecture = await chrome.tabs.sendMessage(tab.id, { action: 'getLectureInfo' });
            if (freshLecture && freshLecture.streamInfo) {
                freshStreamInfo = freshLecture.streamInfo;
                console.log('[Popup] Using FRESH streamInfo:', freshStreamInfo?.baseUrl);
            } else {
                console.log('[Popup] No fresh streamInfo, using cached');
            }
        } catch (e) {
            console.log('[Popup] Could not get fresh streamInfo, using cached:', e.message);
        }

        // Build download request with FRESH stream info
        const downloadRequest = {
            action: 'startDownload',
            lecture: {
                ...currentLecture,
                streamInfo: freshStreamInfo  // Use FRESH data!
            },
            devMode: devModeEnabled
        };

        // Add time settings if dev mode is enabled
        if (devModeEnabled) {
            downloadRequest.startTime = parseTimeToSeconds(elements.startTimeInput.value);
            downloadRequest.endTime = parseTimeToSeconds(elements.endTimeInput.value);
        }

        console.log('[Popup] Sending download request with baseUrl:', freshStreamInfo?.baseUrl);

        // Send download request to background worker
        const response = await chrome.runtime.sendMessage(downloadRequest);

        if (response.success) {
            // Start polling for progress
            pollDownloadProgress(response.downloadId);
        } else {
            throw new Error(response.error || 'Download failed to start');
        }
    } catch (error) {
        console.error('Download error:', error);
        alert(`Download failed: ${error.message}`);
        resetDownloadUI();
    }
}

async function pollDownloadProgress(downloadId) {
    const pollInterval = setInterval(async () => {
        try {
            const response = await fetch(`${API_ENDPOINTS.status}/${downloadId}`);
            const data = await response.json();

            updateProgress(data.progress);

            if (data.status === 'complete') {
                clearInterval(pollInterval);
                onDownloadComplete(data);
            } else if (data.status === 'error') {
                clearInterval(pollInterval);
                throw new Error(data.error);
            }
        } catch (error) {
            clearInterval(pollInterval);
            console.error('Progress polling error:', error);
            resetDownloadUI();
        }
    }, 1000);
}

function updateProgress(percent) {
    elements.progressFill.style.width = `${percent}%`;
    elements.progressText.textContent = `${Math.round(percent)}%`;
}

function onDownloadComplete(data) {
    updateStatus('Download Complete', 'ready');
    updateProgress(100);

    setTimeout(() => {
        elements.progressContainer.style.display = 'none';
        elements.processingSection.style.display = 'block';
        isDownloading = false;
        elements.downloadBtn.disabled = false;
        elements.downloadBtn.innerHTML = '<span class="btn-icon">✅</span>Downloaded';

        // Save to recent downloads
        saveRecentDownload({
            title: currentLecture.title,
            path: data.path,
            date: new Date().toISOString()
        });

        loadRecentDownloads();
    }, 500);
}

function resetDownloadUI() {
    isDownloading = false;
    elements.downloadBtn.disabled = false;
    elements.progressContainer.style.display = 'none';
    updateProgress(0);
    updateStatus('Ready', 'ready');
}

// ============================================
// Processing Functionality
// ============================================

async function handleProcess() {
    if (isProcessing) return;

    const options = {
        transcribe: document.getElementById('optTranscribe').checked,
        notes: document.getElementById('optNotes').checked,
        announcements: document.getElementById('optAnnouncements').checked,
        filter: document.getElementById('optFilter').checked,
    };

    if (!options.transcribe && !options.notes && !options.announcements && !options.filter) {
        alert('Please select at least one processing option');
        return;
    }

    isProcessing = true;
    elements.processBtn.disabled = true;
    updateStatus('Processing with AI...', 'processing');

    try {
        const response = await chrome.runtime.sendMessage({
            action: 'startProcessing',
            lecture: currentLecture,
            options: options
        });

        if (response.success) {
            // Open results in new tab
            chrome.tabs.create({ url: response.resultsUrl });
            updateStatus('Processing Complete', 'ready');
        } else {
            throw new Error(response.error);
        }
    } catch (error) {
        console.error('Processing error:', error);
        alert(`Processing failed: ${error.message}`);
    } finally {
        isProcessing = false;
        elements.processBtn.disabled = false;
        updateStatus('Ready', 'ready');
    }
}

// ============================================
// Recent Downloads
// ============================================

async function loadRecentDownloads() {
    try {
        const data = await chrome.storage.local.get('recentDownloads');
        const downloads = data.recentDownloads || [];

        if (downloads.length === 0) {
            elements.recentList.innerHTML = '<p class="empty-state">No downloads yet</p>';
            return;
        }

        elements.recentList.innerHTML = downloads.slice(0, 5).map(download => `
      <div class="recent-item" data-path="${download.path}">
        <span class="title">${download.title}</span>
        <span class="date">${formatDate(download.date)}</span>
      </div>
    `).join('');

        // Add click handlers
        elements.recentList.querySelectorAll('.recent-item').forEach(item => {
            item.addEventListener('click', () => {
                // TODO: Open in file explorer or load for processing
                console.log('Open:', item.dataset.path);
            });
        });
    } catch (error) {
        console.error('Error loading recent downloads:', error);
    }
}

async function saveRecentDownload(download) {
    try {
        const data = await chrome.storage.local.get('recentDownloads');
        const downloads = data.recentDownloads || [];
        downloads.unshift(download);
        await chrome.storage.local.set({ recentDownloads: downloads.slice(0, 20) });
    } catch (error) {
        console.error('Error saving recent download:', error);
    }
}

// ============================================
// Utilities
// ============================================

function updateStatus(text, state = 'ready') {
    elements.statusText.textContent = text;
    elements.statusDot.className = 'status-dot';

    if (state === 'processing') {
        elements.statusDot.classList.add('processing');
    } else if (state === 'offline') {
        elements.statusDot.classList.add('offline');
    }
}

function formatDuration(seconds) {
    const hrs = Math.floor(seconds / 3600);
    const mins = Math.floor((seconds % 3600) / 60);

    if (hrs > 0) {
        return `${hrs}h ${mins}m`;
    }
    return `${mins} min`;
}

function formatDate(isoString) {
    const date = new Date(isoString);
    const now = new Date();
    const diffDays = Math.floor((now - date) / (1000 * 60 * 60 * 24));

    if (diffDays === 0) return 'Today';
    if (diffDays === 1) return 'Yesterday';
    if (diffDays < 7) return `${diffDays} days ago`;

    return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

function openSettings() {
    chrome.runtime.openOptionsPage();
}

// ============================================
// Developer Mode Functions
// ============================================

async function loadDevModeSettings() {
    try {
        const data = await chrome.storage.local.get(['devModeEnabled', 'devStartTime', 'devEndTime']);
        devModeEnabled = data.devModeEnabled || false;

        // Update UI
        elements.devModeToggle.checked = devModeEnabled;
        elements.devModeOptions.style.display = devModeEnabled ? 'block' : 'none';
        elements.devModeBadge.style.display = devModeEnabled ? 'inline-block' : 'none';

        // Restore time values
        if (data.devStartTime) {
            elements.startTimeInput.value = data.devStartTime;
        }
        if (data.devEndTime) {
            elements.endTimeInput.value = data.devEndTime;
        }
    } catch (error) {
        console.error('Error loading dev mode settings:', error);
    }
}

async function handleDevModeToggle() {
    devModeEnabled = elements.devModeToggle.checked;

    // Update UI
    elements.devModeOptions.style.display = devModeEnabled ? 'block' : 'none';
    elements.devModeBadge.style.display = devModeEnabled ? 'inline-block' : 'none';

    // Save setting
    try {
        await chrome.storage.local.set({
            devModeEnabled: devModeEnabled,
            devStartTime: elements.startTimeInput.value,
            devEndTime: elements.endTimeInput.value
        });
    } catch (error) {
        console.error('Error saving dev mode settings:', error);
    }

    // Update status indicator
    if (devModeEnabled) {
        updateStatus('Developer Mode', 'processing');
    } else {
        updateStatus('Ready', 'ready');
    }
}

function parseTimeToSeconds(timeString) {
    // Parse time in format HH:MM:SS or MM:SS
    const parts = timeString.split(':').map(Number);

    if (parts.length === 3) {
        // HH:MM:SS
        return parts[0] * 3600 + parts[1] * 60 + parts[2];
    } else if (parts.length === 2) {
        // MM:SS
        return parts[0] * 60 + parts[1];
    } else if (parts.length === 1) {
        // Just seconds
        return parts[0];
    }

    return 0;
}

function formatSecondsToTime(totalSeconds) {
    const hours = Math.floor(totalSeconds / 3600);
    const minutes = Math.floor((totalSeconds % 3600) / 60);
    const seconds = totalSeconds % 60;

    return `${hours.toString().padStart(2, '0')}:${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`;
}
