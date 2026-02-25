import asyncio
import json
import math
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from settings import BRANDS_HATCH_MAP, CAR_MODELS, GAME_MAP, TILESIZE


ROAD_TILES = {'.', 'P', 'F', 'C'}
TICK_HZ = 60
CAR_COLLISION_RADIUS = 12.0
LEADERBOARD_FILE = Path(__file__).parent / 'web_leaderboard.json'
TIME_EPOCH_OFFSET = time.time() - time.perf_counter()
LEADERBOARD_PUSH_INTERVAL_SECONDS = 0.5
CUSTOM_TRACK_ID = 'custom'
ALLOWED_MAP_TILES = ROAD_TILES | {'1', 'W'}
CUSTOM_TRACKS_FILE = Path(__file__).parent / 'custom_tracks.json'
DEFAULT_SPAWN_ROTATION_DEG = 90.0
SPAWN_Y_OFFSET = 4.0

PRESET_TRACKS = {
    'brands_hatch': {
        'id': 'brands_hatch',
        'name': 'Brands Hatch',
        'rows': BRANDS_HATCH_MAP,
        'spawnRotationDeg': 90.0,
    },
    'rally_loop': {
        'id': 'rally_loop',
        'name': 'Rally Loop',
        'rows': GAME_MAP,
        'spawnRotationDeg': 180.0,
    },
}


def load_persisted_tracks() -> dict:
    if not CUSTOM_TRACKS_FILE.exists():
        return {}
    try:
        with open(CUSTOM_TRACKS_FILE, 'r', encoding='utf-8') as file:
            data = json.load(file)
        items = data.get('tracks', []) if isinstance(data, dict) else []
    except Exception:
        return {}

    loaded = {}
    for item in items:
        track_id = str(item.get('id', '')).strip()
        track_name = str(item.get('name', track_id)).strip() or track_id
        rows = normalize_map_rows(item.get('rows', []))
        is_valid, _, validated_rows = validate_map_rows(rows)
        if not is_valid:
            continue
        loaded[track_id] = {
            'id': track_id,
            'name': track_name,
            'rows': validated_rows,
            'spawnRotationDeg': normalize_spawn_rotation(item.get('spawnRotationDeg', DEFAULT_SPAWN_ROTATION_DEG)),
        }
    return loaded


def now_seconds() -> float:
    return TIME_EPOCH_OFFSET + time.perf_counter()


def rgb_to_hex(rgb):
    return '#{:02X}{:02X}{:02X}'.format(rgb[0], rgb[1], rgb[2])


def safe_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def normalize_spawn_rotation(value, default=DEFAULT_SPAWN_ROTATION_DEG):
    rotation = safe_float(value, default)
    while rotation < 0:
        rotation += 360
    while rotation >= 360:
        rotation -= 360
    return float(rotation)


def find_spawn(rows: List[str]):
    for row_idx, row in enumerate(rows):
        col_idx = row.find('P')
        if col_idx != -1:
            return (col_idx + 0.5) * TILESIZE, (row_idx + 0.5) * TILESIZE + SPAWN_Y_OFFSET
    return (8.5 * TILESIZE, 8.5 * TILESIZE + SPAWN_Y_OFFSET)


def normalize_map_rows(rows: List[str]) -> List[str]:
    return [str(row).rstrip('\n\r') for row in rows if str(row).strip()]


def validate_map_rows(rows: List[str]):
    cleaned_rows = normalize_map_rows(rows)
    if not cleaned_rows:
        return False, 'Map is empty.', None

    width = len(cleaned_rows[0])
    if width < 16:
        return False, 'Map width must be at least 16 tiles.', None
    if len(cleaned_rows) < 12:
        return False, 'Map height must be at least 12 tiles.', None

    if len(cleaned_rows) > 96 or width > 128:
        return False, 'Map is too large. Max size is 128x96.', None

    for row in cleaned_rows:
        if len(row) != width:
            return False, 'All map rows must have the same width.', None
        for char in row:
            if char not in ALLOWED_MAP_TILES:
                return False, f"Invalid tile '{char}'. Use only 1, W, ., P, F, C.", None

    start_count = sum(row.count('P') for row in cleaned_rows)
    finish_count = sum(row.count('F') for row in cleaned_rows)
    checkpoint_count = sum(row.count('C') for row in cleaned_rows)

    if start_count != 1:
        return False, 'Map must contain exactly one P start tile.', None
    if finish_count < 1:
        return False, 'Map must contain at least one F finish tile.', None
    if checkpoint_count < 1:
        return False, 'Map must contain at least one C checkpoint tile.', None

    return True, '', cleaned_rows


