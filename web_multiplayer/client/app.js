const canvas = document.getElementById('gameCanvas');
const ctx = canvas.getContext('2d');

const roomInput = document.getElementById('roomInput');
const nameInput = document.getElementById('nameInput');
const connectBtn = document.getElementById('connectBtn');
const readyBtn = document.getElementById('readyBtn');
const startRaceBtn = document.getElementById('startRaceBtn');
const resetLobbyBtn = document.getElementById('resetLobbyBtn');
const carSelect = document.getElementById('carSelect');
const lapsSelect = document.getElementById('lapsSelect');
const statusText = document.getElementById('statusText');
const phaseText = document.getElementById('phaseText');
const roomLeaderboard = document.getElementById('roomLeaderboard');
const globalLeaderboard = document.getElementById('globalLeaderboard');

let socket = null;
let connected = false;
let playerId = null;
let players = [];
let mapData = null;
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
  countdownSecondsLeft: 0,
  winnerId: null,
  raceElapsedMs: 0,
  roomLeaderboard: [],
  globalLeaderboard: [],
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
    setStatus(`Connected to '${room}'`);
  };

  socket.onclose = () => {
    connected = false;
    playerId = null;
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
      carModels = message.cars || [];
      populateCars();
      sendGarage(false);
    }

    if (message.type === 'error') {
      setStatus(message.message || 'Server error', true);
    }

    if (message.type === 'state') {
      players = message.players || [];
      roomState = message.room || roomState;
      lapsSelect.value = String(roomState.lapsToWin || 3);
      refreshLeaderboards();
      refreshPhase();
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
lapsSelect.addEventListener('change', () => sendGarage());

function isDriftKey(key, code) {
  return key === 'Shift' || code === 'ShiftLeft' || code === 'ShiftRight';
}

function setKeyState(key, code, pressed) {
  if (key === 'ArrowUp' || key === 'w' || key === 'W') inputState.up = pressed;
  if (key === 'ArrowDown' || key === 's' || key === 'S') inputState.down = pressed;
  if (key === 'ArrowLeft' || key === 'a' || key === 'A') inputState.left = pressed;
  if (key === 'ArrowRight' || key === 'd' || key === 'D') inputState.right = pressed;
  if (isDriftKey(key, code)) inputState.handbrake = pressed;
}

window.addEventListener('keydown', (e) => {
  setKeyState(e.key, e.code, true);
  if (['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight'].includes(e.key)) {
    e.preventDefault();
  }
});

window.addEventListener('keyup', (e) => {
  setKeyState(e.key, e.code, false);
});

setInterval(() => {
  if (!socket || socket.readyState !== WebSocket.OPEN) return;
  send('input', { input: inputState });
}, 1000 / 30);

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

  drawMap();
  updateAndDrawTireMarks(dt);
  updateAndDrawParticles(dt);
  for (const p of players) {
    drawPlayer(p);
  }

  requestAnimationFrame(render);
}

render();
