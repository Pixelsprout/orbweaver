# Paints each Theme's sky: six PNGs in assets/sky/<theme>/. Needs a Python 3
# with numpy, such as the one inside Blender. Run from the repository root:
#   /Applications/Blender.app/Contents/Resources/5.2/python/bin/python3.13 assets/source/make_skies.py
#
# A sky is a function of the view direction, sampled for each texel. The face
# layout is the one engine/sky.odin states: face px holds the directions
# nearest +x, with its top row towards +y and its left column towards +z.
# The script also prints each sky's horizon colour, which Theme.roc uses as
# the fog colour.

import os
import struct
import zlib

import numpy

SKY = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "sky")

# u and v run from -1 at the left and top to 1 at the right and bottom.
FACES = {
    "px": lambda u, v: (1.0, -v, -u),
    "nx": lambda u, v: (-1.0, -v, u),
    "py": lambda u, v: (u, 1.0, v),
    "ny": lambda u, v: (u, -1.0, -v),
    "pz": lambda u, v: (u, -v, 1.0),
    "nz": lambda u, v: (-u, -v, -1.0),
}

# Each face is supersampled SUPERSAMPLE x SUPERSAMPLE times, so the moon and the hills have smooth edges.
SUPERSAMPLE = 3


def write_png(path, srgb):
    rows = numpy.round(numpy.clip(srgb, 0.0, 255.0)).astype(numpy.uint8)
    raw = b"".join(b"\x00" + row.tobytes() for row in rows)

    def chunk(kind, data):
        body = kind + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))

    with open(path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n")
        f.write(chunk(b"IHDR", struct.pack(">IIBBBBB", rows.shape[1], rows.shape[0], 8, 2, 0, 0, 0)))
        f.write(chunk(b"IDAT", zlib.compress(raw, 9)))
        f.write(chunk(b"IEND", b""))


def to_linear(c):
    return numpy.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def smoothstep(edge0, edge1, x):
    t = numpy.clip((x - edge0) / (edge1 - edge0), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


# Value noise from a fixed lattice, so a rerun paints the same sky.
LATTICE = numpy.random.default_rng(2611).random((256, 256))


def value_noise(px, py):
    ix = numpy.floor(px)
    iy = numpy.floor(py)
    fx = px - ix
    fy = py - iy
    ix = ix.astype(numpy.int64) & 255
    iy = iy.astype(numpy.int64) & 255
    sx = fx * fx * (3.0 - 2.0 * fx)
    sy = fy * fy * (3.0 - 2.0 * fy)
    a = LATTICE[iy, ix]
    b = LATTICE[iy, (ix + 1) & 255]
    c = LATTICE[(iy + 1) & 255, ix]
    e = LATTICE[(iy + 1) & 255, (ix + 1) & 255]
    return (a + (b - a) * sx) + ((c + (e - c) * sx) - (a + (b - a) * sx)) * sy


def fbm(px, py, octaves):
    total = numpy.zeros_like(px)
    amplitude = 0.5
    for k in range(octaves):
        total += amplitude * value_noise(px * 2.0**k + 11.0 * k, py * 2.0**k + 23.0 * k)
        amplitude *= 0.5
    return total / (1.0 - 0.5**octaves)


def ramp(keys, x):
    xs = [k[0] for k in keys]
    return numpy.stack([numpy.interp(x, xs, [k[1][c] for k in keys]) for c in range(3)], axis=-1)


# Mixes base towards colour by amount, in sRGB.
def mix(base, colour, amount):
    return base + (numpy.asarray(colour, dtype=numpy.float64) - base) * amount[..., None]


# The gloam sky: a dusk after sunset. A deep blue zenith with stars, a rose
# afterglow low in the +x quarter, a pale moon and two ridges of hills.
# The sRGB colours by elevation in degrees:
GLOAM_SKY = [
    (0.0, (196, 132, 150)),
    (5.0, (150, 112, 158)),
    (14.0, (96, 84, 150)),
    (32.0, (46, 48, 112)),
    (90.0, (14, 18, 52)),
]
GLOAM_AFTERGLOW = (246, 160, 120)
# Theme.roc's gloam sun dir, reversed: where the moon light comes from.
GLOAM_MOON = numpy.array((-6.0, 3.0, 2.0)) / 7.0
GLOAM_MOON_ACROSS = numpy.cross(GLOAM_MOON, (0.0, 1.0, 0.0)) / numpy.linalg.norm(numpy.cross(GLOAM_MOON, (0.0, 1.0, 0.0)))
GLOAM_MOON_UP = numpy.cross(GLOAM_MOON_ACROSS, GLOAM_MOON)
GLOAM_MOON_COLOUR = (240, 242, 226)
GLOAM_MOON_SHADE = (196, 204, 200)
GLOAM_MOON_RADIUS = 3.4
GLOAM_HALO = (170, 178, 210)
GLOAM_STAR = (236, 238, 255)
GLOAM_CLOUD = (182, 150, 186)
GLOAM_FAR_HILLS = (78, 72, 118)
GLOAM_NEAR_HILLS = (30, 36, 66)
GLOAM_GROUND = (16, 20, 40)
GLOAM_SIDE = 512


def paint_gloam(d):
    x, y, z = d[..., 0], d[..., 1], d[..., 2]
    elevation = numpy.degrees(numpy.arcsin(numpy.clip(y, -1.0, 1.0)))
    azimuth = numpy.degrees(numpy.arctan2(z, x))
    sky = ramp(GLOAM_SKY, numpy.maximum(elevation, 0.0))

    flat = numpy.hypot(x, z) + 1e-9
    toward_glow = numpy.clip(x / flat, 0.0, 1.0)
    sky = mix(sky, GLOAM_AFTERGLOW, 0.75 * toward_glow**3 * numpy.exp(-numpy.maximum(elevation, 0.0) / 7.0))

    # Thin cloud bands on a plane above the eye, densest a little above the horizon.
    lift = numpy.maximum(y, 0.02)
    cloud = fbm(x / lift * 1.6, z / lift * 5.0, 5)
    cover = smoothstep(0.55, 0.8, cloud) * smoothstep(2.0, 6.0, elevation) * (1.0 - smoothstep(18.0, 40.0, elevation))
    sky = mix(sky, GLOAM_CLOUD, 0.5 * cover)

    # At most one star in each cell of a grid that is even in degrees across the sky.
    cell = 1.1
    across = azimuth * numpy.cos(numpy.radians(elevation))
    ix = numpy.floor(across / cell).astype(numpy.int64)
    iy = numpy.floor(elevation / cell).astype(numpy.int64)
    keep = LATTICE[iy & 255, ix & 255]
    ox = LATTICE[(iy + 97) & 255, ix & 255]
    oy = LATTICE[(iy + 41) & 255, (ix + 13) & 255]
    gap = numpy.hypot(across - (ix + 0.2 + 0.6 * ox) * cell, elevation - (iy + 0.2 + 0.6 * oy) * cell)
    star = (keep > 0.9) * smoothstep(0.16, 0.05, gap) * smoothstep(12.0, 30.0, elevation) * (1.0 - cover)
    sky = mix(sky, GLOAM_STAR, numpy.clip(star * (0.4 + 6.0 * (keep - 0.9)), 0.0, 1.0))

    moon_angle = numpy.degrees(numpy.arccos(numpy.clip(d @ GLOAM_MOON, -1.0, 1.0)))
    sky = mix(sky, GLOAM_HALO, 0.45 * numpy.exp(-moon_angle / 7.0))
    moon = smoothstep(GLOAM_MOON_RADIUS + 0.15, GLOAM_MOON_RADIUS - 0.15, moon_angle)
    maria = smoothstep(0.52, 0.72, fbm(d @ GLOAM_MOON_ACROSS * 40.0 + 5.0, d @ GLOAM_MOON_UP * 40.0 + 9.0, 3))
    face = mix(numpy.broadcast_to(numpy.asarray(GLOAM_MOON_COLOUR, dtype=numpy.float64), sky.shape), GLOAM_MOON_SHADE, maria)
    sky = sky + (face - sky) * moon[..., None]

    # The ridges sample noise round a circle, so they join up all the way round.
    turn = numpy.radians(azimuth)
    far = 0.6 + 3.2 * fbm(2.4 * numpy.cos(turn) + 3.0, 2.4 * numpy.sin(turn) + 3.0, 4)
    near = 0.2 + 2.4 * fbm(4.4 * numpy.cos(turn) + 40.0, 4.4 * numpy.sin(turn) + 40.0, 4)
    sky = mix(sky, GLOAM_FAR_HILLS, smoothstep(far + 0.05, far - 0.05, elevation))
    sky = mix(sky, GLOAM_NEAR_HILLS, smoothstep(near + 0.05, near - 0.05, elevation))
    return mix(sky, GLOAM_GROUND, smoothstep(0.0, -8.0, elevation))


SKIES = {"gloam": {"paint": paint_gloam, "side": GLOAM_SIDE}}


def directions(n):
    t = (2.0 * numpy.arange(n) + 1.0) / n - 1.0
    u, v = numpy.meshgrid(t, t)
    for face, direction in FACES.items():
        x, y, z = direction(u, v)
        d = numpy.stack(numpy.broadcast_arrays(x, y, z), axis=-1).astype(numpy.float64)
        d /= numpy.linalg.norm(d, axis=-1, keepdims=True)
        yield face, d


def paint_sky(name, sky):
    side = sky["side"]
    out = os.path.join(SKY, name)
    os.makedirs(out, exist_ok=True)
    for face, d in directions(side * SUPERSAMPLE):
        colour = sky["paint"](d)
        colour = colour.reshape(side, SUPERSAMPLE, side, SUPERSAMPLE, 3).mean(axis=(1, 3))
        write_png(os.path.join(out, face + ".png"), colour)


# The engine does not fog the sky, so the fog takes the horizon colour: the
# linear mean of the side faces 2 degrees either side of the horizon.
def horizon(sky):
    total = numpy.zeros(3)
    count = 0
    for face, d in directions(sky["side"]):
        if face in ("py", "ny"):
            continue
        band = d[numpy.abs(numpy.degrees(numpy.arcsin(d[..., 1]))) <= 2.0]
        linear = to_linear(sky["paint"](band) / 255.0)
        total += linear.sum(axis=0)
        count += linear.shape[0]
    return total / count


for name, sky in SKIES.items():
    paint_sky(name, sky)
    r, g, b = horizon(sky)
    print(f"{name}: horizon {{ r: {r:.2f}, g: {g:.2f}, b: {b:.2f} }}")
