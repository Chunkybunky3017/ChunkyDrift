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

from settings import BRANDS_HATCH_MAP, CAR_MODELS, TILESIZE


ROAD_TILES = {'.', 'P', 'F', 'C'}
TICK_HZ = 30
CAR_COLLISION_RADIUS = 12.0
LEADERBOARD_FILE = Path(__file__).parent / 'web_leaderboard.json'

TRACK_WIDTH_TILES = len(BRANDS_HATCH_MAP[0])
TRACK_HEIGHT_TILES = len(BRANDS_HATCH_MAP)


def rgb_to_hex(rgb):
    return '#{:02X}{:02X}{:02X}'.format(rgb[0], rgb[1], rgb[2])


def find_spawn():
    for row_idx, row in enumerate(BRANDS_HATCH_MAP):
        col_idx = row.find('P')
        if col_idx != -1:
            return (col_idx + 0.5) * TILESIZE, (row_idx + 0.5) * TILESIZE
    return (8.5 * TILESIZE, 8.5 * TILESIZE)


SPAWN_X, SPAWN_Y = find_spawn()

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


ROOMS: Dict[str, RoomState] = {}


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


def update_global_leaderboard(player: PlayerState, laps_to_win: int):
    category = leaderboard_category(laps_to_win)
    entries = LEADERBOARD_STORE['brands_hatch'][category]
    entries.append(
        {
            'name': player.name,
            'timeMs': int(player.race_total_time),
            'carId': player.car_id,
            'carName': WEB_CAR_MODELS[player.car_id]['name'],
        }
    )
    entries.sort(key=lambda entry: entry['timeMs'])
    LEADERBOARD_STORE['brands_hatch'][category] = entries[:20]
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
        'name': 'brands_hatch',
        'tileSize': TILESIZE,
        'widthTiles': TRACK_WIDTH_TILES,
        'heightTiles': TRACK_HEIGHT_TILES,
        'rows': BRANDS_HATCH_MAP,
    }


@app.get('/api/cars')
async def get_cars():
    return {'cars': WEB_CAR_MODELS}


@app.get('/api/leaderboard')
async def get_leaderboard():
    return LEADERBOARD_STORE['brands_hatch']


