import random
import math

def generate_track_map():
    WIDTH = 64
    HEIGHT = 48
    TRACK_WIDTH = 3  # Minimum width

    # Initialize grid with obstacles
    grid = [['1' for _ in range(WIDTH)] for _ in range(HEIGHT)]

    # 1. Generate Control Points for the track
    # We'll use a convex hull approach or just points around the center
    # to ensure a loop.
    
    center_x = WIDTH // 2
    center_y = HEIGHT // 2
    
    num_points = 12
    points = []
    
    # Generate points in roughly a circle/ellipse but with noise to make it interesting
    for i in range(num_points):
        angle = (2 * math.pi * i) / num_points
        # Try to make it fit within bounds with some margin
        max_radius_x = (WIDTH // 2) - 6
        max_radius_y = (HEIGHT // 2) - 6
        
        # Vary the radius to create corners/straights
        radius_x = random.uniform(max_radius_x * 0.5, max_radius_x)
        radius_y = random.uniform(max_radius_y * 0.5, max_radius_y)
        
        # Add some noise to angle to make it less perfect
        angle += random.uniform(-0.2, 0.2)
        
        x = int(center_x + math.cos(angle) * radius_x)
        y = int(center_y + math.sin(angle) * radius_y)
        
        # Clamp to bounds
        x = max(2, min(WIDTH - 3, x))
        y = max(2, min(HEIGHT - 3, y))
        
        points.append((x, y))

    # 2. Smooth the path (Catmull-Rom or Bezier-like interpolation)
    # We will interpolate points between the control points
    
    spline_points = []
    num_interpolated = 20 # points between control points
    
    for i in range(num_points):
        p0 = points[(i - 1) % num_points]
        p1 = points[i]
        p2 = points[(i + 1) % num_points]
        p3 = points[(i + 2) % num_points]
        
        for t_step in range(num_interpolated):
            t = t_step / num_interpolated
            
            # Catmull-Rom spline calculation
            # q(t) = 0.5 * ((2*P1) + (-P0 + P2) * t + (2*P0 - 5*P1 + 4*P2 - P3) * t^2 + (-P0 + 3*P1 - 3*P2 + P3) * t^3)
            
            tt = t * t
            ttt = tt * t
            
            x = 0.5 * ((2 * p1[0]) + (-p0[0] + p2[0]) * t + (2 * p0[0] - 5 * p1[0] + 4 * p2[0] - p3[0]) * tt + (-p0[0] + 3 * p1[0] - 3 * p2[0] + p3[0]) * ttt)
            y = 0.5 * ((2 * p1[1]) + (-p0[1] + p2[1]) * t + (2 * p0[1] - 5 * p1[1] + 4 * p2[1] - p3[1]) * tt + (-p0[1] + 3 * p1[1] - 3 * p2[1] + p3[1]) * ttt)
            
            spline_points.append((x, y))

    # 3. Draw the track
    # For each point in spline, clear a circle of radius TRACK_WIDTH/2
    
    for px, py in spline_points:
        for dx in range(-int(TRACK_WIDTH), int(TRACK_WIDTH) + 1):
            for dy in range(-int(TRACK_WIDTH), int(TRACK_WIDTH) + 1):
                if dx*dx + dy*dy <= (TRACK_WIDTH/0.9)**2: # Adjusted thickness
                    nx, ny = int(px + dx), int(py + dy)
                    if 0 <= nx < WIDTH and 0 <= ny < HEIGHT:
                        grid[ny][nx] = '.'

    # 4. cleanup isolated walls or holes (optional simple cellular automata or just leave as is)
    # Let's ensure the track is contiguous. The spline method usually ensures this if steps are small enough.
    
    # 5. Place Start/Finish Line
    # Find a straight section. We'll just pick the first point on the path that is on the grid.
    # Start point
    start_point = spline_points[0]
    sx, sy = int(start_point[0]), int(start_point[1])
    
    # Ensure it's on track
    if grid[sy][sx] == '.':
        grid[sy][sx] = 'P'
    else:
        # Search nearby
        found = False
        for dx in range(-2, 3):
            for dy in range(-2, 3):
                if 0 <= sy+dy < HEIGHT and 0 <= sx+dx < WIDTH and grid[sy+dy][sx+dx] == '.':
                    grid[sy+dy][sx+dx] = 'P'
                    found = True
                    break
            if found: break

    # 6. Format Output
    print("GAME_MAP = [")
    for row in grid:
        line = "".join(row)
        print(f'    "{line}",')
    print("]")

if __name__ == "__main__":
    generate_track_map()
