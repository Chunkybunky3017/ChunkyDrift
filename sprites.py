import pygame
import random
from settings import *
vec = pygame.math.Vector2

def collide_hit_rect(one, two):
    return one.hit_rect.colliderect(two.hit_rect)

class TireMark(pygame.sprite.Sprite):
    def __init__(self, game, pos, direction):
        self._layer = 0 # Ground layer
        self.groups = game.all_sprites
        pygame.sprite.Sprite.__init__(self, self.groups)
        self.game = game
        
        # Fade out timer
        self.spawn_time = pygame.time.get_ticks()
        self.lifetime = 3000 # 3 seconds
        
        # Create mark
        # A small dark rectangle rotated appropriately
        self.image = pygame.Surface((6, 6), pygame.SRCALPHA)
        
        # Color based on mode
        if hasattr(self.game, 'game_mode') and self.game.game_mode in ('rally', 'brands_hatch'):
            # Dark Brown for Dirt
            self.image.fill((70, 50, 30, 150))
        else:
            # Black for Asphalt (Drift/Stunt)
            self.image.fill((10, 10, 10, 120))
            
        self.original_image = self.image
        
        self.pos = vec(pos)
        self.rot = direction
        
        self.image = pygame.transform.rotate(self.original_image, -self.rot)
        self.rect = self.image.get_rect(center=self.pos)
        
    def update(self):
        now = pygame.time.get_ticks()
        if now - self.spawn_time > self.lifetime:
            self.kill()
        else:
            # Fade out calculation
            pct = 1 - ((now - self.spawn_time) / self.lifetime)
            alpha = int(255 * pct)
            self.image.set_alpha(alpha)

