precision highp float;
uniform sampler2D tex;
uniform vec4 round_rect;
uniform vec4 round_r;
varying vec4 v_color;
varying vec2 v_uv;
varying vec2 v_px;
void main() {
	vec2 d = max(abs(v_px - round_rect.xy) - round_rect.zw, vec2(0.0));
	float cover = clamp(round_r.x - length(d) + 0.5, 0.0, 1.0);
	gl_FragColor = texture2D(tex, v_uv) * v_color * cover;
}
