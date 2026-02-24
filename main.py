import pygame
from game import Game

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
        traceback.print_exc()
        pygame.quit()
        input("Press Enter to Exit...") # Pause to read error
