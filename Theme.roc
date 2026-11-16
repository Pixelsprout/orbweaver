import linalg.Vec3
import pf.Vocabulary exposing [Rgb]
import pf.Environment
import pf.Light
import Level

# The look of one level. Each Theme is a pack of its face mesh and its sky, so
# the next level's Theme loads while the current one still draws.
Theme := [].{
	Theme : { pack : Str, face : Str, sky : Str, assets : List(Str), sun : Vec3.Vec3, lights : List(Vocabulary.Light), horizon : Rgb }

	# Levels count from 1. A number past the last level gets the last Theme.
	of_level : U64 -> Theme.Theme
	of_level = |number| by_level.get(number - 1) ?? gloam

	count : U64
	count = by_level.len()

	# sky is the id that the Theme's sky loaded as.
	environment : Theme.Theme, U32, [Fog, NoFog] -> Vocabulary.Environment
	environment = |t, sky, fog| {
		amount = match fog {
			Fog => fog_amount
			NoFog => 0.0
		}
		{ ..Environment.default, sky, tone_map: Neutral, fog: { color: t.horizon, start: fog_start, end: fog_end, amount, sky: 0.0 } }
	}
}

# All three levels share one Theme.
by_level : List(Theme.Theme)
by_level = [gloam, gloam, gloam]

themes : List(Theme.Theme)
themes = [gloam]

# A dusk after sunset. A cool moon low in the -x sky lights the blocks. The
# fill is the warm afterglow from the other side, and the ambient takes the
# blue of the upper sky.
gloam : Theme.Theme
gloam = theme(
	"gloam",
	{
		sun: { x: 6.0 / 7.0, y: -3.0 / 7.0, z: -2.0 / 7.0 },
		sun_colour: { r: 1.2, g: 1.28, b: 1.5 },
		fill: { r: 0.34, g: 0.2, b: 0.24 },
		ambient: { r: 0.17, g: 0.16, b: 0.26 },
		horizon: { r: 0.03, g: 0.03, b: 0.08 },
	},
)

# No two axes of a sun's dir share a size, so each face direction gets its own shade.
# The BRDF divides diffuse light by pi, so a sun of 1.6 lights a white surface facing it to 1.6.
# The fill lights the faces turned away from the sun. The ambient takes the sky's hue.
# make_skies.py paints the moon where this light comes from.
# The sky does not fog, so the fog takes the horizon colour: the linear mean of
# the sky's side faces 2 degrees either side of the horizon.
theme : Str, { sun : Vec3.Vec3, sun_colour : Rgb, fill : Rgb, ambient : Rgb, horizon : Rgb } -> Theme.Theme
theme = |pack, light| {
	face = "${pack}_face"
	sky = "sky/${pack}"
	{
		pack,
		face,
		sky,
		assets: [face, sky],
		sun: light.sun,
		lights: [
			Light.ambient(light.ambient),
			Light.sun(light.sun, times_pi(light.sun_colour)),
			Light.directional(Vec3.neg(light.sun), times_pi(light.fill)),
		],
		horizon: light.horizon,
	}
}

# The fog distances are in cells from the eye.
fog_start : F32
fog_start = 2.0

fog_end : F32
fog_end = 12.0

fog_amount : F32
fog_amount = 0.8

times_pi : Rgb -> Rgb
times_pi = |c| { r: c.r * pi, g: c.g * pi, b: c.b * pi }

pi : F32
pi = 3.14159265

# The sum of all lights on a face with this normal, over the three channels.
shade : List(Vocabulary.Light), Vec3.Vec3 -> F32
shade = |lights, normal| lights.fold(
	0.0,
	|sum, light| match light {
		Ambient(c) => sum + c.r + c.g + c.b
		Directional({ dir, color, shadow: _ }) => {
			facing = Vec3.dot(normal, Vec3.neg(dir))
			if facing > 0.0 {
				sum + (color.r + color.g + color.b) * facing
			} else {
				sum
			}
		}
		Point(_) => sum
	},
)

normals : List(Vec3.Vec3)
normals = [{ x: 1.0, y: 0.0, z: 0.0 }, { x: -1.0, y: 0.0, z: 0.0 }, { x: 0.0, y: 1.0, z: 0.0 }, { x: 0.0, y: -1.0, z: 0.0 }, { x: 0.0, y: 0.0, z: 1.0 }, { x: 0.0, y: 0.0, z: -1.0 }]

expect Theme.count == Level.count
expect themes.map(|t| t.pack) == ["gloam"]
expect [1, 2, 3, 4].map(|n| Theme.of_level(n).pack) == ["gloam", "gloam", "gloam", "gloam"]

expect themes.all(
	|t| {
		shades = normals.map(|n| shade(t.lights, n))
		shades.all(|a| shades.keep_if(|b| (a - b).abs() < 0.06).len() == 1)
	},
)

expect themes.all(|a| themes.keep_if(|b| b.sun == a.sun).len() == 1)
expect themes.all(|t| t.assets == [t.face, t.sky])
expect themes.map(|t| t.assets) == [["gloam_face", "sky/gloam"]]
expect {
	env = Theme.environment(gloam, 3, Fog)
	env.sky == 3 and env.fog.color == gloam.horizon and env.fog.amount > 0.0 and env.fog.start < env.fog.end and env.tone_map == Neutral and env.bloom == Environment.default.bloom
}
expect Theme.environment(gloam, 3, NoFog) == { ..Theme.environment(gloam, 3, Fog), fog: { ..Theme.environment(gloam, 3, Fog).fog, amount: 0.0 } }
expect themes.all(|a| themes.keep_if(|b| b.horizon == a.horizon).len() == 1)
