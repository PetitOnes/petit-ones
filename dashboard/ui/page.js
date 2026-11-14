// dashboard/ui/ のページ(ぷちログ・日記)で共通の下ごしらえ。
//
// - ?embed=1 … トップページの会話の場所に埋めて出している(題と「戻る」は出さない)
// - ?accent=rrggbb … 押せるものの色(トップバーの色)
// - ?char=<id> … 開いたときに選ぶぷち
window.PetitPage = (() => {
  const q = new URLSearchParams(location.search);
  const root = document.documentElement;
  if (q.has("embed")) root.classList.add("embed");
  const accent = q.get("accent");
  if (/^[0-9a-fA-F]{6}$/.test(accent || "")) {
    root.style.setProperty("--ui-accent", "#" + accent);
    root.style.setProperty("--ui-accent-ink", "#fff");
    root.style.setProperty("--ui-accent-text", "#" + accent);
    // 薄い色と枠の色も、同じ色から作る(作らないと、ぷちの色の薄紫が残る)
    root.style.setProperty("--ui-accent-soft", `color-mix(in srgb, #${accent} 14%, white)`);
    root.style.setProperty("--ui-accent-line", `color-mix(in srgb, #${accent} 40%, white)`);
  }

  const esc = t => String(t ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");

  // "2026-11-10" → "11/10(火)"。今日・きのうは言葉を足す
  function dayLabel(iso, weekday) {
    const [y, m, d] = iso.split("-").map(Number);
    const day = new Date(y, m - 1, d), now = new Date();
    const diff = Math.round((new Date(now.getFullYear(), now.getMonth(), now.getDate()) - day) / 86400000);
    const w = weekday || "日月火水木金土"[day.getDay()];
    const base = `${m}/${d}(${w})`;
    return diff === 0 ? `${base} 今日` : diff === 1 ? `${base} きのう` : (y !== now.getFullYear() ? `${y}/` : "") + base;
  }

  // ぷちの一覧を <select> に入れて、選ばれている id を返す。変わったら onChange(id)
  // url: 子の一覧の読み先。ぷちログは、見てよいと決めてもらった子も入る /api/petitlog/characters
  async function charSelect(sel, onChange, url = "/api/characters") {
    let chars = [];
    try { chars = await (await fetch(url)).json(); } catch (e) {}
    chars = Array.isArray(chars) ? chars : [];
    const want = q.get("char");
    const cur = chars.some(c => c.id === want) ? want : (chars[0] && chars[0].id) || "";
    sel.textContent = "";
    for (const c of chars) {
      const o = document.createElement("option");
      o.value = c.id; o.textContent = c.name || c.id; o.selected = c.id === cur;
      sel.appendChild(o);
    }
    // 1 行目の背景は、選んでいる子の色(2026-11-10 ありさん)。文字は、明るい色なら濃く、暗い色なら白
    const paint = id => {
      const c = (chars.find(x => x.id === id) || {}).color || "";
      if (!/^#[0-9a-fA-F]{6}$/.test(c)) { root.style.removeProperty("--p-char"); root.style.removeProperty("--p-char-ink"); return; }
      const [r, g, b] = [1, 3, 5].map(i => parseInt(c.slice(i, i + 2), 16));
      const bright = (r * 299 + g * 587 + b * 114) / 1000 > 160;
      root.style.setProperty("--p-char", c);
      root.style.setProperty("--p-char-ink", bright ? `rgb(${[r, g, b].map(v => Math.round(v * 0.4)).join(",")})` : "#fff");
    };
    paint(cur);
    sel.onchange = () => {
      q.set("char", sel.value);
      history.replaceState(null, "", location.pathname + "?" + q.toString());
      paint(sel.value);
      onChange(sel.value);
    };
    return cur;
  }

  // 月へ飛ぶ一覧: 今月から、いちばん古い日の月まで。選ぶと onPick(その月の次の月の 1 日 = その月の終わりから読む)。
  // 先頭の「いま」は onPick(null)
  function monthSelect(sel, earliestIso, onPick) {
    const keep = sel.value;
    sel.textContent = "";
    const add = (value, text) => { const o = document.createElement("option"); o.value = value; o.textContent = text; sel.appendChild(o); };
    add("", "いま");
    if (earliestIso) {
      const [ey, em] = earliestIso.split("-").map(Number);
      const now = new Date();
      let y = now.getFullYear(), m = now.getMonth() + 1;
      for (let i = 0; i < 240 && (y > ey || (y === ey && m >= em)); i++) {
        add(`${y}-${String(m).padStart(2, "0")}`, `${y}年 ${m}月`);
        if (--m === 0) { m = 12; y--; }
      }
    }
    if ([...sel.options].some(o => o.value === keep)) sel.value = keep;
    sel.onchange = () => {
      if (!sel.value) return onPick(null);
      const [y, m] = sel.value.split("-").map(Number);
      const ny = m === 12 ? y + 1 : y, nm = m === 12 ? 1 : m + 1;
      onPick(`${ny}-${String(nm).padStart(2, "0")}-01`);
    };
  }

  // 同じ並びのページへ移るときの行き先(embed・accent・char を引き継ぐ)
  function link(path, extra) {
    const n = new URLSearchParams(q);
    for (const [k, v] of Object.entries(extra || {})) n.set(k, v);
    return path + "?" + n.toString();
  }

  return { q, esc, dayLabel, charSelect, monthSelect, link };
})();
