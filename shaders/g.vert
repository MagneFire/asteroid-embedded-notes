attribute vec4 pos;
attribute vec2 texcoord;
attribute vec4 color;
uniform vec4 to_px;
varying vec4 v_color;
varying vec2 v_uv;
varying vec2 v_px;
void main() {
	v_color = color;
	v_uv = texcoord;
	v_px = pos.xy * to_px.xy + to_px.zw;
	gl_Position = pos;
}