class Particle(pygame.sprite.Sprite):
    def __init__(self, game, pos, direction, is_drift):
        self._layer = 3 
        pygame.sprite.Sprite.__init__(self)
        self.game = game
        self.groups = self.game.all_sprites
        pygame.sprite.Sprite.add(self, self.groups)
        
        self.pos = vec(pos)
        self.rect = pygame.Rect(0, 0, 4, 4)
        self.rect.center = pos
        
        # Randomize particle direction slightly for natural spread
        # Direction should be generally opposite to car movement
        base_dir = vec(direction)
        if base_dir.length() > 0:
             base_dir = base_dir.normalize()
        else:
             base_dir = vec(-1, 0) # Default left
             
        spread = base_dir.rotate(random.uniform(-40, 40)) # Wider spread
        self.vel = spread * random.uniform(20, 100) # Faster dust
        
        self.lifetime = 0.8 # Lasts longer
        self.spawn_time = pygame.time.get_ticks()
        
        # Create surface
        self.size = random.randint(3, 7) # Varied size
        self.image = pygame.Surface((self.size, self.size), pygame.SRCALPHA)
        
        # Color based on Drift/Rally
        # Rally = Brown Dust
        # Drift = White/Grey Smoke
        is_rally = hasattr(self.game, 'game_mode') and self.game.game_mode in ('rally', 'brands_hatch')
        
        if is_rally:
             # Dirt Cloud
             color_val = random.randint(100, 160)
             color = (color_val, color_val - 30, color_val - 60, 150) # Brownish
        else:
             # Tire Smoke
             color_val = random.randint(200, 240)
             color = (color_val, color_val, color_val, 150) # Light Grey
             
        pygame.draw.circle(self.image, color, (self.size//2, self.size//2), self.size//2)

    def update(self):
        # Move particle
        self.pos += self.vel * self.game.dt
        # Slow down particle (air resistance)
        self.vel *= 0.95 
        
        self.rect.center = self.pos
        
        now = pygame.time.get_ticks()
        if now - self.spawn_time > self.lifetime * 1000:
            self.kill()
        else:
            # Fade out
            pct = 1 - ((now - self.spawn_time) / (self.lifetime * 1000))
            alpha = int(255 * pct * 0.6)
            self.image.set_alpha(alpha)

class Car(pygame.sprite.Sprite):
    def __init__(self, game, x, y, car_specs=None, player_id=1):
        self._layer = 1
        # Always init sprite with NO groups first, then add manually
        pygame.sprite.Sprite.__init__(self)
        self.game = game
        self.all_sprites = game.all_sprites
        self.all_sprites.add(self)
        self.player_id = player_id
        
        # Load Specs or Default
        if car_specs is None:
            car_specs = CAR_MODELS[0] # Default to first car
        self.car_specs = car_specs

        # Car Physics Constants from Specs
        self.ACCELERATION = car_specs['accel']
        self.MAX_SPEED = car_specs['max_speed']
        self.DRAG_COEFF = car_specs['drag'] # Using DRAG_COEFF to separate from logic
        self.FRICTION = car_specs['friction']
        self.BASE_GRIP = car_specs['grip']
        
        # Dimensions for Ford Focus Hatchback style
        self.image_width = 34
        self.image_height = 18
        
        # Create 3 variants of the car image
        self.images = {
            'straight': self.draw_car(0),
            'left': self.draw_car(1),  # Wheels turned left
            'right': self.draw_car(-1) # Wheels turned right
        }
        
        self.original_image = self.images['straight']
        self.image = self.original_image # Required for sprite drawing
        self.current_image_key = 'straight'
        
        self.rect = self.original_image.get_rect()
        self.rect.center = (x, y)
        self.hit_rect = PLAYER_HIT_RECT
        self.hit_rect.center = self.rect.center
        self.vel = vec(0, 0)
        self.pos = vec(x, y)
        self.start_pos = vec(x, y) # Save start position for respawn
        self.start_rot = 0
        self.rot = 0
        self.speed = 0  
        self.is_drifting = False
        self.grip = 1.0 
        
        # Stunt Physics
        self.z = 0 # Height above ground
        self.z_vel = 0
        self.on_ground = True
        self.laps = 0
        self.checkpoint_passed = False
        self.sync_visual_to_rotation()

    def sync_visual_to_rotation(self):
        self.image = pygame.transform.rotate(self.original_image, self.rot)
        self.rect = self.image.get_rect()
        self.rect.center = self.pos
        self.hit_rect.center = self.pos

    def respawn(self):
        self.pos = vec(self.start_pos)
        self.vel = vec(0, 0)
        self.speed = 0
        self.rot = self.start_rot
        self.z = 0
        self.z_vel = 0
        self.on_ground = True
        self.sync_visual_to_rotation()

    def draw_car(self, turn_state):
        # turn_state: 0=straight, 1=left, -1=right
        surf = pygame.Surface((self.image_width + 4, self.image_height + 4), pygame.SRCALPHA)
        # Shift drawing by (2,2) to allow for wheel overhang
        ox, oy = 2, 2
        
        # Car Color from Specs
        body_color = self.car_specs['color']
        window_color = (20, 20, 30)
        
        # 1. Wheels (Black Rectangles)
        wheel_w, wheel_h = 7, 4
        # Wheel offsets (relative to ox, oy)
        fl = (24, 1)  # Front Left
        fr = (24, self.image_height - 5) # Front Right
        bl = (4, 1)   # Back Left
        br = (4, self.image_height - 5)  # Back Right
        
        # Wheel Rotation Logic
        wheel_angle = 0
        if turn_state == 1: wheel_angle = 25  # Turn Left
        elif turn_state == -1: wheel_angle = -25 # Turn Right
            
        # Draw Wheels
        # Back wheels are fixed
        pygame.draw.rect(surf, (10, 10, 10), (ox + bl[0], oy + bl[1], wheel_w, wheel_h))
        pygame.draw.rect(surf, (10, 10, 10), (ox + br[0], oy + br[1], wheel_w, wheel_h))
        
        # Front wheels rotate
        # Use a temporary surface to rotate the rect, then blit
        wheel_surf = pygame.Surface((wheel_w, wheel_h), pygame.SRCALPHA)
        wheel_surf.fill((10, 10, 10))
        rot_wheel = pygame.transform.rotate(wheel_surf, wheel_angle)
        
        # Adjust blit position to keep centered
        w_rect = rot_wheel.get_rect(center=(ox + fl[0] + wheel_w//2, oy + fl[1] + wheel_h//2))
        surf.blit(rot_wheel, w_rect)
        
        w_rect = rot_wheel.get_rect(center=(ox + fr[0] + wheel_w//2, oy + fr[1] + wheel_h//2))
        surf.blit(rot_wheel, w_rect)
        
        # 2. Main Body (Hatchback shape)
        # Main chassis
        pygame.draw.rect(surf, body_color, (ox, oy + 2, self.image_width, self.image_height - 4), border_radius=3)
        # Cabin (slightly narrower)
        pygame.draw.rect(surf, body_color, (ox + 4, oy + 1, self.image_width - 10, self.image_height - 2), border_radius=4)
        
        # 3. Windows
        # Windshield
        pygame.draw.polygon(surf, window_color, [(ox + 20, oy + 3), (ox + 20, oy + 14), (ox + 23, oy + 14), (ox + 23, oy + 3)])
        # Side Windows
        pygame.draw.rect(surf, window_color, (ox + 8, oy + 2, 10, 2)) # Left
        pygame.draw.rect(surf, window_color, (ox + 8, oy + 14, 10, 2)) # Right
        # Rear Window
        pygame.draw.rect(surf, window_color, (ox + 2, oy + 4, 3, 10))

        # 4. Details
        # Headlights (aggressive slanted)
        pygame.draw.polygon(surf, YELLOW, [(ox + self.image_width-1, oy + 2), (ox + self.image_width-6, oy + 2), (ox + self.image_width-1, oy + 5)])
        pygame.draw.polygon(surf, YELLOW, [(ox + self.image_width-1, oy + 15), (ox + self.image_width-6, oy + 15), (ox + self.image_width-1, oy + 12)])
        
        # Spoiler (Big Wing)
        pygame.draw.rect(surf, (0, 0, 150), (ox - 2, oy, 4, self.image_height), border_radius=2)
        
        # Digits/Decals (White squares)
        pygame.draw.rect(surf, WHITE, (ox + 12, oy + 6, 6, 6))

        return surf

    def get_keys(self):
        self.rot_speed = 0
        keys = pygame.key.get_pressed()
        
        # Controller Input Variables
        joy_turn = 0
        joy_gas = 0
        joy_brake = 0
        joy_drift = False

        # Check for Joystick
        if hasattr(self.game, 'joysticks') and len(self.game.joysticks) >= self.player_id:
            joy = self.game.joysticks[self.player_id - 1]
            try:
                # Steering (Left Stick X - Axis 0)
                if abs(joy.get_axis(0)) > 0.2:
                    joy_turn = joy.get_axis(0)
                
                # Gas (R2 / Right Trigger - Axis 5)
                # Note: Triggers often range -1 to 1. -1 is released, 1 is pressed.
                # Or 0 to 1.
                # We will check both commonly used axes for triggers (4 and 5)
                # Some drivers map triggers to Z axis (2). 
                # Let's try standard XInput: Axis 5 is RT.
                if joy.get_numaxes() > 5:
                    rt_val = joy.get_axis(5)
                    if rt_val > -0.8: # Threshold
                         joy_gas = (rt_val + 1) / 2 # Normalize to 0-1
                
                # Brake/Reverse (L2 / Left Trigger - Axis 4)
                if joy.get_numaxes() > 4:
                    lt_val = joy.get_axis(4) 
                    if lt_val > -0.8:
                         joy_brake = (lt_val + 1) / 2
                         
                # Fallback for triggers on Axis 2 (Z-axis)
                if joy.get_numaxes() > 2 and joy_gas == 0 and joy_brake == 0:
                    z_val = joy.get_axis(2)
                    if z_val < -0.2: # Right trigger
                        joy_gas = abs(z_val)
                    elif z_val > 0.2: # Left trigger
                        joy_brake = abs(z_val)
                
                # Fallback to buttons if triggers aren't pressed
                if joy_gas == 0 and joy.get_button(0): # A button
                    joy_gas = 1.0
                if joy_brake == 0 and joy.get_button(1): # B button
                    joy_brake = 1.0
                
                # Drift (Button 2 or 3 - X or Y)
                if joy.get_button(2) or joy.get_button(3):
                     joy_drift = True
                     
                # Respawn (Select or Start - Button 6 or 7)
                if joy.get_button(6) or joy.get_button(7):
                     self.respawn()

            except pygame.error:
                pass
        
        # Determine turning state for animation
        turn_state = 'straight'

        # Drift / Handbrake
        # Player 1 uses Left Shift, Player 2 uses Right Shift or Right Ctrl?
        # Let's map drifting keys based on player ID
        drift_key = False
        if self.player_id == 1:
            drift_key = keys[pygame.K_LSHIFT]
        else:
            drift_key = keys[pygame.K_PERIOD] or keys[pygame.K_KP_PERIOD]

        self.is_drifting = drift_key or joy_drift
        
        # Respawn
        if self.player_id == 1:
            if keys[pygame.K_r]:
                self.respawn()
        else:
            if keys[pygame.K_RETURN] or keys[pygame.K_KP_ENTER]:
                self.respawn()
        
        # --- AIR CONTROLS DISABLED ---
        # if not self.on_ground:
            # No steering or gas in the air!
            # return

        current_rot_speed = PLAYER_ROT_SPEED
        if self.is_drifting:
            current_rot_speed *= 1.3 # Slightly less boost than before for heaviness
        else:
            current_rot_speed *= 0.6 

        turn_left = False
        turn_right = False
        gas = False
        brake = False

        if self.player_id == 1:
            # Player 1: WASD (and Arrows if single player)
            if keys[pygame.K_a]: turn_left = True
            if keys[pygame.K_d]: turn_right = True
            if keys[pygame.K_w]: gas = True
            if keys[pygame.K_s]: brake = True
            
            # Allow Arrows too if not multiplayer
            if hasattr(self.game, 'multiplayer') and not self.game.multiplayer:
                if keys[pygame.K_LEFT]: turn_left = True
                if keys[pygame.K_RIGHT]: turn_right = True
                if keys[pygame.K_UP]: gas = True
                if keys[pygame.K_DOWN]: brake = True
        else:
            # Player 2: Arrows
            if keys[pygame.K_LEFT]: turn_left = True
            if keys[pygame.K_RIGHT]: turn_right = True
            if keys[pygame.K_UP]: gas = True
            if keys[pygame.K_DOWN]: brake = True

        # Apply Input
        if turn_left or joy_turn < -0.2:
            self.rot_speed = current_rot_speed
            if joy_turn < -0.2: self.rot_speed *= abs(joy_turn)
            turn_state = 'left'
        if turn_right or joy_turn > 0.2:
            self.rot_speed = -current_rot_speed
            if joy_turn > 0.2: self.rot_speed *= abs(joy_turn)
            turn_state = 'right'
            
        # Update Image based on turn state
        if turn_state != self.current_image_key:
            self.current_image_key = turn_state
            self.original_image = self.images[turn_state]
        
        # Acceleration logic applying force to self.vel
        forward_vec = vec(1, 0).rotate(-self.rot)
        
        if gas or joy_gas > 0:
             force = self.ACCELERATION * self.game.dt
             if joy_gas > 0: force *= joy_gas
             self.vel += forward_vec * force
             
        if brake or joy_brake > 0:
             force = self.ACCELERATION * self.game.dt * 0.5
             if joy_brake > 0: force *= joy_brake
             self.vel -= forward_vec * force
             
        # Drifting Logic - Tire Marks using simple dots/lines
        if self.is_drifting and self.vel.length() > 50:
            # Spawn tire marks at rear wheels
            # Rear wheels are roughly at -20 x locally
            rear_offset = vec(-20, 0).rotate(-self.rot)
            left_wheel = vec(0, -10).rotate(-self.rot)
            right_wheel = vec(0, 10).rotate(-self.rot)
            
            mark_l = self.pos + rear_offset + left_wheel
            mark_r = self.pos + rear_offset + right_wheel
            
            # Add to game
            # We use a simple sprite for marks that fades
            TireMark(self.game, mark_l, self.rot)
            TireMark(self.game, mark_r, self.rot)

        
        # Heavy Friction/Drag
        # Apply constant friction opposite to velocity (rolling resistance)
        if self.vel.length() > 0:
             friction_force = -self.vel.normalize() * self.FRICTION * self.game.dt
             self.vel += friction_force
             
             # Apply Air Drag (proportional to speed squared, simplifies to linear for game feel)
             self.vel *= self.DRAG_COEFF

        # Cap speed
        if self.vel.length() > self.MAX_SPEED:
            self.vel.scale_to_length(self.MAX_SPEED)

    def update(self):
        self.get_keys()
        
        # 1. Rotation Logic
        old_rot = self.rot
        self.rot = (self.rot + self.rot_speed * self.game.dt) % 360
        self.image = pygame.transform.rotate(self.original_image, self.rot)
        self.rect = self.image.get_rect()
        self.rect.center = self.pos
        
        # Sync hitbox
        self.hit_rect.center = self.pos

        # If rotation causes collision, revert rotation
        if pygame.sprite.spritecollide(self, self.game.walls, False, collide_hit_rect):
            self.rot = old_rot
            self.image = pygame.transform.rotate(self.original_image, self.rot)
            self.rect = self.image.get_rect()
            self.rect.center = self.pos
            self.hit_rect.center = self.pos

        # 2. Velocity Calculation (Drift Physics)
        # Always apply tire physics, even "in air" for decorative jumps
        forward_vec = vec(1, 0).rotate(-self.rot)
        right_vec = vec(0, 1).rotate(-self.rot) # Vector 90 degrees to car
        
        # Calculate forward and sideways speed components
        # Dot product projects velocity onto the direction vector
        vel_forward = forward_vec * (self.vel.dot(forward_vec)) 
        # vel_sideways = right_vec * (self.vel.dot(right_vec)) # Unused variable assignment if we overwrite it or use it differently below? 
        # Actually we likely need the vector component, not just the magnitude
        sideways_component = self.vel.dot(right_vec)
        vel_sideways = right_vec * sideways_component
        
        # Traction Control
        # If drifting, we have LOW sideways friction (car slides)
        # If not drifting, we slowly regain high friction
        
        target_grip = self.BASE_GRIP # Use car spec grip
        if self.is_drifting:
            target_grip = 0.05 # Reduced grip drastically for sliding

        # Smoothly interpolate grip (simulating gradual regain of traction)
        # Slower recovery (was 2) means momentum carries sideways longer
        self.grip += (target_grip - self.grip) * 1.5 * self.game.dt
        
        # Apply grip to sideways velocity
        # Less grip (0.0) -> vel_sideways decays slowly (0.99)
        # More grip (1.0) -> vel_sideways decays quickly (0.5)
        
        # Reduced grip effectiveness slightly to allow more slide momentum
        friction_factor = 0.99 - (self.grip * 0.25)
        
        vel_sideways *= friction_factor
        
        # Create Dust Particles logic
        # 1. Always when driving fast on dirt (Rally Mode)
        # 2. When drifting/sliding (Any Mode)
        # 3. Wheelspin (acceleration from stop)
        
        current_speed = self.vel.length()
        is_rally = hasattr(self.game, 'game_mode') and self.game.game_mode in ('rally', 'brands_hatch')
        
        spawn_dust = False
        dust_intensity = 1 # Number of particles
        
        # Condition 1: Driving fast in Rally
        if is_rally and current_speed > 200:
            if random.random() < 0.3: # 30% chance per frame
                spawn_dust = True
                dust_intensity = 1
        
        # Condition 2: Drifting
        if self.is_drifting and current_speed > 50:
             spawn_dust = True
             dust_intensity = 2 # More dust when drifting
             if is_rally: dust_intensity = 3 # EVEN MORE on dirt
             
        # Condition 3: Wheelspin (High acceleration at low speed)
        # Check if gas is pressed
        gas_pressed = False
        
        multiplayer_on = False
        if hasattr(self.game, 'multiplayer'):
            multiplayer_on = self.game.multiplayer
            
        keys = pygame.key.get_pressed() # Get keys for input check

        if self.player_id == 1:
            gas_pressed = keys[pygame.K_w] or ((not multiplayer_on) and keys[pygame.K_UP])
        else:
            gas_pressed = keys[pygame.K_UP]

        if gas_pressed and current_speed < 100 and current_speed > 10:
             if random.random() < 0.5:
                 spawn_dust = True
                 dust_intensity = 1

        if spawn_dust:
            for _ in range(dust_intensity):
                # Rear tires position approx
                # Rear axle is -20 locally
                offset_l = vec(-20, -10).rotate(-self.rot)
                offset_r = vec(-20, 10).rotate(-self.rot)
                
                # Reverse velocity for dust direction
                dust_dir = -self.vel
                if dust_dir.length() == 0: dust_dir = vec(-1, 0).rotate(-self.rot) # Behind car if stopped
                
                Particle(self.game, self.pos + offset_l, dust_dir, self.is_drifting)
                Particle(self.game, self.pos + offset_r, dust_dir, self.is_drifting)

        # Recombine velocity
        self.vel = vel_forward + vel_sideways
        
        self.speed = self.vel.length() # Update speed for display/logic
        
        # --- Z Velocity (Jumps) ---
        if not self.on_ground:
            self.z_vel -= 500 * self.game.dt # Gravity (Reduced from 800)
            self.z += self.z_vel * self.game.dt
            if self.z <= 0:
                self.z = 0
                self.z_vel = 0
                self.on_ground = True
                
        # 3. Position Logic (with robust collision)
        move = self.vel * self.game.dt

        # Use sub-steps to prevent tunneling through walls at high speed.
        max_component = max(abs(move.x), abs(move.y))
        steps = max(1, int(max_component // (TILESIZE / 3)) + 1)
        step_move = move / steps

        collided_with_wall = False

        for _ in range(steps):
            self.pos += step_move
            self.rect.center = self.pos
            self.hit_rect.center = self.pos

            check_collisions = True
            if self.z > 20: # If flying high enough
                check_collisions = False

            if check_collisions:
                hits = pygame.sprite.spritecollide(self, self.game.walls, False, collide_hit_rect)
                if hits:
                    # Roll back only this sub-step and stop movement this frame.
                    self.pos -= step_move
                    self.rect.center = self.pos
                    self.hit_rect.center = self.pos
                    collided_with_wall = True
                    break

        if collided_with_wall and self.vel.length() > 0:
            # Bounce back with speed loss.
            self.vel = -self.vel * 0.45
        
        # --- JUMP RAMPS ---
        # Detect ramps
        hits = pygame.sprite.spritecollide(self, self.game.ramps, False, collide_hit_rect)
        for ramp in hits:
            if ramp.type == '^': # Up Ramp
                # Trigger VISUAL jump only 
                if self.on_ground: 
                    self.on_ground = False
                    self.z_vel = 180 
                    
                    # --- AUTO JUMP ASSIST ---
                    # To ensure the player "always lands on the exit", we boost strict forward speed
                    # if they are going too slow to clear the gap.
                    current_speed = self.vel.length()
                    if current_speed < 400: # If moving slower than 400 pixels/sec
                        # Vector in direction of facing
                        forward_dir = vec(1, 0).rotate(-self.rot)
                        self.vel = forward_dir * 450 # Force speed to clear the gap
                        
            elif ramp.type == 'v': # Down Ramp / Landing
                 # Could handle smooth landing logic here if needed
                 pass 

        # --- PIT COLLISION ---
        if hasattr(self.game, 'pits'):
            hits = pygame.sprite.spritecollide(self, self.game.pits, False, collide_hit_rect)
            if hits:
                # If we are not 'flying' (z > 10), we fall in
                if self.z < 10:
                     self.respawn()
                     
        # Connect visual rect to physics position
        # If jumping, we shift the visual rect UP (y-axis) to simulate height
        visual_pos = vec(self.pos)
        if self.z > 0:
            visual_pos.y -= self.z # Shift sprite up by height
            
            # Massive scale effect for clarity
            scale_factor = 1.0 + (self.z / 200.0) # Much bigger scaling (was 500)
            scaled_size = (int(self.original_image.get_width() * scale_factor), int(self.original_image.get_height() * scale_factor))
            self.image = pygame.transform.scale(self.image, scaled_size)
            
        self.rect = self.image.get_rect()
        self.rect.center = visual_pos # Update visual position
        
        # Hitbox (physics) remains grounded at self.pos
        self.hit_rect.center = self.pos
        
        # --- LAP COUNTING ---
        if hasattr(self.game, 'checkpoints'):
            hits = pygame.sprite.spritecollide(self, self.game.checkpoints, False)
            if hits:
                self.checkpoint_passed = True
        
        if hasattr(self.game, 'finish_lines'):
            hits = pygame.sprite.spritecollide(self, self.game.finish_lines, False)
            if hits:
                if self.checkpoint_passed:
                    self.laps += 1
                    self.checkpoint_passed = False
                    print(f"Player {self.player_id} completed lap {self.laps}!")

class Wall(pygame.sprite.Sprite):
    def __init__(self, game, x, y, tile_type='1'):
        # Initialize sprite without groups first
        pygame.sprite.Sprite.__init__(self)
        self.game = game
        
        # Manually add to groups
        if hasattr(game, 'all_sprites'):
             self.add(game.all_sprites) 
        if hasattr(game, 'walls'):
             self.add(game.walls)
             
        self.image = pygame.Surface((TILESIZE, TILESIZE))
        if hasattr(game, 'game_mode') and game.game_mode == 'drift':
            # Tokyo Drift Building Style
            self.image.fill(BUILDING_ROOF)
            pygame.draw.rect(self.image, BUILDING_WALL, (2, 2, TILESIZE-4, TILESIZE-4))
            # Little light/window
            if random.random() > 0.7:
                pygame.draw.rect(self.image, BUILDING_LIGHT, (8, 8, 4, 8))
        elif hasattr(game, 'game_mode') and game.game_mode == 'stunt':
             if tile_type == '1' or tile_type == 'W':
                  self.image.fill(STUNT_WALL)
                  pygame.draw.rect(self.image, (150, 40, 40), (2, 2, TILESIZE-4, TILESIZE-4))
        else:
            # Classic Rally Grass Style
            self.image.fill(GRASS_GREEN)
            # Add some graphical noise for grass texture
            for _ in range(5):
                rx = random.randint(0, TILESIZE)
                ry = random.randint(0, TILESIZE)
                pygame.draw.circle(self.image, (30, 100, 30), (rx, ry), 2)
        
        self.rect = self.image.get_rect()
        self.x = x
        self.y = y
        self.rect.x = x * TILESIZE
        self.rect.y = y * TILESIZE
        
        # Hitbox matches tile size to prevent gaps between adjacent wall tiles.
        self.hit_rect = pygame.Rect(x * TILESIZE,
                        y * TILESIZE,
                        TILESIZE,
                        TILESIZE)

class Bridge(pygame.sprite.Sprite):
    def __init__(self, game, x, y):
        pygame.sprite.Sprite.__init__(self)
        self.game = game
        self.add(game.all_sprites)
        # Note: Bridges are NOT walls in 'walls' group unless we want collision
        # We might want separate 'bridges' group for Z-sorting if needed
        
        self.image = pygame.Surface((TILESIZE, TILESIZE))
        self.image.fill(BRIDGE_COLOR)
        # Add texture
        pygame.draw.line(self.image, (100, 100, 100), (0, 0), (0, TILESIZE), 2)
        pygame.draw.line(self.image, (100, 100, 100), (TILESIZE-2, 0), (TILESIZE-2, TILESIZE), 2)
        
        self.rect = self.image.get_rect()
        self.rect.x = x * TILESIZE
        self.rect.y = y * TILESIZE
        self._layer = 0 # Ground layer, but usually drawn after road

class Ramp(pygame.sprite.Sprite):
    def __init__(self, game, x, y, type):
        pygame.sprite.Sprite.__init__(self)
        self.game = game
        self.add(game.all_sprites)
        self.add(game.ramps)
        self.type = type
        
        self.image = pygame.Surface((TILESIZE, TILESIZE), pygame.SRCALPHA)
        
        # Wood Colors
        WOOD_LIGHT = (180, 140, 90)
        WOOD_DARK = (100, 70, 30)
        WOOD_MEDIUM = (140, 100, 60)
        
        # Draw wooden planks background
        pygame.draw.rect(self.image, WOOD_MEDIUM, (0, 0, TILESIZE, TILESIZE))
        
        # Draw individual planks (horizontal stripes)
        plank_height = 4
        for i in range(0, TILESIZE, plank_height):
            # Alternating slightly for texture
            color = WOOD_LIGHT if (i // plank_height) % 2 == 0 else WOOD_MEDIUM
            pygame.draw.rect(self.image, color, (0, i, TILESIZE, plank_height-1))
            # Plank outline/gap
            pygame.draw.line(self.image, WOOD_DARK, (0, i), (TILESIZE, i), 1)
            
            # Nails
            pygame.draw.circle(self.image, (50, 30, 10), (2, i + 2), 1)
            pygame.draw.circle(self.image, (50, 30, 10), (TILESIZE-3, i + 2), 1)

        # Visual indicator for ramp type (overlay)
        if type == '^':
             # Up Ramp (Launch) - Draw a "Support" structure or lighter end to show rise?
             # Let's add bold arrows still so player knows direction, but make them "painted on wood"
             # White painted arrows
             arrow_points = [(4, TILESIZE-4), (TILESIZE//2, 4), (TILESIZE-4, TILESIZE-4)]
             pygame.draw.lines(self.image, (220, 220, 220), False, arrow_points, 3)
        else:
             # Down Ramp (Landing) - Target
             # Painted circle
             pygame.draw.circle(self.image, (220, 220, 220), (TILESIZE//2, TILESIZE//2), TILESIZE//3, 2)
             pygame.draw.circle(self.image, (200, 50, 50), (TILESIZE//2, TILESIZE//2), TILESIZE//6, 0)

        self.rect = self.image.get_rect()
        self.rect.x = x * TILESIZE
        self.rect.y = y * TILESIZE
        self.hit_rect = self.rect # Standard rect for collision

class Pit(pygame.sprite.Sprite):
    def __init__(self, game, x, y):
        pygame.sprite.Sprite.__init__(self)
        self.game = game
        # Not added to all_sprites? If we want to see it, yes.
        # But we already drew it on the map_img!
        # So this sprite is purely for COLISSION logic.
        self.add(game.pits)
        self.image = pygame.Surface((TILESIZE, TILESIZE))
        # No image needed if invisible physics object, but useful for debug
        self.rect = pygame.Rect(x * TILESIZE, y * TILESIZE, TILESIZE, TILESIZE)
        self.hit_rect = self.rect


class FinishLine(pygame.sprite.Sprite):
    def __init__(self, game, x, y):
        self._layer = 1
        self.groups = game.all_sprites, game.finish_lines
        pygame.sprite.Sprite.__init__(self, self.groups)
        self.game = game
        self.image = pygame.Surface((TILESIZE, TILESIZE), pygame.SRCALPHA)
        self.image.fill((255, 255, 255, 50)) # Transparent white
        # Checkerboard pattern
        pygame.draw.rect(self.image, (0, 0, 0), (0, 0, TILESIZE//2, TILESIZE//2))
        pygame.draw.rect(self.image, (0, 0, 0), (TILESIZE//2, TILESIZE//2, TILESIZE//2, TILESIZE//2))
        self.rect = self.image.get_rect()
        self.rect.x = x * TILESIZE
        self.rect.y = y * TILESIZE

class Checkpoint(pygame.sprite.Sprite):
    def __init__(self, game, x, y):
        self._layer = 1
        # Remove from all_sprites so it is invisible (doesn't get drawn)
        self.groups = game.checkpoints
        pygame.sprite.Sprite.__init__(self, self.groups)
        self.game = game
        self.image = pygame.Surface((TILESIZE, TILESIZE), pygame.SRCALPHA)
        # self.image.fill((255, 255, 0, 50)) # Transparent yellow
        self.rect = self.image.get_rect()
        self.rect.x = x * TILESIZE
        self.rect.y = y * TILESIZE
