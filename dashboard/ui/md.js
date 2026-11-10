// markdown を HTML にしたあとの後始末(トップページの会話・ノートで共通)。
//
// fixCjkBold: 「**「かっこ」**です」「**太字（かっこ）**です」のように、** のすぐ内側が記号で外側が文字のとき、
// markdown の決まりでは太字にならず ** がそのまま残る(日本語でよく起きる)。残った **…** を太字に直す。
// コード(<code>・<pre>)の中は触らない。
window.fixCjkBold = function (html) {
  if (!html || html.indexOf("**") < 0) return html;
  const box = document.createElement("template");
  box.innerHTML = html;
  const walker = document.createTreeWalker(box.content, NodeFilter.SHOW_TEXT);
  const targets = [];
  for (let n = walker.nextNode(); n; n = walker.nextNode()) {
    if (n.nodeValue.indexOf("**") < 0) continue;
    if (n.parentElement && n.parentElement.closest("code, pre")) continue;
    targets.push(n);
  }
  const re = /\*\*([^*\n]+?)\*\*/g;
  for (const n of targets) {
    const text = n.nodeValue;
    re.lastIndex = 0;
    let last = 0, m, frag = null;
    while ((m = re.exec(text))) {
      frag = frag || document.createDocumentFragment();
      if (m.index > last) frag.appendChild(document.createTextNode(text.slice(last, m.index)));
      const strong = document.createElement("strong");
      strong.textContent = m[1];
      frag.appendChild(strong);
      last = m.index + m[0].length;
    }
    if (!frag) continue;
    if (last < text.length) frag.appendChild(document.createTextNode(text.slice(last)));
    n.parentNode.replaceChild(frag, n);
  }
  return box.innerHTML;
};
