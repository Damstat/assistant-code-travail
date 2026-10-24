// Interface web : envoie la question à /api/question et affiche la réponse avec ses sources.
// Fonctionnalités : animation de la réponse, historique gardé dans le navigateur,
// thème clair/sombre, copie de la réponse, citations [n] reliées aux passages.
const fil = document.getElementById("fil");
const formulaire = document.getElementById("formulaire");
const champ = document.getElementById("question");
const bouton = document.getElementById("envoyer");
const compteur = document.getElementById("compteur");
const CLE_HISTORIQUE = "historique-code-travail";
const MAX_HISTORIQUE = 30;
const animer = !matchMedia("(prefers-reduced-motion: reduce)").matches;
let numeroReponse = 0; // identifiant unique de chaque réponse (pour les liens [1], [2]…)
let infos = null;

const ICONES = {
  copier: '<svg viewBox="0 0 24 24"><rect x="9" y="9" width="12" height="12" rx="2"/><path d="M5 15V5a2 2 0 0 1 2-2h10"/></svg>',
  valide: '<svg viewBox="0 0 24 24"><path d="M5 12l5 5L20 7"/></svg>',
  horloge: '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></svg>',
  jeton: '<svg viewBox="0 0 24 24"><path d="M4 7h16M4 12h16M4 17h10"/></svg>',
  chevron: '<svg viewBox="0 0 24 24"><path d="M9 6l6 6-6 6"/></svg>',
  alerte: '<svg viewBox="0 0 24 24" width="14" height="14"><path d="M12 9v4M12 17h.01M10.3 3.9L1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/></svg>',
  reessayer: '<svg viewBox="0 0 24 24"><path d="M3 12a9 9 0 1 0 3-6.7L3 8M3 3v5h5"/></svg>',
};

// --- Petits utilitaires -------------------------------------------------
function echapper(texte) {
  const div = document.createElement("div");
  div.textContent = texte;
  return div.innerHTML;
}

function lireStockage(cle, defaut) {
  try { return JSON.parse(localStorage.getItem(cle)) ?? defaut; } catch { return defaut; }
}
function ecrireStockage(cle, valeur) {
  try { localStorage.setItem(cle, JSON.stringify(valeur)); } catch { /* navigation privée */ }
}

function toast(message) {
  const el = document.createElement("div");
  el.className = "toast";
  el.textContent = message;
  document.getElementById("toasts").appendChild(el);
  setTimeout(() => { el.classList.add("sortie"); setTimeout(() => el.remove(), 250); }, 2000);
}

function defilerEnBas() {
  window.scrollTo({ top: document.body.scrollHeight, behavior: animer ? "smooth" : "auto" });
}

// Mise en forme légère de la réponse : paragraphes, **gras**, citations [n] cliquables
function formater(texte, id) {
  return echapper(texte)
    .split(/\n{2,}/)
    .map((para) => "<p>" + para
      .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
      .replace(/\[(\d+)\]/g, `<a class="citation" href="#src-${id}-$1" data-cible="src-${id}-$1">$1</a>`)
      .replace(/\n/g, "<br>") + "</p>")
    .join("");
}

// Fait apparaître la réponse mot par mot (effet « en train d'écrire »), en 1,5 s au plus
function animerMots(conteneur) {
  const noeuds = [];
  const parcours = document.createTreeWalker(conteneur, NodeFilter.SHOW_TEXT);
  while (parcours.nextNode()) {
    if (!parcours.currentNode.parentElement.closest(".citation")) noeuds.push(parcours.currentNode);
  }
  const mots = [];
  for (const noeud of noeuds) {
    const fragment = document.createDocumentFragment();
    for (const morceau of noeud.textContent.split(/(\s+)/)) {
      if (!morceau) continue;
      if (/^\s+$/.test(morceau)) { fragment.append(morceau); continue; }
      const span = document.createElement("span");
      span.className = "mot";
      span.textContent = morceau;
      fragment.append(span);
      mots.push(span);
    }
    noeud.replaceWith(fragment);
  }
  // Les citations [n] apparaissent comme un mot
  conteneur.querySelectorAll(".citation").forEach((c) => { c.classList.add("mot"); });
  const tous = conteneur.querySelectorAll(".mot");
  const pas = Math.min(35, 1500 / Math.max(tous.length, 1));
  tous.forEach((m, i) => { m.style.animationDelay = `${i * pas}ms`; });
  return tous.length * pas;
}

// --- Affichage des messages ---------------------------------------------
function ajouterQuestion(question) {
  const el = document.createElement("div");
  el.className = "message message-question";
  el.innerHTML = `<div class="bulle-question">${echapper(question)}</div>`;
  fil.appendChild(el);
}

