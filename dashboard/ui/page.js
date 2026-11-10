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
  async function charSelect(sel, onChange) {
    let chars = [];
    try { chars = await (await fetch("/api/characters")).json(); } catch (e) {}
    chars = Array.isArray(chars) ? chars : [];
    const want = q.get("char");
    const cur = chars.some(c => c.id === want) ? want : (chars[0] && chars[0].id) || "";
    sel.textContent = "";
    for (const c of chars) {
      const o = document.createElement("option");
      o.value = c.id; o.textContent = c.name || c.id; o.selected = c.id === cur;
      sel.appendChild(o);
    }
    sel.onchange = () => {
      q.set("char", sel.value);
      history.replaceState(null, "", location.pathname + "?" + q.toString());
      onChange(sel.value);
    };
    return cur;
  }

  // 同じ並びのページへ移るときの行き先(embed・accent・char を引き継ぐ)
  function link(path, extra) {
    const n = new URLSearchParams(q);
    for (const [k, v] of Object.entries(extra || {})) n.set(k, v);
    return path + "?" + n.toString();
  }

  return { q, esc, dayLabel, charSelect, link };
})();
