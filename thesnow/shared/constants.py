SEEDS = ("Mandarins", "Pumpkins", "Cabbage", "Pineapples", "Cannabis", "Mushrooms")
SEED_EMOJI = {
    "Mandarins": "🍊",
    "Pumpkins": "🎃",
    "Cabbage": "🥬",
    "Pineapples": "🍍",
    "Cannabis": "🌿",
    "Mushrooms": "🍄",
}
LOCATIONS = ("Plantation", "Cow Shed")
STORAGE_PLACES = ("Warehouse", "Vehicle")
COW_HOURS = (1, 4, 7, 10, 13, 16, 19, 22)

BLUE = 0x5865F2
GREEN = 0x2ECC71
RED = 0xE74C3C
GOLD = 0xF1C40F
PURPLE = 0x9B59B6

DEFAULT_ARMORY = (
    ("Gun", 0, 0),
    ("Armor-Piercing Pistol", 0, 0),
    ("Stun Gun", 0, 0),
    ("PDW Submachine Gun", 0, 0),
    ("Shotgun", 0, 0),
    ("Heavy Shotgun", 0, 0),
    ("Assault Rifle", 0, 0),
    ("Bullpup Assault Rifle", 0, 0),
    ("Sniper Rifle", 0, 0),
    ("Light Machine Gun", 0, 0),
    ("Police Baton", 0, 0),
    ("Balaclava", 0, 0),
    ("Assault Rifle Carbine", 0, 0),
    ("AUG Assault Rifle", 0, 0),
    ("Vest", 0, 0),
)

MAX_AMOUNT = 1_000_000_000_000
MAX_EMBED_FIELD_CHARS = 1024
MAX_EMBED_DESC_CHARS = 4096
MAX_EMBED_FIELDS = 25
MAX_PROOF_BYTES = 8 * 1024 * 1024
ALLOWED_IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp", ".gif")
ALLOWED_IMAGE_HOSTS = frozenset({"cdn.discordapp.com", "media.discordapp.net"})
