pragma Singleton
// Markdown.qml — разбор ответа Нейры на блоки (абзац / заголовок / списки / код) и инлайн-разметка.
import QtQuick

QtObject {
    function escHtml(s) {
        return s.replace(/&/g, "&amp;").replace(/</g, "&lt;")
                .replace(/>/g, "&gt;").replace(/"/g, "&quot;")
    }

    function mdInline(raw) {
        var s = escHtml(raw)
        // адреса прячем в метки \u0001N\u0001 (чтобы _ и * внутри не ломали разметку); возвращаем в конце
        var urls = []
        function tok(u) { urls.push(u); return "\u0001" + (urls.length - 1) + "\u0001" }
        s = s.replace(/\[([^\]]+)\]\(([^)]+)\)/g, function (m, t, u) { return "[" + t + "](" + tok(u) + ")" })
        // голый адрес https://… → ссылка (знаки препинания в конце в ссылку не входят)
        s = s.replace(/https?:\/\/[^\s<>\u0001]+/g, function (m) {
            var tail = ""
            var t = m.match(/(?:&gt;|&lt;|&quot;|[.,;:!?)»\]])+$/)
            if (t) { tail = t[0]; m = m.slice(0, m.length - tail.length) }
            if (/^https?:\/\/$/.test(m)) return m + tail
            return '<a href="' + tok(m) + '" style="color:#B0A0E6;">' + tok(m) + "</a>" + tail
        })
        s = s.replace(/`([^`]+)`/g,
            '<span style="font-family:\'Cascadia Code\'; color:#D9CFFA; background-color:#172150;">$1</span>')
        s = s.replace(/\*\*([^*]+)\*\*/g, "<b>$1</b>")
        s = s.replace(/__([^_]+)__/g, "<b>$1</b>")
        s = s.replace(/(^|[^*])[*]([^*]+)[*]/g, "$1<i>$2</i>")
        s = s.replace(/(^|[^_])[_]([^_]+)[_]/g, "$1<i>$2</i>")
        s = s.replace(/~~([^~]+)~~/g, "<s>$1</s>")
        s = s.replace(/\[([^\]]+)\]\(([^)]+)\)/g,
            '<a href="$2" style="color:#B0A0E6;">$1</a>')
        s = s.replace(/\u0001(\d+)\u0001/g, function (m, n) { return urls[parseInt(n)] })
        return s
    }

    function parseBlocks(md) {
        var lines = String(md).split("\n")
        var out = []
        var i = 0
        while (i < lines.length) {
            var line = lines[i]
            if (/^```/.test(line)) {
                var buf = []
                ++i
                while (i < lines.length && !/^```/.test(lines[i])) { buf.push(lines[i]); ++i }
                ++i
                if (buf.length) out.push({ kind: "code", text: buf.join("\n") })
                continue
            }
            var h = line.match(/^(#{1,4})\s+(.*)$/)
            if (h) { out.push({ kind: "h", level: h[1].length, text: h[2] }); ++i; continue }
            if (/^\s*[-*+]\s+/.test(line)) {
                var items = []
                while (i < lines.length && /^\s*[-*+]\s+/.test(lines[i])) {
                    items.push(lines[i].replace(/^\s*[-*+]\s+/, ""))
                    ++i
                }
                out.push({ kind: "ul", items: items })
                continue
            }
            if (/^\s*\d+\.\s+/.test(line)) {
                var oitems = []
                while (i < lines.length && /^\s*\d+\.\s+/.test(lines[i])) {
                    oitems.push(lines[i].replace(/^\s*\d+\.\s+/, ""))
                    ++i
                }
                out.push({ kind: "ol", items: oitems })
                continue
            }
            if (!line.trim()) { ++i; continue }
            out.push({ kind: "p", text: line })
            ++i
        }
        return out
    }
}