TRACK_LIBRARY = {**PRESET_TRACKS, **load_persisted_tracks()}
DEFAULT_TRACK = TRACK_LIBRARY.get('brands_hatch', next(iter(TRACK_LIBRARY.values())))
DEFAULT_SPAWN_X, DEFAULT_SPAWN_Y = find_spawn(DEFAULT_TRACK['rows'])


def room_map_payload(room):
    return {
        'id': room.track_id,
        'name': room.track_name,
        'spawnRotationDeg': room.spawn_rotation_deg,
        'tileSize': TILESIZE,
        'widthTiles': room.track_width_tiles,
        'heightTiles': room.track_height_tiles,
        'rows': room.track_rows,
    }

WEB_CAR_MODELS = [
    {
        'id': index,
        'name': model['name'],
        'color': rgb_to_hex(model['color']),
        'accel': float(model['accel']),
        'maxSpeed': float(model['max_speed']),
        'grip': float(model['grip']),
        'drag': float(model['drag']),
        'friction': float(model['friction']),
    }
    for index, model in enumerate(CAR_MODELS)
]


@dataclass
class InputState:
    up: bool = False
    down: bool = False
    left: bool = False
    right: bool = False
    handbrake: bool = False
    throttle: float = 0.0
    brake: float = 0.0
    steer: float = 0.0


@dataclass
class PlayerState:
    player_id: str
    name: str
    x: float
    y: float
    rotation_deg: float
    websocket: WebSocket
    car_id: int = 0
    color: str = '#3B82F6'
    ready: bool = False
    finished: bool = False
    laps: int = 0
    checkpoint_passed: bool = False
    last_finish_cross_time: float = 0.0
    lap_start_time: float = 0.0
    best_lap_time: float = 0.0
    race_total_time: float = 0.0
    input_state: InputState = field(default_factory=InputState)
    vx: float = 0.0
    vy: float = 0.0
    grip_state: float = 1.0


@dataclass
class RoomState:
    room_id: str
    players: Dict[str, PlayerState] = field(default_factory=dict)
    tick_task: asyncio.Task | None = None
    phase: str = 'lobby'  # lobby | countdown | racing | finished
    countdown_end_time: float = 0.0
    race_start_time: float = 0.0
    laps_to_win: int = 3
    winner_id: str | None = None
    last_leaderboard_push_time: float = 0.0
    track_id: str = DEFAULT_TRACK['id']
    track_name: str = DEFAULT_TRACK['name']
    track_rows: List[str] = field(default_factory=lambda: list(DEFAULT_TRACK['rows']))
    track_width_tiles: int = len(DEFAULT_TRACK['rows'][0])
    track_height_tiles: int = len(DEFAULT_TRACK['rows'])
    spawn_x: float = DEFAULT_SPAWN_X
    spawn_y: float = DEFAULT_SPAWN_Y
    spawn_rotation_deg: float = normalize_spawn_rotation(DEFAULT_TRACK.get('spawnRotationDeg', DEFAULT_SPAWN_ROTATION_DEG))


ROOMS: Dict[str, RoomState] = {}


def available_tracks_payload():
    tracks = sorted(TRACK_LIBRARY.values(), key=lambda track: track['name'].lower())
    return [
        {
            'id': track['id'],
            'name': track['name'],
            'spawnRotationDeg': normalize_spawn_rotation(track.get('spawnRotationDeg', DEFAULT_SPAWN_ROTATION_DEG)),
        }
        for track in tracks
    ]


def set_room_track(room: RoomState, track_id: str, rows: List[str], track_name: str, spawn_rotation_deg: float):
    room.track_id = track_id
    room.track_name = track_name
    room.track_rows = list(rows)
    room.track_width_tiles = len(rows[0])
    room.track_height_tiles = len(rows)
    room.spawn_x, room.spawn_y = find_spawn(rows)
    room.spawn_rotation_deg = normalize_spawn_rotation(spawn_rotation_deg, DEFAULT_SPAWN_ROTATION_DEG)
    room.phase = 'lobby'
    room.winner_id = None
    room.last_leaderboard_push_time = 0.0
    for index, player in enumerate(room.players.values()):
        player.ready = False
        player.finished = False
        player.laps = 0
        player.checkpoint_passed = False
        player.vx = 0.0
        player.vy = 0.0
        player.x = room.spawn_x + index * 18
        player.y = room.spawn_y


