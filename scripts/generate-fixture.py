"""Generate an original CC0 two-second 440 Hz MP3; requires libmp3lame."""
from pathlib import Path
import ctypes as C
from ctypes.util import find_library
import math

library = find_library("mp3lame")
if library is None:
    raise SystemExit("libmp3lame is required only to regenerate the test fixture")
lame = C.CDLL(library)
lame.lame_init.restype = C.c_void_p
for name in ["lame_set_in_samplerate", "lame_set_num_channels", "lame_set_brate", "lame_set_mode"]:
    getattr(lame, name).argtypes = [C.c_void_p, C.c_int]
for name in ["lame_init_params", "lame_close"]:
    getattr(lame, name).argtypes = [C.c_void_p]
lame.lame_encode_buffer.argtypes = [C.c_void_p, C.POINTER(C.c_short), C.POINTER(C.c_short), C.c_int, C.POINTER(C.c_ubyte), C.c_int]
lame.lame_encode_flush.argtypes = [C.c_void_p, C.POINTER(C.c_ubyte), C.c_int]
encoder = lame.lame_init()
if not encoder:
    raise SystemExit("Could not initialize MP3 encoder")
try:
    for name, value in [("lame_set_in_samplerate", 44100), ("lame_set_num_channels", 1), ("lame_set_brate", 128), ("lame_set_mode", 3)]:
        if getattr(lame, name)(encoder, value) < 0:
            raise RuntimeError(f"Encoder rejected {name}")
    if lame.lame_init_params(encoder) < 0:
        raise RuntimeError("Encoder configuration failed")
    count = 2 * 44100
    samples = (C.c_short * count)(*(int(4000 * math.sin(2 * math.pi * 440 * i / 44100)) for i in range(count)))
    output = (C.c_ubyte * (count * 2 + 7200))()
    size = lame.lame_encode_buffer(encoder, samples, samples, count, output, len(output))
    if size < 0:
        raise RuntimeError("Encoding failed")
    encoded = bytes(output[:size])
    size = lame.lame_encode_flush(encoder, output, len(output))
    if size < 0:
        raise RuntimeError("Encoder flush failed")
    target = Path(__file__).resolve().parents[1] / "tests/fixtures/tone-440hz.mp3"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(encoded + bytes(output[:size]))
    print(f"Generated {target.name}: {target.stat().st_size} bytes")
finally:
    lame.lame_close(encoder)
