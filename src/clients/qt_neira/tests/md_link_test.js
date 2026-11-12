// Запуск: node tests/md_link_test.js — берёт mdInline прямо из qml/Markdown.qml (голые URL и markdown-ссылки).
const fs = require('fs');
const src = fs.readFileSync(__dirname + '/../qml/Markdown.qml', 'utf8');
const body = src.slice(src.indexOf('function escHtml'), src.indexOf('function parseBlocks'));
const { mdInline } = new Function(body + '; return { mdInline }')();
let bad = 0;
function t(name, inp, must, mustNot) {
  const o = mdInline(inp); const ok = must.every(m => o.includes(m)) && !(mustNot || []).some(m => o.includes(m));
  if (!ok) { bad++; console.log('FAIL', name, '\n  ', o); } else console.log('PASS', name);
}
t('голый URL', 'см. https://example.com/a_b_c?x=1&y=2 ок', ['<a href="https://example.com/a_b_c?x=1&amp;y=2"', '>https://example.com/a_b_c?x=1&amp;y=2</a> ок'], ['<i>']);
t('точка в конце', 'Сайт https://ru.wikipedia.org/wiki/Python.', ['href="https://ru.wikipedia.org/wiki/Python"', '</a>.'] );
t('скобки', '(https://example.com)', ['href="https://example.com"', '</a>)']);
t('md-ссылка не дублируется', '[стр](https://example.com/x_y)', ['<a href="https://example.com/x_y"'], ['<a href="<a']);
t('md + голый', '[a](https://a.ru) и https://b.ru', ['href="https://a.ru" style="color:#B0A0E6;">a</a>', 'href="https://b.ru" style="color:#B0A0E6;">https://b.ru</a>']);
t('без URL', 'просто **текст**', ['<b>текст</b>']);
process.exit(bad ? 1 : 0);
