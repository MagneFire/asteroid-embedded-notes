attribute vec4 pos;
attribute vec2 texcoord;
attribute vec4 color;
varying vec4 v_color;
varying vec2 v_uv;
void main() {
	v_color = color;
	v_uv = texcoord;
	gl_Position = pos;
}
