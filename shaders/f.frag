precision mediump float;
uniform sampler2D tex;
varying vec4 v_color;
varying vec2 v_uv;
void main() {
	gl_FragColor = texture2D(tex, v_uv) * v_color;
}