function ajouterCarte() {
  const el = document.createElement("div");
  el.className = "message";
  el.innerHTML = '<img class="avatar" src="logo.svg" alt=""><div class="carte"></div>';
  fil.appendChild(el);
  return el.querySelector(".carte");
}

function afficherChargement(carte) {
  // Le serveur ne renvoie qu'un résultat final : les étapes affichées suivent l'ordre du pipeline
  const etapes = ["Recherche des articles pertinents…", "Lecture des passages…", "Rédaction de la réponse…"];
  carte.innerHTML = `<div class="chargement"><div class="points"><span></span><span></span><span></span></div>
    <span class="etape">${etapes[0]}</span></div>`;
  let i = 0;
  const minuterie = setInterval(() => {
    if (i >= etapes.length - 1) return clearInterval(minuterie);
    const etape = carte.querySelector(".etape");
    if (!etape) return clearInterval(minuterie);
    etape.outerHTML = `<span class="etape">${etapes[++i]}</span>`;
  }, 900);
  return () => clearInterval(minuterie);
}

function afficherReponse(carte, r, avecAnimation) {
  const id = ++numeroReponse;
  const sources = r.passages.map((p, n) => `
    <li class="source" id="src-${id}-${n + 1}" title="Cliquer pour lire le passage">
      <div class="source-entete">
        <span class="source-numero">${n + 1}</span>
        <span class="source-titre">${echapper(p.titre)}</span>
        <span class="score" title="Similarité avec la question">
          <span class="score-barre"><span style="width:${Math.round(Math.max(0, Math.min(1, p.score)) * 100)}%"></span></span>
          <span class="score-valeur">${p.score.toFixed(2)}</span>
        </span>
      </div>
      <p class="source-texte">${echapper(p.texte)}</p>
    </li>`).join("");
  const t = r.trace || {};
  carte.className = "carte" + (r.hors_corpus ? " hors-corpus" : "");
  carte.innerHTML = `
    ${r.hors_corpus ? `<span class="badge">${ICONES.alerte} Hors du Code du Travail</span>` : ""}
    <div class="texte-reponse">${formater(r.reponse, id)}</div>
    ${r.passages.length ? `
    <details class="sources" ${r.hors_corpus ? "" : "open"}>
      <summary>${ICONES.chevron} Sources consultées (${r.passages.length})</summary>
      <ol class="liste-sources">${sources}</ol>
    </details>` : ""}
    <div class="barre">
      <div class="mesures">
        <span class="pastille" title="Temps de réponse">${ICONES.horloge} ${(t.total_ms / 1000).toFixed(1)} s</span>
        <span class="pastille" title="Tokens d'entrée + de sortie">${ICONES.jeton} ${t.tokens_entree} + ${t.tokens_sortie}</span>
      </div>
      <button type="button" class="bouton-texte copier">${ICONES.copier} Copier</button>
    </div>`;
  carte.querySelector(".copier").addEventListener("click", (e) => copier(r, e.currentTarget));
  if (avecAnimation && animer) animerMots(carte.querySelector(".texte-reponse"));
}

function afficherErreur(carte, message, question) {
  carte.className = "carte erreur";
  carte.innerHTML = `<div>${ICONES.alerte} ${echapper(message)}</div>
    <button type="button" class="bouton-texte">${ICONES.reessayer} Réessayer</button>`;
  carte.querySelector("button").addEventListener("click", () => {
    carte.closest(".message").previousElementSibling?.remove();
    carte.closest(".message").remove();
    poser(question);
  });
}

async function copier(r, boutonCopier) {
  const sources = r.passages.map((p, n) => `[${n + 1}] ${p.source}`).join("\n");
  try {
    await navigator.clipboard.writeText(`${r.question}\n\n${r.reponse}\n\nSources :\n${sources}`);
    boutonCopier.innerHTML = `${ICONES.valide} Copié`;
    setTimeout(() => { boutonCopier.innerHTML = `${ICONES.copier} Copier`; }, 1600);
  } catch {
    toast("Impossible de copier dans le presse-papiers");
  }
}

// --- Accueil et historique ----------------------------------------------
function afficherAccueil() {
  fil.innerHTML = "";
  fil.appendChild(document.getElementById("modele-accueil").content.cloneNode(true));
  fil.querySelectorAll(".exemple").forEach((b) =>
    b.addEventListener("click", () => poser(b.lastElementChild.textContent)));
  if (infos) fil.querySelector("#infos").textContent =
    `LLM : ${infos.llm} · embeddings : ${infos.embeddings} · ${infos.top_k} passages par question`;
}

