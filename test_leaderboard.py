import sys
import os
try:
    from leaderboard import Leaderboard
    lb = Leaderboard()
    lb.add_score('rally', '1_lap', 'TestUser', 1000)
    scores = lb.get_top_scores('rally', '1_lap')
    print(f"Scores: {scores}")
except Exception as e:
    import traceback
    traceback.print_exc()
