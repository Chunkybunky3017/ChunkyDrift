# 2D Racing Game

A simple top-down 2D racing game built with Python and Pygame.

## Run Instructions

1.  Make sure you have Python installed.
2.  Install Pygame:
    ```bash
    pip install pygame
    ```
3.  Run the game:
    ```bash
    python main.py
    ```

## Track Editor

Create your own tracks with the built-in editor:

```bash
python track_editor.py
```

- **Paint tools**: `1` Wall, `2` Road, `3` Start (`P`), `4` Finish (`F`), `5` Checkpoint (`C`)
- **Mouse**: Left click/drag paints selected tool, Right click/drag paints Wall
- **Files**:
    - `S` save/load format map: `custom_track_map.txt`
    - `E` export Python list: `custom_track_python.txt`
    - `X` export settings snippet: `custom_track_settings_snippet.txt`
- **Brands Hatch editing**:
    - Editor now opens with `BRANDS_HATCH_MAP` loaded
    - `B` resets canvas to imported Brands Hatch
    - `K` writes your current grid directly back into `settings.py` as `BRANDS_HATCH_MAP`

Copy exported rows into `settings.py` as a new map constant, then wire it in `game.py` like existing maps.

## Controls

-   **Keyboard (Player 1)**:
    -   **WASD** / **Arrow Keys**: Drive
    -   **Left Shift**: Drift / Handbrake
    -   **R**: Respawn
-   **Keyboard (Player 2)**:
    -   **Arrow Keys**: Drive
    -   **Right Shift/Ctrl**: Drift
    -   **Enter**: Respawn
-   **Controller / Gamepad**:
    -   **Right Trigger (R2)**: Accelerate
    -   **Left Trigger (L2)**: Brake / Reverse
    -   **Left Stick**: Steer
    -   **A / B Button**: Drift
    -   **Select / Start**: Respawn

## Features

-   **Game Modes**: Rally, Brands Hatch, Tokyo Drift, Stunt Track.
-   **Single Player**: choose between Free Play or Race Modes (1, 3, 5 laps).
-   **Leaderboards**: Track your best Race Times locally.
-   **Multiplayer**: Local split-screen/shared screen 2-player mode.
-   Top-down view of the entire track.
-   Car physics with acceleration, braking, and drifting friction.
-   Collision detection with walls and obstacles.

## Online Multiplayer Website (Setup)

A browser multiplayer foundation is included in `web_multiplayer/`.

### 1) Run locally

```bash
pip install -r web_multiplayer/requirements.txt
uvicorn web_multiplayer.server:app --reload --port 8000
```

Open:

```text
http://localhost:8000
```

### 2) Play online with friends

- Enter the same **Room** name on each browser.
- Enter different **Name** values.
- Click **Connect**.

### 3) Current scope

- Authoritative WebSocket game loop (server updates physics/state).
- Garage in browser (car selection, lap count, ready/start flow).
- Full race phases: lobby -> countdown -> racing -> finished.
- Lap/checkpoint/finish validation on server.
- Synced room leaderboard + persisted global leaderboard (`web_multiplayer/web_leaderboard.json`).
- Car-to-car collision physics (server-side).
- Uses `BRANDS_HATCH_MAP` from `settings.py`.

### 4) Deploy to Render

- `web_multiplayer/render.yaml` is included.
- Push this repo to GitHub.
- In Render, create a **Blueprint** deploy from repo.
- Render will run:
    - Build: `pip install -r web_multiplayer/requirements.txt`
    - Start: `uvicorn web_multiplayer.server:app --host 0.0.0.0 --port $PORT`
