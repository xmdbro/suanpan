import sys

# How long a key lives without being touched (6 months is a reasonable amount, I believe)
BASE_TTL_SECONDS: int = 60 * 60 * 24 * 7 * 4 * 6

# Namespace / key length constraints
MIN_LENGTH: int = 3
MAX_LENGTH: int = 64

# The largest safe integer value we will store
MAX_INT: int = sys.maxsize
