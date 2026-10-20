"""Align Paraformer text with timestamps without inventing word boundaries."""
import math
import re
import unicodedata


def paraformer_chunks(text, timestamps):
    """Accept character or English-word timing; reject unmatched output."""
    chars = [c for c in text if not c.isspace()
             and not unicodedata.category(c).startswith(('P', 'Z'))]
    # FunASR merges English subwords/abbreviations and their timestamps.
    # Keep those words intact instead of consuming one interval per letter.
    words = []
    for match in re.finditer(r"[A-Za-z]+(?:'[A-Za-z]+)*|[^A-Za-z]", text):
        token = match.group()
        if len(token) > 1 or token in chars:
            words.append(token)
    if len(chars) == len(timestamps):
        tokens = chars
    elif len(words) == len(timestamps):
        tokens = words
    else:
        raise ValueError(
            'Paraformer text/timestamp mismatch: '
            f'{len(chars)} characters, {len(words)} word units, '
            f'{len(timestamps)} timestamps; refusing truncated or shifted chunks'
        )
    chunks = []
    for token, ts in zip(tokens, timestamps):
        if (not isinstance(ts, (list, tuple)) or len(ts) != 2
                or any(isinstance(v, bool) or not isinstance(v, (int, float))
                       or not math.isfinite(v) for v in ts)
                or ts[0] < 0 or ts[1] < ts[0]):
            raise ValueError(f'Invalid Paraformer timestamp: {ts!r}')
        chunks.append({'text': token, 'timestamp': [round(ts[0] / 1000, 3),
                                                   round(ts[1] / 1000, 3)]})
    return chunks
