const canvas = document.getElementById('gameCanvas');
const ctx = canvas.getContext('2d');

const roomInput = document.getElementById('roomInput');
const nameInput = document.getElementById('nameInput');
const connectBtn = document.getElementById('connectBtn');
const fullscreenBtn = document.getElementById('fullscreenBtn');
const readyBtn = document.getElementById('readyBtn');
const startRaceBtn = document.getElementById('startRaceBtn');
const resetLobbyBtn = document.getElementById('resetLobbyBtn');
const carSelect = document.getElementById('carSelect');
const trackSelect = document.getElementById('trackSelect');
const applyTrackBtn = document.getElementById('applyTrackBtn');
const customMapInput = document.getElementById('customMapInput');
const hostCustomMapBtn = document.getElementById('hostCustomMapBtn');
const mapWidthInput = document.getElementById('mapWidthInput');
const mapHeightInput = document.getElementById('mapHeightInput');
const resizeMapBtn = document.getElementById('resizeMapBtn');
const loadCurrentTrackBtn = document.getElementById('loadCurrentTrackBtn');
const editorToTextBtn = document.getElementById('editorToTextBtn');
const clearEditorBtn = document.getElementById('clearEditorBtn');
const mapEditorCanvas = document.getElementById('mapEditorCanvas');
const mapEditorCtx = mapEditorCanvas.getContext('2d');
const tileToolButtons = Array.from(document.querySelectorAll('.tile-tool'));
const lapsSelect = document.getElementById('lapsSelect');
const statusText = document.getElementById('statusText');
const phaseText = document.getElementById('phaseText');
const roomLeaderboard = document.getElementById('roomLeaderboard');
const globalLeaderboard = document.getElementById('globalLeaderboard');
const gameArea = document.getElementById('gameArea');
const hudLap = document.getElementById('hudLap');
const hudLapTime = document.getElementById('hudLapTime');
const hudRaceTime = document.getElementById('hudRaceTime');
const hudBestLap = document.getElementById('hudBestLap');
const hudSpeed = document.getElementById('hudSpeed');
const hudPing = document.getElementById('hudPing');
const hudPhase = document.getElementById('hudPhase');

let socket = null;
let connected = false;
let playerId = null;
let players = [];
let mapData = null;
let availableTracks = [];
let carModels = [];
let mapBuffer = null;
let mapBufferCtx = null;
let lastRenderTs = 0;
const particles = [];
const tireMarks = [];
const tireTrackState = {};
const lastParticleSpawnByPlayer = {};
const lastTireMarkSpawnByPlayer = {};
let roomState = {
  phase: 'lobby',
  lapsToWin: 3,
  trackId: 'brands_hatch',
  trackName: 'Brands Hatch',
  countdownSecondsLeft: 0,
  winnerId: null,
  raceElapsedMs: 0,
  roomLeaderboard: [],
  globalLeaderboard: [],
};

const INTERPOLATION_BACK_TIME_MIN_MS = 45;
const INTERPOLATION_BACK_TIME_MAX_MS = 140;
const INTERPOLATION_BASELINE_MS = 45;
const REMOTE_EXTRAPOLATION_LIMIT_MS = 80;
const SELF_RECONCILE_BLEND = 0.35;
let serverClockOffsetMs = 0;
let rttMsSmoothed = 0;
let interpolationBackTimeMs = 90;
const playerNetState = {};
let lastInputSignature = '';
let lastInputSentAt = 0;
let trackedLapCount = 0;
let trackedLapStartRaceMs = 0;
let keyboardHandbrake = false;

const gamepadState = {
  connected: false,
  throttle: 0,
  brake: 0,
  steer: 0,
  handbrake: false,
};

const mapEditorState = {
  width: 64,
  height: 48,
  rows: [],
  selectedTile: '1',
  painting: false,
  initialized: false,
  hasManualChanges: false,
};

const inputState = {
  up: false,
  down: false,
  left: false,
  right: false,
  handbrake: false,
};

function setStatus(text, isError = false) {
  statusText.textContent = text;
  statusText.style.color = isError ? '#fca5a5' : '#86efac';
}

function wsUrl(room, name) {
  const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws';
  const host = window.location.host;
  return `${protocol}://${host}/ws/${encodeURIComponent(room)}/${encodeURIComponent(name)}`;
}

