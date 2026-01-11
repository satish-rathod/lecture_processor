/**
 * Scaler Companion - Content Script
 * Injects into Scaler Academy pages to detect lectures and capture stream URLs
 */

(function () {
    'use strict';

    // State
    let currentLecture = null;
    let capturedStreamInfo = null;
    let isLiveSession = false;
    let recordingUrl = null;
    let lastKnownUrl = window.location.href;
    let capturedUrls = new Set();  // Track already-captured URLs to avoid duplicates

    // ============================================
    // Navigation State Management (SPA fix)
    // ============================================

    /**
     * Reset all stream-related state when navigating to a new page.
     * This fixes the bug where the same video downloads every time.
     */
    function resetStreamState() {
        console.log('[Scaler Companion] Resetting stream state for new page');
        capturedStreamInfo = null;
        currentLecture = null;
        recordingUrl = null;
        isLiveSession = false;
        capturedUrls.clear();  // Clear captured URLs on navigation

        // Notify background worker to clear cached stream info for this tab
        chrome.runtime.sendMessage({
            action: 'pageNavigated'
        }).catch(() => { }); // Ignore if background not ready
    }

    /**
     * Check if URL has changed (SPA navigation detection)
     */
    function checkUrlChange() {
        const currentUrl = window.location.href;
        if (currentUrl !== lastKnownUrl) {
            console.log('[Scaler Companion] URL changed:', lastKnownUrl, '->', currentUrl);
            lastKnownUrl = currentUrl;
            resetStreamState();

            // Re-detect lecture after navigation with delay for page load
            setTimeout(() => {
                captureExistingRequests();
                detectLecture();
                monitorVideoElements();
            }, 1500);
        }
    }

    /**
     * Set up navigation listeners for SPA
     */
    function setupNavigationListeners() {
        // Override History API to detect pushState/replaceState
        const originalPushState = history.pushState;
        history.pushState = function (...args) {
            originalPushState.apply(this, args);
            setTimeout(checkUrlChange, 100);
        };

        const originalReplaceState = history.replaceState;
        history.replaceState = function (...args) {
            originalReplaceState.apply(this, args);
            setTimeout(checkUrlChange, 100);
        };

        // Listen for back/forward navigation
        window.addEventListener('popstate', () => {
            setTimeout(checkUrlChange, 100);
        });

        // Periodic check as fallback for edge cases
        setInterval(checkUrlChange, 3000);

        console.log('[Scaler Companion] Navigation listeners set up');
    }

    // ============================================
    // Page URL Validation
    // ============================================

    /**
     * Check if current page is a valid lecture page
     * Only capture stream URLs on these pages to avoid unnecessary processing
     */
    function isLecturePage() {
        const url = window.location.href;

        // Only pages with session?joinSession=1 are actual lecture recordings
        // Example: https://www.scaler.com/academy/mentee-dashboard/class/490078/session?joinSession=1
        return /\/class\/\d+\/session\?joinSession=1/.test(url);
    }

    // ============================================
    // Session Type Detection
    // ============================================

    function detectSessionType() {
        const url = window.location.href;

        // Check for actual live indicators (NOT joinSession param - that's used for recordings too)
        // A recording page has a video player with duration, live doesn't
        const videoElement = document.querySelector('video');
        const hasVideoDuration = videoElement && videoElement.duration && videoElement.duration > 0;

        // Check for live indicators in page content
        const liveIndicators = document.querySelectorAll('.live-indicator, [class*="is-live"], [class*="isLive"]');
        const hasLiveIndicator = liveIndicators.length > 0;

        // If we have a video with duration, it's definitely a recording
        if (hasVideoDuration) {
            isLiveSession = false;
            console.log('[Scaler Companion] Detected: RECORDING (video has duration)');
        } else if (url.includes('/recording')) {
            isLiveSession = false;
            console.log('[Scaler Companion] Detected: RECORDING (URL pattern)');
        } else if (hasLiveIndicator) {
            isLiveSession = true;
            console.log('[Scaler Companion] Detected: LIVE SESSION (live indicator found)');
        } else {
            // Default to recording - most common case
            isLiveSession = false;
            console.log('[Scaler Companion] Detected: RECORDING (default)');
        }

        return isLiveSession;
    }

    // ============================================
    // Capture previously loaded network requests
    // ============================================

    function captureExistingRequests() {
        // Only capture on valid lecture pages
        if (!isLecturePage()) {
            return;
        }

        // Use Performance API to get already-loaded resources
        if (window.performance && window.performance.getEntriesByType) {
            const resources = window.performance.getEntriesByType('resource');
            resources.forEach(resource => {
                const url = resource.name;
                if (url.includes('.m3u8')) {
                    captureStreamUrl(url);
                }
                if (url.includes('.ts') && url.includes('media.scaler.com')) {
                    captureSegmentUrl(url);
                }
                if (url.includes('protected-recordings') && url.includes('media.scaler.com')) {
                    captureRecordingUrl(url);
                }
            });
        }
    }

    // ============================================
    // Stream URL Interception
    // ============================================

    // Intercept fetch requests to capture HLS stream URLs
    const originalFetch = window.fetch;
    window.fetch = async function (...args) {
        const [url] = args;

        if (typeof url === 'string') {
            // Capture HLS stream URLs
            if (url.includes('.m3u8') || url.includes('/stream_')) {
                captureStreamUrl(url);
            }

            // Capture video segment URLs for authentication tokens
            if (url.includes('.ts') && (url.includes('Key-Pair-Id') || url.includes('media.scaler.com'))) {
                captureSegmentUrl(url);
            }

            // Capture recording URLs from media.scaler.com
            if (url.includes('media.scaler.com') && url.includes('protected-recordings')) {
                captureRecordingUrl(url);
            }
        }

        return originalFetch.apply(this, args);
    };

    // Intercept XHR for older implementations
    const originalXHROpen = XMLHttpRequest.prototype.open;
    XMLHttpRequest.prototype.open = function (method, url, ...rest) {
        if (typeof url === 'string') {
            if (url.includes('.m3u8') || url.includes('/stream_')) {
                captureStreamUrl(url);
            }
            if (url.includes('.ts') && (url.includes('Key-Pair-Id') || url.includes('media.scaler.com'))) {
                captureSegmentUrl(url);
            }
            if (url.includes('media.scaler.com') && url.includes('protected-recordings')) {
                captureRecordingUrl(url);
            }
        }
        return originalXHROpen.apply(this, [method, url, ...rest]);
    };

    function captureRecordingUrl(url) {
        // Skip if already captured this URL
        if (capturedUrls.has(url)) return;
        capturedUrls.add(url);

        console.log('[Scaler Companion] Captured recording URL:', url);
        recordingUrl = url;

        // Extract base URL and auth from recording URL
        try {
            const urlObj = new URL(url);
            if (!capturedStreamInfo) {
                capturedStreamInfo = {};
            }

            // Get the stream path (e.g., /production/protected-recordings/...)
            const pathMatch = url.match(/(https:\/\/media\.scaler\.com\/[^?]+)/);
            if (pathMatch) {
                const basePath = pathMatch[1].replace(/data\d+\.ts$/, '').replace(/[^/]+\.m3u8$/, '');
                capturedStreamInfo.baseUrl = basePath;
            }

            capturedStreamInfo.keyPairId = urlObj.searchParams.get('Key-Pair-Id');
            capturedStreamInfo.policy = urlObj.searchParams.get('Policy');
            capturedStreamInfo.signature = urlObj.searchParams.get('Signature');

            console.log('[Scaler Companion] Recording stream info captured:', capturedStreamInfo);

            // Notify background worker
            chrome.runtime.sendMessage({
                action: 'recordingCaptured',
                url: url,
                streamInfo: capturedStreamInfo
            });
        } catch (error) {
            console.error('[Scaler Companion] Error parsing recording URL:', error);
        }
    }

    function captureStreamUrl(url) {
        // Skip if already captured this URL
        if (capturedUrls.has(url)) return;
        capturedUrls.add(url);

        console.log('[Scaler Companion] Captured stream URL:', url);

        if (!capturedStreamInfo) {
            capturedStreamInfo = {};
        }
        capturedStreamInfo.streamUrl = url;

        // Notify background worker
        chrome.runtime.sendMessage({
            action: 'streamCaptured',
            url: url
        });
    }

    function captureSegmentUrl(url) {
        // Skip if already captured this URL
        if (capturedUrls.has(url)) return;
        capturedUrls.add(url);

        console.log('[Scaler Companion] Captured segment URL:', url);

        try {
            const urlObj = new URL(url);
            const params = urlObj.searchParams;

            if (!capturedStreamInfo) {
                capturedStreamInfo = {};
            }

            // Extract authentication tokens
            capturedStreamInfo.keyPairId = params.get('Key-Pair-Id');
            capturedStreamInfo.policy = params.get('Policy');
            capturedStreamInfo.signature = params.get('Signature');

            // Extract base URL - handle different URL patterns
            const tsMatch = url.match(/(.+\/)data\d+\.ts/);
            if (tsMatch) {
                capturedStreamInfo.baseUrl = tsMatch[1];
            }

            // Try to extract chunk number from URL pattern
            const chunkMatch = url.match(/data(\d+)\.ts/);
            if (chunkMatch) {
                const chunkNum = parseInt(chunkMatch[1], 10);
                capturedStreamInfo.detectedChunk = chunkNum;
            }

            console.log('[Scaler Companion] Stream info updated:', capturedStreamInfo);

            // Notify background worker
            chrome.runtime.sendMessage({
                action: 'authCaptured',
                auth: capturedStreamInfo
            });
        } catch (error) {
            console.error('[Scaler Companion] Error parsing segment URL:', error);
        }
    }

    // ============================================
    // Find Recording Link on Page
    // ============================================

    function findRecordingLink() {
        // Look for recording links in the page
        const recordingSelectors = [
            'a[href*="/recording"]',
            'a[href*="recordings"]',
            '[class*="recording"] a',
            'button[class*="recording"]'
        ];

        for (const selector of recordingSelectors) {
            const el = document.querySelector(selector);
            if (el) {
                const href = el.href || el.getAttribute('data-url');
                if (href) {
                    console.log('[Scaler Companion] Found recording link:', href);
                    return href;
                }
            }
        }

        return null;
    }

    // ============================================
    // Lecture Detection
    // ============================================

    function detectLecture() {
        // Detect session type first
        detectSessionType();

        const lecture = {
            hasLecture: false,
            title: null,
            duration: null,
            url: window.location.href,
            streamInfo: capturedStreamInfo,
            isLiveSession: isLiveSession,
            recordingAvailable: !!recordingUrl || !isLiveSession,
            recordingLink: findRecordingLink()
        };

        // URL-based detection for Scaler pages
        const url = window.location.href;
        const urlPatterns = [
            /\/class\/\d+\/session/,      // Session pages
            /\/class\/\d+\/recording/,    // Recording pages
            /\/recordings\//,             // Recordings list
            /\/lecture\//,                // Lecture pages
            /\/session\//,                // Session pages (alt)
            /\/mentee-dashboard\/class/   // Mentee dashboard class
        ];

        const matchedUrl = urlPatterns.some(pattern => pattern.test(url));
        if (matchedUrl) {
            lecture.hasLecture = true;
            console.log('[Scaler Companion] URL pattern matched');
        }

        // Try multiple selectors to find lecture title
        const titleSelectors = [
            '.lecture-title',
            '.video-title',
            '[data-lecture-title]',
            'h1.title',
            '.session-title',
            '.class-title',
            '.header-title',
            '[class*="lecture-name"]',
            '[class*="session-name"]',
            '[class*="class-name"]',
            // Scaler specific selectors based on screenshot
            '.lecture-header h1',
            '.lecture-header span',
            'header h1',
            '[class*="header"] h1',
            '[class*="Header"] h1'
        ];

        for (const selector of titleSelectors) {
            try {
                const el = document.querySelector(selector);
                if (el && el.textContent.trim()) {
                    lecture.title = el.textContent.trim();
                    lecture.hasLecture = true;
                    console.log('[Scaler Companion] Title found via selector:', selector, lecture.title);
                    break;
                }
            } catch (e) {
                // Skip invalid selectors
            }
        }

        // Try to get title from page title (e.g., "Lecture | Kaggle3 - Class...")
        if (!lecture.title && document.title) {
            const pageTitle = document.title;
            // Extract from patterns like "Lecture | Name" or "Name - Scaler"
            const titleMatch = pageTitle.match(/^(?:Lecture\s*\|\s*)?([^|\-]+)/);
            if (titleMatch) {
                lecture.title = titleMatch[1].trim();
                if (lecture.title.toLowerCase().includes('scaler')) {
                    // If just "Scaler", try other part
                    const parts = pageTitle.split(/[|\-]/);
                    if (parts.length > 1) {
                        lecture.title = parts[0].trim() || parts[1].trim();
                    }
                }
                if (lecture.title && !lecture.title.toLowerCase().includes('scaler')) {
                    lecture.hasLecture = true;
                    console.log('[Scaler Companion] Title from page title:', lecture.title);
                }
            }
        }

        // Check for video/stream elements
        const videoSelectors = [
            'video',
            '.video-player',
            '.lecture-player',
            '[class*="video"]',
            '[class*="player"]',
            'iframe[src*="zoom"]',
            'iframe[src*="meet"]',
            '[class*="stream"]',
            '[class*="Stream"]'
        ];

        for (const selector of videoSelectors) {
            try {
                const videoPlayer = document.querySelector(selector);
                if (videoPlayer) {
                    lecture.hasLecture = true;
                    console.log('[Scaler Companion] Video element found:', selector);

                    // Try to get duration if it's a video element
                    if (videoPlayer.tagName === 'VIDEO' && videoPlayer.duration) {
                        lecture.duration = videoPlayer.duration;
                    }
                    break;
                }
            } catch (e) {
                // Skip invalid selectors
            }
        }

        // Add stream info if captured
        if (capturedStreamInfo && Object.keys(capturedStreamInfo).length > 0) {
            lecture.streamInfo = capturedStreamInfo;
            lecture.hasLecture = true;
            lecture.recordingAvailable = true;
            console.log('[Scaler Companion] Stream info available');
        }

        // Final fallback: if we're on scaler.com and have class/session in URL
        if (!lecture.hasLecture && url.includes('scaler.com') &&
            (url.includes('/class/') || url.includes('/session'))) {
            lecture.hasLecture = true;
            lecture.title = lecture.title || 'Scaler Class Session';
            console.log('[Scaler Companion] Fallback detection for class URL');
        }

        currentLecture = lecture;
        console.log('[Scaler Companion] Detection result:', lecture);
        return lecture;
    }

    // ============================================
    // UI Injection
    // ============================================

    function injectDownloadButton() {
        // Don't inject if already exists
        if (document.getElementById('scaler-companion-btn')) {
            return;
        }

        // Check if we're on a lecture page
        const lecture = detectLecture();
        if (!lecture.hasLecture) {
            return;
        }

        // Find a suitable container
        const containers = [
            '.video-controls',
            '.player-controls',
            '.lecture-actions',
            '.video-player-container',
            '.lecture-header'
        ];

        let targetContainer = null;
        for (const selector of containers) {
            targetContainer = document.querySelector(selector);
            if (targetContainer) break;
        }

        if (!targetContainer) {
            // Create floating button if no container found
            injectFloatingButton();
            return;
        }

        // Create download button
        const btn = createDownloadButton();
        targetContainer.appendChild(btn);
    }

    function injectFloatingButton() {
        const btn = createDownloadButton();
        btn.classList.add('floating');
        document.body.appendChild(btn);
    }

    function createDownloadButton() {
        const btn = document.createElement('button');
        btn.id = 'scaler-companion-btn';
        btn.innerHTML = `
      <span class="sc-icon">⬇️</span>
      <span class="sc-text">Download</span>
    `;
        btn.title = 'Download with Scaler Companion';

        btn.addEventListener('click', () => {
            chrome.runtime.sendMessage({
                action: 'downloadFromPage',
                lecture: currentLecture
            });
        });

        return btn;
    }

    // ============================================
    // Message Handling
    // ============================================

    chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
        switch (message.action) {
            case 'getLectureInfo':
                const lecture = detectLecture();
                sendResponse(lecture);
                break;

            case 'getStreamInfo':
                sendResponse(capturedStreamInfo);
                break;

            case 'ping':
                sendResponse({ pong: true });
                break;

            default:
                sendResponse({ error: 'Unknown action' });
        }

        return true; // Keep channel open for async response
    });

    // ============================================
    // Initialization
    // ============================================

    function init() {
        console.log('[Scaler Companion] Content script loaded');

        // Set up SPA navigation detection FIRST
        setupNavigationListeners();

        // Capture any requests that happened before script loaded
        captureExistingRequests();

        // Initial detection
        detectLecture();

        // Wait for dynamic content and try again
        setTimeout(() => {
            captureExistingRequests();
            detectLecture();
            injectDownloadButton();
            monitorVideoElements();
        }, 2000);

        // Observe DOM changes for SPA navigation
        const observer = new MutationObserver((mutations) => {
            // Debounce detection
            clearTimeout(window._scCompanionDebounce);
            window._scCompanionDebounce = setTimeout(() => {
                // Check for URL change first
                checkUrlChange();
                captureExistingRequests();
                detectLecture();
                injectDownloadButton();
            }, 500);
        });

        observer.observe(document.body, {
            childList: true,
            subtree: true
        });
    }

    // Monitor video elements for their source URLs
    function monitorVideoElements() {
        const videos = document.querySelectorAll('video');
        videos.forEach(video => {
            // Check video src
            if (video.src && video.src.includes('blob:')) {
                console.log('[Scaler Companion] Found blob video src - HLS is being used');
            }

            // Check source elements
            const sources = video.querySelectorAll('source');
            sources.forEach(source => {
                const src = source.src;
                if (src && (src.includes('.m3u8') || src.includes('media.scaler.com'))) {
                    console.log('[Scaler Companion] Found video source:', src);
                    captureStreamUrl(src);
                }
            });

            // Add event listener for when video loads new source
            video.addEventListener('loadedmetadata', () => {
                console.log('[Scaler Companion] Video metadata loaded, duration:', video.duration);
                captureExistingRequests();
                detectLecture();
            });
        });
    }

    // Run when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
