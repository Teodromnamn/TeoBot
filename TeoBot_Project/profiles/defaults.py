DEFAULT_OFFENSIVE = [
    {"name": "exori amp kor", "key": "F5", "priority": 1, "mana_cost": 10.0, "cd": 14.0, "type": "spell"},
    {"name": "exori gran ico", "key": "F6", "priority": 2, "mana_cost": 15.0, "cd": 30.0, "type": "spell"},
    {"name": "exori gran", "key": "F7", "priority": 3, "mana_cost": 15.0, "cd": 6.0, "type": "spell"},
    {"name": "exori min", "key": "F8", "priority": 4, "mana_cost": 10.0, "cd": 6.0, "type": "spell"},
    {"name": "exori", "key": "F9", "priority": 5, "mana_cost": 5.0, "cd": 4.0, "type": "spell"},
]

DEFAULT_HEALING = [
    {"name": "exura gran ico", "key": "F1", "hp%": 15.0, "mana_cost": 0.0, "cd": 600.0},
    {"name": "exura med ico", "key": "F2", "hp%": 95.0, "mana_cost": 0.0, "cd": 1.0},
]

DEFAULT_POTIONS = [
    {"type": "mana", "key": "F3", "%": 90.0, "cd": 1.0},
    {"type": "hp", "key": "F4", "%": 80.0, "cd": 1.0},
]

DEFAULT_SUPPORT = [
    {"name": "Auto Targeting", "key": "space", "cd": 10.0, "enabled": True},
    {"name": "utito tempo", "key": "F10", "cd": 10.0, "enabled": False},
]