function formatMs(ms) {
  const total = Math.max(0, Math.floor(ms));
  const m = Math.floor(total / 60000);
  const s = Math.floor((total % 60000) / 1000);
  const t = total % 1000;
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}.${String(t).padStart(3, '0')}`;
}

function normalizeAngleDeg(degrees) {
  let value = degrees % 360;
  if (value > 180) value -= 360;
  if (value < -180) value += 360;
  return value;
}

function lerp(start, end, t) {
  return start + (end - start) * t;
}

function lerpAngleDeg(start, end, t) {
  const delta = normalizeAngleDeg(end - start);
  return start + delta * t;
}

function inputSignature() {
  const payload = composeInputPayload();
  return [
    payload.up ? 1 : 0,
    payload.down ? 1 : 0,
    payload.left ? 1 : 0,
    payload.right ? 1 : 0,
    payload.handbrake ? 1 : 0,
    payload.throttle.toFixed(2),
    payload.brake.toFixed(2),
    payload.steer.toFixed(2),
  ].join('|');
}

function composeInputPayload() {
  const throttle = Math.max(inputState.up ? 1 : 0, gamepadState.throttle);
  const brake = Math.max(inputState.down ? 1 : 0, gamepadState.brake);

  let steer = gamepadState.steer;
  if (inputState.left && !inputState.right) {
    steer = Math.min(steer, -1);
  } else if (inputState.right && !inputState.left) {
    steer = Math.max(steer, 1);
  }

  const handbrake = Boolean(keyboardHandbrake || gamepadState.handbrake);

  return {
    up: throttle > 0.05,
    down: brake > 0.05,
    left: steer < -0.1,
    right: steer > 0.1,
    handbrake,
    throttle,
    brake,
    steer,
  };
}

function sendInputUpdate(force = false) {
  if (!socket || socket.readyState !== WebSocket.OPEN) return;

  const now = performance.now();
  const signature = inputSignature();
  const changed = signature !== lastInputSignature;
  const enoughTimePassed = now - lastInputSentAt >= 60;
  const keepaliveDue = now - lastInputSentAt >= 180;

  if (!force && !changed && !keepaliveDue) {
    return;
  }
  if (!force && changed && !enoughTimePassed) {
    return;
  }

  send('input', { input: composeInputPayload() });
  lastInputSignature = signature;
  lastInputSentAt = now;
}

function updateServerClockOffset(serverTimeSeconds) {
  if (typeof serverTimeSeconds !== 'number') return;
  const sampleOffset = serverTimeSeconds * 1000 - performance.now();
  if (!Number.isFinite(serverClockOffsetMs) || serverClockOffsetMs === 0) {
    serverClockOffsetMs = sampleOffset;
    return;
  }
  serverClockOffsetMs += (sampleOffset - serverClockOffsetMs) * 0.08;
}

function updateLatencyModel(rttMs) {
  if (!Number.isFinite(rttMs) || rttMs <= 0) return;
  if (rttMsSmoothed <= 0) {
    rttMsSmoothed = rttMs;
  } else {
    rttMsSmoothed += (rttMs - rttMsSmoothed) * 0.2;
  }

  const target = INTERPOLATION_BASELINE_MS + rttMsSmoothed * 0.5;
  interpolationBackTimeMs = Math.max(
    INTERPOLATION_BACK_TIME_MIN_MS,
    Math.min(INTERPOLATION_BACK_TIME_MAX_MS, target)
  );
}

function updateFullscreenButtonLabel() {
  const isFullscreen = document.fullscreenElement === gameArea;
  fullscreenBtn.textContent = isFullscreen ? 'Exit Fullscreen' : 'Fullscreen';
}

async function toggleFullscreen() {
  try {
    const isFullscreen = document.fullscreenElement === gameArea;
    if (isFullscreen) {
      await document.exitFullscreen();
    } else {
      await gameArea.requestFullscreen();
    }
  } catch {
    setStatus('Fullscreen not supported in this browser', true);
  }
}

function refreshRaceHud() {
  const me = findMe();
  const phase = roomState.phase || 'lobby';
  const lapsToWin = Number(roomState.lapsToWin || 0);
  const raceElapsedMs = Number(roomState.raceElapsedMs || 0);

  if (!me || phase === 'lobby') {
    trackedLapCount = 0;
    trackedLapStartRaceMs = 0;
  } else if (me.laps !== trackedLapCount) {
    trackedLapCount = me.laps;
    trackedLapStartRaceMs = raceElapsedMs;
  }

  const lapCurrent = me ? Math.min(me.laps + 1, lapsToWin || me.laps + 1) : 0;
  const lapTimeMs = Math.max(0, raceElapsedMs - trackedLapStartRaceMs);

  hudLap.textContent = me ? `${lapCurrent}/${lapsToWin || 0}` : '-';
  hudLapTime.textContent = formatMs(lapTimeMs);
  hudRaceTime.textContent = formatMs(raceElapsedMs);
  hudBestLap.textContent = me && me.bestLapMs ? formatMs(me.bestLapMs) : '--:--.---';
  hudSpeed.textContent = me ? `${Math.round(Number(me.speed || 0))}` : '0';
  hudPing.textContent = rttMsSmoothed > 0 ? `${Math.round(rttMsSmoothed)} ms` : '-- ms';
  hudPhase.textContent = phase;
}

function ingestPlayerState(serverPlayers, serverTimeSeconds) {
  const serverTimeMs = typeof serverTimeSeconds === 'number'
    ? serverTimeSeconds * 1000
    : performance.now() + serverClockOffsetMs;

  players = serverPlayers || [];
  const activeIds = new Set();

  for (const player of players) {
    activeIds.add(player.id);
    const state = playerNetState[player.id];

    if (!state) {
      playerNetState[player.id] = {
        prevX: player.x,
        prevY: player.y,
        prevRot: player.rotationDeg,
        prevServerMs: serverTimeMs,
        targetX: player.x,
        targetY: player.y,
        targetRot: player.rotationDeg,
        targetServerMs: serverTimeMs,
        velocityX: 0,
        velocityY: 0,
        rotationVelocity: 0,
      };
      continue;
    }

    const dtMs = Math.max(1, serverTimeMs - state.targetServerMs);
    state.prevX = state.targetX;
    state.prevY = state.targetY;
    state.prevRot = state.targetRot;
    state.prevServerMs = state.targetServerMs;

    state.targetX = player.x;
    state.targetY = player.y;
    state.targetRot = player.rotationDeg;
    state.targetServerMs = serverTimeMs;

    state.velocityX = Number.isFinite(player.vx) ? player.vx : (state.targetX - state.prevX) / (dtMs / 1000);
    state.velocityY = Number.isFinite(player.vy) ? player.vy : (state.targetY - state.prevY) / (dtMs / 1000);
    state.rotationVelocity = normalizeAngleDeg(state.targetRot - state.prevRot) / (dtMs / 1000);
  }

  for (const id of Object.keys(playerNetState)) {
    if (!activeIds.has(id)) {
      delete playerNetState[id];
      delete tireTrackState[id];
      delete lastParticleSpawnByPlayer[id];
      delete lastTireMarkSpawnByPlayer[id];
    }
  }
}

function getRenderedPlayers(renderTimeMs) {
  const sampledServerMs = renderTimeMs + serverClockOffsetMs - interpolationBackTimeMs;

  return players.map((player) => {
    const net = playerNetState[player.id];
    if (!net) {
      return player;
    }

    const dt = net.targetServerMs - net.prevServerMs;
    let x = net.targetX;
    let y = net.targetY;
    let rotationDeg = net.targetRot;

    if (dt > 0 && sampledServerMs <= net.targetServerMs) {
      const t = Math.max(0, Math.min(1, (sampledServerMs - net.prevServerMs) / dt));
      x = lerp(net.prevX, net.targetX, t);
      y = lerp(net.prevY, net.targetY, t);
      rotationDeg = lerpAngleDeg(net.prevRot, net.targetRot, t);
    } else {
      const extraMs = Math.max(0, sampledServerMs - net.targetServerMs);
      const cappedMs = Math.min(REMOTE_EXTRAPOLATION_LIMIT_MS, extraMs);
      const extraSec = cappedMs / 1000;
      x = net.targetX + net.velocityX * extraSec;
      y = net.targetY + net.velocityY * extraSec;
      rotationDeg = net.targetRot + net.rotationVelocity * extraSec;
    }

    if (player.id === playerId) {
      x = lerp(player.x, x, SELF_RECONCILE_BLEND);
      y = lerp(player.y, y, SELF_RECONCILE_BLEND);
      rotationDeg = lerpAngleDeg(player.rotationDeg, rotationDeg, SELF_RECONCILE_BLEND);
    }

    return {
      ...player,
      x,
      y,
      rotationDeg,
    };
  });
}

function tileNoise(x, y, seed = 1) {
  const n = Math.sin((x + 1) * 127.1 + (y + 1) * 311.7 + seed * 19.13) * 43758.5453123;
  return n - Math.floor(n);
}

function drawCurbEdge(ctx2d, px, py, tileSize, edge, keySeed) {
  const stripeLen = 4;
  const band = 4;
  const total = tileSize;
  const offset = Math.floor(tileNoise(keySeed, keySeed * 0.73, 77) * stripeLen);

  for (let t = -offset; t < total; t += stripeLen) {
    const isRed = (Math.floor((t + offset) / stripeLen) % 2) === 0;
    ctx2d.fillStyle = isRed ? '#d62828' : '#f2f2f2';

    if (edge === 'top') {
      ctx2d.fillRect(px + Math.max(0, t), py, Math.min(stripeLen, total - Math.max(0, t)), band);
    } else if (edge === 'bottom') {
      ctx2d.fillRect(px + Math.max(0, t), py + tileSize - band, Math.min(stripeLen, total - Math.max(0, t)), band);
    } else if (edge === 'left') {
      ctx2d.fillRect(px, py + Math.max(0, t), band, Math.min(stripeLen, total - Math.max(0, t)));
    } else if (edge === 'right') {
      ctx2d.fillRect(px + tileSize - band, py + Math.max(0, t), band, Math.min(stripeLen, total - Math.max(0, t)));
    }
  }
}

function findMe() {
  return players.find((p) => p.id === playerId) || null;
}

function populateCars() {
  carSelect.innerHTML = '';
  for (const car of carModels) {
    const option = document.createElement('option');
    option.value = String(car.id);
    option.textContent = `${car.name} (A:${Math.round(car.accel)} V:${Math.round(car.maxSpeed)})`;
    carSelect.appendChild(option);
  }
}

function populateTracks(selectedId = null) {
  const preserve = selectedId || trackSelect.value || '';
  trackSelect.innerHTML = '';
  for (const track of availableTracks) {
    const option = document.createElement('option');
    option.value = String(track.id);
    option.textContent = track.name;
    trackSelect.appendChild(option);
  }
  if (preserve && Array.from(trackSelect.options).some((opt) => opt.value === preserve)) {
    trackSelect.value = preserve;
  }
}

function applySelectedTrack() {
  const selected = trackSelect.value;
  if (!selected) {
    setStatus('Pick a track first.', true);
    return;
  }
  send('set_track', { trackId: selected });
}

function hostCustomMap() {
  const customMap = customMapInput.value.trim();
  if (!customMap) {
    setStatus('Paste map rows before hosting a custom track.', true);
    return;
  }
  send('set_track', {
    trackId: 'custom',
    customMap,
  });
}

function createEmptyEditorRows(width, height, fillTile = '1') {
  const rows = [];
  for (let y = 0; y < height; y++) {
    rows.push(fillTile.repeat(width));
  }
  return rows;
}

function normalizeRows(rows) {
  return (rows || []).map((row) => String(row || '').trimEnd()).filter((row) => row.length > 0);
}

function setEditorRows(rows, markManual = false) {
  const normalized = normalizeRows(rows);
  if (!normalized.length) return;
  const width = normalized[0].length;
  if (width < 1) return;
  if (!normalized.every((row) => row.length === width)) return;

  mapEditorState.rows = normalized;
  mapEditorState.width = width;
  mapEditorState.height = normalized.length;
  mapEditorState.initialized = true;
  if (markManual) {
    mapEditorState.hasManualChanges = true;
  }

  mapWidthInput.value = String(width);
  mapHeightInput.value = String(normalized.length);
  drawMapEditor();
}

function exportEditorRows() {
  return mapEditorState.rows.join('\n');
}

function setSelectedEditorTile(tile) {
  mapEditorState.selectedTile = tile;
  tileToolButtons.forEach((button) => {
    button.classList.toggle('active', button.dataset.tile === tile);
  });
}

function replaceAt(text, index, value) {
  return text.substring(0, index) + value + text.substring(index + 1);
}

function ensureSingleStart(rows, newX, newY) {
  for (let y = 0; y < rows.length; y++) {
    if (!rows[y].includes('P')) continue;
    rows[y] = rows[y].replaceAll('P', '.');
  }
  rows[newY] = replaceAt(rows[newY], newX, 'P');
}

function paintEditorTileAt(canvasX, canvasY, overrideTile = null) {
  if (!mapEditorState.rows.length) return;
  const tileW = mapEditorCanvas.width / mapEditorState.width;
  const tileH = mapEditorCanvas.height / mapEditorState.height;
  const x = Math.max(0, Math.min(mapEditorState.width - 1, Math.floor(canvasX / tileW)));
  const y = Math.max(0, Math.min(mapEditorState.height - 1, Math.floor(canvasY / tileH)));
  const paintTile = overrideTile || mapEditorState.selectedTile;

  const rows = [...mapEditorState.rows];
  if (paintTile === 'P') {
    ensureSingleStart(rows, x, y);
  } else {
    rows[y] = replaceAt(rows[y], x, paintTile);
  }

  mapEditorState.rows = rows;
  mapEditorState.hasManualChanges = true;
  drawMapEditor();
}

function getCanvasPointFromEvent(event) {
  const rect = mapEditorCanvas.getBoundingClientRect();
  const x = ((event.clientX - rect.left) / rect.width) * mapEditorCanvas.width;
  const y = ((event.clientY - rect.top) / rect.height) * mapEditorCanvas.height;
  return { x, y };
}

function tileColor(tile) {
  if (tile === '1' || tile === 'W') return '#2f6f2f';
  if (tile === '.') return '#9f7a52';
  if (tile === 'P') return '#60a5fa';
  if (tile === 'F') return '#e5e7eb';
  if (tile === 'C') return '#22d3ee';
  return '#334155';
}

function drawMapEditor() {
  const rows = mapEditorState.rows;
  if (!rows.length) return;

  const tileW = mapEditorCanvas.width / mapEditorState.width;
  const tileH = mapEditorCanvas.height / mapEditorState.height;

  mapEditorCtx.clearRect(0, 0, mapEditorCanvas.width, mapEditorCanvas.height);

  for (let y = 0; y < rows.length; y++) {
    const row = rows[y];
    for (let x = 0; x < row.length; x++) {
      const tile = row[x];
      const px = x * tileW;
      const py = y * tileH;
      mapEditorCtx.fillStyle = tileColor(tile);
      mapEditorCtx.fillRect(px, py, tileW, tileH);

      mapEditorCtx.strokeStyle = 'rgba(15, 23, 42, 0.25)';
      mapEditorCtx.lineWidth = 1;
      mapEditorCtx.strokeRect(px, py, tileW, tileH);
    }
  }
}

function resizeEditorGrid() {
  const width = Math.max(16, Math.min(128, Number(mapWidthInput.value || 64)));
  const height = Math.max(12, Math.min(96, Number(mapHeightInput.value || 48)));
  mapWidthInput.value = String(width);
  mapHeightInput.value = String(height);
  setEditorRows(createEmptyEditorRows(width, height, '1'), true);
}

function loadCurrentTrackIntoEditor() {
  if (!mapData?.rows?.length) {
    setStatus('No track loaded yet.', true);
    return;
  }
  setEditorRows(mapData.rows, true);
}

function syncEditorToText() {
  if (!mapEditorState.rows.length) {
    setStatus('Map editor is empty.', true);
    return;
  }
  customMapInput.value = exportEditorRows();
  setStatus('Custom map text updated from editor.');
}

function initMapEditor() {
  if (!mapEditorState.initialized) {
    setEditorRows(createEmptyEditorRows(mapEditorState.width, mapEditorState.height, '1'));
  }

  setSelectedEditorTile('1');

  mapEditorCanvas.addEventListener('contextmenu', (event) => {
    event.preventDefault();
  });

  mapEditorCanvas.addEventListener('mousedown', (event) => {
    mapEditorState.painting = true;
    const { x, y } = getCanvasPointFromEvent(event);
    paintEditorTileAt(x, y, event.button === 2 ? '1' : null);
  });

  window.addEventListener('mouseup', () => {
    mapEditorState.painting = false;
  });

  mapEditorCanvas.addEventListener('mousemove', (event) => {
    if (!mapEditorState.painting) return;
    const { x, y } = getCanvasPointFromEvent(event);
    const isRightButton = (event.buttons & 2) !== 0;
    paintEditorTileAt(x, y, isRightButton ? '1' : null);
  });

  tileToolButtons.forEach((button) => {
    button.addEventListener('click', () => {
      setSelectedEditorTile(button.dataset.tile || '1');
    });
  });

  resizeMapBtn.addEventListener('click', () => resizeEditorGrid());
  loadCurrentTrackBtn.addEventListener('click', () => loadCurrentTrackIntoEditor());
  editorToTextBtn.addEventListener('click', () => syncEditorToText());
  clearEditorBtn.addEventListener('click', () => {
    setEditorRows(createEmptyEditorRows(mapEditorState.width, mapEditorState.height, '1'), true);
  });
}

function send(type, extra = {}) {
  if (!socket || socket.readyState !== WebSocket.OPEN) return;
  socket.send(JSON.stringify({ type, ...extra }));
}

function sendGarage(readyOverride = null) {
  const me = findMe();
  const ready = readyOverride !== null ? readyOverride : Boolean(me?.ready);
  send('garage', {
    carId: Number(carSelect.value || 0),
    lapsToWin: Number(lapsSelect.value || 3),
    ready,
  });
}

function connect() {
  if (socket) {
    socket.close();
    socket = null;
  }

  const room = roomInput.value.trim() || 'brands-public';
  const name = nameInput.value.trim() || 'Player';

  socket = new WebSocket(wsUrl(room, name));
  setStatus(`Connecting to room '${room}'...`);

  socket.onopen = () => {
    connected = true;
    lastInputSignature = '';
    lastInputSentAt = 0;
    trackedLapCount = 0;
    trackedLapStartRaceMs = 0;
    setStatus(`Connected to '${room}'`);
  };

  socket.onclose = () => {
    connected = false;
    playerId = null;
    players = [];
    Object.keys(playerNetState).forEach((id) => delete playerNetState[id]);
    trackedLapCount = 0;
    trackedLapStartRaceMs = 0;
    refreshRaceHud();
    setStatus('Disconnected', true);
  };

  socket.onerror = () => {
    setStatus('Connection error', true);
  };

  socket.onmessage = (event) => {
    const message = JSON.parse(event.data);

    if (message.type === 'welcome') {
      playerId = message.playerId;
      mapData = message.map;
      buildMapBuffer();
      if (!mapEditorState.hasManualChanges && mapData?.rows?.length) {
        setEditorRows(mapData.rows);
      }
      availableTracks = message.tracks || availableTracks;
      populateTracks(message.map?.id || null);
      carModels = message.cars || [];
      populateCars();
      sendGarage(false);
    }

    if (message.type === 'map') {
      mapData = message.map || mapData;
      if (message.tracks) {
        availableTracks = message.tracks;
      }
      populateTracks(mapData?.id || null);
      buildMapBuffer();
      if (!mapEditorState.hasManualChanges && mapData?.rows?.length) {
        setEditorRows(mapData.rows);
      }
    }

    if (message.type === 'error') {
      setStatus(message.message || 'Server error', true);
    }

    if (message.type === 'state') {
      updateServerClockOffset(message.serverTime);
      ingestPlayerState(message.players || [], message.serverTime);
      roomState = {
        ...roomState,
        ...(message.room || {}),
      };
      if (roomState.trackId) {
        populateTracks(roomState.trackId);
      }
      lapsSelect.value = String(roomState.lapsToWin || 3);
      refreshLeaderboards();
      refreshPhase();
      refreshRaceHud();
    }

    if (message.type === 'pong') {
      const now = performance.now();
      const clientTime = Number(message.clientTime || 0);
      const rttMs = now - clientTime;
      updateLatencyModel(rttMs);
      updateServerClockOffset(message.serverTime);
    }
  };
}

function buildMapBuffer() {
  if (!mapData) {
    mapBuffer = null;
    mapBufferCtx = null;
    tireMarks.length = 0;
    particles.length = 0;
    Object.keys(tireTrackState).forEach((key) => delete tireTrackState[key]);
    return;
  }

  const rows = mapData.rows;
  const tileSize = mapData.tileSize;
  const height = rows.length;
  const width = rows[0]?.length || 0;

  mapBuffer = document.createElement('canvas');
  mapBuffer.width = width * tileSize;
  mapBuffer.height = height * tileSize;
  mapBufferCtx = mapBuffer.getContext('2d');
  tireMarks.length = 0;
  particles.length = 0;
  Object.keys(tireTrackState).forEach((key) => delete tireTrackState[key]);

  for (let y = 0; y < rows.length; y++) {
    const row = rows[y];
    for (let x = 0; x < row.length; x++) {
      const tile = row[x];
      const px = x * tileSize;
      const py = y * tileSize;

      if (tile === '1' || tile === 'W') {
        const shade = 0.9 + tileNoise(x, y, 21) * 0.22;
        const g = Math.max(70, Math.min(168, Math.floor(118 * shade)));
        const r = Math.max(22, Math.min(64, Math.floor(42 * shade)));
        const b = Math.max(18, Math.min(52, Math.floor(31 * shade)));
        mapBufferCtx.fillStyle = `rgb(${r}, ${g}, ${b})`;
        mapBufferCtx.fillRect(px, py, tileSize, tileSize);

        const patches = 4;
        for (let i = 0; i < patches; i++) {
          const n = tileNoise(x + i * 1.7, y - i * 0.8, 3);
          const gx = px + Math.floor(n * (tileSize - 2));
          const gy = py + Math.floor(tileNoise(y + i * 1.3, x, 7) * (tileSize - 2));
          mapBufferCtx.fillStyle = n > 0.6 ? '#3aa83a' : n > 0.3 ? '#2a8d2a' : '#1b611b';
          mapBufferCtx.fillRect(gx, gy, 2, 2);
        }
      } else {
        const shade = 0.9 + tileNoise(x, y, 41) * 0.2;
        const r = Math.max(112, Math.min(182, Math.floor(148 * shade)));
        const g = Math.max(82, Math.min(136, Math.floor(112 * shade)));
        const b = Math.max(52, Math.min(96, Math.floor(75 * shade)));
        mapBufferCtx.fillStyle = `rgb(${r}, ${g}, ${b})`;
        mapBufferCtx.fillRect(px, py, tileSize, tileSize);

        const dust = 4;
        for (let i = 0; i < dust; i++) {
          const n = tileNoise(x + i * 2.3, y + i * 1.1, 11);
          const dx = px + Math.floor(n * tileSize);
          const dy = py + Math.floor(tileNoise(y + i * 1.8, x + i * 0.6, 13) * tileSize);
          mapBufferCtx.fillStyle = n > 0.68 ? '#b99366' : n > 0.35 ? '#946f48' : '#6b4f33';
          mapBufferCtx.fillRect(dx, dy, 2, 2);
        }

        const top = y > 0 ? rows[y - 1][x] : '1';
        const bottom = y < rows.length - 1 ? rows[y + 1][x] : '1';
        const left = x > 0 ? row[x - 1] : '1';
        const right = x < row.length - 1 ? row[x + 1] : '1';

        if (top === '1' || top === 'W') drawCurbEdge(mapBufferCtx, px, py, tileSize, 'top', x * 97 + y * 131 + 1);
        if (bottom === '1' || bottom === 'W') drawCurbEdge(mapBufferCtx, px, py, tileSize, 'bottom', x * 101 + y * 137 + 2);
        if (left === '1' || left === 'W') drawCurbEdge(mapBufferCtx, px, py, tileSize, 'left', x * 103 + y * 139 + 3);
        if (right === '1' || right === 'W') drawCurbEdge(mapBufferCtx, px, py, tileSize, 'right', x * 107 + y * 149 + 4);

        if (tile === 'F') {
          mapBufferCtx.fillStyle = '#e5e7eb';
          mapBufferCtx.fillRect(px, py, tileSize, tileSize);
          mapBufferCtx.fillStyle = '#111827';
          mapBufferCtx.fillRect(px, py, tileSize / 2, tileSize / 2);
          mapBufferCtx.fillRect(px + tileSize / 2, py + tileSize / 2, tileSize / 2, tileSize / 2);
        }

        if (tile === 'C') {
          mapBufferCtx.fillStyle = '#22d3ee';
          mapBufferCtx.fillRect(px + 4, py + 4, tileSize - 8, tileSize - 8);
        }
      }
    }
  }
}

function refreshPhase() {
  const me = findMe();
  let text = `Phase: ${roomState.phase}`;
  if (roomState.trackName) {
    text += ` | Track: ${roomState.trackName}`;
  }
  if (roomState.phase === 'countdown') {
    text += ` (${roomState.countdownSecondsLeft})`;
  }
  if (roomState.phase === 'racing' || roomState.phase === 'finished') {
    text += ` | Race: ${formatMs(roomState.raceElapsedMs || 0)}`;
  }
  if (roomState.winnerId) {
    const winner = players.find((p) => p.id === roomState.winnerId);
    text += ` | Winner: ${winner ? winner.name : roomState.winnerId}`;
  }
  if (me) {
    text += ` | You: Lap ${me.laps}/${roomState.lapsToWin}`;
    if (me.bestLapMs) {
      text += ` | Best ${formatMs(me.bestLapMs)}`;
    }
    text += me.ready ? ' | READY' : ' | NOT READY';
  }
  phaseText.textContent = text;
}

function renderList(target, entries, formatter) {
  target.innerHTML = '';
  for (const entry of entries || []) {
    const li = document.createElement('li');
    li.textContent = formatter(entry);
    target.appendChild(li);
  }
}

function refreshLeaderboards() {
  renderList(roomLeaderboard, roomState.roomLeaderboard || [], (entry) =>
    `${entry.name} — ${formatMs(entry.timeMs)} (${entry.carName})`
  );

  renderList(globalLeaderboard, roomState.globalLeaderboard || [], (entry) =>
    `${entry.name} — ${formatMs(entry.timeMs)} (${entry.carName})`
  );
}

connectBtn.addEventListener('click', connect);
readyBtn.addEventListener('click', () => {
  const me = findMe();
  sendGarage(!(me?.ready || false));
});
startRaceBtn.addEventListener('click', () => send('start_race'));
resetLobbyBtn.addEventListener('click', () => send('reset_lobby'));
carSelect.addEventListener('change', () => sendGarage());
trackSelect.addEventListener('change', () => {
  if (trackSelect.value !== 'custom') {
    applySelectedTrack();
  }
});
applyTrackBtn.addEventListener('click', () => applySelectedTrack());
hostCustomMapBtn.addEventListener('click', () => hostCustomMap());
lapsSelect.addEventListener('change', () => sendGarage());
fullscreenBtn.addEventListener('click', () => toggleFullscreen());
document.addEventListener('fullscreenchange', updateFullscreenButtonLabel);

function isDriftKey(key, code) {
  return key === 'Shift' || code === 'ShiftLeft' || code === 'ShiftRight';
}

function setKeyState(key, code, pressed) {
  if (key === 'ArrowUp' || key === 'w' || key === 'W') inputState.up = pressed;
  if (key === 'ArrowDown' || key === 's' || key === 'S') inputState.down = pressed;
  if (key === 'ArrowLeft' || key === 'a' || key === 'A') inputState.left = pressed;
  if (key === 'ArrowRight' || key === 'd' || key === 'D') inputState.right = pressed;
  if (isDriftKey(key, code)) keyboardHandbrake = pressed;
}

window.addEventListener('keydown', (e) => {
  setKeyState(e.key, e.code, true);
  sendInputUpdate();
  if (['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight'].includes(e.key)) {
    e.preventDefault();
  }
});

window.addEventListener('keyup', (e) => {
  setKeyState(e.key, e.code, false);
  sendInputUpdate();
});

setInterval(() => {
  sendInputUpdate(true);
}, 1000 / 20);

setInterval(() => {
  if (!socket || socket.readyState !== WebSocket.OPEN) return;
  send('ping', { clientTime: performance.now() });
}, 1000);

function readTrigger(axisValue) {
  if (typeof axisValue !== 'number') return 0;
  return Math.max(0, Math.min(1, (axisValue + 1) * 0.5));
}

function applyDeadzone(value, deadzone = 0.15) {
  if (!Number.isFinite(value)) return 0;
  if (Math.abs(value) <= deadzone) return 0;
  const sign = Math.sign(value);
  const normalized = (Math.abs(value) - deadzone) / (1 - deadzone);
  return sign * Math.max(0, Math.min(1, normalized));
}

function updateGamepadState() {
  const pads = navigator.getGamepads ? navigator.getGamepads() : [];
  const pad = Array.from(pads).find((gp) => gp && gp.connected);

  if (!pad) {
    gamepadState.connected = false;
    gamepadState.throttle = 0;
    gamepadState.brake = 0;
    gamepadState.steer = 0;
    gamepadState.handbrake = false;
    return;
  }

  const steerAxis = applyDeadzone(pad.axes[0] || 0, 0.14);
  const throttleAxis = readTrigger(pad.axes[5]);
  const brakeAxis = readTrigger(pad.axes[2]);

  const throttleButton = pad.buttons?.[7]?.value || 0;
  const brakeButton = pad.buttons?.[6]?.value || 0;
  const handbrakePressed = Boolean(pad.buttons?.[0]?.pressed || pad.buttons?.[1]?.pressed || pad.buttons?.[2]?.pressed);

  gamepadState.connected = true;
  gamepadState.steer = steerAxis;
  gamepadState.throttle = Math.max(throttleAxis, throttleButton);
  gamepadState.brake = Math.max(brakeAxis, brakeButton);
  gamepadState.handbrake = handbrakePressed;
}

window.addEventListener('gamepadconnected', () => {
  setStatus('Controller connected');
});

window.addEventListener('gamepaddisconnected', () => {
  setStatus('Controller disconnected');
});

function drawMap() {
  if (!mapData || !mapBuffer) {
    ctx.fillStyle = '#0b3d20';
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    return;
  }
  ctx.drawImage(mapBuffer, 0, 0);
}

function spawnDriftParticles(player) {
  const rad = (Math.PI / 180) * player.rotationDeg + Math.PI;
  const fx = Math.cos(rad);
  const fy = Math.sin(rad);
  const rx = -fy;
  const ry = fx;

  const rearX = player.x - fx * 14;
  const rearY = player.y - fy * 14;

  const points = [
    { x: rearX + rx * 6, y: rearY + ry * 6 },
    { x: rearX - rx * 6, y: rearY - ry * 6 },
  ];

  for (const pt of points) {
    for (let i = 0; i < 1; i++) {
      particles.push({
        x: pt.x + (Math.random() - 0.5) * 2,
        y: pt.y + (Math.random() - 0.5) * 2,
        vx: -fx * (24 + Math.random() * 34) + (Math.random() - 0.5) * 18,
        vy: -fy * (24 + Math.random() * 34) + (Math.random() - 0.5) * 18,
        life: 0.8,
        maxLife: 0.8,
        size: 2 + Math.random() * 3,
        r: 86,
        g: 62,
        b: 40,
      });
    }
  }

  if (particles.length > 1200) {
    particles.splice(0, particles.length - 1200);
  }
}

function spawnTireMarks(player) {
  const rad = (Math.PI / 180) * player.rotationDeg + Math.PI;
  const fx = Math.cos(rad);
  const fy = Math.sin(rad);
  const rx = -fy;
  const ry = fx;

  const rearX = player.x - fx * 14;
  const rearY = player.y - fy * 14;
  const left = { x: rearX + rx * 6, y: rearY + ry * 6 };
  const right = { x: rearX - rx * 6, y: rearY - ry * 6 };

  const previous = tireTrackState[player.id];
  if (previous) {
    const leftDist = Math.hypot(left.x - previous.left.x, left.y - previous.left.y);
    const rightDist = Math.hypot(right.x - previous.right.x, right.y - previous.right.y);

    if (leftDist < 25 && rightDist < 25) {
      tireMarks.push(
        {
          x1: previous.left.x,
          y1: previous.left.y,
          x2: left.x,
          y2: left.y,
          width: 3.8,
          life: 8.5,
          maxLife: 8.5,
          alpha: 0.9,
        },
        {
          x1: previous.right.x,
          y1: previous.right.y,
          x2: right.x,
          y2: right.y,
          width: 3.8,
          life: 8.5,
          maxLife: 8.5,
          alpha: 0.9,
        }
      );
    }
  }

  tireTrackState[player.id] = { left, right };

  if (tireMarks.length > 2500) {
    tireMarks.splice(0, tireMarks.length - 2500);
  }
}

function updateAndDrawTireMarks(dt) {
  for (let i = tireMarks.length - 1; i >= 0; i--) {
    const mark = tireMarks[i];
    mark.life -= dt;
    if (mark.life <= 0) {
      tireMarks.splice(i, 1);
      continue;
    }

    const alpha = Math.max(0, mark.life / mark.maxLife) * mark.alpha;
    ctx.strokeStyle = `rgba(8, 6, 5, ${alpha.toFixed(3)})`;
    ctx.lineWidth = mark.width;
    ctx.lineCap = 'round';
    ctx.beginPath();
    ctx.moveTo(mark.x1, mark.y1);
    ctx.lineTo(mark.x2, mark.y2);
    ctx.stroke();
  }
}

function updateAndDrawParticles(dt) {
  for (let i = particles.length - 1; i >= 0; i--) {
    const p = particles[i];
    p.life -= dt;
    if (p.life <= 0) {
      particles.splice(i, 1);
      continue;
    }
    p.x += p.vx * dt;
    p.y += p.vy * dt;
    p.vx *= 0.95;
    p.vy *= 0.95;

    const a = Math.max(0, p.life / p.maxLife) * 0.95;
    ctx.fillStyle = `rgba(${p.r}, ${p.g}, ${p.b}, ${a.toFixed(3)})`;
    ctx.beginPath();
    ctx.arc(p.x, p.y, p.size, 0, Math.PI * 2);
    ctx.fill();
  }
}

function drawPlayer(p) {
  const width = 34;
  const height = 18;
  const turnState = Number(p.turnState || 0);
  const wheelAngle = turnState * 0.45;

  if (p.isDrifting && p.speed > 55) {
    const now = performance.now();
    const lastParticle = lastParticleSpawnByPlayer[p.id] || 0;
    if (now - lastParticle >= 55) {
      spawnDriftParticles(p);
      lastParticleSpawnByPlayer[p.id] = now;
    }

    const lastMark = lastTireMarkSpawnByPlayer[p.id] || 0;
    if (now - lastMark >= 35) {
      spawnTireMarks(p);
      lastTireMarkSpawnByPlayer[p.id] = now;
    }
  } else {
    delete tireTrackState[p.id];
  }

  ctx.save();
  ctx.translate(p.x, p.y);
  ctx.rotate((Math.PI / 180) * p.rotationDeg + Math.PI);

  ctx.fillStyle = '#0a0a0a';
  ctx.fillRect(-15, -9, 7, 4);
  ctx.fillRect(-15, 5, 7, 4);

  ctx.save();
  ctx.translate(8, -7);
  ctx.rotate(wheelAngle);
  ctx.fillRect(-3.5, -2, 7, 4);
  ctx.restore();

  ctx.save();
  ctx.translate(8, 7);
  ctx.rotate(wheelAngle);
  ctx.fillRect(-3.5, -2, 7, 4);
  ctx.restore();

  ctx.fillStyle = p.color;
  ctx.beginPath();
  ctx.roundRect(-width / 2, -height / 2 + 2, width, height - 4, 3);
  ctx.fill();

  ctx.beginPath();
  ctx.roundRect(-13, -8, 24, 16, 4);
  ctx.fill();

  ctx.fillStyle = '#1d2330';
  ctx.fillRect(-10, -7, 10, 2);
  ctx.fillRect(-10, 5, 10, 2);
  ctx.fillRect(4, -6, 3, 12);

  ctx.fillStyle = '#facc15';
  ctx.beginPath();
  ctx.moveTo(15, -7);
  ctx.lineTo(10, -7);
  ctx.lineTo(15, -4);
  ctx.closePath();
  ctx.fill();

  ctx.beginPath();
  ctx.moveTo(15, 7);
  ctx.lineTo(10, 7);
  ctx.lineTo(15, 4);
  ctx.closePath();
  ctx.fill();

  ctx.fillStyle = '#1e3a8a';
  ctx.fillRect(-18, -9, 4, 18);

  ctx.fillStyle = '#f8fafc';
  ctx.fillRect(-2, -3, 6, 6);

  ctx.restore();

  ctx.fillStyle = '#e2e8f0';
  ctx.font = '12px Arial';
  const label = `${p.name} L${p.laps}`;
  ctx.fillText(label, p.x - 22, p.y - 14);
}

function render(ts = 0) {
  let dt = 1 / 60;
  if (lastRenderTs > 0) {
    dt = Math.min(0.05, (ts - lastRenderTs) / 1000);
  }
  lastRenderTs = ts;

  updateGamepadState();
  sendInputUpdate();

  drawMap();
  updateAndDrawTireMarks(dt);
  updateAndDrawParticles(dt);
  const renderedPlayers = getRenderedPlayers(ts);
  for (const p of renderedPlayers) {
    drawPlayer(p);
  }
  refreshRaceHud();

  requestAnimationFrame(render);
}

updateFullscreenButtonLabel();
refreshRaceHud();
initMapEditor();
render();