function enregistrer(resultat) {
  const historique = lireStockage(CLE_HISTORIQUE, []);
  // On ne garde que ce qui sert à réafficher la réponse
  const { question, reponse, passages, hors_corpus, trace } = resultat;
  historique.push({ question, reponse, passages, hors_corpus,
    trace: { total_ms: trace.total_ms, tokens_entree: trace.tokens_entree, tokens_sortie: trace.tokens_sortie } });
  ecrireStockage(CLE_HISTORIQUE, historique.slice(-MAX_HISTORIQUE));
}

function restaurer() {
  const historique = lireStockage(CLE_HISTORIQUE, []);
  if (!historique.length) return afficherAccueil();
  for (const r of historique) {
    ajouterQuestion(r.question);
    afficherReponse(ajouterCarte(), r, false);
  }
  window.scrollTo(0, document.body.scrollHeight);
}

// --- Envoi d'une question -----------------------------------------------
async function poser(question) {
  fil.querySelector(".accueil")?.remove();
  ajouterQuestion(question);
  const carte = ajouterCarte();
  const arreterChargement = afficherChargement(carte);
  defilerEnBas();
  bouton.disabled = true;
  try {
    const rep = await fetch("/api/question", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question }),
    });
    const donnees = await rep.json().catch(() => ({}));
    if (!rep.ok) throw new Error(donnees.erreur || `Erreur ${rep.status}`);
    arreterChargement();
    afficherReponse(carte, donnees, true);
    enregistrer(donnees);
  } catch (erreur) {
    arreterChargement();
    const message = erreur instanceof TypeError ? "Le serveur ne répond pas. Est-il bien lancé ?" : erreur.message;
    afficherErreur(carte, message, question);
  } finally {
    bouton.disabled = false;
    defilerEnBas();
    champ.focus();
  }
}

// --- Événements ---------------------------------------------------------
formulaire.addEventListener("submit", (e) => {
  e.preventDefault();
  const question = champ.value.trim();
  if (!question || bouton.disabled) return;
  champ.value = "";
  champ.dispatchEvent(new Event("input"));
  poser(question);
});

// Entrée = envoyer, Maj+Entrée = nouvelle ligne
champ.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey && !e.isComposing) {
    e.preventDefault();
    formulaire.requestSubmit();
  }
});

// Le champ s'agrandit avec le texte ; le compteur apparaît près de la limite
champ.addEventListener("input", () => {
  champ.style.height = "auto";
  champ.style.height = champ.scrollHeight + "px";
  const reste = champ.maxLength - champ.value.length;
  compteur.hidden = reste > 200;
  compteur.textContent = reste;
});

// « / » place le curseur dans le champ, comme sur beaucoup de sites
document.addEventListener("keydown", (e) => {
  if (e.key === "/" && document.activeElement !== champ) { e.preventDefault(); champ.focus(); }
});

// Clic sur [n] : ouvre les sources, met le passage en évidence et l'affiche
fil.addEventListener("click", (e) => {
  const lien = e.target.closest(".citation");
  if (lien) {
    e.preventDefault();
    const cible = document.getElementById(lien.dataset.cible);
    if (!cible) return;
    cible.closest(".sources").open = true;
    cible.classList.add("ouverte", "surbrillance");
    cible.scrollIntoView({ behavior: animer ? "smooth" : "auto", block: "center" });
    setTimeout(() => cible.classList.remove("surbrillance"), 1800);
    return;
  }
  // Clic sur une source : affiche ou cache le texte du passage
  const source = e.target.closest(".source");
  if (source && !window.getSelection().toString()) source.classList.toggle("ouverte");
});

document.getElementById("nouvelle").addEventListener("click", () => {
  ecrireStockage(CLE_HISTORIQUE, []);
  afficherAccueil();
  champ.focus();
});

document.getElementById("theme").addEventListener("click", () => {
  const racine = document.documentElement;
  const sombre = racine.dataset.theme
    ? racine.dataset.theme === "dark"
    : matchMedia("(prefers-color-scheme: dark)").matches;
  racine.dataset.theme = sombre ? "light" : "dark";
  try { localStorage.setItem("theme", racine.dataset.theme); } catch { /* navigation privée */ }
});

fetch("/api/infos")
  .then((r) => r.json())
  .then((i) => {
    infos = i;
    const el = fil.querySelector("#infos");
    if (el) el.textContent = `LLM : ${i.llm} · embeddings : ${i.embeddings} · ${i.top_k} passages par question`;
  })
  .catch(() => {});

restaurer();
champ.focus();

// Lien partageable : /?q=Ma+question pose directement la question
const questionLien = new URLSearchParams(location.search).get("q");
if (questionLien) {
  history.replaceState(null, "", location.pathname);
  poser(questionLien.slice(0, champ.maxLength));
}
