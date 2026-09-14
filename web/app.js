let currentJobId = null;
let pollInterval = null;

const urlInput = document.getElementById('urlInput');
const checkBtn = document.getElementById('checkBtn');
const downloadBtn = document.getElementById('downloadBtn');
const infoPanel = document.getElementById('infoPanel');
const infoTitle = document.getElementById('infoTitle');
const infoSource = document.getElementById('infoSource');
const infoDetails = document.getElementById('infoDetails');
const infoDesc = document.getElementById('infoDesc');
const infoTags = document.getElementById('infoTags');
const progressSection = document.getElementById('progressSection');
const progressBar = document.getElementById('progressBar');
const progressText = document.getElementById('progressText');
const progressPercent = document.getElementById('progressPercent');
const resultSection = document.getElementById('resultSection');
const resultTitle = document.getElementById('resultTitle');
const resultMessage = document.getElementById('resultMessage');
const downloadLink = document.getElementById('downloadLink');
const errorSection = document.getElementById('errorSection');
const errorTitle = document.getElementById('errorTitle');
const errorMessage = document.getElementById('errorMessage');
const pollingOverlay = document.getElementById('pollingOverlay');

async function checkInfo() {
    const url = urlInput.value.trim();
    if (!url) return;

    try {
        const res = await fetch('/api/info', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ url })
        });
        const data = await res.json();
        if (data.error) { showError('Could not fetch info', data.error); return; }
        renderInfo(data);
        infoPanel.classList.remove('hidden');
        downloadBtn.style.display = 'inline-flex';
        window.scrollTo({ top: infoPanel.offsetTop - 20, behavior: 'smooth' });
    } catch (e) {
        showError('Network error', e.message);
    }
}

function renderInfo(data) {
    infoTitle.textContent = data.title || 'Unknown';
    infoSource.textContent = data.source || '';

    let html = '';
    const items = [
        { label: 'Channel', value: data.channel },
        { label: 'Upload', value: data.upload_date },
        { label: 'Duration', value: data.duration ? formatDuration(data.duration) : null },
        { label: 'Views', value: data.view_count ? formatNumber(data.view_count) : null },
        { label: 'Likes', value: data.like_count ? formatNumber(data.like_count) : null },
        { label: 'Comments', value: data.comment_count ? formatNumber(data.comment_count) : null },
        { label: 'Category', value: data.category },
    ];
    items.forEach(item => {
        if (item.value) {
            html += `<div class="info-item"><div class="label">${item.label}</div><div class="value">${item.value}</div></div>`;
        }
    });
    infoDetails.innerHTML = html;

    const desc = data.description || '';
    infoDesc.textContent = desc ? desc.substring(0, 300) + (desc.length > 300 ? '...' : '') : '';

    const tags = data.tags || [];
    if (tags.length) {
        infoTags.innerHTML = tags.slice(0, 8).map(t => `<span class="tag">${t}</span>`).join('');
    } else {
        infoTags.innerHTML = '';
    }
}

async function startDownload() {
    const url = urlInput.value.trim();
    if (!url) return;

    downloadBtn.style.display = 'none';
    pollingOverlay.classList.remove('hidden');
    progressSection.classList.remove('hidden');
    infoPanel.classList.add('hidden');
    resultSection.classList.add('hidden');
    errorSection.classList.add('hidden');
    progressBar.style.width = '0%';
    progressPercent.textContent = '0%';

    try {
        const res = await fetch('/api/download', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ url })
        });
        const data = await res.json();
        if (data.error) { showError('Download failed', data.error); return; }
        currentJobId = data.job_id;
        pollJob();
    } catch (e) {
        showError('Network error', e.message);
    }
}

function pollJob() {
    pollInterval = setInterval(async () => {
        try {
            const res = await fetch(`/api/status/${currentJobId}`);
            const data = await res.json();
            if (!data) return;

            const pct = data.progress || 0;
            progressBar.style.width = pct + '%';
            progressPercent.textContent = pct + '%';
            progressText.textContent = data.message || 'Processing...';

            if (data.status === 'complete') {
                clearInterval(pollInterval);
                pollingOverlay.classList.add('hidden');
                downloadLink.href = `/api/download/${currentJobId}`;
                resultTitle.textContent = 'Done!';
                resultMessage.textContent = data.message || 'All tracks zipped.';
                resultSection.classList.remove('hidden');
            } else if (data.status === 'failed') {
                clearInterval(pollInterval);
                pollingOverlay.classList.add('hidden');
                showError('Download failed', data.message || 'Unknown error');
            }
        } catch (e) {
            console.error('Poll error:', e);
        }
    }, 2000);
}

function showError(title, message) {
    pollingOverlay.classList.add('hidden');
    progressSection.classList.add('hidden');
    resultSection.classList.add('hidden');
    errorSection.classList.remove('hidden');
    errorTitle.textContent = title;
    errorMessage.textContent = message;
}

function resetPage() {
    if (pollInterval) clearInterval(pollInterval);
    if (currentJobId) {
        fetch(`/api/cleanup/${currentJobId}`, { method: 'DELETE' }).catch(() => {});
    }
    currentJobId = null;
    urlInput.value = '';
    infoPanel.classList.add('hidden');
    downloadBtn.style.display = 'none';
    progressSection.classList.add('hidden');
    resultSection.classList.add('hidden');
    errorSection.classList.add('hidden');
    pollingOverlay.classList.add('hidden');
    progressBar.style.width = '0%';
    progressPercent.textContent = '0%';
}

function formatNumber(n) {
    if (!n) return '0';
    n = Math.floor(n);
    if (n >= 1000000) return (n / 1000000).toFixed(1) + 'M';
    if (n >= 1000) return (n / 1000).toFixed(1) + 'K';
    return n.toString();
}

function formatDuration(seconds) {
    if (!seconds) return 'N/A';
    const s = Math.floor(seconds);
    const h = Math.floor(s / 3600);
    const m = Math.floor((s % 3600) / 60);
    if (h > 0) return `${h}:${String(m).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`;
    return `${m}:${String(s % 60).padStart(2, '0')}`;
}
