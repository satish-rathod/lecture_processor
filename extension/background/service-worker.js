/**
 * Scaler Companion - Background Service Worker
 * Handles communication between popup, content scripts, and backend API
 */

// Constants
const BACKEND_URL = 'http://localhost:8000';
const API_ENDPOINTS = {
    health: `${BACKEND_URL}/health`,
    download: `${BACKEND_URL}/api/download`,
    process: `${BACKEND_URL}/api/process`,
    status: `${BACKEND_URL}/api/status`,
};

// State
let capturedStreams = new Map();
let activeDownloads = new Map();

// ============================================
// Message Handling
// ============================================

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    console.log('[Background] Received message:', message.action);

    switch (message.action) {
        case 'streamCaptured':
            handleStreamCapture(message, sender);
            sendResponse({ success: true });
            break;

        case 'authCaptured':
            handleAuthCapture(message, sender);
            sendResponse({ success: true });
            break;

        case 'pageNavigated':
            // Content script detected SPA navigation - clear cached stream data
            handlePageNavigated(sender);
            sendResponse({ success: true });
            break;

        case 'startDownload':
            handleStartDownload(message, sendResponse);
            return true; // Keep channel open for async

        case 'downloadFromPage':
            handleDownloadFromPage(message, sender, sendResponse);
            return true;

        case 'startProcessing':
            handleStartProcessing(message, sendResponse);
            return true;

        case 'getDownloadStatus':
            handleGetDownloadStatus(message, sendResponse);
            return true;

        default:
            sendResponse({ error: 'Unknown action' });
    }

    return false;
});

// ============================================
// Stream Capture Handlers
// ============================================

function handleStreamCapture(message, sender) {
    const tabId = sender.tab?.id;
    if (!tabId) return;

    if (!capturedStreams.has(tabId)) {
        capturedStreams.set(tabId, {});
    }

    capturedStreams.get(tabId).streamUrl = message.url;
    console.log('[Background] Stream captured for tab', tabId);
}

function handleAuthCapture(message, sender) {
    const tabId = sender.tab?.id;
    if (!tabId) return;

    if (!capturedStreams.has(tabId)) {
        capturedStreams.set(tabId, {});
    }

    Object.assign(capturedStreams.get(tabId), message.auth);
    console.log('[Background] Auth captured for tab', tabId);
}

function handlePageNavigated(sender) {
    const tabId = sender.tab?.id;
    if (!tabId) return;

    if (capturedStreams.has(tabId)) {
        capturedStreams.delete(tabId);
        console.log('[Background] Cleared stream data on SPA navigation for tab', tabId);
    }
}

// ============================================
// Download Handlers
// ============================================

async function handleStartDownload(message, sendResponse) {
    try {
        const { lecture, devMode, startTime, endTime } = message;

        // Check backend health
        const healthCheck = await fetch(API_ENDPOINTS.health);
        if (!healthCheck.ok) {
            throw new Error('Backend server is not running');
        }

        // Get active tab to look up captured stream data
        const [activeTab] = await chrome.tabs.query({ active: true, currentWindow: true });
        const tabId = activeTab?.id;

        // IMPORTANT: Use capturedStreams as source of truth, not popup's stale data!
        // The popup's currentLecture.streamInfo might be stale if user navigated
        let streamInfo = {};

        if (tabId && capturedStreams.has(tabId)) {
            // Use the LATEST captured stream info for this tab
            streamInfo = capturedStreams.get(tabId);
            console.log('[Background] Using capturedStreams for tab', tabId, streamInfo);
        } else if (lecture.streamInfo) {
            // Fallback to popup's data if no captured stream
            streamInfo = lecture.streamInfo;
            console.log('[Background] Using popup streamInfo (no captured stream for tab)', tabId);
        }

        console.log('[Background] Final streamInfo baseUrl:', streamInfo.baseUrl);

        if (!streamInfo.baseUrl && !streamInfo.streamUrl) {
            throw new Error('No stream URL captured. Please play the video first.');
        }

        // Build request body with dev mode settings
        const requestBody = {
            title: lecture.title || 'Untitled Lecture',
            url: lecture.url,
            streamInfo: streamInfo,
            devMode: devMode || false,
            startTime: startTime || null,
            endTime: endTime || null
        };

        console.log('[Background] Download request:', { devMode, startTime, endTime });

        // Send download request to backend
        const response = await fetch(API_ENDPOINTS.download, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(requestBody),
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Download request failed');
        }

        const result = await response.json();

        // Track active download
        activeDownloads.set(result.downloadId, {
            title: lecture.title,
            startTime: Date.now(),
            status: 'downloading'
        });

        sendResponse({
            success: true,
            downloadId: result.downloadId
        });

    } catch (error) {
        console.error('[Background] Download error:', error);
        sendResponse({
            success: false,
            error: error.message
        });
    }
}

async function handleDownloadFromPage(message, sender, sendResponse) {
    try {
        const tabId = sender.tab?.id;
        const lecture = message.lecture;

        // Merge with any captured stream info
        if (tabId && capturedStreams.has(tabId)) {
            lecture.streamInfo = {
                ...lecture.streamInfo,
                ...capturedStreams.get(tabId)
            };
        }

        // Forward to main download handler
        await handleStartDownload({ lecture }, sendResponse);

    } catch (error) {
        console.error('[Background] Download from page error:', error);
        sendResponse({
            success: false,
            error: error.message
        });
    }
}

async function handleGetDownloadStatus(message, sendResponse) {
    try {
        const { downloadId } = message;

        const response = await fetch(`${API_ENDPOINTS.status}/${downloadId}`);
        if (!response.ok) {
            throw new Error('Failed to get status');
        }

        const status = await response.json();
        sendResponse(status);

    } catch (error) {
        console.error('[Background] Status check error:', error);
        sendResponse({
            status: 'error',
            error: error.message
        });
    }
}

// ============================================
// Processing Handlers
// ============================================

async function handleStartProcessing(message, sendResponse) {
    try {
        const { lecture, options } = message;

        const response = await fetch(API_ENDPOINTS.process, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                title: lecture.title,
                videoPath: lecture.downloadPath,
                options: options
            }),
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Processing request failed');
        }

        const result = await response.json();

        sendResponse({
            success: true,
            processId: result.processId,
            resultsUrl: `${BACKEND_URL}/results/${result.processId}`
        });

    } catch (error) {
        console.error('[Background] Processing error:', error);
        sendResponse({
            success: false,
            error: error.message
        });
    }
}

// ============================================
// Tab Management
// ============================================

chrome.tabs.onRemoved.addListener((tabId) => {
    // Clean up captured streams for closed tabs
    if (capturedStreams.has(tabId)) {
        capturedStreams.delete(tabId);
        console.log('[Background] Cleaned up stream data for tab', tabId);
    }
});

chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
    // Clear stream data on navigation
    if (changeInfo.url && capturedStreams.has(tabId)) {
        capturedStreams.delete(tabId);
        console.log('[Background] Cleared stream data on navigation', tabId);
    }
});

// ============================================
// Initialization
// ============================================

console.log('[Scaler Companion] Background service worker started');

// Check backend health on startup
fetch(API_ENDPOINTS.health)
    .then(res => res.ok ? console.log('[Background] Backend is online') : console.log('[Background] Backend is offline'))
    .catch(() => console.log('[Background] Backend is offline'));
