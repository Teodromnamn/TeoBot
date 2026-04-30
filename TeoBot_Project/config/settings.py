import time

# ===== Window / profile settings =====
PROFILE_FILE = "profiles.json"
WINDOW_NAME = "Tibia - {profile}"  # używane w formatowaniu
#WINDOW_NAME = "Mortus Client"  # używane w formatowaniu
#WINDOW_NAME = "Altaron (beta 0.18.10)"
#WINDOW_NAME = "Eternal Odyssey - {profile}"  # używane w formatowaniu

# ===== HP/MP rects =====
HP_RECT = (196, 36, 680, 1)
MANA_RECT = (884, 36, 680, 1)
HP_RECT_SIO = (35, 88, 129, 1)
MANA_RECT_SIO = (35, 94, 129, 1)

# ===== HP/MP rects MORTUS =====
#HP_RECT = (196, 37, 678, 1)
#MANA_RECT = (885, 37, 679, 1)
#HP_RECT_SIO = (35, 88, 129, 1)
#MANA_RECT_SIO = (35, 94, 129, 1)

# ===== HP/MP rects ETERNAL=====
#HP_RECT = (214, 37, 667, 1)
#MANA_RECT = (1054, 37, 667, 1)
#HP_RECT_SIO = (35, 88, 129, 1)
#MANA_RECT_SIO = (35, 94, 129, 1)

# ===== HP/MP rects ALTARON=====
#HP_RECT = (461, 45, 290, 1)
#MANA_RECT = (800, 46, 289, 1)
#HP_RECT_SIO = (35, 88, 129, 1)
#MANA_RECT_SIO = (35, 94, 129, 1)

# ===== GCD =====
Heal_GCD = 1.1
Support_GCD = 2.1
Offensive_GCD = 2.1
Potion_GCD = 1.1

# ===== App license time =====
end_time = time.mktime((2027, 1, 1, 0, 0, 0, 0, 0, -1))
