'use strict';

let current = null;
let timer = null;
let polling = false;
let refreshAgain = false;
let changing = false;
const byId = id => document.getElementById(id);

function node(tag, text, className) {
  const element = document.createElement(tag);
  if (text !== undefined && text !== null) element.textContent = String(text);
  if (className) element.className = className;
  return element;
}
function say(id, message) { byId(id).textContent = message; }
function button(label, action, disabled = false, className = '') {
  const element = node('button', label, className);
  element.type = 'button';
  element.disabled = disabled || changing;
  element.addEventListener('click', action);
  return element;
}
function table(headers) {
  const element = node('table');
  const head = node('thead');
  const row = node('tr');
  for (const title of headers) {
    const cell = node('th', title); cell.scope = 'col'; row.append(cell);
  }
  head.append(row);
  const body = node('tbody');
  element.append(head, body);
  return [element, body];
}
function choices(track) {
  const cell = node('td', null, 'actions');
  if (track.available) {
    cell.append(button(track.desired === true ? 'Requested on watch' : 'Download to watch',
      () => setDesired(track.track_id, true), track.desired === true));
  }
  if (track.observed === true || track.desired === true) {
    const label = track.observed === true ? 'Remove watch copy' : 'Cancel download request';
    cell.append(button(label, () => setDesired(track.track_id, false), track.desired === false, 'secondary'));
  }
  return cell;
}
function details(track) {
  const labels = [];
  if (track.observed === true) labels.push('Last reported downloaded');
  else if (track.observed === null) labels.push('Watch inventory unknown');
  else labels.push('Not in last report');
  if (track.pending_download) labels.push('Pending download');
  if (track.pending_removal) labels.push('Pending removal of watch copy');
  if (!track.available) labels.push('PC source unavailable');
  return labels.join(' · ');
}
function renderLibrary(data) {
  const root = byId('library'); root.replaceChildren();
  if (!data.tracks.length) {
    root.append(node('p', 'No MP3 files indexed. Add music to your configured folder, then rescan.', 'empty')); return;
  }
  const [element, body] = table(['Track', 'Status', 'Your choice']);
  for (const track of data.tracks) {
    const row = node('tr');
    row.append(node('td', track.filename, 'filename'));
    const state = node('td', details(track), 'track-status');
    if (track.last_error) state.append(node('p', 'Last error: ' + track.last_error, 'error'));
    row.append(state, choices(track)); body.append(row);
  }
  root.append(element);
}
function renderWatch(data) {
  const root = byId('watch'); root.replaceChildren();
  if (data.inventory === null) {
    root.append(node('p', 'Inventory unknown. Sync your watch to report its contents.', 'empty')); return;
  }
  if (data.inventory.length === 0) {
    root.append(node('p', 'No tracks in the last complete report.', 'empty')); return;
  }
  const tracks = new Map(data.tracks.map(track => [track.track_id, track]));
  const [element, body] = table(['Downloaded track', 'Status', 'Your choice']);
  for (const entry of data.inventory) {
    const track = tracks.get(entry.track_id);
    const row = node('tr');
    row.append(node('td', entry.filename || (track ? track.filename : 'Unknown cache entry'), 'filename'));
    if (!track || entry.track_id === null) {
      row.append(node('td', 'Unknown cache entry — retained', 'track-status'), node('td', ''));
    } else {
      row.append(node('td', details(track), 'track-status'), choices(track));
    }
    body.append(row);
  }
  root.append(element);
}
function renderAssociation(data) {
  const root = byId('association'); root.replaceChildren();
  if (data.association === null) {
    root.append(node('p', 'Sync your watch once to establish its connection.')); return;
  }
  if (data.association.confirmed) {
    root.append(node('p', 'Watch connection confirmed. Removal requests apply only to this app’s watch copies.')); return;
  }
  const pair = {server_id: data.association.server_id, device_epoch: data.association.device_epoch};
  root.append(node('p', 'New watch connection. Removals are paused until you confirm the watch that most recently synced.'));
  root.append(button('Confirm watch connection', () => mutate('/api/local/association/confirm', 'POST', pair,
    'Watch connection confirmed. Start another sync to apply removal requests.')));
}
function render(data) {
  say('available-count', data.tracks.filter(track => track.available).length);
  say('watch-count', data.inventory === null ? 'Unknown' : data.inventory.length);
  say('pending-count', data.tracks.filter(track => track.pending_download || track.pending_removal).length);
  const report = byId('reported-time'); report.replaceChildren();
  if (data.reported_at === null) report.append(node('span', 'No complete report yet'));
  else {
    report.append(node('span', 'Last complete report: '));
    const time = node('time', new Date(data.reported_at).toLocaleString()); time.dateTime = data.reported_at;
    report.append(time);
  }
  const labels = {in_progress: 'In progress', expired: 'Expired; start a new sync', success: 'Completed',
    failed: 'Failed; pending choices remain', cancelled: 'Cancelled'};
  say('sync-outcome', data.latest_sync ? 'Latest sync: ' + (labels[data.latest_sync.outcome] || data.latest_sync.outcome) : 'No sync recorded yet.');
  renderAssociation(data); renderLibrary(data); renderWatch(data);
  byId('rescan').disabled = changing;
}
async function jsonRequest(path, options = {}) {
  const response = await fetch(path, {cache: 'no-store', ...options});
  let body;
  try { body = await response.json(); } catch { throw new Error('The local server returned an invalid response.'); }
  if (!response.ok) throw new Error(typeof body.detail === 'string' ? body.detail : 'The request could not be saved.');
  return body;
}
async function refresh() {
  if (polling) { refreshAgain = true; return; }
  clearTimeout(timer); polling = true;
  try {
    const data = await jsonRequest('/api/local/status');
    current = data; render(data);
    say('connection', 'Local server connected'); byId('connection').classList.remove('error');
  } catch {
    say('connection', current ? 'Local server unavailable. Showing the previous complete report.' : 'Local server unavailable. Retrying when this page is visible.');
    byId('connection').classList.add('error');
  } finally {
    polling = false;
    if (!document.hidden) {
      const delay = refreshAgain ? 0 : 5000;
      refreshAgain = false; timer = setTimeout(refresh, delay);
    }
  }
}
async function mutate(path, method, body, message) {
  if (changing || current === null) return;
  changing = true; render(current); say('feedback', 'Saving…');
  try {
    await jsonRequest(path, {method, headers: {'Content-Type': 'application/json', 'X-CSRF-Token': current.csrf_token},
      ...(body === null ? {} : {body: JSON.stringify(body)})});
    say('feedback', message);
  } catch (error) { say('feedback', error.message); }
  finally { changing = false; if (current) render(current); await refresh(); }
}
function setDesired(track, present) {
  return mutate('/api/local/desired/' + track, 'PUT', {present},
    present ? 'Download requested. Start Sync on your watch.' : 'Requested absent from watch. PC original stays unchanged. Start Sync on your watch.');
}
byId('rescan').addEventListener('click', () => mutate('/api/local/rescan', 'POST', null, 'PC music rescanned.'));
document.addEventListener('visibilitychange', () => {
  clearTimeout(timer);
  if (!document.hidden) refresh();
});
refresh();
