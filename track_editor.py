import os
import pygame

from settings import BRANDS_HATCH_MAP


TILE_WALL = '1'
TILE_ROAD = '.'
TILE_START = 'P'
TILE_FINISH = 'F'
TILE_CHECKPOINT = 'C'

TOOLS = {
    pygame.K_1: TILE_WALL,
    pygame.K_2: TILE_ROAD,
    pygame.K_3: TILE_START,
    pygame.K_4: TILE_FINISH,
    pygame.K_5: TILE_CHECKPOINT,
}

TOOL_NAMES = {
    TILE_WALL: 'Wall/Grass',
    TILE_ROAD: 'Road',
    TILE_START: 'Player Spawn',
    TILE_FINISH: 'Finish Line',
    TILE_CHECKPOINT: 'Checkpoint',
}

COLORS = {
    TILE_WALL: (34, 139, 34),
    TILE_ROAD: (150, 115, 75),
    TILE_START: (70, 130, 220),
    TILE_FINISH: (230, 230, 230),
    TILE_CHECKPOINT: (0, 220, 220),
}

GRID_LINE_COLOR = (40, 40, 40)
PANEL_BG = (25, 25, 25)
TEXT_COLOR = (230, 230, 230)
HIGHLIGHT = (255, 220, 0)


class TrackEditor:
    def __init__(self):
        pygame.init()
        self.font = pygame.font.SysFont('consolas', 18)
        self.small_font = pygame.font.SysFont('consolas', 15)

        self.map_name = 'BRANDS_HATCH_MAP'
        self.map_height = len(BRANDS_HATCH_MAP)
        self.map_width = len(BRANDS_HATCH_MAP[0])

        self.tile_size = 12
        self.map_px_w = self.map_width * self.tile_size
        self.map_px_h = self.map_height * self.tile_size

        self.panel_w = 360
        self.screen = pygame.display.set_mode((self.map_px_w + self.panel_w, self.map_px_h))
        pygame.display.set_caption('Racing Track Editor')

        self.clock = pygame.time.Clock()
        self.running = True

        self.original_grid = [list(row) for row in BRANDS_HATCH_MAP]
        self.grid = [row[:] for row in self.original_grid]
        self.current_tool = TILE_ROAD
        self.status_text = 'Editing BRANDS_HATCH_MAP'

        self.default_map_path = 'custom_track_map.txt'
        self.default_python_path = 'custom_track_python.txt'
        self.default_snippet_path = 'custom_track_settings_snippet.txt'
        self.settings_file_path = os.path.join(os.path.dirname(__file__), 'settings.py')

    def set_status(self, text):
        self.status_text = text

    def map_bounds_check(self, col, row):
        return 0 <= row < self.map_height and 0 <= col < self.map_width

    def place_tile(self, col, row, tile):
        if not self.map_bounds_check(col, row):
            return

        if tile == TILE_START:
            for y in range(self.map_height):
                for x in range(self.map_width):
                    if self.grid[y][x] == TILE_START:
                        self.grid[y][x] = TILE_ROAD

        self.grid[row][col] = tile

    def mouse_to_cell(self, mouse_pos):
        mx, my = mouse_pos
        if mx < 0 or my < 0 or mx >= self.map_px_w or my >= self.map_px_h:
            return None
        return mx // self.tile_size, my // self.tile_size

    def clear_map(self):
        self.grid = [[TILE_WALL for _ in range(self.map_width)] for _ in range(self.map_height)]
        self.set_status('Cleared map to walls')

    def reset_to_brands_hatch(self):
        self.grid = [row[:] for row in self.original_grid]
        self.set_status('Reset to current BRANDS_HATCH_MAP from settings import')

    def save_map(self, path=None):
        file_path = path or self.default_map_path
        try:
            with open(file_path, 'w', encoding='utf-8') as file:
                for row in self.grid:
                    file.write(''.join(row) + '\n')
            self.set_status(f'Saved map to {file_path}')
        except OSError as exc:
            self.set_status(f'Save failed: {exc}')

    def load_map(self, path=None):
        file_path = path or self.default_map_path
        if not os.path.exists(file_path):
            self.set_status(f'No file found: {file_path}')
            return

        try:
            with open(file_path, 'r', encoding='utf-8') as file:
                lines = [line.rstrip('\n') for line in file.readlines() if line.strip()]

            if len(lines) != self.map_height:
                self.set_status(f'Load failed: expected {self.map_height} rows, got {len(lines)}')
                return

            if any(len(line) != self.map_width for line in lines):
                self.set_status(f'Load failed: each row must be {self.map_width} chars')
                return

            self.grid = [list(line) for line in lines]
            self.set_status(f'Loaded map from {file_path}')
        except OSError as exc:
            self.set_status(f'Load failed: {exc}')

    def export_python_list(self, path=None):
        file_path = path or self.default_python_path
        try:
            with open(file_path, 'w', encoding='utf-8') as file:
                file.write('[' + '\n')
                for row in self.grid:
                    file.write(f'    "{"".join(row)}",\n')
                file.write(']\n')
            self.set_status(f'Exported Python list to {file_path}')
        except OSError as exc:
            self.set_status(f'Export failed: {exc}')

    def export_settings_snippet(self, path=None, map_name='CUSTOM_MAP'):
        file_path = path or self.default_snippet_path
        try:
            with open(file_path, 'w', encoding='utf-8') as file:
                file.write(f'{map_name} = [\n')
                for row in self.grid:
                    file.write(f'    "{"".join(row)}",\n')
                file.write(']\n')
            self.set_status(f'Exported settings snippet to {file_path}')
        except OSError as exc:
            self.set_status(f'Export failed: {exc}')

    def write_back_to_settings(self):
        if not os.path.exists(self.settings_file_path):
            self.set_status(f'Write failed: settings.py not found')
            return

        try:
            with open(self.settings_file_path, 'r', encoding='utf-8') as file:
                lines = file.readlines()

            start_index = None
            for index, line in enumerate(lines):
                if line.strip().startswith(f'{self.map_name} = ['):
                    start_index = index
                    break

            if start_index is None:
                self.set_status(f'Write failed: {self.map_name} block not found')
                return

            end_index = None
            for index in range(start_index + 1, len(lines)):
                if lines[index].strip() == ']':
                    end_index = index
                    break

            if end_index is None:
                self.set_status('Write failed: could not find end of map block')
                return

            block_lines = [f'{self.map_name} = [\n']
            for row in self.grid:
                block_lines.append(f'    "{"".join(row)}",\n')
            block_lines.append(']\n')

            updated_lines = lines[:start_index] + block_lines + lines[end_index + 1:]
            with open(self.settings_file_path, 'w', encoding='utf-8') as file:
                file.writelines(updated_lines)

            self.set_status(f'Updated {self.map_name} in settings.py')
        except OSError as exc:
            self.set_status(f'Write failed: {exc}')

    def draw_map(self):
        for row in range(self.map_height):
            for col in range(self.map_width):
                tile = self.grid[row][col]
                color = COLORS.get(tile, COLORS[TILE_WALL])
                rect = pygame.Rect(
                    col * self.tile_size,
                    row * self.tile_size,
                    self.tile_size,
                    self.tile_size,
                )

                if tile == TILE_FINISH:
                    base = (220, 220, 220)
                    pygame.draw.rect(self.screen, base, rect)
                    checker = pygame.Rect(rect.x, rect.y, self.tile_size // 2, self.tile_size // 2)
                    pygame.draw.rect(self.screen, (0, 0, 0), checker)
                    checker.x += self.tile_size // 2
                    checker.y += self.tile_size // 2
                    pygame.draw.rect(self.screen, (0, 0, 0), checker)
                else:
                    pygame.draw.rect(self.screen, color, rect)

                pygame.draw.rect(self.screen, GRID_LINE_COLOR, rect, 1)

    def draw_panel(self):
        panel_rect = pygame.Rect(self.map_px_w, 0, self.panel_w, self.map_px_h)
        pygame.draw.rect(self.screen, PANEL_BG, panel_rect)

        x = self.map_px_w + 14
        y = 14

        title = self.font.render('TRACK EDITOR', True, HIGHLIGHT)
        self.screen.blit(title, (x, y))
        y += 34

        map_title = self.small_font.render(f'Map: {self.map_name}', True, (180, 220, 255))
        self.screen.blit(map_title, (x, y))
        y += 26

        active_text = self.font.render(f'Tool: {TOOL_NAMES[self.current_tool]}', True, TEXT_COLOR)
        self.screen.blit(active_text, (x, y))
        y += 28

        hints = [
            'Left click/drag: paint current tool',
            'Right click/drag: paint Wall',
            '1 Wall  2 Road  3 Start  4 Finish  5 Checkpoint',
            'N: New blank map (all walls)',
            'B: Reset to imported Brands Hatch map',
            'S: Save map (custom_track_map.txt)',
            'L: Load map (custom_track_map.txt)',
            'E: Export Python list',
            'X: Export settings snippet',
            'K: Write map back to settings.py',
            'ESC: Quit',
            '',
            'Tip: Start tile (P) is unique.',
        ]

        for line in hints:
            text = self.small_font.render(line, True, TEXT_COLOR)
            self.screen.blit(text, (x, y))
            y += 24

        y = self.map_px_h - 52
        status = self.small_font.render(self.status_text[:55], True, (170, 255, 170))
        self.screen.blit(status, (x, y))

    def handle_input(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    self.running = False
                elif event.key in TOOLS:
                    self.current_tool = TOOLS[event.key]
                    self.set_status(f'Selected tool: {TOOL_NAMES[self.current_tool]}')
                elif event.key == pygame.K_n:
                    self.clear_map()
                elif event.key == pygame.K_b:
                    self.reset_to_brands_hatch()
                elif event.key == pygame.K_s:
                    self.save_map()
                elif event.key == pygame.K_l:
                    self.load_map()
                elif event.key == pygame.K_e:
                    self.export_python_list()
                elif event.key == pygame.K_x:
                    self.export_settings_snippet()
                elif event.key == pygame.K_k:
                    self.write_back_to_settings()

        left, _, right = pygame.mouse.get_pressed()
        if not (left or right):
            return

        cell = self.mouse_to_cell(pygame.mouse.get_pos())
        if cell is None:
            return

        col, row = cell
        if right:
            self.place_tile(col, row, TILE_WALL)
        elif left:
            self.place_tile(col, row, self.current_tool)

    def run(self):
        while self.running:
            self.clock.tick(60)
            self.handle_input()

            self.screen.fill((0, 0, 0))
            self.draw_map()
            self.draw_panel()
            pygame.display.flip()

        pygame.quit()


if __name__ == '__main__':
    editor = TrackEditor()
    editor.run()
