// md_converter_test.js — автономный юнит-тест конвертера Markdown->HTML
// из D:\AI\neira-tools\qt_neira\qml\Main.qml.
//
// Запуск:  node D:\AI\neira-tools\qt_neira\tests\md_converter_test.js
// Выход:   PASS/FAIL по каждому кейсу; код возврата 0 при всех PASS.

// ---------- точная копия функций из Main.qml ----------
function escHtml(s) {
    return s.replace(/&/g, "&amp;").replace(/</g, "&lt;")
            .replace(/>/g, "&gt;").replace(/"/g, "&quot;")
}

function mdInline(raw) {
    var s = escHtml(raw)

    s = s.replace(/`([^`]+)`/g,
        '<span style="font-family:\'Consolas\'; color:#7fd0ff; background-color:#161822;">$1</span>')

    s = s.replace(/\*\*([^*]+)\*\*/g, "<b>$1</b>")
    s = s.replace(/__([^_]+)__/g, "<b>$1</b>")

    s = s.replace(/(^|[^*])[*]([^*]+)[*]/g, "$1<i>$2</i>")
    s = s.replace(/(^|[^_])[_]([^_]+)[_]/g, "$1<i>$2</i>")

    s = s.replace(/~~([^~]+)~~/g, "<s>$1</s>")

    s = s.replace(/\[([^\]]+)\]\(([^)]+)\)/g,
        '<a href="$2" style="color:#00e5ff;">$1</a>')

    return s
}

function codeBlockHtml(code) {
    var e = escHtml(code).replace(/\n/g, "<br/>")
    return '<table width="100%" cellspacing="0" cellpadding="0" border="0" '
        + 'style="margin-top:6px; margin-bottom:6px;">'
        + '<tr><td bgcolor="#0d0e15" style="border:1px solid #1A1B26; padding:8px;">'
        + '<pre style="font-family:\'Consolas\'; font-size:13px; color:#dce0ee;">'
        + e + '</pre>'
        + '</td></tr></table>'
}

function mdToHtml(md) {
    var lines = md.split("\n")
    var html = ""
    var i = 0
    var inCode = false
    var codeBuf = []

    while (i < lines.length) {
        var line = lines[i]

        if (/^```/.test(line)) {
            if (!inCode) { inCode = true; codeBuf = [] }
            else { html += codeBlockHtml(codeBuf.join("\n")); inCode = false }
            ++i
            continue
        }
        if (inCode) { codeBuf.push(line); ++i; continue }

        var h = line.match(/^(#{1,4})\s+(.*)$/)
        if (h) {
            var lvl = h[1].length
            var hSize = lvl === 1 ? 19 : lvl === 2 ? 17 : 15
            html += '<p style="font-size:' + hSize + 'px; font-weight:600; '
                + 'margin-top:6px; margin-bottom:4px;">' + mdInline(h[2]) + '</p>'
            ++i
            continue
        }

        if (/^\s*[-*+]\s+/.test(line)) {
            html += '<ul style="margin-top:2px; margin-bottom:2px;">'
            while (i < lines.length && /^\s*[-*+]\s+/.test(lines[i])) {
                html += '<li>' + mdInline(lines[i].replace(/^\s*[-*+]\s+/, "")) + '</li>'
                ++i
            }
            html += '</ul>'
            continue
        }

        if (/^\s*\d+\.\s+/.test(line)) {
            html += '<ol style="margin-top:2px; margin-bottom:2px;">'
            while (i < lines.length && /^\s*\d+\.\s+/.test(lines[i])) {
                html += '<li>' + mdInline(lines[i].replace(/^\s*\d+\.\s+/, "")) + '</li>'
                ++i
            }
            html += '</ol>'
            continue
        }

        if (/^\s*>\s?/.test(line)) {
            html += '<p style="color:#686b7c; margin-left:8px;">'
                + mdInline(line.replace(/^\s*>\s?/, "")) + '</p>'
            ++i
            continue
        }

        if (!line.trim()) { ++i; continue }

        html += '<p style="margin-top:2px; margin-bottom:2px;">' + mdInline(line) + '</p>'
        ++i
    }

    if (inCode) html += codeBlockHtml(codeBuf.join("\n"))
    return html
}

// ---------- тестовые кейсы ----------
const cases = [
    { name: "жирный **", in: "привет **мир**", expect: ["<b>мир</b>"] },
    { name: "жирный __", in: "привет __мир__", expect: ["<b>мир</b>"] },
    { name: "курсив *", in: "привет *мир*", expect: ["<i>мир</i>"] },
    { name: "курсив _", in: "привет _мир_", expect: ["<i>мир</i>"] },
    { name: "bold+italic не конфликтуют", in: "**a** и *b*", expect: ["<b>a</b>", "<i>b</i>"] },
    { name: "зачёркнутый", in: "~~нет~~", expect: ["<s>нет</s>"] },
    { name: "инлайн-код: Consolas+фон", in: "`var x`", expect: ["Consolas", "#161822", "var x"] },
    { name: "заголовок h1", in: "# Привет", expect: ["font-size:19px", "Привет"] },
    { name: "заголовок h2", in: "## Привет", expect: ["font-size:17px"] },
    { name: "заголовок h3", in: "### Привет", expect: ["font-size:15px"] },
    { name: "маркированный список", in: "- раз\n- два", expect: ["<ul", "<li>раз</li>", "<li>два</li>"] },
    { name: "нумерованный список", in: "1. раз\n2. два", expect: ["<ol", "<li>раз</li>", "<li>два</li>"] },
    { name: "цитата", in: "> важно", expect: ["color:#686b7c", "важно"] },
    { name: "код-блок: плашка+Consolas", in: "```cpp\nint x = 1;\n```",
      expect: ["<table width=\"100%\"", "bgcolor=\"#0d0e15\"", "Consolas", "int x = 1;"] },
    { name: "HTML/XML-экранирование", in: "a < b & c \"q\"",
      expect: ["a &lt; b &amp; c", "&quot;q&quot;"] },
    { name: "незакрытый код-блок (стриминг)", in: "```cpp\nint x = 1;",
      expect: ["bgcolor=\"#0d0e15\"", "int x = 1;"] },
    { name: "ссылка", in: "[сайт](https://example.com)",
      expect: ['<a href="https://example.com" style="color:#00e5ff;">сайт</a>'] },
    { name: "абзацы через пустую строку", in: "a\n\nb",
      expect: ["<p style=\"margin-top:2px; margin-bottom:2px;\">a</p>",
               "<p style=\"margin-top:2px; margin-bottom:2px;\">b</p>"] },
    { name: "пустой ввод", in: "", expect: [""] },
];

let failed = 0;
for (const c of cases) {
    const out = mdToHtml(c.in);
    const missing = c.expect.filter(e => !out.includes(e));
    if (missing.length === 0) {
        console.log("PASS  " + c.name);
    } else {
        failed++;
        console.log("FAIL  " + c.name);
        console.log("      input:    " + JSON.stringify(c.in));
        console.log("      missing:   " + JSON.stringify(missing));
        console.log("      actual:    " + out);
    }
}

console.log("-----");
console.log(failed === 0 ? "ALL " + cases.length + " TESTS PASSED" : failed + " OF " + cases.length + " TESTS FAILED");
process.exit(failed === 0 ? 0 : 1);
