import random
import math

def generate_racing_map():
    WIDTH = 64
    HEIGHT = 48
    TRACK_RADIUS = 2  # Results in width of roughly 2*2+1 = 5 tiles if using simple distance, user asked for 2-3 tiles width. 
                      # 2-3 tiles width means radius should be around 1 to 1.5. 
                      # Let's use 1.5 float radius.

    # Initialize grid with walls
    grid = [['1' for _ in range(WIDTH)] for _ in range(HEIGHT)]

    # 1. Generate Control Points for the loop
    center_x = WIDTH // 2
    center_y = HEIGHT // 2
    
    # Use an ellipse that fills most of the map with a small margin
    margin = 4
    radius_x = (WIDTH // 2) - margin
    radius_y = (HEIGHT // 2) - margin
    
    num_points = 16
    control_points = []
    
    for i in range(num_points):
        angle = (2 * math.pi * i) / num_points
        # Add some randomness to the radius to make the track interesting, but keep it near the edge
        # Variation between 0.8 and 1.0 of the max radius
        variation = random.uniform(0.8, 1.0)
        
        # Add some angle noise
        angle_noise = random.uniform(-0.1, 0.1)
        
        r_x = radius_x * variation
        r_y = radius_y * variation
        
        x = center_x + math.cos(angle + angle_noise) * r_x
        y = center_y + math.sin(angle + angle_noise) * r_y
        
        # Clamp to ensure it stays within bounds
        x = max(margin, min(WIDTH - margin, x))
        y = max(margin, min(HEIGHT - margin, y))
        
        control_points.append((x, y))

    # 2. Generate smooth path using Catmull-Rom Spline
    path_points = []
    steps_per_segment = 20
    
    # Duplicate points to handle wrapping for closed loop
    # For Catmull-Rom, we need p0, p1, p2, p3. To interpolate between p1 and p2.
    # We extend the list to wrap around.
    
    extended_points = control_points + control_points[:3]
    
    for i in range(num_points):
        p0 = extended_points[i]
        p1 = extended_points[i+1]
        p2 = extended_points[i+2]
        p3 = extended_points[i+3]
        
        for t_step in range(steps_per_segment):
            t = t_step / steps_per_segment
            t2 = t * t
            t3 = t2 * t
            
            # Catmull-Rom formula
            # 0.5 * ( (2*p1) + (-p0 + p2)*t + (2*p0 - 5*p1 + 4*p2 - p3)*t2 + (-p0 + 3*p1 - 3*p2 + p3)*t3 )
            
            x = 0.5 * ((2 * p1[0]) + (-p0[0] + p2[0]) * t + (2 * p0[0] - 5 * p1[0] + 4 * p2[0] - p3[0]) * t2 + (-p0[0] + 3 * p1[0] - 3 * p2[0] + p3[0]) * t3)
            y = 0.5 * ((2 * p1[1]) + (-p0[1] + p2[1]) * t + (2 * p0[1] - 5 * p1[1] + 4 * p2[1] - p3[1]) * t2 + (-p0[1] + 3 * p1[1] - 3 * p2[1] + p3[1]) * t3)
            
            path_points.append((x, y))

    # 3. Draw the track
    # User requested 2-3 tiles width.
    # If we mark the cell itself and neighbors, we can get width.
    # Radius 1.2 gives roughly a 3x3 block or a cross shape.
    
    track_radius = 1.9 # Slightly larger to ensure connectivity and 2-3 tile width
    
    track_cells = set()

    for px, py in path_points:
        # Determine integer range to check
        min_x = int(px - track_radius - 1)
        max_x = int(px + track_radius + 2)
        min_y = int(py - track_radius - 1)
        max_y = int(py + track_radius + 2)
        
        for y in range(min_y, max_y):
            for x in range(min_x, max_x):
                if 0 <= x < WIDTH and 0 <= y < HEIGHT:
                    # Check distance
                    dist = math.sqrt((x - px)**2 + (y - py)**2)
                    if dist <= track_radius:
                        grid[y][x] = '.'
                        track_cells.add((x, y))

    # Helper to get perpendicular direction
    def get_perp_vector(idx):
        # returns normalized perpendicular vector (dy, -dx)
        prev_p = path_points[idx - 1]
        next_p = path_points[(idx + 1) % len(path_points)]
        dx = next_p[0] - prev_p[0]
        dy = next_p[1] - prev_p[1]
        length = math.sqrt(dx*dx + dy*dy)
        if length == 0: return (0, 0)
        return (-dy/length, dx/length)

    # 4. Place Finish Line 'F'
    # Use index 0 for finish line
    finish_idx = 0
    fx, fy = path_points[finish_idx]
    p_dx, p_dy = get_perp_vector(finish_idx)
    
    # Draw logic for line across track
    # We trace along the perpendicular vector in both directions until we hit a wall
    for direction in [1, -1]:
        dist = 0
        while True:
            tx = int(fx + p_dx * dist * direction)
            ty = int(fy + p_dy * dist * direction)
            
            if (tx, ty) not in track_cells: # Hit wall (or outside track bounds logic)
                 # Actually, we should check if it WAS a track piece before overwriting
                 break
            
            # Additional check: ensure we are within reasonable distance from center line
            # so we don't draw 'F' on a parallel track segment if the track loops close to itself
            if math.sqrt((tx-fx)**2 + (ty-fy)**2) > track_radius + 1:
                break

            grid[ty][tx] = 'F'
            dist += 0.5 # smaller steps

    # 5. Place Checkpoint 'C'
    # Halfway around
    check_idx = len(path_points) // 2
    cx, cy = path_points[check_idx]
    c_dx, c_dy = get_perp_vector(check_idx)
    
    for direction in [1, -1]:
        dist = 0
        while True:
            tx = int(cx + c_dx * dist * direction)
            ty = int(cy + c_dy * dist * direction)
            
            if (tx, ty) not in track_cells:
                 break
            if math.sqrt((tx-cx)**2 + (ty-cy)**2) > track_radius + 1:
                break
                
            grid[ty][tx] = 'C'
            dist += 0.5


    # 6. Place Player 'P'
    # Just before finish line. Go back a moderate distance along the path.
    # path_points wraps around, so index -10 is valid in python list or logic
    start_dist_back = 15 # steps back
    start_idx = (finish_idx - start_dist_back) % len(path_points)
    sx, sy = path_points[start_idx]
    
    # Ensure distinct from F and is a valid spot
    # We just place P at that integer coordinate
    grid[int(sy)][int(sx)] = 'P'

    # 7. Print Result
    print("GAME_MAP = [")
    for row in grid:
        line = "".join(row)
        print(f'    "{line}",')
    print("]")

if __name__ == "__main__":
    generate_racing_map()
