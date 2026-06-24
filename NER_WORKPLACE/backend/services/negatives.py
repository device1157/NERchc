from __future__ import annotations

import random


def sample_negative_types(all_tags: list[str], present_tags: set[str], ratio: float = 2.0, seed: int = 17) -> list[str]:
    missing = [tag for tag in all_tags if tag not in present_tags]
    if not missing:
        return []
    rng = random.Random(seed)
    max_count = max(1, round(len(present_tags) / max(ratio, 0.1)))
    return rng.sample(missing, min(max_count, len(missing)))

