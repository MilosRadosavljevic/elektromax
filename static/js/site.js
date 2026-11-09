// Elektromax – javni deo: status radnog vremena, meni, animacije.
// window.RV dolazi iz baze (tabela radno_vreme): [{dan, radi, od, do, napomena}, ...]
(function () {
  const DANI = ["nedelja", "ponedeljak", "utorak", "sreda", "četvrtak", "petak", "subota"];
  const rv = {};
  (window.RV || []).forEach(d => { rv[d.dan] = d; });
  const now = new Date();
  const danas = now.getDay();

  // Označi današnji dan u svim tabelama radnog vremena
  document.querySelectorAll('[data-dan="' + danas + '"]').forEach(tr => tr.classList.add("today"));

  // Status "Otvoreno / Zatvoreno"
  const st = document.getElementById("status"), stt = document.getElementById("status-text");
  if (st && stt) {
    const min = s => { const [h, m] = s.split(":").map(Number); return h * 60 + m; };
    const sad = now.getHours() * 60 + now.getMinutes();
    const sledece = () => {
      for (let i = 1; i <= 7; i++) {
        const d = (danas + i) % 7, x = rv[d];
        if (x && x.radi) return (i === 1 ? "sutra" : DANI[d]) + " u " + x.od;
      }
      return "";
    };
    const t = rv[danas];
    if (!t || !t.radi) { st.classList.add("closed"); stt.textContent = "Danas zatvoreno · otvara " + sledece(); }
    else if (sad < min(t.od)) { st.classList.add("closed"); stt.textContent = "Zatvoreno · otvara danas u " + t.od; }
    else if (sad < min(t.do)) { st.classList.add("open"); stt.textContent = "Otvoreno · do " + t.do; }
    else { st.classList.add("closed"); stt.textContent = "Zatvoreno · otvara " + sledece(); }
  }

  // Mobilni meni
  const burger = document.getElementById("burger"), nav = document.getElementById("nav");
  if (burger && nav) {
    burger.addEventListener("click", () => {
      const open = nav.classList.toggle("open");
      burger.setAttribute("aria-expanded", open);
    });
  }

  // Animacija pri skrolovanju
  const els = document.querySelectorAll(".reveal");
  if (!("IntersectionObserver" in window)) { els.forEach(e => e.classList.add("in")); return; }
  const io = new IntersectionObserver(es => es.forEach(en => {
    if (en.isIntersecting) { en.target.classList.add("in"); io.unobserve(en.target); }
  }), { threshold: .12 });
  els.forEach((el, i) => { el.style.transitionDelay = (i % 4) * 70 + "ms"; io.observe(el); });
})();
