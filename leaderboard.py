import json
import os

LEADERBOARD_FILE = "leaderboard.json"

class Leaderboard:
    def __init__(self):
        self.scores = self.load_scores()

    def load_scores(self):
        if not os.path.exists(LEADERBOARD_FILE):
            return self.create_default_scores()
        try:
            with open(LEADERBOARD_FILE, 'r') as f:
                loaded_scores = json.load(f)
                return self.ensure_score_schema(loaded_scores)
        except (json.JSONDecodeError, IOError):
            return self.create_default_scores()

    def ensure_score_schema(self, loaded_scores):
        defaults = self.create_default_scores()

        if not isinstance(loaded_scores, dict):
            return defaults

        for mode, categories in defaults.items():
            if mode not in loaded_scores or not isinstance(loaded_scores[mode], dict):
                loaded_scores[mode] = {}
            for category in categories:
                if category not in loaded_scores[mode] or not isinstance(loaded_scores[mode][category], list):
                    loaded_scores[mode][category] = []

        return loaded_scores

    def create_default_scores(self):
        # Structure: { key_mode: { "1_lap": [], "3_laps": [], "5_laps": [], "best_lap": [] } }
        # Modes: rally, brands_hatch, drift, stunt
        defaults = {}
        for mode in ['rally', 'brands_hatch', 'drift', 'stunt']:
            defaults[mode] = {
                "1_lap": [],
                "3_laps": [],
                "5_laps": [],
                "best_lap": [] # Single best lap record
            }
        return defaults

    def save_scores(self):
        try:
            with open(LEADERBOARD_FILE, 'w') as f:
                json.dump(self.scores, f, indent=4)
        except IOError:
            print("Failed to save leaderboard")

    def add_score(self, mode, category, name, time):
        """
        category: "1_lap", "3_laps", "5_laps", "best_lap"
        """
        if mode not in self.scores:
            self.scores[mode] = {}
            
        if category not in self.scores[mode]:
            self.scores[mode][category] = []
            
        entry = {"name": name, "time": time}
        self.scores[mode][category].append(entry)
        
        # Sort by time (ascending)
        self.scores[mode][category].sort(key=lambda x: x['time'])
        
        # Keep top 10
        self.scores[mode][category] = self.scores[mode][category][:10]
        self.save_scores()

    def get_top_scores(self, mode, category):
        return self.scores.get(mode, {}).get(category, [])

    def is_high_score(self, mode, category, time):
        scores = self.get_top_scores(mode, category)
        if len(scores) < 10:
            return True
        return time < scores[-1]['time']
