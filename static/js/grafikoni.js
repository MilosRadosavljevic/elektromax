// Mali SVG grafikoni za analitiku (bez spoljnih biblioteka).
// Jedna serija = jedna boja (plava); intenzitet = sekvencijalna plava skala; tekst uvek u boji teksta.
(function () {
  const NS = "http://www.w3.org/2000/svg";
  const PLAVA = "#2a78d6";
  const SKALA = ["#cde2fb", "#b7d3f6", "#9ec5f4", "#86b6ef", "#6da7ec", "#5598e7", "#3987e5",
                 "#2a78d6", "#256abf", "#1c5cab", "#184f95", "#104281", "#0d366b"];
  const din = (x, dec = 0) => Number(x).toLocaleString("sr-RS", {minimumFractionDigits: dec, maximumFractionDigits: dec});
  const kratko = x => Math.abs(x) >= 1e6 ? din(x / 1e6, 1) + " mil" : Math.abs(x) >= 1e3 ? din(x / 1e3, 0) + " hilj" : din(x);

  function el(tag, attrs, roditelj) {
    const e = document.createElementNS(NS, tag);
    for (const k in attrs) e.setAttribute(k, attrs[k]);
    if (roditelj) roditelj.appendChild(e);
    return e;
  }

  // zajednički tooltip
  const tip = document.createElement("div");
  tip.className = "viz-tip";
  document.body.appendChild(tip);
  function pokazi(ev, html) {
    tip.innerHTML = html;
    tip.style.display = "block";
    const r = tip.getBoundingClientRect();
    let x = ev.clientX + 14, y = ev.clientY - r.height - 10;
    if (x + r.width > innerWidth - 8) x = ev.clientX - r.width - 14;
    if (y < 8) y = ev.clientY + 16;
    tip.style.left = x + "px";
    tip.style.top = y + "px";
  }
  const sakrij = () => { tip.style.display = "none"; };

  function lepaSkala(max) {
    if (max <= 0) return [0, 1];
    const sirov = max / 4, mag = Math.pow(10, Math.floor(Math.log10(sirov)));
    const korak = [1, 2, 2.5, 5, 10].map(m => m * mag).find(s => s >= sirov);
    return [korak, Math.ceil(max / korak) * korak];
  }

  // ---------------------------------------------------------------- stubići kroz vreme
  function stubici(kont, podaci, opcije = {}) {
    const crtaj = () => {
      kont.innerHTML = "";
      const W = kont.clientWidth || 600, H = opcije.visina || (W < 500 ? 200 : 240), L = W < 500 ? 46 : 64, R = 10, T = 12, B = 30;
      const svg = el("svg", {viewBox: `0 0 ${W} ${H}`, width: W, height: H, role: "img",
                             "aria-label": opcije.opis || ""}, kont);
      const max = Math.max(0, ...podaci.map(d => d.v));
      const [korak, vrh] = lepaSkala(max);
      const y = v => T + (H - T - B) * (1 - v / vrh);
      for (let v = 0; v <= vrh + 1e-9; v += korak) {
        el("line", {x1: L, x2: W - R, y1: y(v), y2: y(v), class: v ? "viz-grid" : "viz-osa"}, svg);
        el("text", {x: L - 8, y: y(v) + 4, "text-anchor": "end", class: "viz-oznaka"}, svg).textContent = kratko(v);
      }
      const n = podaci.length, sl = (W - L - R) / n, sirina = Math.max(1, sl - 2);
      const svakiN = Math.ceil(n / Math.max(1, Math.floor((W - L - R) / 64)));
      podaci.forEach((d, i) => {
        const x = L + i * sl + 1, h = Math.max(0, y(0) - y(Math.max(0, d.v)));
        if (h > 0) {
          const r = Math.min(4, sirina / 2, h);
          el("path", {class: "viz-stub", fill: PLAVA,
            d: `M${x},${y(0)} V${y(0) - h + r} Q${x},${y(0) - h} ${x + r},${y(0) - h} H${x + sirina - r} Q${x + sirina},${y(0) - h} ${x + sirina},${y(0) - h + r} V${y(0)} Z`}, svg);
        }
        const meta = el("rect", {x: L + i * sl, y: T, width: sl, height: H - T - B, fill: "transparent"}, svg);
        meta.addEventListener("mousemove", ev => pokazi(ev, opcije.tooltip(d)));
        meta.addEventListener("mouseleave", sakrij);
        if (i % svakiN === 0) el("text", {x: x + sirina / 2, y: H - 10, "text-anchor": "middle", class: "viz-oznaka"}, svg)
          .textContent = opcije.oznaka ? opcije.oznaka(d) : d.label;
      });
    };
    crtaj();
    new ResizeObserver(() => crtaj()).observe(kont);
  }

  // ---------------------------------------------------------------- horizontalne trake
  function trake(kont, podaci, opcije = {}) {
    const crtaj = () => {
      kont.innerHTML = "";
      const W = kont.clientWidth || 500, red = 30, H = podaci.length * red + 6;
      const L = Math.min(opcije.levo || 170, Math.round(W * 0.38)), R = Math.min(96, Math.round(W * 0.2));
      const maxZnak = Math.floor((L - 14) / 6.6);   // skraćuje predug naziv da stane levo od trake
      const skrati = t => t.length > maxZnak ? t.slice(0, Math.max(3, maxZnak - 1)) + "…" : t;
      const svg = el("svg", {viewBox: `0 0 ${W} ${H}`, width: W, height: H, role: "img",
                             "aria-label": opcije.opis || ""}, kont);
      const max = Math.max(1, ...podaci.map(d => d.v));
      podaci.forEach((d, i) => {
        const yy = i * red + 4, w = Math.max(0, (W - L - R) * d.v / max), h = red - 10;
        const ime = el("text", {x: L - 10, y: yy + h / 2 + 5, "text-anchor": "end", class: "viz-ime"}, svg);
        ime.textContent = skrati(d.label);
        if (w > 0) {
          const r = Math.min(4, w, h / 2);
          el("path", {fill: PLAVA, class: "viz-stub",
            d: `M${L},${yy} H${L + w - r} Q${L + w},${yy} ${L + w},${yy + r} V${yy + h - r} Q${L + w},${yy + h} ${L + w - r},${yy + h} H${L} Z`}, svg);
        }
        el("text", {x: L + w + 8, y: yy + h / 2 + 5, class: "viz-vrednost"}, svg).textContent = opcije.vrednost ? opcije.vrednost(d) : din(d.v);
        const meta = el("rect", {x: 0, y: yy - 4, width: W, height: red, fill: "transparent"}, svg);
        if (opcije.tooltip) {
          meta.addEventListener("mousemove", ev => pokazi(ev, opcije.tooltip(d)));
          meta.addEventListener("mouseleave", sakrij);
        }
      });
    };
    crtaj();
    new ResizeObserver(() => crtaj()).observe(kont);
  }

  // ---------------------------------------------------------------- toplotna mapa (dan x sat)
  function toplota(kont, celije, opcije) {
    const dani = opcije.dani, sati = opcije.sati;
    const mapa = {};
    celije.forEach(c => { mapa[c.dan + "-" + c.sat] = c; });
    const max = Math.max(1, ...celije.map(c => c.v));
    const crtaj = () => {
      kont.innerHTML = "";
      const W = kont.clientWidth || 600, L = 40, T = 22, cw = (W - L) / sati.length, ch = W < 420 ? 26 : 30, H = T + dani.length * ch + 4;
      const svakiSat = cw < 30 ? 2 : 1;   // na uskom ekranu oznaka za svaki drugi sat
      const svg = el("svg", {viewBox: `0 0 ${W} ${H}`, width: W, height: H, role: "img", "aria-label": opcije.opis || ""}, kont);
      sati.forEach((s, j) => { if (j % svakiSat === 0) el("text", {x: L + j * cw + cw / 2, y: 14, "text-anchor": "middle", class: "viz-oznaka"}, svg).textContent = s + "h"; });
      dani.forEach(([dan, ime], i) => {
        el("text", {x: L - 8, y: T + i * ch + ch / 2 + 4, "text-anchor": "end", class: "viz-ime"}, svg).textContent = ime;
        sati.forEach((s, j) => {
          const c = mapa[dan + "-" + s];
          const v = c ? Math.max(0, c.v) : 0;
          const boja = v > 0 ? SKALA[Math.min(SKALA.length - 1, Math.floor(v / max * (SKALA.length - 1)))] : "#f3f1ec";
          const r = el("rect", {x: L + j * cw + 1, y: T + i * ch + 1, width: cw - 2, height: ch - 2, rx: 4, fill: boja}, svg);
          r.addEventListener("mousemove", ev => pokazi(ev, opcije.tooltip(ime, s, c)));
          r.addEventListener("mouseleave", sakrij);
        });
      });
    };
    crtaj();
    new ResizeObserver(() => crtaj()).observe(kont);
  }

  window.Grafikoni = {stubici, trake, toplota, din, kratko, SKALA};
})();