async def broadcast_room_map(room: RoomState):
    payload = {
        'type': 'map',
        'map': room_map_payload(room),
        'tracks': available_tracks_payload(),
    }
    recipients = [player.websocket for player in list(room.players.values())]
    if recipients:
        await asyncio.gather(*(safe_send_json(socket, payload) for socket in recipients), return_exceptions=True)


def load_leaderboard_store():
    if not LEADERBOARD_FILE.exists():
        return {'brands_hatch': {'1_laps': [], '3_laps': [], '5_laps': []}}
    try:
        with open(LEADERBOARD_FILE, 'r', encoding='utf-8') as file:
            data = json.load(file)
        if not isinstance(data, dict):
            raise ValueError('Invalid leaderboard structure')
    except Exception:
        data = {'brands_hatch': {'1_laps': [], '3_laps': [], '5_laps': []}}

    if 'brands_hatch' not in data or not isinstance(data['brands_hatch'], dict):
        data['brands_hatch'] = {}

    for category in ['1_laps', '3_laps', '5_laps']:
        if category not in data['brands_hatch'] or not isinstance(data['brands_hatch'][category], list):
            data['brands_hatch'][category] = []

    return data


LEADERBOARD_STORE = load_leaderboard_store()


def save_leaderboard_store():
    try:
        with open(LEADERBOARD_FILE, 'w', encoding='utf-8') as file:
            json.dump(LEADERBOARD_STORE, file, indent=2)
    except Exception:
        pass


def leaderboard_category(laps: int) -> str:
    if laps <= 1:
        return '1_laps'
    if laps >= 5:
        return '5_laps'
    return '3_laps'


def ensure_track_leaderboard(track_id: str):
    if track_id not in LEADERBOARD_STORE or not isinstance(LEADERBOARD_STORE[track_id], dict):
        LEADERBOARD_STORE[track_id] = {'1_laps': [], '3_laps': [], '5_laps': []}
    for category in ['1_laps', '3_laps', '5_laps']:
        if category not in LEADERBOARD_STORE[track_id] or not isinstance(LEADERBOARD_STORE[track_id][category], list):
            LEADERBOARD_STORE[track_id][category] = []


def update_global_leaderboard(track_id: str, player: PlayerState, laps_to_win: int):
    ensure_track_leaderboard(track_id)
    category = leaderboard_category(laps_to_win)
    entries = LEADERBOARD_STORE[track_id][category]
    entries.append(
        {
            'name': player.name,
            'timeMs': int(player.race_total_time),
            'carId': player.car_id,
            'carName': WEB_CAR_MODELS[player.car_id]['name'],
        }
    )
    entries.sort(key=lambda entry: entry['timeMs'])
    LEADERBOARD_STORE[track_id][category] = entries[:20]
    save_leaderboard_store()


app = FastAPI(title='Racing Game Web Multiplayer')

CLIENT_DIR = Path(__file__).parent / 'client'
app.mount('/client', StaticFiles(directory=str(CLIENT_DIR)), name='client')


@app.get('/')
async def root():
    return FileResponse(CLIENT_DIR / 'index.html')


@app.get('/api/map')
async def get_map():
    return {
        'name': DEFAULT_TRACK['id'],
        'tileSize': TILESIZE,
        'widthTiles': len(DEFAULT_TRACK['rows'][0]),
        'heightTiles': len(DEFAULT_TRACK['rows']),
        'rows': DEFAULT_TRACK['rows'],
    }


@app.get('/api/tracks')
async def get_tracks():
    return {'tracks': available_tracks_payload()}


@app.get('/api/cars')
async def get_cars():
    return {'cars': WEB_CAR_MODELS}


@app.get('/api/leaderboard')
async def get_leaderboard():
    ensure_track_leaderboard(DEFAULT_TRACK['id'])
    return LEADERBOARD_STORE[DEFAULT_TRACK['id']]


