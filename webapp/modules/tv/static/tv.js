const state = {
  streams: [],
  selectedIndex: 0,
};

const streamList = document.getElementById('stream-list');
const form = document.getElementById('add-stream-form');
const statusEl = document.getElementById('stream-form-status');
const viewerTitle = document.getElementById('viewer-title');
const deleteBtn = document.getElementById('delete-stream-btn');
const streamFrame = document.getElementById('stream-frame');

function setStatus(message, isError = false) {
  statusEl.textContent = message || '';
  statusEl.style.color = isError ? '#ff8a8a' : '#8ec7ff';
}

function renderSidebar() {
  if (!streamList) return;
  streamList.innerHTML = '';

  state.streams.forEach((stream, index) => {
    const item = document.createElement('button');
    item.type = 'button';
    item.className = 'stream-item' + (index === state.selectedIndex ? ' active' : '');
    item.dataset.index = String(index);

    item.innerHTML = `
      <span class="stream-name">${escapeHtml(stream.name || 'Unnamed stream')}</span>
      <span class="stream-source">${escapeHtml(stream.source || 'custom')}</span>
    `;

    item.addEventListener('click', () => {
      state.selectedIndex = index;
      renderSidebar();
      renderSelectedStream();
    });

    streamList.appendChild(item);
  });
}

function escapeHtml(value) {
  return String(value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

function renderSelectedStream() {
  const selected = state.streams[state.selectedIndex];

  if (!selected) {
    viewerTitle.textContent = 'No stream selected';
    deleteBtn.disabled = true;
    if (streamFrame) {
      streamFrame.src = 'about:blank';
    }
    return;
  }

  viewerTitle.textContent = selected.name || 'Unnamed stream';
  deleteBtn.disabled = false;

  if (streamFrame) {
    streamFrame.src = selected.url;
    streamFrame.title = selected.name || 'Stream';
  }
}

async function loadStreams() {
  const response = await fetch('/api/tv/streams');
  const payload = await response.json();
  state.streams = payload.streams || [];
  if (state.selectedIndex >= state.streams.length) {
    state.selectedIndex = 0;
  }
  renderSidebar();
  renderSelectedStream();
}

form.addEventListener('submit', async (event) => {
  event.preventDefault();
  const formData = new FormData(form);
  const payload = {
    name: formData.get('name') || '',
    url: formData.get('url') || '',
    iframe_html: formData.get('iframe_html') || '',
  };

  if (!payload.url && !payload.iframe_html) {
    setStatus('Please provide a URL or iframe snippet.', true);
    return;
  }

  const response = await fetch('/api/tv/streams', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });

  const body = await response.json();
  if (!response.ok) {
    setStatus(body.error || 'Could not save stream.', true);
    return;
  }

  state.streams = body.streams || [];
  state.selectedIndex = Math.max(0, state.streams.length - 1);
  renderSidebar();
  renderSelectedStream();
  form.reset();
  setStatus('Stream saved.');
});

deleteBtn.addEventListener('click', async () => {
  const selected = state.streams[state.selectedIndex];
  if (!selected) return;

  const response = await fetch(`/api/tv/streams/${state.selectedIndex}`, { method: 'DELETE' });
  const payload = await response.json();
  state.streams = payload.streams || [];
  state.selectedIndex = Math.min(state.selectedIndex, Math.max(0, state.streams.length - 1));
  renderSidebar();
  renderSelectedStream();
});

loadStreams();
