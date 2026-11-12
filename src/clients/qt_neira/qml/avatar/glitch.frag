#version 440
// «сбой голограммы» (задача 13): сдвиг горизонтальных полос, расхождение красного/голубого канала, мерцание, линии развёртки.
layout(location = 0) in vec2 qt_TexCoord0;
layout(location = 0) out vec4 fragColor;
layout(std140, binding = 0) uniform buf {
    mat4 qt_Matrix;
    float qt_Opacity;
    float amt;        // 0..1 — сила вспышки
    float time;       // секунды (шаг ~30 кадров/с)
    float splitUv;    // расхождение каналов, доля ширины (2..6 px / ширина на экране)
    float bandShift;  // максимальный сдвиг полосы, доля ширины
    float lineAmt;    // сила линий развёртки 0..1
    float rows;       // число строк развёртки на высоту
};
layout(binding = 1) uniform sampler2D src;

float hash(vec2 p) { return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }

void main() {
    vec2 uv = qt_TexCoord0;
    float tick = floor(time * 24.0);
    // полосы: высота 1/40..1/14, часть полос сдвинута влево/вправо
    float band = floor(uv.y * 28.0);
    float h = hash(vec2(band, tick));
    float shift = (h > 0.72 ? (hash(vec2(tick, band)) - 0.5) * 2.0 : 0.0) * bandShift * amt;
    vec2 p = vec2(uv.x + shift, uv.y);
    vec4 sr = texture(src, p + vec2(splitUv * amt, 0.0));
    vec4 sg = texture(src, p);
    vec4 sb = texture(src, p - vec2(splitUv * amt, 0.0));
    vec4 c = vec4(sr.r, sg.g, sb.b, max(sr.a, max(sg.a, sb.a)));
    // мерцание прозрачности
    float fl = 1.0 - amt * (0.35 * step(0.5, hash(vec2(tick, 3.0))) + 0.15 * hash(vec2(tick, 7.0)));
    // линии развёртки
    float ln = 1.0 - lineAmt * amt * 0.45 * step(0.5, fract(uv.y * rows));
    c *= fl * ln;
    fragColor = c * qt_Opacity;
}