def is_on_road(room: RoomState, x: float, y: float) -> bool:
    col = int(x // TILESIZE)
    row = int(y // TILESIZE)
    if row < 0 or col < 0 or row >= room.track_height_tiles or col >= room.track_width_tiles:
        return False
    return room.track_rows[row][col] in ROAD_TILES


def current_tile(room: RoomState, x: float, y: float):
    col = int(x // TILESIZE)
    row = int(y // TILESIZE)
    if row < 0 or col < 0 or row >= room.track_height_tiles or col >= room.track_width_tiles:
        return '1'
    return room.track_rows[row][col]


async def safe_send_json(ws: WebSocket, payload: dict):
    try:
        await ws.send_json(payload)
    except Exception:
        pass


def room_leaderboard_snapshot(room: RoomState):
    finished = [p for p in room.players.values() if p.finished]
    finished.sort(key=lambda p: p.race_total_time)
    return [
        {
            'id': p.player_id,
            'name': p.name,
            'timeMs': int(p.race_total_time),
            'carName': WEB_CAR_MODELS[p.car_id]['name'],
        }
        for p in finished
    ]


async def broadcast_room_state(room: RoomState):
    now = now_seconds()
    include_leaderboards = (
        room.phase in ('lobby', 'finished')
        or room.last_leaderboard_push_time <= 0
        or (now - room.last_leaderboard_push_time) >= LEADERBOARD_PUSH_INTERVAL_SECONDS
    )
    if include_leaderboards:
        room.last_leaderboard_push_time = now

    room_payload = {
        'phase': room.phase,
        'lapsToWin': room.laps_to_win,
        'trackId': room.track_id,
        'trackName': room.track_name,
        'countdownSecondsLeft': max(0, int(math.ceil(room.countdown_end_time - now))) if room.phase == 'countdown' else 0,
        'winnerId': room.winner_id,
        'raceElapsedMs': int((now - room.race_start_time) * 1000) if room.phase in ('racing', 'finished') and room.race_start_time > 0 else 0,
    }

    if include_leaderboards:
        ensure_track_leaderboard(room.track_id)
        room_payload['roomLeaderboard'] = room_leaderboard_snapshot(room)
        room_payload['globalLeaderboard'] = LEADERBOARD_STORE[room.track_id][leaderboard_category(room.laps_to_win)]

    payload = {
        'type': 'state',
        'serverTime': now,
        'room': room_payload,
        'players': [
            {
                'id': p.player_id,
                'name': p.name,
                'color': p.color,
                'carId': p.car_id,
                'x': p.x,
                'y': p.y,
                'rotationDeg': p.rotation_deg,
                'vx': p.vx,
                'vy': p.vy,
                'speed': math.sqrt(p.vx * p.vx + p.vy * p.vy),
                'turnState': (
                    -1 if p.input_state.steer < -0.1
                    else 1 if p.input_state.steer > 0.1
                    else -1 if p.input_state.left and not p.input_state.right
                    else 1 if p.input_state.right and not p.input_state.left
                    else 0
                ),
                'isDrifting': bool(p.input_state.handbrake and math.sqrt(p.vx * p.vx + p.vy * p.vy) > 50),
                'ready': p.ready,
                'laps': p.laps,
                'finished': p.finished,
                'bestLapMs': int(p.best_lap_time) if p.best_lap_time > 0 else 0,
            }
            for p in room.players.values()
        ],
    }

    recipients = [player.websocket for player in list(room.players.values())]
    if recipients:
        await asyncio.gather(*(safe_send_json(socket, payload) for socket in recipients), return_exceptions=True)


def set_player_car(player: PlayerState, car_id: int):
    if car_id < 0 or car_id >= len(WEB_CAR_MODELS):
        car_id = 0
    player.car_id = car_id
    player.color = WEB_CAR_MODELS[car_id]['color']
    player.grip_state = WEB_CAR_MODELS[car_id]['grip']


def reset_player_for_race(room: RoomState, player: PlayerState, index_in_grid: int):
    spawn_spacing = 18
    player.x = room.spawn_x + index_in_grid * spawn_spacing
    player.y = room.spawn_y
    player.rotation_deg = room.spawn_rotation_deg
    player.vx = 0.0
    player.vy = 0.0
    player.ready = False
    player.finished = False
    player.laps = 0
    player.checkpoint_passed = False
    player.last_finish_cross_time = 0.0
    player.lap_start_time = now_seconds()
    player.best_lap_time = 0.0
    player.race_total_time = 0.0
    player.input_state = InputState()
    player.grip_state = WEB_CAR_MODELS[player.car_id]['grip']


def start_countdown(room: RoomState):
    if not room.players:
        return

    room.phase = 'countdown'
    room.winner_id = None
    room.countdown_end_time = now_seconds() + 3.0

    for idx, player in enumerate(room.players.values()):
        reset_player_for_race(room, player, idx)


def maybe_begin_race(room: RoomState):
    if room.phase != 'countdown':
        return
    if now_seconds() < room.countdown_end_time:
        return

    room.phase = 'racing'
    room.race_start_time = now_seconds()
    for player in room.players.values():
        player.lap_start_time = room.race_start_time


def step_player_physics(room: RoomState, player: PlayerState, dt: float):
    car = WEB_CAR_MODELS[player.car_id]
    accel = car['accel']
    brake_accel = car['accel'] * 0.5
    max_speed = car['maxSpeed']
    drag = car['drag']
    friction = car['friction']
    base_grip = car['grip']
    turn_rate = 150.0

    if player.finished:
        player.vx *= 0.9
        player.vy *= 0.9
        return

    analog_steer = max(-1.0, min(1.0, float(player.input_state.steer)))
    if abs(analog_steer) < 0.05:
        turn_dir = 0.0
        if player.input_state.left:
            turn_dir -= 1.0
        if player.input_state.right:
            turn_dir += 1.0
    else:
        turn_dir = analog_steer

    speed = math.sqrt(player.vx * player.vx + player.vy * player.vy)
    if speed > 2 and turn_dir != 0.0:
        turn_multiplier = 1.3 if player.input_state.handbrake else 0.6
        player.rotation_deg = (player.rotation_deg + turn_dir * turn_rate * turn_multiplier * dt) % 360

    radians = math.radians(player.rotation_deg)
    fx = math.cos(radians)
    fy = math.sin(radians)

    throttle_amount = max(0.0, min(1.0, float(player.input_state.throttle)))
    brake_amount = max(0.0, min(1.0, float(player.input_state.brake)))
    if throttle_amount <= 0 and player.input_state.up:
        throttle_amount = 1.0
    if brake_amount <= 0 and player.input_state.down:
        brake_amount = 1.0

    if throttle_amount > 0:
        player.vx -= fx * accel * throttle_amount * dt
        player.vy -= fy * accel * throttle_amount * dt
    if brake_amount > 0:
        player.vx += fx * brake_accel * brake_amount * dt
        player.vy += fy * brake_accel * brake_amount * dt

    speed = math.sqrt(player.vx * player.vx + player.vy * player.vy)
    if speed > 0.0001:
        friction_force = friction * dt
        player.vx -= (player.vx / speed) * friction_force
        player.vy -= (player.vy / speed) * friction_force

    player.vx *= drag
    player.vy *= drag

    right_x = -fy
    right_y = fx

    forward_dot = player.vx * fx + player.vy * fy
    sideways_dot = player.vx * right_x + player.vy * right_y

    vel_forward_x = fx * forward_dot
    vel_forward_y = fy * forward_dot
    vel_side_x = right_x * sideways_dot
    vel_side_y = right_y * sideways_dot

    if player.input_state.handbrake:
        target_grip = 0.05
        player.grip_state += (target_grip - player.grip_state) * 4.0 * dt
    else:
        player.grip_state = base_grip

    friction_factor = 0.99 - (player.grip_state * 0.25)
    vel_side_x *= friction_factor
    vel_side_y *= friction_factor

    if not player.input_state.handbrake:
        vel_side_x *= 0.55
        vel_side_y *= 0.55

    player.vx = vel_forward_x + vel_side_x
    player.vy = vel_forward_y + vel_side_y

    speed = math.sqrt(player.vx * player.vx + player.vy * player.vy)
    if speed > max_speed:
        scale = max_speed / speed
        player.vx *= scale
        player.vy *= scale

    if speed < 3 and not player.input_state.up and not player.input_state.down:
        player.vx = 0.0
        player.vy = 0.0

    # sub-step movement to avoid tunneling through walls
    move_x = player.vx * dt
    move_y = player.vy * dt
    max_component = max(abs(move_x), abs(move_y))
    steps = max(1, int(max_component // (TILESIZE / 3)) + 1)

    step_x = move_x / steps
    step_y = move_y / steps

    for _ in range(steps):
        next_x = player.x + step_x
        next_y = player.y + step_y
        if is_on_road(room, next_x, next_y):
            player.x = next_x
            player.y = next_y
        else:
            player.vx *= -0.25
            player.vy *= -0.25
            break


def solve_car_collisions(players: List[PlayerState]):
    restitution = 0.35
    radius = CAR_COLLISION_RADIUS

    for i in range(len(players)):
        for j in range(i + 1, len(players)):
            a = players[i]
            b = players[j]

            dx = b.x - a.x
            dy = b.y - a.y
            dist_sq = dx * dx + dy * dy
            min_dist = radius * 2
            min_dist_sq = min_dist * min_dist

            if dist_sq <= 0.0001 or dist_sq >= min_dist_sq:
                continue

            dist = math.sqrt(dist_sq)
            nx = dx / dist
            ny = dy / dist

            # positional correction
            overlap = min_dist - dist
            correction = overlap * 0.5
            a.x -= nx * correction
            a.y -= ny * correction
            b.x += nx * correction
            b.y += ny * correction

            # resolve velocity along normal
            rvx = b.vx - a.vx
            rvy = b.vy - a.vy
            vel_along_normal = rvx * nx + rvy * ny
            if vel_along_normal > 0:
                continue

            impulse = -(1.0 + restitution) * vel_along_normal / 2.0
            ix = impulse * nx
            iy = impulse * ny

            a.vx -= ix
            a.vy -= iy
            b.vx += ix
            b.vy += iy


def update_laps_and_finish(room: RoomState):
    if room.phase != 'racing':
        return

    now = now_seconds()

    for player in room.players.values():
        if player.finished:
            continue

        tile = current_tile(room, player.x, player.y)

        if tile == 'C':
            player.checkpoint_passed = True

        if tile == 'F' and player.checkpoint_passed and (now - player.last_finish_cross_time) > 1.0:
            player.last_finish_cross_time = now
            lap_time_ms = (now - player.lap_start_time) * 1000.0
            player.lap_start_time = now
            player.laps += 1
            player.checkpoint_passed = False

            if player.best_lap_time == 0 or lap_time_ms < player.best_lap_time:
                player.best_lap_time = lap_time_ms

            if player.laps >= room.laps_to_win:
                player.finished = True
                player.race_total_time = (now - room.race_start_time) * 1000.0
                if room.winner_id is None:
                    room.winner_id = player.player_id
                    update_global_leaderboard(room.track_id, player, room.laps_to_win)
                    room.phase = 'finished'


def get_or_create_room(room_id: str) -> RoomState:
    room = ROOMS.get(room_id)
    if room:
        return room

    room = RoomState(room_id=room_id)
    ROOMS[room_id] = room
    return room


async def room_tick_loop(room: RoomState):
    dt = 1.0 / TICK_HZ
    next_tick = now_seconds()

    try:
        while True:
            if not room.players:
                await asyncio.sleep(0.2)
                if not room.players:
                    break

            maybe_begin_race(room)

            if room.phase == 'racing':
                player_list = list(room.players.values())
                for player in player_list:
                    step_player_physics(room, player, dt)
                solve_car_collisions(player_list)
                update_laps_and_finish(room)

            await broadcast_room_state(room)

            next_tick += dt
            sleep_for = next_tick - now_seconds()
            if sleep_for > 0:
                await asyncio.sleep(sleep_for)
            else:
                next_tick = now_seconds()
    finally:
        room.tick_task = None
        if not room.players and room.room_id in ROOMS:
            del ROOMS[room.room_id]


@app.websocket('/ws/{room_id}/{player_name}')
async def websocket_game(websocket: WebSocket, room_id: str, player_name: str):
    await websocket.accept()

    room = get_or_create_room(room_id)

    player_id = str(uuid.uuid4())[:8]

    player = PlayerState(
        player_id=player_id,
        name=player_name[:18] or 'Player',
        x=room.spawn_x + len(room.players) * 18,
        y=room.spawn_y,
        rotation_deg=room.spawn_rotation_deg,
        websocket=websocket,
    )
    set_player_car(player, len(room.players) % max(1, len(WEB_CAR_MODELS)))
    room.players[player_id] = player

    if room.tick_task is None or room.tick_task.done():
        room.tick_task = asyncio.create_task(room_tick_loop(room))

    await safe_send_json(
        websocket,
        {
            'type': 'welcome',
            'playerId': player_id,
            'roomId': room_id,
            'map': room_map_payload(room),
            'tracks': available_tracks_payload(),
            'cars': WEB_CAR_MODELS,
        },
    )

    await broadcast_room_state(room)

    try:
        while True:
            message = await websocket.receive_json()
            msg_type = message.get('type')

            if msg_type == 'input':
                input_payload = message.get('input', {})
                player.input_state = InputState(
                    up=bool(input_payload.get('up', False)),
                    down=bool(input_payload.get('down', False)),
                    left=bool(input_payload.get('left', False)),
                    right=bool(input_payload.get('right', False)),
                    handbrake=bool(input_payload.get('handbrake', False)),
                    throttle=max(0.0, min(1.0, safe_float(input_payload.get('throttle', 0.0), 0.0))),
                    brake=max(0.0, min(1.0, safe_float(input_payload.get('brake', 0.0), 0.0))),
                    steer=max(-1.0, min(1.0, safe_float(input_payload.get('steer', 0.0), 0.0))),
                )

            elif msg_type == 'garage':
                requested_car_id = int(message.get('carId', 0))
                requested_laps = int(message.get('lapsToWin', room.laps_to_win))
                requested_ready = bool(message.get('ready', False))

                set_player_car(player, requested_car_id)
                if room.phase in ('lobby', 'finished'):
                    room.laps_to_win = max(1, min(5, requested_laps))
                    player.ready = requested_ready

            elif msg_type == 'set_track':
                if room.phase not in ('lobby', 'finished'):
                    await safe_send_json(
                        websocket,
                        {
                            'type': 'error',
                            'message': 'Track can only be changed in lobby or after race finish.',
                        },
                    )
                else:
                    requested_track_id = str(message.get('trackId', DEFAULT_TRACK['id']))

                    if requested_track_id == CUSTOM_TRACK_ID:
                        raw_map = str(message.get('customMap', ''))
                        requested_rotation = normalize_spawn_rotation(message.get('spawnRotationDeg', DEFAULT_SPAWN_ROTATION_DEG))
                        custom_rows = raw_map.splitlines()
                        is_valid, error_message, validated_rows = validate_map_rows(custom_rows)
                        if not is_valid:
                            await safe_send_json(
                                websocket,
                                {
                                    'type': 'error',
                                    'message': error_message,
                                },
                            )
                        else:
                            set_room_track(room, CUSTOM_TRACK_ID, validated_rows, f'Custom by {player.name}', requested_rotation)
                            await broadcast_room_map(room)
                    elif requested_track_id in TRACK_LIBRARY:
                        preset = TRACK_LIBRARY[requested_track_id]
                        set_room_track(
                            room,
                            preset['id'],
                            preset['rows'],
                            preset['name'],
                            normalize_spawn_rotation(preset.get('spawnRotationDeg', DEFAULT_SPAWN_ROTATION_DEG)),
                        )
                        await broadcast_room_map(room)
                    else:
                        await safe_send_json(
                            websocket,
                            {
                                'type': 'error',
                                'message': 'Unknown track selection.',
                            },
                        )

            elif msg_type == 'start_race':
                if room.phase in ('lobby', 'finished') and room.players:
                    if all(p.ready for p in room.players.values()):
                        start_countdown(room)
                    else:
                        await safe_send_json(
                            websocket,
                            {
                                'type': 'error',
                                'message': 'All players must be ready before starting race.',
                            },
                        )

            elif msg_type == 'reset_lobby':
                room.phase = 'lobby'
                room.winner_id = None
                for p in room.players.values():
                    p.ready = False
                    p.finished = False
                    p.laps = 0

            elif msg_type == 'ping':
                await safe_send_json(
                    websocket,
                    {
                        'type': 'pong',
                        'clientTime': float(message.get('clientTime', 0.0)),
                        'serverTime': now_seconds(),
                    },
                )

            await broadcast_room_state(room)

    except WebSocketDisconnect:
        pass
    finally:
        if player_id in room.players:
            del room.players[player_id]
        await broadcast_room_state(room)
