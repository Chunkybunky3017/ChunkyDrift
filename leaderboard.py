import json
import os
import shutil

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LEADERBOARD_FILE = os.path.join(BASE_DIR, "leaderboard.json")
LEADERBOARD_TMP_FILE = f"{LEADERBOARD_FILE}.tmp"
LEADERBOARD_BACKUP_FILE = f"{LEADERBOARD_FILE}.bak"

class Leaderboard:
    def __init__(self):
        self.scores = self.load_scores()

    def _read_json_file(self, path):
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def load_scores(self):
        if not os.path.exists(LEADERBOARD_FILE):
            defaults = self.create_default_scores()
            self.scores = defaults
            self.save_scores()
            return defaults

        try:
            loaded_scores = self._read_json_file(LEADERBOARD_FILE)
            return self.ensure_score_schema(loaded_scores)
        except (json.JSONDecodeError, IOError):
            # Try recovering from the last known good backup.
            if os.path.exists(LEADERBOARD_BACKUP_FILE):
                try:
                    loaded_scores = self._read_json_file(LEADERBOARD_BACKUP_FILE)
                    recovered_scores = self.ensure_score_schema(loaded_scores)
                    self.scores = recovered_scores
                    self.save_scores()
                    return recovered_scores
                except (json.JSONDecodeError, IOError):
                    pass

            defaults = self.create_default_scores()
            self.scores = defaults
            self.save_scores()
            return defaults

    def ensure_score_schema(self, loaded_scores):
        defaults = self.create_default_scores()

        if not isinstance(loaded_scores, dict):
            return defaults

        # Merge legacy aliases into canonical mode keys.
        mode_aliases = {
            'brands hatch': 'brands_hatch',
            'brandshatch': 'brands_hatch',
            'brands-hatch': 'brands_hatch'
        }
        for legacy_mode, canonical_mode in mode_aliases.items():
            if legacy_mode in loaded_scores:
                if canonical_mode not in loaded_scores or not isinstance(loaded_scores[canonical_mode], dict):
                    loaded_scores[canonical_mode] = {}

                legacy_data = loaded_scores.get(legacy_mode, {})
                if isinstance(legacy_data, dict):
                    for category, entries in legacy_data.items():
                        if category not in loaded_scores[canonical_mode] or not isinstance(loaded_scores[canonical_mode][category], list):
                            loaded_scores[canonical_mode][category] = []
                        if isinstance(entries, list):
                            loaded_scores[canonical_mode][category].extend(entries)

                del loaded_scores[legacy_mode]

        for mode, categories in defaults.items():
            if mode not in loaded_scores or not isinstance(loaded_scores[mode], dict):
                loaded_scores[mode] = {}
            for category in categories:
                if category not in loaded_scores[mode] or not isinstance(loaded_scores[mode][category], list):
                    loaded_scores[mode][category] = []

                # Ensure all entries are valid and sorted, then keep top 10.
                valid_entries = [
                    entry for entry in loaded_scores[mode][category]
                    if isinstance(entry, dict) and 'name' in entry and 'time' in entry
                ]
                valid_entries.sort(key=lambda x: x['time'])
                loaded_scores[mode][category] = valid_entries[:10]

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
            os.makedirs(os.path.dirname(LEADERBOARD_FILE), exist_ok=True)

            with open(LEADERBOARD_TMP_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.scores, f, indent=4)
                f.flush()
                os.fsync(f.fileno())

            if os.path.exists(LEADERBOARD_FILE):
                shutil.copyfile(LEADERBOARD_FILE, LEADERBOARD_BACKUP_FILE)

            os.replace(LEADERBOARD_TMP_FILE, LEADERBOARD_FILE)
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
