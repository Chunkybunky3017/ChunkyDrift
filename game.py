import pygame
import sys
import random
from settings import *
from sprites import *
from leaderboard import Leaderboard

class Game:
    def __init__(self):
        pygame.init()
        pygame.joystick.init()
        self.joysticks = [pygame.joystick.Joystick(x) for x in range(pygame.joystick.get_count())]
        for joy in self.joysticks:
            joy.init()
            print(f"Controller connected: {joy.get_name()}")
            
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
        pygame.display.set_caption(TITLE)
        self.clock = pygame.time.Clock()
        self.font_name = pygame.font.match_font('arial')
        self.selected_car_index = 0 # Default car for P1
        self.selected_car_index_p2 = 1 # Default car for P2
        self.game_mode = 'rally' # Default mode, can be 'rally' or 'drift'
        self.multiplayer = False # Default to single player
        self.total_laps = -1 # Default laps (Free Play)
        self.leaderboard = Leaderboard() # Initialize Leaderboard
        self.load_data()
        # Initialize sprite group early for garage preview
        self.all_sprites = pygame.sprite.Group()

    def load_data(self):
        self.create_map_image()

    def draw_text(self, text, size, color, x, y, align="nw"):
        font = pygame.font.Font(self.font_name, size)
        text_surface = font.render(text, True, color)
        text_rect = text_surface.get_rect()
        if align == 'nw':
            text_rect.topleft = (x, y)
        if align == 'ne':
            text_rect.topright = (x, y)
        if align == 'sw':
            text_rect.bottomleft = (x, y)
        if align == 'se':
            text_rect.bottomright = (x, y)
        if align == 'n':
            text_rect.midtop = (x, y)
        if align == 's':
            text_rect.midbottom = (x, y)
        if align == 'e':
            text_rect.midright = (x, y)
        if align == 'w':
            text_rect.midleft = (x, y)
        if align == 'center':
            text_rect.center = (x, y)
        self.screen.blit(text_surface, text_rect)
        return text_rect

    def new(self):
        # initialize all variables and do all the setup for a new game
        self.all_sprites = pygame.sprite.Group()
        self.walls = pygame.sprite.Group()
        self.ramps = pygame.sprite.Group() # New ramping group
        self.pits = pygame.sprite.Group() # New pit group (for death detection)
        self.finish_lines = pygame.sprite.Group()
        self.checkpoints = pygame.sprite.Group()
        
        # Re-generate map for the current mode
        current_map = GAME_MAP
        if self.game_mode == 'stunt':
            current_map = STUNT_MAP
        elif self.game_mode == 'brands_hatch':
            current_map = BRANDS_HATCH_MAP
            
        self.create_map_image()

        # Reset player to None to ensure new car creation
        self.player = None
        
        # Create map from settings
        self.players = []
        player_spawned = False
        
        for row, tiles in enumerate(current_map):
            for col, tile in enumerate(tiles):
                if tile == '1' or tile == 'W':
                    Wall(self, col, row, tile_type=tile)
                if tile == 'B':
                    # Bridge Segment (Visual + Layer logic)
                    Bridge(self, col, row)
                if tile == '^' or tile == 'v':
                    Ramp(self, col, row, tile)
                if tile == 'X':
                    Pit(self, col, row)
                if tile == 'F':
                    FinishLine(self, col, row)
                if tile == 'C':
                    Checkpoint(self, col, row)
                if tile == 'P':
                    # Spawning Points
                    # We spawn BOTH players at the first 'P' we find, side by side or offset
                    if not player_spawned:
                        spawn_rot = 90 if self.game_mode == 'brands_hatch' else 0

                        # P1
                        p1_specs = CAR_MODELS[self.selected_car_index]
                        p1 = Car(self, col * TILESIZE + TILESIZE / 2, row * TILESIZE + TILESIZE / 2, p1_specs, player_id=1)
                        p1.start_rot = spawn_rot
                        p1.rot = spawn_rot
                        p1.sync_visual_to_rotation()
                        self.players.append(p1)
                        
                        # P2 (Offset slightly to avoid overlap)
                        if self.multiplayer:
                            # Detect if we should offset X or Y based on map type or surrounding walls
                            # For now, hardcode check:
                            if self.game_mode == 'stunt':
                                # Stunt map starts vertical (at top left going down)
                                # Offset X + 40 (Side by side)
                                p2_x = col * TILESIZE + TILESIZE / 2 + 40
                                p2_y = row * TILESIZE + TILESIZE / 2
                            elif self.game_mode == 'brands_hatch':
                                # Brands Hatch start is vertical, so offset X for side-by-side start
                                p2_x = col * TILESIZE + TILESIZE / 2 + 40
                                p2_y = row * TILESIZE + TILESIZE / 2
                            else:
                                # Rally/Drift map starts horizontal
                                p2_x = col * TILESIZE + TILESIZE / 2
                                p2_y = row * TILESIZE + TILESIZE / 2 - 40
                                
                            p2_specs = CAR_MODELS[self.selected_car_index_p2]
                            p2 = Car(self, p2_x, p2_y, p2_specs, player_id=2)
                            p2.start_rot = spawn_rot
                            p2.rot = spawn_rot
                            p2.sync_visual_to_rotation()
                            self.players.append(p2)
                        
                        player_spawned = True
                        self.player = p1 # Keep reference for legacy camera if we add one

        # If player wasn't placed by map, place at default
        if not player_spawned:
             if self.game_mode == 'stunt':
                 cx, cy = WIDTH//2, HEIGHT//2
             else:
                 cx, cy = 100, 100
                 
             if len(CAR_MODELS) > 0:
                 p1_specs = CAR_MODELS[self.selected_car_index % len(CAR_MODELS)]
                 p2_specs = CAR_MODELS[self.selected_car_index_p2 % len(CAR_MODELS)]
             else:
                 # Fallback
                 p1_specs = {"name": "Default", "color": RED, "accel": 400, "max_speed": 600, "grip": 1.0, "drag": 0.99, "friction": 200}
                 p2_specs = p1_specs.copy()
                 p2_specs["color"] = BLUE

             p1 = Car(self, cx, cy, p1_specs, player_id=1)
             if self.game_mode == 'brands_hatch':
                 p1.start_rot = 90
                 p1.rot = 90
                 p1.sync_visual_to_rotation()
             self.players = [p1]
             if self.multiplayer:
                 p2 = Car(self, cx, cy + 50, p2_specs, player_id=2)
                 if self.game_mode == 'brands_hatch':
                     p2.start_rot = 90
                     p2.rot = 90
                     p2.sync_visual_to_rotation()
                 self.players.append(p2)
             self.player = p1

        # Race Timing
        self.race_start_time = pygame.time.get_ticks()
        for p in self.players:
            p.lap_start_time = self.race_start_time
            p.current_lap_time = 0
            p.best_lap_time = float('inf')


    
    def run(self):
        # game loop - set self.playing = False to end the game
        self.playing = True
        
        # Countdown logic
        countdown_val = 3
        last_count_tick = pygame.time.get_ticks()
        
        # Use a flag to avoid calling flip multiple times
        # We will manually manage drawing during countdown
        
        while countdown_val > 0 and self.playing:
            self.clock.tick(FPS)
            
            # Allow quit
            for event in self.get_events():
                if event.type == pygame.QUIT:
                    self.quit()
                if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                    self.playing = False
                    return

            now = pygame.time.get_ticks()
            if now - last_count_tick >= 1000:
                countdown_val -= 1
                last_count_tick = now
            
            # Draw game state (without flipping)
            # We can't use self.draw() because it flips.
            # So we replicate draw logic lightly here or create a draw_frame method?
            # Replicating logic:
            self.screen.blit(self.map_img, (0, 0))
            self.all_sprites.draw(self.screen)
            
            # Big Countdown Text
            txt = str(countdown_val) if countdown_val > 0 else "GO!"
            color = RED if countdown_val > 0 else GREEN
            self.draw_text(txt, 150, color, WIDTH // 2, HEIGHT // 2 - 80, "center")
            
            pygame.display.flip()
        
        # "GO!" Frame
        self.screen.blit(self.map_img, (0, 0))
        self.all_sprites.draw(self.screen)
        self.draw_text("GO!", 150, GREEN, WIDTH // 2, HEIGHT // 2 - 80, "center")
        pygame.display.flip()
        pygame.time.wait(500)

        # Reset Timers for accurate start
        start_time = pygame.time.get_ticks()
        self.race_start_time = start_time
        for p in self.players:
            p.lap_start_time = start_time

        while self.playing:
            self.dt = self.clock.tick(FPS) / 1000.0
            self.events()
            self.update()
            self.draw()

    def quit(self):
        pygame.quit()
        sys.exit()

    def update(self):
        # update portion of the game loop
        self.all_sprites.update()

    def draw_grid(self):
        for x in range(0, WIDTH, TILESIZE):
            pygame.draw.line(self.screen, LIGHTGREY, (x, 0), (x, HEIGHT))
        for y in range(0, HEIGHT, TILESIZE):
            pygame.draw.line(self.screen, LIGHTGREY, (0, y), (WIDTH, y))

    def format_time(self, milliseconds):
        minutes = int(milliseconds // 60000)
        seconds = int((milliseconds % 60000) // 1000)
        millis = int(milliseconds % 1000)
        return f"{minutes:02}:{seconds:02}.{millis:03}"

    def get_player_name(self, player_id, time_msg):
        # Simple blocking text input
        name = ["A", "A", "A"]
        char_idx = 0
        typing = True
        self.last_input_time = pygame.time.get_ticks() + 500
        while typing:
            joy_p1 = self.joysticks[0] if self.joysticks else None
            self.clock.tick(FPS)
            self.screen.fill(BGCOLOR)
            self.draw_text(f"NEW RECORD! P{player_id}", 48, YELLOW, WIDTH // 2, HEIGHT // 3, "center")
            self.draw_text(time_msg, 32, WHITE, WIDTH // 2, HEIGHT // 3 + 50, "center")
            self.draw_text("Enter Name:", 32, WHITE, WIDTH // 2, HEIGHT // 2, "center")
            
            # Input Box
            pygame.draw.rect(self.screen, BLACK, (WIDTH//2 - 100, HEIGHT//2 + 40, 200, 40))
            pygame.draw.rect(self.screen, WHITE, (WIDTH//2 - 100, HEIGHT//2 + 40, 200, 40), 2)
            
            # Draw characters
            for i in range(3):
                color = YELLOW if i == char_idx else WHITE
                self.draw_text(name[i], 28, color, WIDTH // 2 - 30 + i * 30, HEIGHT // 2 + 50, "center")
            
            pygame.display.flip()
            
            now = pygame.time.get_ticks()
            if joy_p1 and now - getattr(self, 'last_input_time', 0) > 200:
                axis_x = joy_p1.get_axis(0)
                axis_y = joy_p1.get_axis(1)
                if abs(axis_x) > 0.5:
                    char_idx = (char_idx + (1 if axis_x > 0 else -1)) % 3
                    self.last_input_time = now
                elif joy_p1.get_hat(0)[0] != 0:
                    char_idx = (char_idx + joy_p1.get_hat(0)[0]) % 3
                    self.last_input_time = now
                elif abs(axis_y) > 0.5:
                    val = ord(name[char_idx]) + (1 if axis_y > 0 else -1)
                    if val > ord('Z'): val = ord('A')
                    if val < ord('A'): val = ord('Z')
                    name[char_idx] = chr(val)
                    self.last_input_time = now
                elif joy_p1.get_hat(0)[1] != 0:
                    val = ord(name[char_idx]) - joy_p1.get_hat(0)[1]
                    if val > ord('Z'): val = ord('A')
                    if val < ord('A'): val = ord('Z')
                    name[char_idx] = chr(val)
                    self.last_input_time = now
                if joy_p1.get_button(0): # A button to confirm
                    return "".join(name)

            for event in self.get_events():
                if event.type == pygame.QUIT:
                    self.quit()
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_RETURN:
                         return "".join(name)
                    elif event.key == pygame.K_LEFT or event.key == pygame.K_a:
                         char_idx = (char_idx - 1) % 3
                    elif event.key == pygame.K_RIGHT or event.key == pygame.K_d:
                         char_idx = (char_idx + 1) % 3
                    elif event.key == pygame.K_UP or event.key == pygame.K_w:
                         val = ord(name[char_idx]) + 1
                         if val > ord('Z'): val = ord('A')
                         name[char_idx] = chr(val)
                    elif event.key == pygame.K_DOWN or event.key == pygame.K_s:
                         val = ord(name[char_idx]) - 1
                         if val < ord('A'): val = ord('Z')
                         name[char_idx] = chr(val)
        return "".join(name)

    def draw(self):
        self.screen.blit(self.map_img, (0, 0))
        
        # Shadows
        if hasattr(self, 'players'):
             for p in self.players:
                 if p.z > 0:
                     shadow_radius = max(5, 10 - p.z // 20)
                     shadow_pos = (int(p.pos.x + 5), int(p.pos.y + 10))
                     pygame.draw.ellipse(self.screen, (0, 0, 0, 150), 
                                         (shadow_pos[0]-shadow_radius, shadow_pos[1]-shadow_radius//2, shadow_radius*2, shadow_radius), 0)
        
        self.all_sprites.draw(self.screen)
        
        # Stunt text
        if hasattr(self, 'players'):
             for i, p in enumerate(self.players):
                 if p.z > 50:
                     msg = "P1 AIR TIME!" if p.player_id == 1 else "P2 AIR TIME!"
                     offset_y = -100 if p.player_id == 1 else -60
                     self.draw_text(msg, 48, YELLOW, WIDTH//2, HEIGHT//2 + offset_y, "center")
        
        if self.game_mode == 'stunt':
             self.draw_text("Press 'R' to Respawn", 14, WHITE, WIDTH - 10, HEIGHT - 20, "se")
        
        # --- HUD & Logic ---
        now = pygame.time.get_ticks()
        
        if hasattr(self, 'players'):
            for i, p in enumerate(self.players):
                 lap_info = getattr(p, 'laps', 0)
                 color = GREEN if p.player_id == 1 else CYAN
                 y_pos = 10 + (i * 80) # Increased spacing for more info
                 
                 # 1. Lap Count
                 lap_text = f"P{p.player_id}: Lap {lap_info}"
                 if self.total_laps > 0:
                      lap_text += f"/{self.total_laps}"
                 self.draw_text(lap_text, 22, color, 10, y_pos, "nw")
                 
                 # 2. Current Lap Time
                 current_lap_dur = now - getattr(p, 'lap_start_time', now)
                 self.draw_text(self.format_time(current_lap_dur), 22, WHITE, 200, y_pos, "nw")
                 
                 # 3. Best Lap Time
                 best = getattr(p, 'best_lap_time', float('inf'))
                 best_str = "--:--.--"
                 if best != float('inf'):
                     best_str = self.format_time(best)
                 self.draw_text(f"Best: {best_str}", 18, LIGHTGREY, 10, y_pos + 25, "nw")

                 # Win Condition Logic
                 if self.total_laps > 0 and lap_info >= self.total_laps: # Completed laps
                     # Calculate total time (approximate based on race start)
                     total_race_time = now - self.race_start_time
                     
                     self.draw_text(f"P{p.player_id} FINISHED!", 64, color, WIDTH//2, HEIGHT//2 - 50, "center")
                     self.draw_text(f"Time: {self.format_time(total_race_time)}", 32, WHITE, WIDTH//2, HEIGHT//2 + 20, "center")
                     pygame.display.flip()
                     pygame.time.wait(2000)
                     
                     # Check Leaderboard
                     race_cat = f"{self.total_laps}_laps"
                     if self.total_laps == 1:
                         race_cat = "1_lap"
                     if self.leaderboard.is_high_score(self.game_mode, race_cat, total_race_time):
                         name = self.get_player_name(p.player_id, self.format_time(total_race_time))
                         self.leaderboard.add_score(self.game_mode, race_cat, name, total_race_time)
                     
                     self.playing = False
                     return

        pygame.display.flip()
    
    def create_map_image(self):
        # Create a static image of the map background
        self.map_img = pygame.Surface((WIDTH, HEIGHT))

        ROAD_TILES = {'.', 'P', 'U', 'C', 'F'}
        
        # Base Color
        if self.game_mode == 'drift':
            self.map_img.fill(SIDEWALK) # Dark grey for drift
        elif self.game_mode == 'stunt':
            self.map_img.fill((50, 50, 100)) # Dark blue for stunt
        else:
            self.map_img.fill(BGCOLOR) # Grass green for rally

        # Choose Map
        current_map = GAME_MAP
        if self.game_mode == 'stunt':
            current_map = STUNT_MAP
        elif self.game_mode == 'brands_hatch':
            current_map = BRANDS_HATCH_MAP

        # Draw the road based on the map
        for row, tiles in enumerate(current_map):
            for col, tile in enumerate(tiles):
                rect = pygame.Rect(col * TILESIZE, row * TILESIZE, TILESIZE, TILESIZE)
                
                # Ground Layer (Always drawn on map image)
                if tile == 'X':
                    # Pit
                    pygame.draw.rect(self.map_img, PIT_COLOR, rect)
                    # Pit shading (make it look deep)
                    pygame.draw.rect(self.map_img, (10, 10, 10), (col * TILESIZE + 2, row * TILESIZE + 2, TILESIZE-4, TILESIZE-4))
                elif tile == '.' or tile == 'P' or tile == 'U' or tile == 'C':
                     if self.game_mode == 'drift':
                         pygame.draw.rect(self.map_img, ASPHALT, rect)
                     elif self.game_mode == 'stunt':
                         pygame.draw.rect(self.map_img, STUNT_ROAD, rect)
                     else:
                         pygame.draw.rect(self.map_img, DIRT_MEDIUM, rect)
                         # Add texture (noise)
                         for _ in range(20):
                            rx = random.randint(0, TILESIZE)
                            ry = random.randint(0, TILESIZE)
                            color = random.choice([DIRT_LIGHT, DIRT_DARK])
                            pygame.draw.rect(self.map_img, color, (col * TILESIZE + rx, row * TILESIZE + ry, 3, 3))

        if self.game_mode == 'brands_hatch':
            def is_road(r, c):
                if r < 0 or c < 0 or r >= len(current_map) or c >= len(current_map[r]):
                    return False
                return current_map[r][c] in ROAD_TILES

            def draw_edge_stripes(rect, edge):
                stripe_count = 4
                stripe_thickness = 3
                stripe_len = max(1, TILESIZE // stripe_count)
                for i in range(stripe_count):
                    stripe_color = RED if i % 2 == 0 else WHITE
                    if edge == 'top':
                        pygame.draw.rect(
                            self.map_img,
                            stripe_color,
                            (rect.x + i * stripe_len, rect.y, stripe_len, stripe_thickness)
                        )
                    elif edge == 'bottom':
                        pygame.draw.rect(
                            self.map_img,
                            stripe_color,
                            (rect.x + i * stripe_len, rect.y + TILESIZE - stripe_thickness, stripe_len, stripe_thickness)
                        )
                    elif edge == 'left':
                        pygame.draw.rect(
                            self.map_img,
                            stripe_color,
                            (rect.x, rect.y + i * stripe_len, stripe_thickness, stripe_len)
                        )
                    elif edge == 'right':
                        pygame.draw.rect(
                            self.map_img,
                            stripe_color,
                            (rect.x + TILESIZE - stripe_thickness, rect.y + i * stripe_len, stripe_thickness, stripe_len)
                        )

            for row, tiles in enumerate(current_map):
                for col, tile in enumerate(tiles):
                    if tile not in ROAD_TILES:
                        continue

                    north = is_road(row - 1, col)
                    south = is_road(row + 1, col)
                    west = is_road(row, col - 1)
                    east = is_road(row, col + 1)

                    rect = pygame.Rect(col * TILESIZE, row * TILESIZE, TILESIZE, TILESIZE)

                    # Add curbs on some corners for F1-style visual effect.
                    if (row + col) % 2 != 0:
                        continue

                    if north and east and not south and not west:
                        draw_edge_stripes(rect, 'bottom')
                        draw_edge_stripes(rect, 'left')
                    elif north and west and not south and not east:
                        draw_edge_stripes(rect, 'bottom')
                        draw_edge_stripes(rect, 'right')
                    elif south and east and not north and not west:
                        draw_edge_stripes(rect, 'top')
                        draw_edge_stripes(rect, 'left')
                    elif south and west and not north and not east:
                        draw_edge_stripes(rect, 'top')
                        draw_edge_stripes(rect, 'right')

    def update_joysticks(self):
        pygame.joystick.init()
        self.joysticks = [pygame.joystick.Joystick(x) for x in range(pygame.joystick.get_count())]
        for joy in self.joysticks:
            joy.init()

    def get_events(self):
        events = pygame.event.get()
        for event in events:
            if event.type == pygame.QUIT:
                self.quit()
            if event.type == pygame.JOYDEVICEADDED or event.type == pygame.JOYDEVICEREMOVED:
                self.update_joysticks()
        return events

    def events(self):
        # catch all events here
        for event in self.get_events():
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    self.show_pause_screen()
            if event.type == pygame.JOYBUTTONDOWN:
                if event.button == 7: # Start button
                    self.show_pause_screen()

    def show_pause_screen(self):
        paused = True
        self.last_input_time = pygame.time.get_ticks() + 200
        
        # Dim the screen once
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 150))
        self.screen.blit(overlay, (0,0))
        
        while paused:
            joy_p1 = self.joysticks[0] if self.joysticks else None
            self.clock.tick(FPS)
            
            # Draw Menu Box
            menu_rect = pygame.Rect(WIDTH//2 - 150, HEIGHT//2 - 100, 300, 200)
            pygame.draw.rect(self.screen, DARKGREY, menu_rect)
            pygame.draw.rect(self.screen, WHITE, menu_rect, 3)
            
            self.draw_text("PAUSED", 48, WHITE, WIDTH // 2, HEIGHT // 2 - 60, "center")
            
            # Resume Button / Text
            self.draw_text("Press ESC / Start to Resume", 22, GREEN, WIDTH // 2, HEIGHT // 2 + 10, "center")
            
            # Quit Button / Text
            self.draw_text("Press Q / Select to Main Menu", 22, RED, WIDTH // 2, HEIGHT // 2 + 50, "center")
            
            pygame.display.flip()
            
            now = pygame.time.get_ticks()
            if joy_p1 and now - getattr(self, 'last_input_time', 0) > 200:
                if joy_p1.get_button(7): # Start button to resume
                    paused = False
                    self.last_input_time = now
                if joy_p1.get_button(6): # Select button to quit
                    paused = False
                    self.playing = False
                    self.show_start_screen()
                    return

            for event in self.get_events():
                if event.type == pygame.QUIT:
                    self.quit()
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        paused = False # Resume
                    if event.key == pygame.K_q:
                        paused = False
                        self.playing = False # Stop current game loop
                        self.show_start_screen() # Show menu and wait for selection
                        return

    def show_lap_selection_screen(self):
        # Only for Rally mode in Multiplayer
        running = True
        options = [3, 5, 10, "Free Roam"]
        selected_idx = 0
        
        self.last_input_time = pygame.time.get_ticks() + 200
        
        while running:
            joy_p1 = self.joysticks[0] if self.joysticks else None
            self.clock.tick(FPS)
            self.screen.fill(BGCOLOR)
            self.draw_text("SELECT RACE LENGTH", 48, WHITE, WIDTH // 2, HEIGHT // 4, "center")
            
            mx, my = pygame.mouse.get_pos()
            click = pygame.mouse.get_pressed()[0]
            
            # Draw Options
            start_y = HEIGHT // 2 - 50
            for i, opt in enumerate(options):
                rect = pygame.Rect(WIDTH // 2 - 150, start_y + i * 70, 300, 50)
                color = DARKGREY
                if i == selected_idx:
                    color = LIGHTGREY
                    pygame.draw.rect(self.screen, YELLOW, rect.inflate(6, 6), 3)
                if rect.collidepoint(mx, my):
                    color = LIGHTGREY
                    if click:
                        if opt == "Free Roam":
                            self.total_laps = -1 # Infinite
                        else:
                            self.total_laps = opt
                        return True
                
                pygame.draw.rect(self.screen, color, rect)
                label = f"{opt} Laps" if isinstance(opt, int) else opt
                self.draw_text(label, 24, WHITE, rect.centerx, rect.centery - 12, "center")

            pygame.display.flip()
            
            now = pygame.time.get_ticks()
            if joy_p1 and now - getattr(self, 'last_input_time', 0) > 200:
                if joy_p1.get_button(1): # B button to back
                    return False
                axis_y = joy_p1.get_axis(1)
                if abs(axis_y) > 0.5:
                    selected_idx = (selected_idx + (1 if axis_y > 0 else -1)) % len(options)
                    self.last_input_time = now
                elif joy_p1.get_hat(0)[1] != 0:
                    selected_idx = (selected_idx - joy_p1.get_hat(0)[1]) % len(options)
                    self.last_input_time = now
                if joy_p1.get_button(0): # A button to select
                    opt = options[selected_idx]
                    if opt == "Free Roam":
                        self.total_laps = -1
                    else:
                        self.total_laps = opt
                    return True

            for event in self.get_events():
                if event.type == pygame.QUIT:
                    self.quit()
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        return False # Back
                    if event.key == pygame.K_UP or event.key == pygame.K_w:
                        selected_idx = (selected_idx - 1) % len(options)
                    if event.key == pygame.K_DOWN or event.key == pygame.K_s:
                        selected_idx = (selected_idx + 1) % len(options)
                    if event.key == pygame.K_RETURN or event.key == pygame.K_SPACE:
                        opt = options[selected_idx]
                        if opt == "Free Roam":
                            self.total_laps = -1
                        else:
                            self.total_laps = opt
                        return True

    def show_start_screen(self):
        screen_running = True
        click_cooldown = 0
        selected_item = 0 # 0: Rally, 1: Brands Hatch, 2: Drift, 3: Stunt, 4: Leaderboard, 5: Multiplayer
        menu_items = ['rally', 'brands_hatch', 'drift', 'stunt', 'leaderboard', 'multiplayer']
        
        # Controller check
        
        last_input_time = pygame.time.get_ticks() + 200
        
        while screen_running:
            joy_p1 = self.joysticks[0] if self.joysticks else None
            self.clock.tick(FPS)
            if click_cooldown > 0:
                click_cooldown -= 1
                
            self.screen.fill(BGCOLOR)
            self.draw_text(TITLE, 64, WHITE, WIDTH // 2, HEIGHT // 8, "center")

            # Mouse
            mx, my = pygame.mouse.get_pos()
            click = pygame.mouse.get_pressed()[0]
            
            # Helper to draw buttons
            def draw_button(rect, text, item_index):
                color = DARKGREY
                is_selected = (selected_item == item_index)
                
                # Mouse Hover Override
                if rect.collidepoint((mx, my)):
                    if click and click_cooldown == 0:
                         return True # Clicked
                    # If mouse moves, update selection to this item? optional
                
                if is_selected:
                    color = LIGHTGREY
                    pygame.draw.rect(self.screen, YELLOW, rect.inflate(6, 6), 3) # Selection outline

                pygame.draw.rect(self.screen, color, rect)
                text_color = WHITE
                if item_index == 3: # Multiplayer Toggle special text
                     text_color = BLACK if self.multiplayer else WHITE
                
                self.draw_text(text, 22, text_color, rect.centerx, rect.centery - 12, "center")
                return False

            # Button Layout
            # RALLY
            if draw_button(pygame.Rect(WIDTH // 2 - 100, HEIGHT // 2 - 115, 200, 50), "RALLY MODE", 0):
                self.game_mode = 'rally'
                if self.multiplayer:
                    if self.show_lap_selection_screen(): # Ask for laps first in rally/multiplayer
                         if self.show_multiplayer_selection(): return
                else:
                    self.total_laps = -1 # Free play Default
                    if self.show_singleplayer_selection(): return

            # BRANDS HATCH
            if draw_button(pygame.Rect(WIDTH // 2 - 100, HEIGHT // 2 - 55, 200, 50), "BRANDS HATCH", 1):
                self.game_mode = 'brands_hatch'
                if self.multiplayer:
                    if self.show_lap_selection_screen():
                         if self.show_multiplayer_selection(): return
                else:
                    self.total_laps = -1
                    if self.show_singleplayer_selection(): return
            
            # DRIFT
            if draw_button(pygame.Rect(WIDTH // 2 - 100, HEIGHT // 2 + 5, 200, 50), "TOKYO DRIFT", 2):
                self.game_mode = 'drift'
                if self.multiplayer:
                    self.total_laps = -1 
                    if self.show_multiplayer_selection(): return
                else:
                    self.total_laps = -1
                    if self.show_singleplayer_selection(): return

            # STUNT
            if draw_button(pygame.Rect(WIDTH // 2 - 100, HEIGHT // 2 + 65, 200, 50), "STUNT TRACK", 3):
                self.game_mode = 'stunt'
                if self.multiplayer:
                    self.total_laps = -1 
                    if self.show_multiplayer_selection(): return
                else:
                    self.total_laps = -1
                    if self.show_singleplayer_selection(): return

            # LEADERBOARD
            if draw_button(pygame.Rect(WIDTH // 2 - 100, HEIGHT // 2 + 125, 200, 50), "LEADERBOARD", 4):
                self.show_leaderboard_screen()


            # MULTIPLAYER TOGGLE
            mp_btn = pygame.Rect(WIDTH // 2 - 100, HEIGHT - 100, 200, 50)
            mp_color = GREEN if self.multiplayer else RED
            mp_text = "MULTIPLAYER: ON" if self.multiplayer else "MULTIPLAYER: OFF"
            
            # Special Draw for Toggle
            is_sel = (selected_item == 5)
            if is_sel:
                 pygame.draw.rect(self.screen, YELLOW, mp_btn.inflate(6, 6), 3)
            
            pygame.draw.rect(self.screen, mp_color, mp_btn)
            self.draw_text(mp_text, 20, BLACK if self.multiplayer else WHITE, mp_btn.centerx, mp_btn.centery - 12, "center")

            # Mouse Click Handling for MP Toggle
            if mp_btn.collidepoint((mx, my)) and click and click_cooldown == 0:
                self.multiplayer = not self.multiplayer
                click_cooldown = 15

            pygame.display.flip()

            # Input Handling
            for event in self.get_events():
                if event.type == pygame.QUIT:
                    self.quit()
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_DOWN or event.key == pygame.K_s:
                        selected_item = (selected_item + 1) % 6
                    if event.key == pygame.K_UP or event.key == pygame.K_w:
                        selected_item = (selected_item - 1) % 6
                    if event.key == pygame.K_RETURN or event.key == pygame.K_SPACE:
                        # Activate Selected
                        if selected_item == 0: # Rally
                            self.game_mode = 'rally'
                            if self.multiplayer:
                                if self.show_lap_selection_screen():
                                     if self.show_multiplayer_selection(): return
                            else:
                                self.total_laps = -1 # Free play Default
                                if self.show_singleplayer_selection(): return
                        elif selected_item == 1: # Brands Hatch
                            self.game_mode = 'brands_hatch'
                            if self.multiplayer:
                                if self.show_lap_selection_screen():
                                     if self.show_multiplayer_selection(): return
                            else:
                                self.total_laps = -1
                                if self.show_singleplayer_selection(): return
                        elif selected_item == 2: # Drift
                            self.game_mode = 'drift'
                            if self.multiplayer:
                                self.total_laps = -1 
                                if self.show_multiplayer_selection(): return
                            else:
                                self.total_laps = -1
                                if self.show_singleplayer_selection(): return
                        elif selected_item == 3: # Stunt
                            self.game_mode = 'stunt'
                            if self.multiplayer:
                                self.total_laps = -1 
                                if self.show_multiplayer_selection(): return
                            else:
                                self.total_laps = -1
                                if self.show_singleplayer_selection(): return
                        elif selected_item == 4: # Leaderboard
                            self.show_leaderboard_screen()
                        elif selected_item == 5: # Multiplayer Toggle
                             self.multiplayer = not self.multiplayer

            # Controller Logic
            now = pygame.time.get_ticks()
            if joy_p1 and now - last_input_time > 200:
                # D-pad Y / Axis Y
                move = 0
                if abs(joy_p1.get_axis(1)) > 0.5:
                     move = 1 if joy_p1.get_axis(1) > 0 else -1
                elif joy_p1.get_hat(0)[1] != 0:
                     move = -joy_p1.get_hat(0)[1] # Hat up is 1
                
                if move != 0:
                     selected_item = (selected_item + move) % 6
                     last_input_time = now
                
                # Confirm (A button)
                if joy_p1.get_button(0):
                     # Activate Selected (Copy logic from keyboard)
                        if selected_item == 0: # Rally
                            self.game_mode = 'rally'
                            if self.multiplayer:
                                if self.show_lap_selection_screen():
                                     if self.show_multiplayer_selection(): return
                            else:
                                self.total_laps = -1 # Free play Default
                                if self.show_singleplayer_selection(): return
                        elif selected_item == 1: # Brands Hatch
                            self.game_mode = 'brands_hatch'
                            if self.multiplayer:
                                if self.show_lap_selection_screen():
                                     if self.show_multiplayer_selection(): return
                            else:
                                self.total_laps = -1
                                if self.show_singleplayer_selection(): return
                        elif selected_item == 2: # Drift
                            self.game_mode = 'drift'
                            if self.multiplayer:
                                self.total_laps = -1 
                                if self.show_multiplayer_selection(): return
                            else:
                                self.total_laps = -1
                                if self.show_singleplayer_selection(): return
                        elif selected_item == 3: # Stunt
                            self.game_mode = 'stunt'
                            if self.multiplayer:
                                self.total_laps = -1 
                                if self.show_multiplayer_selection(): return
                            else:
                                self.total_laps = -1
                                if self.show_singleplayer_selection(): return
                        elif selected_item == 4:
                             self.show_leaderboard_screen()
                        elif selected_item == 5: # Multiplayer Toggle
                             self.multiplayer = not self.multiplayer
                             last_input_time = now # Debounce toggle

    def show_leaderboard_screen(self):
        running = True
        modes = ['rally', 'brands_hatch', 'drift', 'stunt']
        mode_idx = 0
        
        self.last_input_time = pygame.time.get_ticks() + 200
        
        while running:
            joy_p1 = self.joysticks[0] if self.joysticks else None
            self.clock.tick(FPS)
            self.screen.fill(BGCOLOR)
            
            # Header
            self.draw_text("LEADERBOARDS", 48, WHITE, WIDTH // 2, 50, "center")
            
            # Mode Selector
            current_mode = modes[mode_idx]
            mode_label = current_mode.replace('_', ' ').upper()
            self.draw_text(f"< {mode_label} MODE >", 32, YELLOW, WIDTH // 2, 110, "center")
            self.draw_text("(Left/Right to Change Mode)", 18, LIGHTGREY, WIDTH // 2, 140, "center")
            
            # Display Scores for 1, 3, 5 laps
            # Layout: 3 Columns? Or just list sequentially
            
            # 1 Lap
            self.draw_text("1 Lap Sprint", 24, CYAN, WIDTH // 4, 180, "center")
            scores_1 = self.leaderboard.get_top_scores(current_mode, "1_lap")
            for i, s in enumerate(scores_1[:5]):
                 t_str = self.format_time(s['time'])
                 self.draw_text(f"{i+1}. {s['name']}: {t_str}", 20, WHITE, WIDTH // 4, 220 + i*25, "center")
                 
            # 3 Laps
            self.draw_text("3 Lap Race", 24, CYAN, WIDTH // 2, 180, "center")
            scores_3 = self.leaderboard.get_top_scores(current_mode, "3_laps")
            for i, s in enumerate(scores_3[:5]):
                 t_str = self.format_time(s['time'])
                 self.draw_text(f"{i+1}. {s['name']}: {t_str}", 20, WHITE, WIDTH // 2, 220 + i*25, "center")

            # 5 Laps
            self.draw_text("5 Lap Endurance", 24, CYAN, 3 * WIDTH // 4, 180, "center")
            scores_5 = self.leaderboard.get_top_scores(current_mode, "5_laps")
            for i, s in enumerate(scores_5[:5]):
                 t_str = self.format_time(s['time'])
                 self.draw_text(f"{i+1}. {s['name']}: {t_str}", 20, WHITE, 3 * WIDTH // 4, 220 + i*25, "center")

            self.draw_text("Press ESC to Back", 22, GREEN, WIDTH // 2, HEIGHT - 50, "center")

            pygame.display.flip()
            
            now = pygame.time.get_ticks()
            if joy_p1 and now - getattr(self, 'last_input_time', 0) > 200:
                if joy_p1.get_button(1): # B button to back
                    running = False
                axis_x = joy_p1.get_axis(0)
                if abs(axis_x) > 0.5:
                    mode_idx = (mode_idx + (1 if axis_x > 0 else -1)) % len(modes)
                    self.last_input_time = now
                elif joy_p1.get_hat(0)[0] != 0:
                    mode_idx = (mode_idx + joy_p1.get_hat(0)[0]) % len(modes)
                    self.last_input_time = now

            for event in self.get_events():
                if event.type == pygame.QUIT:
                    self.quit()
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        running = False
                    if event.key == pygame.K_LEFT or event.key == pygame.K_a:
                        mode_idx = (mode_idx - 1) % len(modes)
                    if event.key == pygame.K_RIGHT or event.key == pygame.K_d:
                        mode_idx = (mode_idx + 1) % len(modes)

    def show_multiplayer_selection(self):
        # This replaces the old garage/selection screen logic
        running = True
        
        # Clear existing sprites
        for sprite in self.all_sprites:
            sprite.kill()
            
        p1_idx = self.selected_car_index
        p2_idx = self.selected_car_index_p2
        
        # We need two preview cars
        # P1 on Left, P2 on Right
        preview_car_p1 = Car(self, WIDTH // 4, HEIGHT // 2, CAR_MODELS[p1_idx], player_id=1)
        preview_car_p2 = Car(self, 3 * WIDTH // 4, HEIGHT // 2, CAR_MODELS[p2_idx], player_id=2)
        
        p1_ready = False
        p2_ready = False
        
        self.last_input_time_p1 = pygame.time.get_ticks() + 200
        self.last_input_time_p2 = pygame.time.get_ticks() + 200

        while running:
            joy_p1 = self.joysticks[0] if self.joysticks else None
            self.clock.tick(FPS)
            self.screen.fill(BGCOLOR)
            self.draw_text("MULTIPLAYER GARAGE", 48, WHITE, WIDTH // 2, 50, "center")
            self.draw_text("Player 1 (WASD)", 32, WHITE, WIDTH // 4, 120, "center")
            self.draw_text("Player 2 (Arrows)", 32, WHITE, 3 * WIDTH // 4, 120, "center")
            
            # --- P1 Update ---
            if preview_car_p1.original_image:
                 preview_car_p1.rot = (preview_car_p1.rot - 2) % 360 
                 preview_car_p1.image = pygame.transform.rotate(preview_car_p1.original_image, preview_car_p1.rot)
                 preview_car_p1.rect = preview_car_p1.image.get_rect(center=(WIDTH // 4, HEIGHT // 2))
                 self.screen.blit(preview_car_p1.image, preview_car_p1.rect)
            
            # --- P2 Update ---
            if preview_car_p2.original_image:
                 preview_car_p2.rot = (preview_car_p2.rot - 2) % 360 
                 preview_car_p2.image = pygame.transform.rotate(preview_car_p2.original_image, preview_car_p2.rot)
                 preview_car_p2.rect = preview_car_p2.image.get_rect(center=(3 * WIDTH // 4, HEIGHT // 2))
                 self.screen.blit(preview_car_p2.image, preview_car_p2.rect)
            
            # --- P1 Stats ---
            spec_p1 = CAR_MODELS[p1_idx]
            y1 = HEIGHT // 2 + 100
            self.draw_text(f"< {spec_p1['name']} >", 24, YELLOW, WIDTH//4, y1, "center")
            self.draw_bar_small("Speed", spec_p1['max_speed'], 750, y1 + 30, WIDTH // 4)
            self.draw_bar_small("Accel", spec_p1['accel'], 500, y1 + 50, WIDTH // 4)
            
            if p1_ready:
                self.draw_text("READY", 32, GREEN, WIDTH // 4, y1 + 100, "center")
            else:
                self.draw_text("Select Car", 20, LIGHTGREY, WIDTH // 4, y1 + 100, "center")

            # --- P2 Stats ---
            spec_p2 = CAR_MODELS[p2_idx]
            self.draw_text(f"< {spec_p2['name']} >", 24, YELLOW, 3 * WIDTH // 4, y1, "center")
            self.draw_bar_small("Speed", spec_p2['max_speed'], 750, y1 + 30, 3 * WIDTH // 4)
            self.draw_bar_small("Accel", spec_p2['accel'], 500, y1 + 50, 3 * WIDTH // 4)
            
            if p2_ready:
                self.draw_text("READY", 32, GREEN, 3 * WIDTH // 4, y1 + 100, "center")
            else:
                self.draw_text("Select Car", 20, LIGHTGREY, 3 * WIDTH // 4, y1 + 100, "center")

            # Confirm Text
            if not (p1_ready and p2_ready):
                self.draw_text("Press SPACE to Toggle Ready", 24, WHITE, WIDTH // 2, HEIGHT - 50, "center")
            else:
                self.draw_text("Both Ready! Press SPACE again to Start", 28, CYAN, WIDTH // 2, HEIGHT - 90, "center")

            pygame.display.flip()
            
            now = pygame.time.get_ticks()
            joy_p2 = self.joysticks[1] if len(self.joysticks) > 1 else None
            
            if joy_p1 and now - getattr(self, 'last_input_time_p1', 0) > 200:
                if joy_p1.get_button(1): # B button to back
                    running = False
                    for s in self.all_sprites: s.kill()
                    return False
                if not p1_ready:
                    axis_x = joy_p1.get_axis(0)
                    if abs(axis_x) > 0.5:
                        preview_car_p1.kill()
                        p1_idx = (p1_idx + (1 if axis_x > 0 else -1)) % len(CAR_MODELS)
                        preview_car_p1 = Car(self, WIDTH // 4, HEIGHT // 2, CAR_MODELS[p1_idx], player_id=1)
                        self.last_input_time_p1 = now
                    elif joy_p1.get_hat(0)[0] != 0:
                        preview_car_p1.kill()
                        p1_idx = (p1_idx + joy_p1.get_hat(0)[0]) % len(CAR_MODELS)
                        preview_car_p1 = Car(self, WIDTH // 4, HEIGHT // 2, CAR_MODELS[p1_idx], player_id=1)
                        self.last_input_time_p1 = now
                if joy_p1.get_button(0): # A button to ready
                    if p1_ready and p2_ready:
                        self.selected_car_index = p1_idx
                        self.selected_car_index_p2 = p2_idx
                        running = False
                        for s in self.all_sprites: s.kill()
                        return True
                    else:
                        p1_ready = True
                        self.last_input_time_p1 = now

            if joy_p2 and now - getattr(self, 'last_input_time_p2', 0) > 200:
                if not p2_ready:
                    axis_x = joy_p2.get_axis(0)
                    if abs(axis_x) > 0.5:
                        preview_car_p2.kill()
                        p2_idx = (p2_idx + (1 if axis_x > 0 else -1)) % len(CAR_MODELS)
                        preview_car_p2 = Car(self, 3 * WIDTH // 4, HEIGHT // 2, CAR_MODELS[p2_idx], player_id=2)
                        self.last_input_time_p2 = now
                    elif joy_p2.get_hat(0)[0] != 0:
                        preview_car_p2.kill()
                        p2_idx = (p2_idx + joy_p2.get_hat(0)[0]) % len(CAR_MODELS)
                        preview_car_p2 = Car(self, 3 * WIDTH // 4, HEIGHT // 2, CAR_MODELS[p2_idx], player_id=2)
                        self.last_input_time_p2 = now
                if joy_p2.get_button(0): # A button to ready
                    if p1_ready and p2_ready:
                        self.selected_car_index = p1_idx
                        self.selected_car_index_p2 = p2_idx
                        running = False
                        for s in self.all_sprites: s.kill()
                        return True
                    else:
                        p2_ready = True
                        self.last_input_time_p2 = now

            for event in self.get_events():
                if event.type == pygame.QUIT:
                    self.quit()
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        running = False
                        # Ensure sprites are cleared
                        for s in self.all_sprites: s.kill()
                        return False # Back to menu

                    # P1 Selection (WASD)
                    if not p1_ready:
                        change = 0
                        if event.key == pygame.K_a: change = -1
                        if event.key == pygame.K_d: change = 1
                        
                        if change != 0:
                            preview_car_p1.kill()
                            p1_idx = (p1_idx + change) % len(CAR_MODELS)
                            preview_car_p1 = Car(self, WIDTH // 4, HEIGHT // 2, CAR_MODELS[p1_idx], player_id=1)

                    # P2 Selection (Arrows)
                    if not p2_ready:
                        change = 0
                        if event.key == pygame.K_LEFT: change = -1
                        if event.key == pygame.K_RIGHT: change = 1
                        
                        if change != 0:
                            preview_car_p2.kill()
                            p2_idx = (p2_idx + change) % len(CAR_MODELS)
                            preview_car_p2 = Car(self, 3 * WIDTH // 4, HEIGHT // 2, CAR_MODELS[p2_idx], player_id=2)
                    
                    # Confirm (Space)
                    if event.key == pygame.K_SPACE:
                        if p1_ready and p2_ready:
                            # Start Game!
                            self.selected_car_index = p1_idx
                            self.selected_car_index_p2 = p2_idx
                            running = False
                            for s in self.all_sprites: s.kill()
                            return True # Start game!
                        else:
                            # Toggle ready state for both
                            if not p1_ready: p1_ready = True
                            if not p2_ready: p2_ready = True
                            # If they are already ready, we do nothing until BOTH are ready and space is pressed again.
                            # But wait, if P1 is ready and P2 is NOT, pressing space makes P2 Ready.
                            # Then next press starts game.

    def show_singleplayer_selection(self):
        running = True
        
        # Clear existing sprites
        for sprite in self.all_sprites:
            sprite.kill()
            
        p1_idx = self.selected_car_index
        race_options = [-1, 1, 3, 5] # -1 is Free Play
        current_opt_idx = 0 
        
        # Preview Car
        preview_car_p1 = Car(self, WIDTH // 2, HEIGHT // 2, CAR_MODELS[p1_idx], player_id=1)
        
        # Controller check
        
        last_input_time = pygame.time.get_ticks() + 200

        while running:
            joy_p1 = self.joysticks[0] if self.joysticks else None
            self.clock.tick(FPS)
            self.screen.fill(BGCOLOR)
            
            # --- Input Handling for Menu ---
            # Use basic delay for menu movement with controller
            now = pygame.time.get_ticks()
            controller_move = 0
            
            if joy_p1 and now - last_input_time > 200:
                axis_x = joy_p1.get_axis(0)
                if abs(axis_x) > 0.5:
                    controller_move = 1 if axis_x > 0 else -1
                    last_input_time = now
                elif joy_p1.get_hat(0)[0] != 0:
                     controller_move = joy_p1.get_hat(0)[0]
                     last_input_time = now
                
                # Check for confirm (A button usually 0)
                if joy_p1.get_button(0):
                     self.selected_car_index = p1_idx
                     self.total_laps = race_options[current_opt_idx]
                     for s in self.all_sprites: s.kill()
                     return True
                # Check for cancel/back (B button usually 1)
                if joy_p1.get_button(1):
                     running = False
                     for s in self.all_sprites: s.kill()
                     return False
                     
                # Check axis 1 (Left Stick Y) for mode change
                axis_y = joy_p1.get_axis(1)
                if abs(axis_y) > 0.5:
                     if axis_y < -0.5: # Up
                         current_opt_idx = (current_opt_idx + 1) % len(race_options)
                     else: # Down
                         current_opt_idx = (current_opt_idx - 1) % len(race_options)
                     last_input_time = now
                # D-pad Y
                elif joy_p1.get_hat(0)[1] != 0:
                     if joy_p1.get_hat(0)[1] == 1: # Up
                          current_opt_idx = (current_opt_idx + 1) % len(race_options)
                     else:
                          current_opt_idx = (current_opt_idx - 1) % len(race_options)
                     last_input_time = now
                     
            
            self.draw_text("SINGLE PLAYER GARAGE", 48, WHITE, WIDTH // 2, 50, "center")
            
            # Display current mode
            mode_text = "FREE PLAY"
            if race_options[current_opt_idx] != -1:
                mode_text = f"{race_options[current_opt_idx]} LAP RACE"
            
            # Mode Selection Header
            self.draw_text("< " + mode_text + " >", 32, CYAN, WIDTH // 2, 100, "center")
            self.draw_text("(Up/Down to Change Mode)", 20, LIGHTGREY, WIDTH // 2, 130, "center")

            # Car Selection Header
            self.draw_text("Select Car", 24, WHITE, WIDTH // 2, HEIGHT // 2 - 120, "center")
            self.draw_text("(Left/Right to Change Car)", 20, LIGHTGREY, WIDTH // 2, HEIGHT // 2 - 90, "center")

            # --- P1 Update ---
            if preview_car_p1.original_image:
                 preview_car_p1.rot = (preview_car_p1.rot - 2) % 360 
                 preview_car_p1.image = pygame.transform.rotate(preview_car_p1.original_image, preview_car_p1.rot)
                 preview_car_p1.rect = preview_car_p1.image.get_rect(center=(WIDTH // 2, HEIGHT // 2))
                 self.screen.blit(preview_car_p1.image, preview_car_p1.rect)
            
            # --- Stats ---
            spec_p1 = CAR_MODELS[p1_idx]
            y1 = HEIGHT // 2 + 100
            self.draw_text(f"< {spec_p1['name']} >", 24, YELLOW, WIDTH//2, y1, "center")
            self.draw_bar_small("Speed", spec_p1['max_speed'], 750, y1 + 30, WIDTH // 2)
            self.draw_bar_small("Accel", spec_p1['accel'], 500, y1 + 50, WIDTH // 2)
            
            self.draw_text("Press SPACE / A to Start", 20, GREEN, WIDTH // 2, y1 + 100, "center")

            pygame.display.flip()
            
            for event in self.get_events():
                if event.type == pygame.QUIT:
                    self.quit()
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        running = False
                        for s in self.all_sprites: s.kill()
                        return False # Back

                    # Mode Selection (Up/Down)
                    if event.key == pygame.K_w or event.key == pygame.K_UP:
                         current_opt_idx = (current_opt_idx + 1) % len(race_options)
                    if event.key == pygame.K_s or event.key == pygame.K_DOWN:
                         current_opt_idx = (current_opt_idx - 1) % len(race_options)

                    # Car Selection (Left/Right)
                    change = 0
                    if event.key == pygame.K_a or event.key == pygame.K_LEFT: change = -1
                    if event.key == pygame.K_d or event.key == pygame.K_RIGHT: change = 1
                    
                    if change != 0:
                        preview_car_p1.kill()
                        p1_idx = (p1_idx + change) % len(CAR_MODELS)
                        preview_car_p1 = Car(self, WIDTH // 2, HEIGHT // 2, CAR_MODELS[p1_idx], player_id=1)
                
                    # Confirm (Space or Enter)
                    if event.key == pygame.K_SPACE or event.key == pygame.K_RETURN:
                         self.selected_car_index = p1_idx
                         self.total_laps = race_options[current_opt_idx]
                         for s in self.all_sprites: s.kill()
                         return True
            
            # Apply Controller Changes if any
            if controller_move != 0:
                preview_car_p1.kill()
                p1_idx = (p1_idx + controller_move) % len(CAR_MODELS)
                preview_car_p1 = Car(self, WIDTH // 2, HEIGHT // 2, CAR_MODELS[p1_idx], player_id=1)

    def draw_bar_small(self, label, value, max_val, y, cx):
        # Centered bar at cx
        bar_w = 150
        pct = value / max_val
        fill_w = int(bar_w * pct)
        
        # Outline
        pygame.draw.rect(self.screen, WHITE, (cx - bar_w//2, y, bar_w, 10), 1)
        # Fill
        pygame.draw.rect(self.screen, GREEN, (cx - bar_w//2 + 1, y+1, fill_w, 8))

    def draw_bar(self, label, value, max_val, y):
        # Label
        self.draw_text(label, 20, WHITE, WIDTH // 2 - 150, y, "e") # Align east/right of text to x
        # Bar Outline
        outline_rect = pygame.Rect(WIDTH // 2 - 140, y - 10, 280, 20)
        pygame.draw.rect(self.screen, WHITE, outline_rect, 2)
        # Fill
        pct = value / max_val
        fill_width = int(276 * pct)
        fill_rect = pygame.Rect(WIDTH // 2 - 138, y - 8, fill_width, 16)
        pygame.draw.rect(self.screen, GREEN, fill_rect)

    def show_go_screen(self):
        pass



if __name__ == '__main__':
    try:
        g = Game()
        g.show_start_screen()
        while True:
            g.new()
            g.run()
            g.show_go_screen()
    except Exception as e:
        import traceback
        with open("error_log.txt", "w") as f:
            traceback.print_exc(file=f)
        traceback.print_exc()
        pygame.quit()
        input("Press Enter to Exit...")
