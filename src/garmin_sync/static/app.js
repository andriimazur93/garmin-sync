'use strict';

let current = null;
let timer = null;
let inFlight = null;
let changing = false;
let filter = 'all';
const rows = new Map();
const byId = id => document.getElementById(id);
const titles = {all: 'Songs', watch: 'On watch', pending: 'Pending changes', attention: 'Needs attention'};

function node(tag, text, className) {
  const element = document.createElement(tag);
  if (text !== undefined && text !== null) element.textContent = String(text);
  if (className) element.className = className;
  return element;
}
function say(id, message) {
  if (byId(id).textContent !== String(message)) byId(id).textContent = String(message);
}
function action(label, callback, key) {
  const button = node('button', label, 'track-action');
  button.type = 'button'; button.dataset.focus = key; button.dataset.mutation = '';
  button.addEventListener('click', callback);
  return button;
}
function allItems(data) {
  const items = data.tracks.map(track => ({...track, key: 'track:' + track.track_id}));
  const known = new Set(data.tracks.map(track => track.track_id));
  for (const entry of data.inventory || []) {
    if (entry.track_id === null || !known.has(entry.track_id)) {
      items.push({key: 'cache:' + entry.cache_id, filename: entry.filename || 'Unknown cache entry',
        unknown: true, observed: true, available: false});
    }
  }
  return items;
}
function inView(item) {
  const matches = filter === 'all' || (filter === 'watch' && item.observed === true) ||
    (filter === 'pending' && (item.pending_download || item.pending_removal)) ||
    (filter === 'attention' && (item.unknown || !item.available || item.last_error));
  return matches && item.filename.toLocaleLowerCase().includes(byId('search').value.toLocaleLowerCase().trim());
}
function buildRow(track) {
  const row = node('tr');
  const number = node('td', '', 'number');
  const name = node('td', track.filename, 'filename');
  if (!track.available && !track.unknown) name.append(node('span', 'PC source unavailable', 'source-note'));
  const size = node('td', track.size_bytes ? formatSize(track.size_bytes) : '—', 'size');
  const status = node('td', null, 'track-status');
  const choices = node('td', null, 'actions');
  if (track.unknown) {
    status.append(node('span', 'Unknown cache entry — retained', 'warning'));
    choices.append(node('span', 'Retained', 'muted'));
  } else {
    const observation = track.observed === null ? 'Watch inventory unknown' :
      track.observed ? 'On watch in last report' : 'Absent from last report';
    if (track.pending_download) status.append(node('span', 'Download requested', 'requested'));
    if (track.pending_removal) status.append(node('span', 'Removal requested', 'warning'));
    status.append(node('span', observation, track.pending_download || track.pending_removal ? 'status-detail' : 'observation'));
    if (track.last_error) status.append(node('span', 'Last error: ' + track.last_error, 'error status-detail'));
    const choose = (label, present, message) => choices.append(action(label,
      () => setDesired(track.track_id, present, message), track.key + ':' + label));
    if (track.pending_removal) {
      if (track.available) choose('Keep on watch', true, 'Removal request cancelled. Start Sync on your watch.');
      else choices.append(node('span', 'Removal requested', 'muted'));
    } else if (track.observed === true) {
      choose('Remove watch copy', false, 'Removal requested. PC original stays unchanged. Start Sync on your watch.');
    } else if (track.desired === true) {
      choose('Cancel download request', false, 'Download request cancelled. Start Sync on your watch to reconcile.');
    } else if (track.available) {
      choose('Download to watch', true, 'Download requested. Start Sync on your watch.');
    } else choices.append(node('span', 'Source unavailable', 'muted'));
  }
  row.append(number, name, size, status, choices);
  return row;
}
function formatSize(bytes) {
  return bytes < 1000000 ? (bytes / 1000).toFixed(0) + ' KB' : (bytes / 1000000).toFixed(1) + ' MB';
}
function focusView() { document.querySelector(`[data-filter="${filter}"]`).focus({preventScroll: true}); }
function renderLibrary(items) {
  const focused = document.activeElement;
  const focusKey = focused?.dataset.focus;
  const body = byId('library-body');
  const visible = items.filter(inView);
  const keys = new Set(visible.map(item => item.key));
  // Remove obsolete rows first, so later rows need not move past them.
  for (const [key, record] of rows) {
    if (!keys.has(key)) {record.element.remove(); rows.delete(key);}
  }
  let position = 0;
  for (const item of visible) {
    const signature = JSON.stringify(item);
    let record = rows.get(item.key);
    if (!record || record.signature !== signature) {
      const element = buildRow(item);
      if (record) record.element.replaceWith(element);
      record = {element, signature}; rows.set(item.key, record);
    }
    // Leave unchanged nodes in place: polling must not discard keyboard focus.
    const expected = body.children[position];
    if (expected !== record.element) body.insertBefore(record.element, expected || null);
    record.element.firstChild.textContent = String(++position);
  }
  if (focusKey && document.activeElement !== focused) {
    const replacement = [...body.querySelectorAll('[data-focus]')].find(b => b.dataset.focus === focusKey);
    if (replacement) replacement.focus({preventScroll: true}); else focusView();
  }
  byId('library-table').hidden = position === 0;
  byId('empty').hidden = position !== 0;
  let empty = 'No music matches this search and view.';
  if (!byId('search').value.trim()) {
    if (filter === 'watch') empty = current.inventory === null ?
      'Watch inventory is unknown. Sync your watch to report its contents.' : 'No tracks in the last complete watch report.';
    else if (filter === 'pending') empty = 'No pending changes. Choose music in Songs to request a download.';
    else if (filter === 'attention') empty = 'No tracks need attention.';
    else if (!items.length) empty = 'No MP3 files indexed. Add music to your configured folder, then rescan.';
  }
  say('empty', empty);
  say('view-count', position + (position === 1 ? ' song' : ' songs'));
}
function renderAssociation(data) {
  const association = data.association;
  const message = association === null ? 'Sync your watch once to establish its connection.' :
    association.confirmed ? 'Watch connection confirmed. This does not indicate a live watch connection.' :
      'New watch connection. Removals are paused until you confirm the watch that most recently synced.';
  say('association-state', message);
  const root = byId('association');
  const signature = JSON.stringify(association);
  if (root.dataset.signature === signature) return;
  root.dataset.signature = signature;
  root.replaceChildren(); root.hidden = !!association?.confirmed;
  if (root.hidden) return;
  root.append(node('p', message));
  if (association) {
    const pair = {server_id: association.server_id, device_epoch: association.device_epoch};
    root.append(action('Confirm watch connection', () => mutate('/api/local/association/confirm', 'POST', pair,
      'Watch connection confirmed. Start another sync to apply removal requests.'), 'confirm-association'));
  }
}
function disableMutations() {
  document.querySelectorAll('[data-mutation]').forEach(button => {button.disabled = changing || current === null;});
}
function render(data) {
  const items = allItems(data);
  const downloads = data.tracks.filter(t => t.pending_download).length;
  const removals = data.tracks.filter(t => t.pending_removal).length;
  say('all-count', items.length);
  say('watch-count', data.inventory === null ? 'Unknown' : data.inventory.length);
  say('pending-count', downloads + removals);
  say('attention-count', items.filter(t => t.unknown || !t.available || t.last_error).length);
  say('pending-summary', downloads + removals ?
    `${downloads} ${downloads === 1 ? 'download' : 'downloads'} and ${removals} ${removals === 1 ? 'removal' : 'removals'} pending` : 'No pending changes');
  say('sync-guidance', downloads + removals ? 'Start Sync on your watch to apply your choices. Changes made during a sync may need another sync.' :
    'Choose music below. Start Sync on your watch to refresh its report.');
  byId('review').hidden = downloads + removals === 0;
  say('view-title', titles[filter]);
  document.querySelectorAll('[data-filter]').forEach(button => {
    const active = button.dataset.filter === filter;
    button.classList.toggle('active', active); button.setAttribute('aria-pressed', String(active));
  });
  say('reported-time', data.reported_at === null ? 'Watch inventory unknown. No complete report yet.' :
    `Last complete watch report: ${new Date(data.reported_at).toLocaleString()} · ${data.inventory.length} tracks`);
  const labels = {in_progress: 'In progress; new choices may need another sync', expired: 'Expired; start a new sync',
    success: 'Completed', failed: 'Failed; pending choices remain', cancelled: 'Cancelled; check pending choices'};
  say('sync-outcome', data.latest_sync ? 'Latest sync: ' + (labels[data.latest_sync.outcome] || data.latest_sync.outcome) : 'No sync recorded yet.');
  renderAssociation(data); renderLibrary(items); disableMutations();
  byId('library').setAttribute('aria-busy', 'false');
}
async function jsonRequest(path, options = {}) {
  const response = await fetch(path, {cache: 'no-store', ...options});
  let body;
  try { body = await response.json(); } catch { throw new Error('The local server returned an invalid response.'); }
  if (!response.ok) throw new Error(typeof body.detail === 'string' ? body.detail : 'The request could not be saved.');
  return body;
}
function refresh(afterMutation = false) {
  // Retry and timer events must not start snapshots while a save is outstanding.
  if (changing && !afterMutation) return inFlight || Promise.resolve();
  if (inFlight) return inFlight;
  clearTimeout(timer);
  inFlight = (async () => {
    try {
      current = await jsonRequest('/api/local/status'); render(current);
      say('connection', 'Local server connected'); byId('connection').classList.remove('error');
      byId('retry').hidden = true;
    } catch {
      say('connection', current ? 'Local server unavailable. Showing the previous complete report.' :
        'Local server unavailable. Retry to load your library.');
      byId('connection').classList.add('error'); byId('retry').hidden = false;
      if (!current) {
        say('empty', 'Connect to the local server to load your music. Check that the administration service is running.');
        say('view-count', 'Library unavailable'); say('pending-summary', 'Choices unavailable');
        byId('library').setAttribute('aria-busy', 'false');
      }
    }
  })().finally(() => {
    inFlight = null;
    if (!document.hidden && !changing) timer = setTimeout(refresh, 5000);
  });
  return inFlight;
}
async function mutate(path, method, body, message) {
  if (changing || current === null) return;
  changing = true; clearTimeout(timer); disableMutations();
  const focused = document.activeElement;
  say('feedback', 'Saving…'); byId('feedback').className = 'feedback';
  try {
    // Finish any older snapshot before saving; fetch a new snapshot after saving.
    await inFlight;
    await jsonRequest(path, {method, headers: {'Content-Type': 'application/json', 'X-CSRF-Token': current.csrf_token},
      ...(body === null ? {} : {body: JSON.stringify(body)})});
    say('feedback', message); byId('feedback').classList.add('success');
  } catch (error) { say('feedback', error.message); byId('feedback').classList.add('error'); }
  finally {
    await refresh(true); changing = false; disableMutations();
    if (!focused.isConnected && (document.activeElement === document.body || document.activeElement.disabled)) focusView();
    if (!document.hidden) timer = setTimeout(refresh, 5000);
  }
}
function setDesired(track, present, message) {
  return mutate('/api/local/desired/' + encodeURIComponent(track), 'PUT', {present}, message);
}
function selectView(next) { filter = next; if (current) render(current); }
document.querySelectorAll('[data-filter]').forEach(button => button.addEventListener('click', () => selectView(button.dataset.filter)));
byId('search').addEventListener('input', () => {if (current) render(current);});
byId('review').addEventListener('click', () => {selectView('pending'); focusView();});
byId('setup-toggle').addEventListener('click', () => {
  const panel = byId('setup-panel'); panel.hidden = !panel.hidden;
  byId('setup-toggle').setAttribute('aria-expanded', String(!panel.hidden));
  if (!panel.hidden) panel.scrollIntoView({block: 'nearest'});
});
byId('rescan').addEventListener('click', () => mutate('/api/local/rescan', 'POST', null, 'PC music rescanned.'));
byId('retry').addEventListener('click', () => refresh());
document.addEventListener('visibilitychange', () => {clearTimeout(timer); if (!document.hidden && !changing) refresh();});
refresh();
