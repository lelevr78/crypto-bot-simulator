"use strict";

const $ = (sel) => document.querySelector(sel);
const eur = new Intl.NumberFormat("it-IT", { style: "currency", currency: "EUR", maximumFractionDigits: 0 });
const int = new Intl.NumberFormat("it-IT");
const pct = (x) => Math.round(x * 100) + "%";
const dayFmt = new Intl.DateTimeFormat("it-IT", { weekday: "short", day: "numeric", month: "short" });
const monthFmt = new Intl.DateTimeFormat("it-IT", { month: "long", year: "numeric" });
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const day = (iso) => dayFmt.format(new Date(iso + "T12:00:00"));

const form = $("#filters");
const PREFS_KEY = "radar-voli-filtri";
let deals = [];

function loadPrefs() {
  try {
    const saved = JSON.parse(localStorage.getItem(PREFS_KEY) || "{}");
    for (const [k, v] of Object.entries(saved)) if (form.elements[k]) form.elements[k].value = v;
  } catch { /* storage non disponibile */ }
}
function savePrefs() {
  try { localStorage.setItem(PREFS_KEY, JSON.stringify(Object.fromEntries(new FormData(form)))); } catch { /* ignora */ }
}

function badge(level) {
  const cls = level === "Error fare" ? "b-error" : level === "Super offerta" ? "b-super" : "b-ok";
  return `<span class="badge ${cls}">${esc(level)}</span>`;
}
function isNew(d) { return Date.now() - new Date(d.found_at).getTime() < 10 * 60 * 1000; }
function stopsText(n) { return n === 0 ? "diretto" : n === 1 ? "1 scalo" : `${n} scali`; }

function card(d, i) {
  return `
  <button class="card" type="button" data-i="${i}">
    <div class="card-top">${badge(d.level)}${isNew(d) ? '<span class="new">Nuova</span>' : ""}</div>
    <div class="route">${esc(d.origin_city)} → ${esc(d.destination_city)}
      <small>${esc(d.origin)} – ${esc(d.destination)} · ${esc(d.destination_country)}</small></div>
    <div class="dates">${day(d.depart)}${d.ret ? " → " + day(d.ret) + ` · ${d.nights} notti` : " · solo andata"}</div>
    <div class="price-row">
      <span class="price">${eur.format(d.price)}</span>
      <span class="was">${eur.format(d.normal_price)}</span>
      <span class="off">−${pct(d.discount)}</span>
    </div>
    <div class="meta">${esc(d.airline)} · ${stopsText(d.stops)}</div>
  </button>`;
}

function render() {
  $("#grid").innerHTML = deals.map(card).join("");
  $("#empty").hidden = deals.length > 0;
  $("#count").textContent = deals.length ? `${deals.length} offerte trovate` : "";
}

function openDetail(d) {
  const max = Math.max(d.normal_price, d.price);
  const bar = (label, value, color) => `
    <div class="bar"><span>${label}</span>
      <div class="bar-track"><div class="bar-fill" style="width:${(value / max) * 100}%;background:${color}"></div></div>
      <b>${eur.format(value)}</b></div>`;
  $("#detail-body").innerHTML = `
    ${badge(d.level)}
    <h2 class="d-title">${esc(d.origin_city)} → ${esc(d.destination_city)}</h2>
    <p class="d-sub">${day(d.depart)}${d.ret ? " → " + day(d.ret) : ""} · ${esc(d.airline)} · ${stopsText(d.stops)}</p>
    <div class="bars">
      ${bar("Prezzo abituale", d.normal_price, "var(--muted)")}
      ${bar("Minimo normale", d.min_seen, "var(--warm)")}
      ${bar("Questa offerta", d.price, "var(--good)")}
    </div>
    <div class="facts">
      <span>Risparmi</span><b>${eur.format(d.saving)} (−${pct(d.discount)})</b>
      <span>Quanto è insolito</span><b>${d.zscore.toFixed(1)}× la variazione tipica</b>
      <span>Prezzi confrontati</span><b>${int.format(d.samples)}</b>
      <span>Trovata</span><b>${new Date(d.found_at).toLocaleString("it-IT", { dateStyle: "short", timeStyle: "short" })}</b>
    </div>
    <a class="cta" href="${esc(d.links.skyscanner)}" target="_blank" rel="noopener">Verifica e prenota su Skyscanner</a>
    <a class="cta2" href="${esc(d.links.google)}" target="_blank" rel="noopener">oppure controlla su Google Voli</a>`;
  $("#detail").showModal();
}

async function loadDeals() {
  const params = new URLSearchParams(new FormData(form));
  params.set("limit", "120");
  try {
    const res = await fetch("/api/deals?" + params);
    deals = (await res.json()).deals;
    render();
  } catch { /* server momentaneamente non raggiungibile */ }
}

async function loadStatus() {
  try {
    const s = await (await fetch("/api/status")).json();
    $("#s-comb").textContent = int.format(s.combinations);
    $("#s-deals").textContent = int.format(s.active_deals);
    $("#s-avg").textContent = s.active_deals ? "−" + pct(s.avg_discount) : "–";
    $("#s-min").textContent = s.min_price != null ? eur.format(s.min_price) : "–";
    $("#live-text").textContent = `In scansione · ${s.routes} rotte monitorate`;
    $("#provider-note").textContent = s.provider === "simulato"
      ? " Modalità dimostrativa: le tariffe sono simulate."
      : "";
  } catch {
    $("#live-text").textContent = "Connessione persa…";
  }
}

async function init() {
  const { origins } = await (await fetch("/api/airports")).json();
  $("#f-origin").insertAdjacentHTML("beforeend",
    origins.map((a) => `<option value="${esc(a.code)}">${esc(a.city)} (${esc(a.code)})</option>`).join(""));
  const now = new Date();
  for (let i = 0; i < 8; i++) {
    const m = new Date(now.getFullYear(), now.getMonth() + i, 1);
    const value = `${m.getFullYear()}-${String(m.getMonth() + 1).padStart(2, "0")}`;
    const label = monthFmt.format(m);
    $("#f-month").insertAdjacentHTML("beforeend", `<option value="${value}">${label[0].toUpperCase() + label.slice(1)}</option>`);
  }
  loadPrefs();
  form.addEventListener("change", () => { savePrefs(); loadDeals(); });
  $("#grid").addEventListener("click", (e) => {
    const el = e.target.closest(".card");
    if (el) openDetail(deals[Number(el.dataset.i)]);
  });
  await Promise.all([loadDeals(), loadStatus()]);
  setInterval(loadStatus, 2000);
  setInterval(loadDeals, 15000);
}

init();