def is_on_road(x: float, y: float) -> bool:
    col = int(x // TILESIZE)
    row = int(y // TILESIZE)
    if row < 0 or col < 0 or row >= TRACK_HEIGHT_TILES or col >= TRACK_WIDTH_TILES:
        return False
    return BRANDS_HATCH_MAP[row][col] in ROAD_TILES


def current_tile(x: float, y: float):
    col = int(x // TILESIZE)
    row = int(y // TILESIZE)
    if row < 0 or col < 0 or row >= TRACK_HEIGHT_TILES or col >= TRACK_WIDTH_TILES:
        return '1'
    return BRANDS_HATCH_MAP[row][col]


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
    now = time.time()
    payload = {
        'type': 'state',
        'serverTime': now,
        'room': {
            'phase': room.phase,
            'lapsToWin': room.laps_to_win,
            'countdownSecondsLeft': max(0, int(math.ceil(room.countdown_end_time - now))) if room.phase == 'countdown' else 0,
            'winnerId': room.winner_id,
            'raceElapsedMs': int((now - room.race_start_time) * 1000) if room.phase in ('racing', 'finished') and room.race_start_time > 0 else 0,
            'roomLeaderboard': room_leaderboard_snapshot(room),
            'globalLeaderboard': LEADERBOARD_STORE['brands_hatch'][leaderboard_category(room.laps_to_win)],
        },
        'players': [
            {
                'id': p.player_id,
                'name': p.name,
                'color': p.color,
                'carId': p.car_id,
                'carName': WEB_CAR_MODELS[p.car_id]['name'],
                'x': p.x,
                'y': p.y,
                'rotationDeg': p.rotation_deg,
                'speed': math.sqrt(p.vx * p.vx + p.vy * p.vy),
                'turnState': (-1 if p.input_state.left and not p.input_state.right else 1 if p.input_state.right and not p.input_state.left else 0),
                'isDrifting': bool(p.input_state.handbrake and math.sqrt(p.vx * p.vx + p.vy * p.vy) > 50),
                'ready': p.ready,
                'laps': p.laps,
                'finished': p.finished,
                'bestLapMs': int(p.best_lap_time) if p.best_lap_time > 0 else 0,
            }
            for p in room.players.values()
        ],
    }

    for player in list(room.players.values()):
        await safe_send_json(player.websocket, payload)


def set_player_car(player: PlayerState, car_id: int):
    if car_id < 0 or car_id >= len(WEB_CAR_MODELS):
        car_id = 0
    player.car_id = car_id
    player.color = WEB_CAR_MODELS[car_id]['color']
    player.grip_state = WEB_CAR_MODELS[car_id]['grip']


def reset_player_for_race(player: PlayerState, index_in_grid: int):
    spawn_spacing = 18
    player.x = SPAWN_X + index_in_grid * spawn_spacing
    player.y = SPAWN_Y
    player.rotation_deg = 90
    player.vx = 0.0
    player.vy = 0.0
    player.ready = False
    player.finished = False
    player.laps = 0
    player.checkpoint_passed = False
    player.last_finish_cross_time = 0.0
    player.lap_start_time = time.time()
    player.best_lap_time = 0.0
    player.race_total_time = 0.0
    player.input_state = InputState()
    player.grip_state = WEB_CAR_MODELS[player.car_id]['grip']


def start_countdown(room: RoomState):
    if not room.players:
        return

    room.phase = 'countdown'
    room.winner_id = None
    room.countdown_end_time = time.time() + 3.0

    for idx, player in enumerate(room.players.values()):
        reset_player_for_race(player, idx)


def maybe_begin_race(room: RoomState):
    if room.phase != 'countdown':
        return
    if time.time() < room.countdown_end_time:
        return

    room.phase = 'racing'
    room.race_start_time = time.time()
    for player in room.players.values():
        player.lap_start_time = room.race_start_time


def step_player_physics(player: PlayerState, dt: float):
    car = WEB_CAR_MODELS[player.car_id]
    accel = car['accel']
    brake_accel = car['accel'] * 0.5
    max_speed = car['maxSpeed']
    drag = car['drag']
    friction = car['friction']
    base_grip = car['grip']
    turn_rate = 200.0

    if player.finished:
        player.vx *= 0.9
        player.vy *= 0.9
        return

    turn_dir = 0.0
    if player.input_state.left:
        turn_dir -= 1.0
    if player.input_state.right:
        turn_dir += 1.0

    speed = math.sqrt(player.vx * player.vx + player.vy * player.vy)
    if speed > 2 and turn_dir != 0.0:
        turn_multiplier = 1.3 if player.input_state.handbrake else 0.6
        player.rotation_deg = (player.rotation_deg + turn_dir * turn_rate * turn_multiplier * dt) % 360

    radians = math.radians(player.rotation_deg)
    fx = math.cos(radians)
    fy = math.sin(radians)

    if player.input_state.up:
        player.vx -= fx * accel * dt
        player.vy -= fy * accel * dt
    if player.input_state.down:
        player.vx += fx * brake_accel * dt
        player.vy += fy * brake_accel * dt

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

    target_grip = 0.05 if player.input_state.handbrake else base_grip
    player.grip_state += (target_grip - player.grip_state) * 1.5 * dt

    friction_factor = 0.99 - (player.grip_state * 0.25)
    vel_side_x *= friction_factor
    vel_side_y *= friction_factor

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
        if is_on_road(next_x, next_y):
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

    now = time.time()

    for player in room.players.values():
        if player.finished:
            continue

        tile = current_tile(player.x, player.y)

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
                    update_global_leaderboard(player, room.laps_to_win)
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
                    step_player_physics(player, dt)
                solve_car_collisions(player_list)
                update_laps_and_finish(room)

            await broadcast_room_state(room)
            await asyncio.sleep(dt)
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
        x=SPAWN_X + len(room.players) * 18,
        y=SPAWN_Y,
        rotation_deg=90,
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
            'map': {
                'name': 'brands_hatch',
                'tileSize': TILESIZE,
                'widthTiles': TRACK_WIDTH_TILES,
                'heightTiles': TRACK_HEIGHT_TILES,
                'rows': BRANDS_HATCH_MAP,
            },
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
                )

            elif msg_type == 'garage':
                requested_car_id = int(message.get('carId', 0))
                requested_laps = int(message.get('lapsToWin', room.laps_to_win))
                requested_ready = bool(message.get('ready', False))

                set_player_car(player, requested_car_id)
                if room.phase in ('lobby', 'finished'):
                    room.laps_to_win = max(1, min(5, requested_laps))
                    player.ready = requested_ready

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

            await broadcast_room_state(room)

    except WebSocketDisconnect:
        pass
    finally:
        if player_id in room.players:
            del room.players[player_id]
        await broadcast_room_state(room)
