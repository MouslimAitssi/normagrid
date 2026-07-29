// ============================================================
// Config generale
// ============================================================

// Ordre des onglets de saisie (vue "Saisie des donnees")
const TAB_ORDER = [
  "client", "projet", "site",
  "reseau_ht", "tableaux", "transfos", "groupes_electrogenes",
  "cable", "charge",
  "tableau_jointure", "tag",
];

const HINTS = {
  tag: "Registre central : rempli automatiquement quand vous ajoutez un equipement (evite les doublons de tag dans le projet).",
  tableau_jointure: "Utilisez cet onglet quand un tableau a plusieurs amonts (arrivees multiples).",
};

const NODE_TYPE_STYLE = {
  reseau_ht: { color: "#1F3864", label: "Reseau HT" },
  transfos: { color: "#0E7C7B", label: "Transformateur" },
  groupes_electrogenes: { color: "#2C5F2D", label: "Groupe electrogene" },
  tableaux: { color: "#5B4B8A", label: "Tableau" },
  cable: { color: "#6D2E46", label: "Cable" },
  charge: { color: "#B85042", label: "Charge" },
};

let SCHEMA = {};
let TREE_DATA = [];
let GRAPH_NODES = [];
let GRAPH_EDGES = [];
let ACTIVE_PROJECT = null;
let DEFAULT_FOLDER = "";

function hasNativeDialogs() {
  return !!(window.pywebview && window.pywebview.api);
}

async function chooseFolderInto(inputEl) {
  if (!hasNativeDialogs()) return;
  try {
    const path = await window.pywebview.api.choose_folder();
    if (path) inputEl.value = path;
  } catch (e) {
    console.error("Erreur boite de dialogue dossier :", e);
  }
}

async function chooseDbFileInto(inputEl, mode) {
  if (!hasNativeDialogs()) return;
  try {
    const path = await window.pywebview.api.choose_db_file(mode || "open");
    if (path) inputEl.value = path;
  } catch (e) {
    console.error("Erreur boite de dialogue fichier :", e);
  }
}

function updateBrowseButtonsAvailability() {
  const native = hasNativeDialogs();
  document.querySelectorAll(".browse-btn").forEach((btn) => {
    btn.disabled = !native;
    btn.title = native ? "" : "Disponible uniquement dans l'application de bureau NormaGrid (pas dans un simple navigateur).";
  });
  document.querySelectorAll(".field-hint").forEach((hint) => {
    if (hint.id && hint.id.endsWith("-hint") && native) {
      hint.style.display = "none";
    }
  });
}

async function init() {
  wireFileMenu();
  wireModals();
  updateBrowseButtonsAvailability();

  // Le pont window.pywebview.api est injecte APRES le chargement initial de la
  // page : un simple check au demarrage peut donc arriver trop tot et
  // desactiver les boutons Parcourir a tort. On reagit a l'evenement officiel
  // pywebview, et on revient egalement periodiquement au cas ou l'evenement
  // aurait deja ete emis avant que ce script ne s'execute.
  window.addEventListener("pywebviewready", updateBrowseButtonsAvailability);
  let attempts = 0;
  const retry = setInterval(() => {
    attempts += 1;
    updateBrowseButtonsAvailability();
    if (hasNativeDialogs() || attempts > 20) clearInterval(retry);
  }, 250);

  try {
    const data = await (await fetch("/api/projects/default-folder")).json();
    DEFAULT_FOLDER = data.folder || "";
  } catch (e) {
    DEFAULT_FOLDER = "";
  }
  await refreshProjectState();
}

// ============================================================
// Gestion des projets (fichiers)
// ============================================================

async function refreshProjectState() {
  const data = await (await fetch("/api/projects")).json();
  ACTIVE_PROJECT = data.active;
  if (!ACTIVE_PROJECT) {
    showWelcomeScreen();
    return;
  }
  await showMainUI();
}

function showWelcomeScreen() {
  document.getElementById("view-welcome").style.display = "flex";
  document.getElementById("top-tabs").style.display = "none";
  ["equipements", "bilan", "cablesched", "synoptique", "saisie"].forEach((v) => {
    document.getElementById(`view-${v}`).style.display = "none";
  });
  document.getElementById("active-project-label").textContent = "";
  setImportEnabled(false);
}

async function showMainUI() {
  document.getElementById("view-welcome").style.display = "none";
  document.getElementById("top-tabs").style.display = "flex";
  const label = document.getElementById("active-project-label");
  label.textContent = ACTIVE_PROJECT ? ACTIVE_PROJECT.split(/[\\/]/).pop().replace(/\.db$/, "") : "";
  label.title = ACTIVE_PROJECT || "";
  setImportEnabled(true);

  wireTopTabs();
  SCHEMA = await Api.getSchema();
  renderTabs();
  selectTab(TAB_ORDER[0]);

  document.getElementById("tree-refresh").onclick = () => loadEquipementsView();
  document.getElementById("diagram-refresh").onclick = () => renderDiagramView();
  document.getElementById("bilan-refresh").onclick = () => loadBilanPuissanceView();
  document.getElementById("bilan-switchgear-filter").onchange = () => renderBilanPuissance();
  document.getElementById("bilan-export-open").onclick = () => {
    document.getElementById("bilan-export-folder").value = DEFAULT_FOLDER;
    document.getElementById("bilan-export-filename").value = "Bilan_de_puissance.xlsx";
    document.getElementById("bilan-export-error").textContent = "";
    document.getElementById("bilan-export-success").style.display = "none";
    openModal("modal-bilan-export");
  };
  document.getElementById("bilan-export-folder-browse").onclick = () =>
    chooseFolderInto(document.getElementById("bilan-export-folder"));
  document.getElementById("bilan-export-cancel").onclick = () => closeModal();
  document.getElementById("bilan-export-confirm").onclick = runBilanExport;
  document.getElementById("cable-schedule-export-open").onclick = () => {
    document.getElementById("cable-export-folder").value = DEFAULT_FOLDER;
    document.getElementById("cable-export-filename").value = "Carnet_de_cables.xlsx";
    document.getElementById("cable-export-error").textContent = "";
    document.getElementById("cable-export-success").style.display = "none";
    openModal("modal-cable-schedule-export");
  };
  document.getElementById("cable-export-folder-browse").onclick = () =>
    chooseFolderInto(document.getElementById("cable-export-folder"));
  document.getElementById("cable-export-cancel").onclick = () => closeModal();
  document.getElementById("cable-export-confirm").onclick = runCableScheduleExport;

  document.getElementById("excel-import-cancel").onclick = () => closeModal();
  document.getElementById("caneco-staging-upload-cancel").onclick = () => closeModal();
  document.getElementById("caneco-staging-upload-analyze").onclick = runCanecoStagingAnalyze;
  document.getElementById("caneco-staging-cancel").onclick = () => { CANECO_STAGING_ROWS = null; closeModal(); };
  document.getElementById("caneco-staging-confirm").onclick = runCanecoStagingConfirm;
  document.getElementById("excel-import-analyze").onclick = runExcelAnalyze;
  document.getElementById("excel-mapping-cancel").onclick = () => { EXCEL_IMPORT_STATE = null; closeModal(); };
  document.getElementById("excel-mapping-confirm").onclick = runExcelImportConfirm;

  document.getElementById("export-db-folder-browse").onclick = () =>
    chooseFolderInto(document.getElementById("export-db-folder"));
  document.getElementById("export-db-cancel").onclick = () => closeModal();
  document.getElementById("export-db-confirm").onclick = runExportDb;
  document.getElementById("tableaux-filter-all").onclick = () => {
    DIAGRAM_HIDDEN_NODES.clear();
    renderEquipmentFilterTree();
    redrawDiagram();
  };
  document.getElementById("tableaux-filter-none").onclick = () => {
    if (DIAGRAM_GRAPH) {
      DIAGRAM_GRAPH.nodes.forEach((n) => DIAGRAM_HIDDEN_NODES.add(n.id));
    }
    renderEquipmentFilterTree();
    redrawDiagram();
  };
  document.getElementById("diagram-zoom-in").onclick = () => diagramZoomIn();
  document.getElementById("diagram-zoom-out").onclick = () => diagramZoomOut();
  document.getElementById("diagram-zoom-reset").onclick = () => diagramZoomReset();
  document.getElementById("diagram-svg-wrap").addEventListener("wheel", (ev) => {
    if (!ev.ctrlKey) return; // molette seule = defilement normal ; Ctrl+molette = zoom
    ev.preventDefault();
    if (ev.deltaY < 0) diagramZoomIn(); else diagramZoomOut();
  }, { passive: false });

  // Glisser-deplacer (pan) au clic maintenu : navigue gauche-droite et haut-bas
  wireDiagramPan();

  showTopView("equipements");
}

function wireDiagramPan() {
  const wrap = document.getElementById("diagram-svg-wrap");
  let dragging = false;
  let startX = 0, startY = 0, startScrollLeft = 0, startScrollTop = 0;

  wrap.addEventListener("mousedown", (ev) => {
    if (ev.button !== 0) return; // bouton gauche uniquement
    dragging = true;
    startX = ev.clientX;
    startY = ev.clientY;
    startScrollLeft = wrap.scrollLeft;
    startScrollTop = wrap.scrollTop;
    wrap.classList.add("panning");
    ev.preventDefault(); // evite la selection de texte pendant le glisser
  });

  window.addEventListener("mousemove", (ev) => {
    if (!dragging) return;
    const dx = ev.clientX - startX;
    const dy = ev.clientY - startY;
    wrap.scrollLeft = startScrollLeft - dx;
    wrap.scrollTop = startScrollTop - dy;
  });

  window.addEventListener("mouseup", () => {
    if (!dragging) return;
    dragging = false;
    wrap.classList.remove("panning");
  });

  // si le curseur quitte la fenetre pendant le glisser, on arrete proprement
  window.addEventListener("blur", () => {
    dragging = false;
    wrap.classList.remove("panning");
  });
}

function setImportEnabled(enabled) {
  const toggle = document.getElementById("btn-import-toggle");
  toggle.disabled = !enabled;
  toggle.title = enabled ? "" : "Ouvrez ou creez d'abord un projet pour pouvoir importer.";
}

function wireFileMenu() {
  document.getElementById("btn-new-project").onclick = () => {
    document.getElementById("new-project-folder").value = DEFAULT_FOLDER;
    openModal("modal-new-project");
  };
  document.getElementById("btn-open-project").onclick = () => openOpenProjectModal();
  document.getElementById("btn-save-as-project").onclick = () => {
    document.getElementById("save-as-folder").value = DEFAULT_FOLDER;
    openModal("modal-save-as-project");
  };
  document.getElementById("btn-close-project").onclick = async () => {
    await fetch("/api/projects/close", { method: "POST" });
    setImportEnabled(false);
    await refreshProjectState();
  };
  document.getElementById("welcome-new-btn").onclick = () => {
    document.getElementById("new-project-folder").value = DEFAULT_FOLDER;
    openModal("modal-new-project");
  };
  document.getElementById("welcome-open-btn").onclick = () => openOpenProjectModal();

  const importToggle = document.getElementById("btn-import-toggle");
  const importDropdown = document.getElementById("import-dropdown");
  importToggle.onclick = (ev) => {
    ev.stopPropagation();
    if (importToggle.disabled) return;
    importDropdown.classList.toggle("open");
  };
  document.addEventListener("click", () => importDropdown.classList.remove("open"));

  document.querySelectorAll("#import-dropdown .dropdown-item").forEach((btn) => {
    btn.onclick = () => {
      importDropdown.classList.remove("open");
      const kind = btn.dataset.import;
      if (kind === "normagrid") {
        openModal("modal-import-normagrid");
      } else if (kind === "caneco") {
        openCanecoStagingUploadModal();
      } else if (kind === "caneco-convert") {
        openCanecoConvertModal();
      } else if (kind === "excel") {
        openExcelImportModal();
      } else {
        alert("Import " + btn.textContent.replace("...", "") + " : fonctionnalite prevue dans une prochaine etape.");
      }
    };
  });

  const exportToggle = document.getElementById("btn-export-toggle");
  const exportDropdown = document.getElementById("export-dropdown");
  exportToggle.onclick = (ev) => {
    ev.stopPropagation();
    exportDropdown.classList.toggle("open");
  };
  document.addEventListener("click", () => exportDropdown.classList.remove("open"));
  document.querySelectorAll("#export-dropdown .dropdown-item").forEach((btn) => {
    btn.onclick = () => {
      exportDropdown.classList.remove("open");
      openExportDbModal(btn.dataset.export);
    };
  });

  setImportEnabled(false); // etat initial, corrige par refreshProjectState()
}

function openModal(id) {
  document.getElementById("modal-overlay").style.display = "flex";
  document.querySelectorAll(".modal-box").forEach((m) => { m.style.display = "none"; });
  document.getElementById(id).style.display = "block";
}

function closeModal() {
  document.getElementById("modal-overlay").style.display = "none";
}

function wireModals() {
  document.getElementById("modal-overlay").addEventListener("click", (ev) => {
    if (ev.target.id === "modal-overlay") closeModal();
  });

  // --- Nouveau projet ---
  document.getElementById("new-project-cancel").onclick = () => closeModal();
  document.getElementById("new-project-folder-browse").onclick = () =>
    chooseFolderInto(document.getElementById("new-project-folder"));
  document.getElementById("new-project-confirm").onclick = async () => {
    const nameInput = document.getElementById("new-project-name");
    const folderInput = document.getElementById("new-project-folder");
    const errorEl = document.getElementById("new-project-error");
    errorEl.textContent = "";
    const name = nameInput.value.trim();
    const folder = folderInput.value.trim();
    if (!name) { errorEl.textContent = "Le nom du projet est requis."; return; }
    if (!folder) { errorEl.textContent = "Le dossier de destination est obligatoire."; return; }
    try {
      const r = await fetch("/api/projects/new", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, folder }),
      });
      const body = await r.json();
      if (!r.ok) throw new Error(body.error || "Erreur inconnue");
      nameInput.value = "";
      folderInput.value = "";
      closeModal();
      await refreshProjectState();
    } catch (e) {
      errorEl.textContent = e.message;
    }
  };

  // --- Ouvrir projet ---
  document.getElementById("open-project-cancel").onclick = () => closeModal();
  document.getElementById("open-project-path-browse").onclick = () =>
    chooseDbFileInto(document.getElementById("open-project-path"), "open");
  document.getElementById("open-project-path-confirm").onclick = async () => {
    const pathInput = document.getElementById("open-project-path");
    const errorEl = document.getElementById("open-project-error");
    errorEl.textContent = "";
    const path = pathInput.value.trim();
    if (!path) { errorEl.textContent = "Saisissez un chemin de fichier."; return; }
    try {
      const r = await fetch("/api/projects/open", {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ path }),
      });
      const body = await r.json();
      if (!r.ok) throw new Error(body.error || "Erreur inconnue");
      pathInput.value = "";
      closeModal();
      await refreshProjectState();
    } catch (e) {
      errorEl.textContent = e.message;
    }
  };

  // --- Enregistrer sous ---
  document.getElementById("save-as-cancel").onclick = () => closeModal();
  document.getElementById("save-as-folder-browse").onclick = () =>
    chooseFolderInto(document.getElementById("save-as-folder"));
  document.getElementById("save-as-confirm").onclick = async () => {
    const nameInput = document.getElementById("save-as-name");
    const folderInput = document.getElementById("save-as-folder");
    const errorEl = document.getElementById("save-as-error");
    errorEl.textContent = "";
    const name = nameInput.value.trim();
    const folder = folderInput.value.trim();
    if (!name) { errorEl.textContent = "Le nom du projet est requis."; return; }
    if (!folder) { errorEl.textContent = "Le dossier de destination est obligatoire."; return; }
    try {
      const r = await fetch("/api/projects/save-as", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, folder }),
      });
      const body = await r.json();
      if (!r.ok) throw new Error(body.error || "Erreur inconnue");
      nameInput.value = "";
      folderInput.value = "";
      closeModal();
      await refreshProjectState();
    } catch (e) {
      errorEl.textContent = e.message;
    }
  };

  // --- Importer ancienne version ---
  document.getElementById("import-cancel").onclick = () => closeModal();
  document.getElementById("import-project-folder-browse").onclick = () =>
    chooseFolderInto(document.getElementById("import-project-folder"));
  document.getElementById("import-confirm").onclick = async () => {
    const fileInput = document.getElementById("import-file");
    const nameInput = document.getElementById("import-project-name");
    const folderInput = document.getElementById("import-project-folder");
    const errorEl = document.getElementById("import-error");
    errorEl.textContent = "";
    if (!fileInput.files.length) { errorEl.textContent = "Choisissez un fichier .db."; return; }
    const formData = new FormData();
    formData.append("file", fileInput.files[0]);
    if (nameInput.value.trim()) formData.append("name", nameInput.value.trim());
    if (folderInput.value.trim()) formData.append("folder", folderInput.value.trim());
    try {
      const r = await fetch("/api/projects/import-normagrid", { method: "POST", body: formData });
      const body = await r.json();
      if (!r.ok) throw new Error(body.error || body.message || "Erreur inconnue");
      fileInput.value = "";
      nameInput.value = "";
      folderInput.value = "";
      closeModal();
      await refreshProjectState();
    } catch (e) {
      errorEl.textContent = e.message;
    }
  };

  // --- Importer note de calcul Caneco ---
  document.getElementById("caneco-cancel").onclick = () => closeModal();
  document.getElementById("caneco-confirm").onclick = runCanecoAnalyze;
  document.getElementById("caneco-preview-cancel").onclick = () => { CANECO_PREVIEW = null; closeModal(); };
  document.getElementById("caneco-preview-confirm").onclick = runCanecoConfirm;
  document.getElementById("caneco-convert-cancel").onclick = () => { CANECO_CONVERT = null; closeModal(); };
  document.getElementById("caneco-convert-confirm").onclick = runCanecoConvert;

  // --- Edition d'equipement ---
  document.getElementById("edit-equipment-cancel").onclick = () => closeModal();
  document.getElementById("edit-equipment-save").onclick = saveEditEquipment;

  // --- Creation d'equipement (glisser-depose) ---
  document.getElementById("create-equipment-cancel").onclick = () => closeModal();
  document.getElementById("create-equipment-save").onclick = saveCreateEquipment;
}

async function openOpenProjectModal() {
  openModal("modal-open-project");
  const listEl = document.getElementById("open-project-list");
  const errorEl = document.getElementById("open-project-error");
  errorEl.textContent = "";
  listEl.innerHTML = "Chargement...";
  try {
    const data = await (await fetch("/api/projects")).json();
    listEl.innerHTML = "";
    if (!data.projects.length) {
      listEl.innerHTML = '<p class="empty">Aucun projet existant.</p>';
      return;
    }
    data.projects.forEach((p) => {
      const item = document.createElement("div");
      item.className = "project-item" + (p.active ? " active-item" : "");
      item.innerHTML = `
        <div>
          <div class="project-item-name">${p.name}</div>
          <div class="project-item-meta">${p.folder}</div>
          <div class="project-item-meta">Modifie le ${p.modified} - ${p.size_kb} Ko</div>
        </div>
        ${p.active ? '<span class="project-badge-active">Ouvert</span>' : ""}
      `;
      item.onclick = async () => {
        if (p.active) { closeModal(); return; }
        try {
          const r = await fetch("/api/projects/open", {
            method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ path: p.path }),
          });
          const body = await r.json();
          if (!r.ok) throw new Error(body.error || "Erreur inconnue");
          closeModal();
          await refreshProjectState();
        } catch (e) {
          errorEl.textContent = e.message;
        }
      };
      listEl.appendChild(item);
    });
  } catch (e) {
    listEl.innerHTML = "";
    errorEl.textContent = "Erreur de chargement des projets.";
  }
}

// ============================================================
// Import Caneco (note de calcul PDF)
// ============================================================

async function openCanecoModal() {
  document.getElementById("caneco-error").textContent = "";
  document.getElementById("caneco-progress").style.display = "none";
  document.getElementById("caneco-file").value = "";
  document.getElementById("caneco-include-charges").checked = false;
  openModal("modal-import-caneco");

  const select = document.getElementById("caneco-reseau-select");
  const noReseauEl = document.getElementById("caneco-no-reseau");
  const reseauFieldEl = document.getElementById("caneco-reseau-field");
  const confirmBtn = document.getElementById("caneco-confirm");
  select.innerHTML = "";

  let reseaux = [];
  try {
    reseaux = await Api.list("reseau_ht");
  } catch (e) {
    reseaux = [];
  }

  if (!reseaux.length) {
    noReseauEl.style.display = "block";
    reseauFieldEl.style.display = "none";
    confirmBtn.disabled = true;
  } else {
    noReseauEl.style.display = "none";
    reseauFieldEl.style.display = "block";
    confirmBtn.disabled = false;
    reseaux.forEach((r) => {
      const opt = document.createElement("option");
      opt.value = r.tag_id;
      opt.textContent = r.nom && r.nom !== r.tag_id ? `${r.tag_id} (${r.nom})` : r.tag_id;
      select.appendChild(opt);
    });
  }
}

let CANECO_PREVIEW = null; // { session_id, boards, reseau_ht_tag }

// --- Etape 1 : analyse (lecture seule) puis affichage de l'apercu ---
async function runCanecoAnalyze() {
  const fileInput = document.getElementById("caneco-file");
  const select = document.getElementById("caneco-reseau-select");
  const errorEl = document.getElementById("caneco-error");
  const progressEl = document.getElementById("caneco-progress");
  errorEl.textContent = "";

  if (!fileInput.files.length) { errorEl.textContent = "Choisissez un fichier PDF."; return; }
  if (!select.value) { errorEl.textContent = "Choisissez un reseau HT de rattachement."; return; }

  const formData = new FormData();
  formData.append("file", fileInput.files[0]);

  progressEl.style.display = "block";
  document.getElementById("caneco-confirm").disabled = true;
  try {
    const r = await fetch("/api/projects/import-caneco/analyze", { method: "POST", body: formData });
    const body = await r.json();
    if (!r.ok) throw new Error(body.error || body.message || "Erreur inconnue");

    CANECO_PREVIEW = {
      session_id: body.session_id, boards: body.boards, reseau_ht_tag: select.value,
      include_charges: document.getElementById("caneco-include-charges").checked,
    };
    closeModal();
    openCanecoPreviewModal();
  } catch (e) {
    errorEl.textContent = e.message;
  } finally {
    progressEl.style.display = "none";
    document.getElementById("caneco-confirm").disabled = false;
  }
}

function canecoAmontOptionsHtml(boardNames, selected) {
  const opts = [
    `<option value="__AUCUN__">-- aucun (source autonome) --</option>`,
    `<option value="__RESEAU_HT__">Reseau HT choisi</option>`,
    ...boardNames.map((n) => `<option value="${n.replace(/"/g, "&quot;")}">${escapeXml(n)}</option>`),
  ];
  return opts.map((o) => o.replace(`value="${selected}"`, `value="${selected}" selected`)).join("");
}

// --- Etape intermediaire : apercu des amonts, modifiable avant confirmation ---
function openCanecoPreviewModal() {
  const { boards } = CANECO_PREVIEW;
  document.getElementById("caneco-preview-error").textContent = "";
  document.getElementById("caneco-final-report").style.display = "none";
  document.getElementById("caneco-preview-table-wrap").style.display = "block";
  document.getElementById("caneco-preview-confirm").style.display = "inline-block";
  document.getElementById("caneco-preview-summary").textContent =
    `${boards.length} tableaux/transfos/groupes detectes. Les charges (circuits terminaux) ne seront pas importees.`;

  const allNames = boards.map((b) => b.name).sort((a, b2) => a.localeCompare(b2));
  const TYPE_LABEL = { tableaux: "Tableau", transfos: "Transformateur", groupes_electrogenes: "Groupe electrogene" };

  const table = document.createElement("table");
  table.innerHTML = `<thead><tr><th>Tableau</th><th>Type</th><th>Amont(s)</th></tr></thead>`;
  const tbody = document.createElement("tbody");

  boards.forEach((b) => {
    const tr = document.createElement("tr");
    tr.dataset.board = b.name;
    const style = NODE_TYPE_STYLE[b.type] || { color: "#64748B" };
    const isGroupe = b.type === "groupes_electrogenes";
    const slots = isGroupe ? [] : (b.proposed_amonts.length ? b.proposed_amonts.slice(0, 2) : [""]);

    const amontCellHtml = isGroupe
      ? `<span class="field-hint">source autonome</span>`
      : slots.map((val) => `
          <div class="caneco-amont-row">
            <select class="caneco-amont-select">${canecoAmontOptionsHtml(allNames.filter((n) => n !== b.name), val || "__AUCUN__")}</select>
          </div>
        `).join("") + `<button type="button" class="secondary caneco-add-amont" style="font-size:0.72rem; padding:0.1rem 0.4rem;">+ amont</button>`;

    tr.innerHTML = `
      <td><strong>${escapeXml(b.name)}</strong></td>
      <td><span class="type-chip" style="background:${style.color}">${TYPE_LABEL[b.type] || b.type}</span></td>
      <td class="caneco-amont-cell">${amontCellHtml}</td>
    `;
    tbody.appendChild(tr);

    const addBtn = tr.querySelector(".caneco-add-amont");
    if (addBtn) {
      addBtn.onclick = () => {
        const cell = tr.querySelector(".caneco-amont-cell");
        if (cell.querySelectorAll(".caneco-amont-row").length >= 2) return;
        const div = document.createElement("div");
        div.className = "caneco-amont-row";
        div.innerHTML = `<select class="caneco-amont-select">${canecoAmontOptionsHtml(allNames.filter((n) => n !== b.name), "__AUCUN__")}</select>`;
        cell.insertBefore(div, addBtn);
      };
    }
  });
  table.appendChild(tbody);

  const wrap = document.getElementById("caneco-preview-table-wrap");
  wrap.innerHTML = "";
  wrap.appendChild(table);

  openModal("modal-caneco-preview");
}

// --- Etape 2 : confirmation (ecriture reelle en base) ---
async function runCanecoConfirm() {
  const errorEl = document.getElementById("caneco-preview-error");
  errorEl.textContent = "";
  if (!CANECO_PREVIEW) { errorEl.textContent = "Session expiree, relancez l'analyse."; return; }

  const amonts = {};
  document.querySelectorAll("#caneco-preview-table-wrap tbody tr").forEach((tr) => {
    const board = tr.dataset.board;
    const values = Array.from(tr.querySelectorAll(".caneco-amont-select"))
      .map((s) => s.value)
      .filter((v) => v && v !== "__AUCUN__");
    amonts[board] = values;
  });

  document.getElementById("caneco-confirm-progress").style.display = "block";
  document.getElementById("caneco-preview-table-wrap").style.display = "none";
  document.getElementById("caneco-preview-confirm").disabled = true;

  try {
    const r = await fetch("/api/projects/import-caneco/confirm", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        session_id: CANECO_PREVIEW.session_id, reseau_ht_tag: CANECO_PREVIEW.reseau_ht_tag,
        amonts, include_charges: CANECO_PREVIEW.include_charges,
      }),
    });
    const body = await r.json();
    if (!r.ok) throw new Error(body.error || body.message || "Erreur inconnue");

    const rep = body.report;
    let html = `
      <p><strong>Import termine.</strong></p>
      <ul style="margin:0.4rem 0 0.6rem 1.1rem; padding:0;">
        <li>${rep.tableaux} tableaux</li>
        <li>${rep.transfos} transformateurs</li>
        <li>${rep.groupes_electrogenes} groupes electrogenes</li>
        <li>${rep.cables} cables</li>
        ${CANECO_PREVIEW.include_charges ? `<li>${rep.charges} charges</li>` : ""}
      </ul>
    `;
    if (rep.warnings && rep.warnings.length) {
      html += `<p style="color:var(--danger); margin-top:0.6rem;"><strong>Avertissements (${rep.warnings.length}) :</strong></p>
        <ul style="margin:0.2rem 0 0 1.1rem; padding:0; color:var(--danger); font-size:0.85rem;">
          ${rep.warnings.map((w) => `<li>${escapeXml(w)}</li>`).join("")}
        </ul>`;
    }
    document.getElementById("caneco-final-report").innerHTML = html;
    document.getElementById("caneco-final-report").style.display = "block";
    document.getElementById("caneco-preview-confirm").style.display = "none";
    CANECO_PREVIEW = null;
    await loadEquipementsView();
  } catch (e) {
    errorEl.textContent = e.message;
    document.getElementById("caneco-preview-table-wrap").style.display = "block";
  } finally {
    document.getElementById("caneco-confirm-progress").style.display = "none";
    document.getElementById("caneco-preview-confirm").disabled = false;
  }
}

// ============================================================
// Conversion Caneco : table de preparation -> equipements reels
// ============================================================

let CANECO_CONVERT = null; // { boards, nb_rows }

async function openCanecoConvertModal() {
  document.getElementById("caneco-convert-error").textContent = "";
  document.getElementById("caneco-convert-progress").style.display = "none";
  document.getElementById("caneco-convert-report").style.display = "none";
  document.getElementById("caneco-convert-include-charges").checked = false;
  document.getElementById("caneco-convert-confirm").style.display = "inline-block";
  document.getElementById("caneco-convert-confirm").disabled = true;
  document.getElementById("caneco-convert-empty").style.display = "none";
  document.getElementById("caneco-convert-no-reseau").style.display = "none";
  document.getElementById("caneco-convert-body").style.display = "block";
  CANECO_CONVERT = null;
  openModal("modal-caneco-convert");

  let preview;
  try {
    preview = await (await fetch("/api/projects/import-caneco/staging-preview")).json();
  } catch (e) {
    document.getElementById("caneco-convert-error").textContent = "Erreur de chargement.";
    return;
  }

  if (!preview.boards || !preview.boards.length) {
    document.getElementById("caneco-convert-body").style.display = "none";
    document.getElementById("caneco-convert-empty").style.display = "block";
    return;
  }

  const select = document.getElementById("caneco-convert-reseau-select");
  const noReseauEl = document.getElementById("caneco-convert-no-reseau");
  const reseauFieldEl = document.getElementById("caneco-convert-reseau-field");
  select.innerHTML = "";

  let reseaux = [];
  try {
    reseaux = await Api.list("reseau_ht");
  } catch (e) {
    reseaux = [];
  }

  if (!reseaux.length) {
    noReseauEl.style.display = "block";
    reseauFieldEl.style.display = "none";
    document.getElementById("caneco-convert-table-wrap").innerHTML = "";
    document.getElementById("caneco-convert-summary").textContent = "";
    return;
  }
  noReseauEl.style.display = "none";
  reseauFieldEl.style.display = "block";
  reseaux.forEach((r) => {
    const opt = document.createElement("option");
    opt.value = r.tag_id;
    opt.textContent = r.nom && r.nom !== r.tag_id ? `${r.tag_id} (${r.nom})` : r.tag_id;
    select.appendChild(opt);
  });

  CANECO_CONVERT = { boards: preview.boards, nb_rows: preview.nb_rows };
  document.getElementById("caneco-convert-confirm").disabled = false;
  renderCanecoConvertTable();
}

function renderCanecoConvertTable() {
  const { boards, nb_rows } = CANECO_CONVERT;
  document.getElementById("caneco-convert-summary").textContent =
    `${boards.length} tableaux/transfos/groupes detectes (${nb_rows} lignes de circuits en attente de conversion).`;

  const allNames = boards.map((b) => b.name).sort((a, b2) => a.localeCompare(b2));
  const TYPE_LABEL = { tableaux: "Tableau", transfos: "Transformateur", groupes_electrogenes: "Groupe electrogene" };

  const table = document.createElement("table");
  table.innerHTML = `<thead><tr><th>Tableau</th><th>Type</th><th>Amont(s)</th></tr></thead>`;
  const tbody = document.createElement("tbody");

  boards.forEach((b) => {
    const tr = document.createElement("tr");
    tr.dataset.board = b.name;
    const style = NODE_TYPE_STYLE[b.type] || { color: "#64748B" };
    const isGroupe = b.type === "groupes_electrogenes";
    const slots = isGroupe ? [] : (b.proposed_amonts.length ? b.proposed_amonts.slice(0, 2) : [""]);

    const amontCellHtml = isGroupe
      ? `<span class="field-hint">source autonome</span>`
      : slots.map((val) => `
          <div class="caneco-amont-row">
            <select class="caneco-amont-select">${canecoAmontOptionsHtml(allNames.filter((n) => n !== b.name), val || "__AUCUN__")}</select>
          </div>
        `).join("") + `<button type="button" class="secondary caneco-add-amont" style="font-size:0.72rem; padding:0.1rem 0.4rem;">+ amont</button>`;

    tr.innerHTML = `
      <td><strong>${escapeXml(b.name)}</strong></td>
      <td><span class="type-chip" style="background:${style.color}">${TYPE_LABEL[b.type] || b.type}</span></td>
      <td class="caneco-amont-cell">${amontCellHtml}</td>
    `;
    tbody.appendChild(tr);

    const addBtn = tr.querySelector(".caneco-add-amont");
    if (addBtn) {
      addBtn.onclick = () => {
        const cell = tr.querySelector(".caneco-amont-cell");
        if (cell.querySelectorAll(".caneco-amont-row").length >= 2) return;
        const div = document.createElement("div");
        div.className = "caneco-amont-row";
        div.innerHTML = `<select class="caneco-amont-select">${canecoAmontOptionsHtml(allNames.filter((n) => n !== b.name), "__AUCUN__")}</select>`;
        cell.insertBefore(div, addBtn);
      };
    }
  });
  table.appendChild(tbody);

  const wrap = document.getElementById("caneco-convert-table-wrap");
  wrap.innerHTML = "";
  wrap.appendChild(table);
}

async function runCanecoConvert() {
  const errorEl = document.getElementById("caneco-convert-error");
  errorEl.textContent = "";
  if (!CANECO_CONVERT) { errorEl.textContent = "Aucune donnee a convertir."; return; }

  const select = document.getElementById("caneco-convert-reseau-select");
  if (!select.value) { errorEl.textContent = "Choisissez un reseau HT de rattachement."; return; }

  const amonts = {};
  document.querySelectorAll("#caneco-convert-table-wrap tbody tr").forEach((tr) => {
    const board = tr.dataset.board;
    const values = Array.from(tr.querySelectorAll(".caneco-amont-select"))
      .map((s) => s.value)
      .filter((v) => v && v !== "__AUCUN__");
    amonts[board] = values;
  });

  const includeCharges = document.getElementById("caneco-convert-include-charges").checked;

  document.getElementById("caneco-convert-progress").style.display = "block";
  document.getElementById("caneco-convert-body").style.display = "none";
  document.getElementById("caneco-convert-confirm").disabled = true;

  try {
    const r = await fetch("/api/projects/import-caneco/staging-convert", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ reseau_ht_tag: select.value, amonts, include_charges: includeCharges }),
    });
    const body = await r.json();
    if (!r.ok) throw new Error(body.error || body.message || "Erreur inconnue");

    const rep = body.report;
    let html = `
      <p><strong>Conversion terminee.</strong></p>
      <ul style="margin:0.4rem 0 0.6rem 1.1rem; padding:0;">
        <li>${rep.tableaux} tableaux</li>
        <li>${rep.transfos} transformateurs</li>
        <li>${rep.groupes_electrogenes} groupes electrogenes</li>
        <li>${rep.cables} cables</li>
        ${includeCharges ? `<li>${rep.charges} charges</li>` : ""}
      </ul>
    `;
    if (rep.warnings && rep.warnings.length) {
      html += `<p style="color:var(--danger); margin-top:0.6rem;"><strong>Avertissements (${rep.warnings.length}) :</strong></p>
        <ul style="margin:0.2rem 0 0 1.1rem; padding:0; color:var(--danger); font-size:0.85rem;">
          ${rep.warnings.map((w) => `<li>${escapeXml(w)}</li>`).join("")}
        </ul>`;
    }
    document.getElementById("caneco-convert-report").innerHTML = html;
    document.getElementById("caneco-convert-report").style.display = "block";
    document.getElementById("caneco-convert-confirm").style.display = "none";
    CANECO_CONVERT = null;
    await loadEquipementsView();
  } catch (e) {
    errorEl.textContent = e.message;
    document.getElementById("caneco-convert-body").style.display = "block";
  } finally {
    document.getElementById("caneco-convert-progress").style.display = "none";
    document.getElementById("caneco-convert-confirm").disabled = false;
  }
}

function wireTopTabs() {
  document.querySelectorAll(".top-tab-btn").forEach((btn) => {
    btn.onclick = () => showTopView(btn.dataset.view);
  });
}

function showTopView(view) {
  document.querySelectorAll(".top-tab-btn").forEach((b) => {
    b.classList.toggle("active", b.dataset.view === view);
  });
  ["equipements", "bilan", "cablesched", "synoptique", "saisie"].forEach((v) => {
    document.getElementById(`view-${v}`).style.display = v === view ? "block" : "none";
  });
  if (view === "synoptique") renderDiagramView();
  if (view === "equipements") loadEquipementsView();
  if (view === "cablesched") loadCableScheduleView();
  if (view === "bilan") loadBilanPuissanceView();
}

// ============================================================
// Vue "Liste des equipements" : arbre + table Tag/Type
// ============================================================

async function loadEquipementsView() {
  const treeRoot = document.getElementById("tree-root");
  treeRoot.innerHTML = "Chargement...";
  try {
    const [tree, graph] = await Promise.all([
      fetch("/api/tree").then((r) => r.json()),
      fetch("/api/graph").then((r) => r.json()),
    ]);
    TREE_DATA = tree;
    GRAPH_NODES = graph.nodes;
    GRAPH_EDGES = graph.edges;
  } catch (e) {
    treeRoot.innerHTML = '<p class="error">Erreur de chargement.</p>';
    return;
  }
  renderTree();
  renderEquipTable(null); // pas de filtre = tout afficher
  renderPalette();
}

// ============================================================
// Palette de glisser-depose (creation rapide d'equipements)
// ============================================================

const PALETTE_ITEMS = [
  "reseau_ht", "tableaux", "transfos", "groupes_electrogenes", "cable", "charge",
];

function renderPalette() {
  const wrap = document.getElementById("palette-list");
  if (!wrap) return;
  wrap.innerHTML = "";
  PALETTE_ITEMS.forEach((table) => {
    const cfg = SCHEMA[table];
    if (!cfg) return;
    const item = document.createElement("div");
    item.className = "palette-item";
    item.textContent = cfg.label;
    item.draggable = true;
    item.style.background = NODE_TYPE_STYLE[table] ? NODE_TYPE_STYLE[table].color : "#334155";
    item.addEventListener("dragstart", (ev) => {
      ev.dataTransfer.setData("text/plain", table);
      item.classList.add("dragging");
    });
    item.addEventListener("dragend", () => item.classList.remove("dragging"));
    wrap.appendChild(item);
  });
}

function renderTree() {
  const root = document.getElementById("tree-root");
  root.innerHTML = "";
  if (!TREE_DATA.length) {
    root.innerHTML = '<p class="tree-empty">Aucun client saisi. Rendez-vous dans "Saisie des donnees".</p>';
    return;
  }
  TREE_DATA.forEach((clientNode) => root.appendChild(buildTreeNode(clientNode, 0, true, [])));
}

// Equipements "racine" d'un site : ceux qui n'ont aucun amont parmi les
// equipements du meme site (typiquement le reseau HT). Point de depart de
// l'arbre electrique. Les charges et les cables sont exclus de l'arbre (les
// cables sont un detail de liaison, pas un equipement a naviguer).
function rootEquipmentForSite(siteTag) {
  const siteNodes = GRAPH_NODES.filter((n) => n.site_id === siteTag && n.type !== "charge" && n.type !== "cable");
  const siteIds = new Set(siteNodes.map((n) => n.id));
  const hasIncoming = new Set();
  GRAPH_EDGES.forEach((e) => {
    if (siteIds.has(e.to)) hasIncoming.add(e.to);
  });
  return siteNodes.filter((n) => !hasIncoming.has(n.id));
}

// Avals "visibles" d'un equipement : on traverse les cables de facon
// transparente (un cable n'est jamais un noeud affiche, seulement un trait
// de liaison) pour retrouver le prochain equipement reel en aval.
function getVisibleDownstream(tagId) {
  const children = {};
  GRAPH_EDGES.forEach((e) => { (children[e.from] = children[e.from] || []).push(e.to); });
  const result = new Set();
  const visited = new Set();
  const queue = [...(children[tagId] || [])];
  while (queue.length) {
    const id = queue.shift();
    if (visited.has(id)) continue;
    visited.add(id);
    const node = GRAPH_NODES.find((n) => n.id === id);
    if (!node) continue;
    if (node.type === "cable") {
      (children[id] || []).forEach((gc) => queue.push(gc));
    } else {
      result.add(id);
    }
  }
  return result;
}

// Avals directs d'un equipement, charges exclues (les charges ne sont
// jamais des noeuds de l'arbre, seulement visibles via la liste de droite).
function directDownstreamNodes(tagId) {
  const ids = getVisibleDownstream(tagId);
  return GRAPH_NODES.filter((n) => ids.has(n.id) && n.type !== "charge");
}

function buildTreeNode(node, level, autoExpand, ancestors) {
  level = level || 0;
  ancestors = ancestors || [];
  const wrap = document.createElement("div");
  wrap.className = "tree-node";

  const row = document.createElement("div");
  row.className = "tree-row";
  row.style.paddingLeft = `${level * 0.2}rem`;

  let childData = [];
  if (node.kind === "site") {
    childData = rootEquipmentForSite(node.tag).map((eq) => ({ kind: "leaf", tag: eq.id, type: eq.type }));
  } else if (node.kind === "leaf") {
    // garde-fou anti-cycle : si ce tag est deja un ancetre dans cette branche, pas d'enfants
    if (!ancestors.includes(node.tag)) {
      childData = directDownstreamNodes(node.tag).map((eq) => ({ kind: "leaf", tag: eq.id, type: eq.type }));
    }
  } else {
    childData = node.children || [];
  }
  const hasChildren = childData.length > 0;

  const caret = document.createElement("span");
  caret.className = "tree-caret";
  caret.textContent = hasChildren ? (autoExpand ? "\u25BE" : "\u25B8") : "";
  row.appendChild(caret);

  const icon = document.createElement("span");
  if (node.kind === "leaf") {
    icon.className = "tree-icon-leaf";
    icon.textContent = "\u2022";
  } else {
    icon.className = "tree-icon-folder";
    icon.textContent = "\u25A0";
  }
  row.appendChild(icon);

  const label = document.createElement("span");
  label.textContent = node.kind === "leaf" ? node.tag : `${node.nom || node.tag}`;
  row.appendChild(label);

  wrap.appendChild(row);

  const childrenBox = document.createElement("div");
  childrenBox.className = "tree-children";
  childrenBox.style.display = autoExpand && hasChildren ? "block" : "none";
  wrap.appendChild(childrenBox);

  const nextAncestors = node.kind === "leaf" ? [...ancestors, node.tag] : ancestors;

  function populateChildren(expandChildren) {
    if (childrenBox.dataset.loaded) return;
    childrenBox.dataset.loaded = "1";
    childData.forEach((child) => {
      childrenBox.appendChild(buildTreeNode(child, level + 1, expandChildren, nextAncestors));
    });
  }

  if (autoExpand && hasChildren) populateChildren(true);

  row.onclick = () => {
    document.querySelectorAll(".tree-row.selected").forEach((r) => r.classList.remove("selected"));
    row.classList.add("selected");

    if (hasChildren) {
      populateChildren(false);
      const isOpen = childrenBox.style.display === "block";
      childrenBox.style.display = isOpen ? "none" : "block";
      caret.textContent = isOpen ? "\u25B8" : "\u25BE";
    }

    if (node.kind === "leaf") {
      renderEquipTable(null, node.tag); // avals directs de l'equipement clique
    } else {
      renderEquipTable({ kind: node.kind, tag: node.tag, nom: node.nom });
    }
  };

  // Cible de glisser-depose : uniquement un site ou un equipement (pas client/projet)
  if (node.kind === "site" || node.kind === "leaf") {
    row.addEventListener("dragover", (ev) => {
      ev.preventDefault();
      row.classList.add("drop-target");
    });
    row.addEventListener("dragleave", () => row.classList.remove("drop-target"));
    row.addEventListener("drop", (ev) => {
      ev.preventDefault();
      row.classList.remove("drop-target");
      const table = ev.dataTransfer.getData("text/plain");
      if (!table) return;
      if (node.kind === "site") {
        openCreateEquipmentModal(table, { siteTag: node.tag, siteLabel: node.nom || node.tag, amontTag: null });
      } else {
        const siteTag = (GRAPH_NODES.find((n) => n.id === node.tag) || {}).site_id;
        openCreateEquipmentModal(table, { siteTag, siteLabel: siteTag, amontTag: node.tag });
      }
    });
  }

  return wrap;
}

// Determine l'ensemble des sites couverts par un scope (client/projet/site)
function sitesForScope(scope) {
  if (!scope) return null; // pas de filtre = tous
  if (scope.kind === "site") return [scope.tag];

  const sites = [];
  TREE_DATA.forEach((clientNode) => {
    if (scope.kind === "client" && clientNode.tag !== scope.tag) return;
    (clientNode.children || []).forEach((projetNode) => {
      if (scope.kind === "projet" && projetNode.tag !== scope.tag) return;
      (projetNode.children || []).forEach((siteNode) => sites.push(siteNode.tag));
    });
  });
  return sites;
}

async function renderEquipTable(scope, singleTag) {
  const title = document.getElementById("list-scope-title");
  let rows;

  if (singleTag) {
    const visibleIds = getVisibleDownstream(singleTag);
    rows = GRAPH_NODES.filter((n) => visibleIds.has(n.id));
    title.textContent = `Avals directs de : ${singleTag}`;
  } else if (scope) {
    const sites = sitesForScope(scope);
    rows = GRAPH_NODES.filter((n) => sites.includes(n.site_id) && n.type !== "cable");
    title.textContent = `${scope.nom || scope.tag}`;
  } else {
    rows = GRAPH_NODES.filter((n) => n.type !== "cable");
    title.textContent = "Tous les equipements";
  }

  const wrap = document.getElementById("equip-table-wrap");
  if (!rows.length) {
    wrap.innerHTML = '<p class="empty">Aucun equipement pour cette selection.</p>';
    return;
  }

  // Quand la selection ne contient que des charges, on affiche toutes les
  // colonnes de la table charge (fiche complete), pas juste Tag/Type/Detail.
  if (rows.every((r) => r.type === "charge")) {
    await renderChargeFullTable(rows, wrap);
    return;
  }

  const table = document.createElement("table");
  table.innerHTML = `<thead><tr><th>Tag</th><th>Type</th><th>Detail</th><th></th></tr></thead>`;
  const tbody = document.createElement("tbody");
  rows.forEach((r) => {
    const style = NODE_TYPE_STYLE[r.type] || { color: "#64748B", label: r.type };
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${escapeXml(r.id)}</td>
      <td><span class="type-chip" style="background:${style.color}">${escapeXml(style.label)}</span></td>
      <td>${r.detail !== null && r.detail !== undefined ? escapeXml(String(r.detail)) : ""}</td>
      <td></td>
    `;
    const tdAction = tr.querySelector("td:last-child");
    const delBtn = document.createElement("button");
    delBtn.className = "btn-del";
    delBtn.textContent = "Supprimer";
    delBtn.onclick = async (ev) => {
      ev.stopPropagation();
      if (!SCHEMA[r.type]) { alert("Type d'equipement inconnu."); return; }
      if (!confirm(`Confirmer la suppression de ${r.id} ?`)) return;
      try {
        await Api.remove(r.type, [r.id]);
        await loadEquipementsView();
      } catch (e) {
        alert(e.message);
      }
    };
    tdAction.appendChild(delBtn);
    tr.ondblclick = () => openEditEquipmentModal(r.id, r.type);
    tr.style.cursor = "pointer";
    tbody.appendChild(tr);
  });
  table.appendChild(tbody);
  wrap.innerHTML = "";
  wrap.appendChild(table);
}

async function renderChargeFullTable(rows, wrap) {
  wrap.innerHTML = "Chargement...";
  const tagSet = new Set(rows.map((r) => r.id));
  let allCharges = [];
  try {
    allCharges = await Api.list("charge");
  } catch (e) {
    wrap.innerHTML = '<p class="error">Impossible de charger le detail des charges.</p>';
    return;
  }
  const chargeRows = allCharges.filter((c) => tagSet.has(c.tag_id));
  const columns = SCHEMA["charge"].columns;

  const scrollWrap = document.createElement("div");
  scrollWrap.className = "charge-full-table-scroll";
  const table = document.createElement("table");
  table.innerHTML = `<thead><tr>${columns.map((c) => `<th>${escapeXml(c.label)}</th>`).join("")}<th></th></tr></thead>`;
  const tbody = document.createElement("tbody");
  chargeRows.forEach((row) => {
    const tr = document.createElement("tr");
    tr.innerHTML = columns.map((c) => {
      const v = row[c.name];
      return `<td>${v !== null && v !== undefined ? escapeXml(String(v)) : ""}</td>`;
    }).join("") + "<td></td>";
    const tdAction = tr.querySelector("td:last-child");
    const delBtn = document.createElement("button");
    delBtn.className = "btn-del";
    delBtn.textContent = "Supprimer";
    delBtn.onclick = async (ev) => {
      ev.stopPropagation();
      if (!confirm(`Confirmer la suppression de ${row.tag_id} ?`)) return;
      try {
        await Api.remove("charge", [row.tag_id]);
        await loadEquipementsView();
      } catch (e) {
        alert(e.message);
      }
    };
    tdAction.appendChild(delBtn);
    tr.ondblclick = () => openEditEquipmentModal(row.tag_id, "charge");
    tr.style.cursor = "pointer";
    tbody.appendChild(tr);
  });
  table.appendChild(tbody);
  scrollWrap.appendChild(table);
  wrap.innerHTML = "";
  wrap.appendChild(scrollWrap);
}

// ============================================================
// Vue "Synoptique" (schema unifilaire, reconstruit depuis /api/graph)
// ============================================================

function escapeXml(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function computeLayers(nodes, edges) {
  const children = {};
  const inDeg = {};
  nodes.forEach((n) => { children[n.id] = []; inDeg[n.id] = 0; });
  edges.forEach((e) => {
    if (children[e.from] && e.to in inDeg) {
      children[e.from].push(e.to);
      inDeg[e.to] += 1;
    }
  });

  const layer = {};
  nodes.forEach((n) => { layer[n.id] = 0; });

  const indegCopy = { ...inDeg };
  const queue = nodes.filter((n) => indegCopy[n.id] === 0).map((n) => n.id);
  const visited = new Set();

  while (queue.length) {
    const id = queue.shift();
    if (visited.has(id)) continue;
    visited.add(id);
    (children[id] || []).forEach((childId) => {
      layer[childId] = Math.max(layer[childId], layer[id] + 1);
      indegCopy[childId] -= 1;
      if (indegCopy[childId] === 0) queue.push(childId);
    });
  }
  return layer;
}

function renderLegend() {
  const el = document.getElementById("diagram-legend");
  el.innerHTML = "";
  Object.values(NODE_TYPE_STYLE).forEach((style) => {
    const chip = document.createElement("span");
    chip.className = "legend-chip";
    chip.innerHTML = `<span class="legend-swatch" style="background:${style.color}"></span>${style.label}`;
    el.appendChild(chip);
  });
}

let DIAGRAM_GRAPH = null;
let DIAGRAM_HIDDEN_NODES = new Set(); // tags manuellement decoches par l'utilisateur

async function renderDiagramView() {
  renderLegend();
  const wrap = document.getElementById("diagram-svg-wrap");
  wrap.innerHTML = "Chargement...";

  try {
    DIAGRAM_GRAPH = await (await fetch("/api/graph")).json();
  } catch (e) {
    wrap.innerHTML = `<p class="error">Impossible de charger le graphe.</p>`;
    return;
  }

  renderEquipmentFilterTree();
  redrawDiagram();
}

function computeHiddenNodeSet(nodes, edges, hiddenRoots) {
  if (!hiddenRoots.size) return new Set();
  const children = {};
  edges.forEach((e) => { (children[e.from] = children[e.from] || []).push(e.to); });
  const hidden = new Set();
  const queue = [];
  hiddenRoots.forEach((tag) => { hidden.add(tag); queue.push(tag); });
  while (queue.length) {
    const id = queue.shift();
    (children[id] || []).forEach((ch) => {
      if (!hidden.has(ch)) { hidden.add(ch); queue.push(ch); }
    });
  }
  return hidden;
}

// Arborescence complete (tous types d'equipements) pour cocher/decocher ce
// qui doit s'afficher dans le synoptique. Decocher un noeud masque aussi
// tous ses avals (recursivement), mais ne change rien aux donnees en base.
function renderEquipmentFilterTree() {
  const container = document.getElementById("tableaux-filter-list");
  if (!container || !DIAGRAM_GRAPH) return;
  container.innerHTML = "";

  const nodes = DIAGRAM_GRAPH.nodes;
  const edges = DIAGRAM_GRAPH.edges;
  const nodeById = {};
  nodes.forEach((n) => { nodeById[n.id] = n; });
  const children = {};
  const hasIncoming = new Set();
  edges.forEach((e) => {
    if (!nodeById[e.from] || !nodeById[e.to]) return;
    (children[e.from] = children[e.from] || []).push(e.to);
    hasIncoming.add(e.to);
  });
  const roots = nodes.filter((n) => !hasIncoming.has(n.id)).sort((a, b) => a.id.localeCompare(b.id));

  function buildNode(n, level, ancestors) {
    const wrap = document.createElement("div");
    wrap.className = "tree-node";

    const row = document.createElement("div");
    row.className = "filter-tree-row";
    row.style.paddingLeft = `${level * 0.85}rem`;

    const kidIds = (children[n.id] || []).filter((id) => nodeById[id] && !ancestors.includes(id));
    const hasKids = kidIds.length > 0;

    const caret = document.createElement("span");
    caret.className = "tree-caret";
    caret.textContent = hasKids ? "\u25BE" : "";
    row.appendChild(caret);

    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.checked = !DIAGRAM_HIDDEN_NODES.has(n.id);
    checkbox.onclick = (ev) => {
      ev.stopPropagation();
      if (checkbox.checked) {
        DIAGRAM_HIDDEN_NODES.delete(n.id);
      } else {
        // decoche aussi tous les avals (recursivement), dans l'arbre et pas
        // seulement dans le dessin
        const toHide = computeHiddenNodeSet(DIAGRAM_GRAPH.nodes, DIAGRAM_GRAPH.edges, new Set([n.id]));
        toHide.forEach((id) => DIAGRAM_HIDDEN_NODES.add(id));
      }
      renderEquipmentFilterTree();
      redrawDiagram();
    };
    row.appendChild(checkbox);

    const style = NODE_TYPE_STYLE[n.type] || { color: "#64748B", label: n.type };
    const swatch = document.createElement("span");
    swatch.className = "filter-tree-swatch";
    swatch.style.background = style.color;
    row.appendChild(swatch);

    const label = document.createElement("span");
    label.className = "filter-tree-label";
    label.textContent = n.id;
    label.title = `${n.id} (${style.label})`;
    row.appendChild(label);

    wrap.appendChild(row);

    const childrenBox = document.createElement("div");
    childrenBox.style.display = hasKids ? "block" : "none";
    wrap.appendChild(childrenBox);

    if (hasKids) {
      kidIds
        .map((id) => nodeById[id])
        .sort((a, b) => a.id.localeCompare(b.id))
        .forEach((child) => childrenBox.appendChild(buildNode(child, level + 1, [...ancestors, n.id])));

      row.onclick = () => {
        const isOpen = childrenBox.style.display === "block";
        childrenBox.style.display = isOpen ? "none" : "block";
        caret.textContent = isOpen ? "\u25B8" : "\u25BE";
      };
    }

    return wrap;
  }

  if (!roots.length) {
    container.innerHTML = '<p class="empty">Aucun equipement.</p>';
    return;
  }
  roots.forEach((r) => container.appendChild(buildNode(r, 0, [])));
}

function redrawDiagram() {
  const wrap = document.getElementById("diagram-svg-wrap");
  if (!DIAGRAM_GRAPH) return;

  const hiddenSet = computeHiddenNodeSet(DIAGRAM_GRAPH.nodes, DIAGRAM_GRAPH.edges, DIAGRAM_HIDDEN_NODES);
  const nodes = DIAGRAM_GRAPH.nodes.filter((n) => !hiddenSet.has(n.id));
  const edges = DIAGRAM_GRAPH.edges.filter((e) => !hiddenSet.has(e.from) && !hiddenSet.has(e.to));

  if (!DIAGRAM_GRAPH.nodes.length) {
    wrap.innerHTML = '<p class="empty">Aucun equipement saisi pour le moment. Ajoutez un reseau HT, un transfo, un tableau... puis revenez ici.</p>';
    return;
  }
  if (!nodes.length) {
    wrap.innerHTML = '<p class="empty">Tous les tableaux sont masques. Cochez-en au moins un dans le panneau de gauche.</p>';
    return;
  }

  const layer = computeLayers(nodes, edges);
  const layers = {};
  nodes.forEach((n) => {
    const l = layer[n.id];
    (layers[l] = layers[l] || []).push(n);
  });
  const layerKeys = Object.keys(layers).map(Number).sort((a, b) => a - b);

  // A compact electrical drawing grid: symbols sit freely in the cells,
  // while the grid remains a drafting guide rather than a component frame.
  const CELL_SIZE = 80, NODE_W = CELL_SIZE, NODE_H = CELL_SIZE, MARGIN = 0;
  // A component row followed by one link-only row: connections therefore
  // occupy exactly one grid square vertically before the next component.
  const LAYER_STRIDE = CELL_SIZE * 2;

  let maxRowWidth = 0;
  layerKeys.forEach((l) => {
    const w = layers[l].length * CELL_SIZE;
    maxRowWidth = Math.max(maxRowWidth, w);
  });

  const positions = {};
  layerKeys.forEach((l) => {
    const rowNodes = layers[l];
    const rowWidth = rowNodes.length * CELL_SIZE;
    const startX = MARGIN + (maxRowWidth - rowWidth) / 2;
    rowNodes.forEach((n, i) => {
      positions[n.id] = {
        x: startX + i * CELL_SIZE,
        y: MARGIN + l * LAYER_STRIDE,
      };
    });
  });

  const svgWidth = Math.max(maxRowWidth + MARGIN * 2, 300);
  const svgHeight = MARGIN * 2 + (layerKeys.length - 1) * LAYER_STRIDE + CELL_SIZE;

  const parts = [];
  parts.push(
    '<defs>' +
    `<pattern id="diagram-grid" width="${CELL_SIZE}" height="${CELL_SIZE}" patternUnits="userSpaceOnUse">` +
    `<path d="M ${CELL_SIZE} 0 L 0 0 0 ${CELL_SIZE}" fill="none" stroke="#D8E2EE" stroke-width="1"/></pattern>` +
    '</defs>'
  );
  parts.push(`<rect x="0" y="0" width="${svgWidth}" height="${svgHeight}" fill="url(#diagram-grid)"/>`);

  edges.forEach((e) => {
    const p1 = positions[e.from], p2 = positions[e.to];
    if (!p1 || !p2) return;
    const x1 = p1.x + NODE_W / 2, y1 = p1.y + NODE_H;
    const x2 = p2.x + NODE_W / 2, y2 = p2.y;
    const midY = (y1 + y2) / 2;
    parts.push(
      `<path d="M${x1},${y1} C${x1},${midY} ${x2},${midY} ${x2},${y2}" ` +
      'stroke="#4B5563" stroke-width="1.6" fill="none" />'
    );
  });

  nodes.forEach((n) => {
    const p = positions[n.id];
    if (!p) return;
    const style = NODE_TYPE_STYLE[n.type] || { color: "#64748B", label: n.type };
    const detail = n.detail !== null && n.detail !== undefined && n.detail !== "" ? String(n.detail) : "";

    if (n.type === "reseau_ht") {
      const box = 46, x = p.x + (NODE_W - box) / 2, y = p.y + (NODE_H - box) / 2;
      parts.push(`
        <g>
          <title>${escapeXml(`${style.label}: ${n.id}`)}</title>
          <rect x="${x}" y="${y}" width="${box}" height="${box}" fill="#FFFFFF" stroke="${style.color}" stroke-width="3"/>
          <line x1="${x + 3}" y1="${y + 3}" x2="${x + box - 3}" y2="${y + box - 3}" stroke="${style.color}" stroke-width="3"/>
          <line x1="${x + box - 3}" y1="${y + 3}" x2="${x + 3}" y2="${y + box - 3}" stroke="${style.color}" stroke-width="3"/>
        </g>
      `);
      return;
    }

    if (n.type === "cable") {
      const cx = p.x + NODE_W / 2;
      const barW = 14, barH = 9, term = 8;
      parts.push(`
        <g>
          <title>${escapeXml(`${style.label}: ${n.id}`)}</title>
          <line x1="${cx}" y1="${p.y}" x2="${cx}" y2="${p.y + NODE_H}" stroke="${style.color}" stroke-width="2"/>
          <rect x="${cx - term / 2}" y="${p.y - 1}" width="${term}" height="${term}" fill="${style.color}"/>
          <rect x="${cx - term / 2}" y="${p.y + NODE_H - term + 1}" width="${term}" height="${term}" fill="${style.color}"/>
          <rect x="${cx - barW / 2}" y="${p.y + NODE_H / 2 - barH / 2}" width="${barW}" height="${barH}" fill="${style.color}"/>
        </g>
      `);
      return;
    }

    if (n.type === "transfos") {
      const cx = p.x + NODE_W / 2;
      const r = 13, term = 8;
      const c1y = p.y + NODE_H / 2 - r * 0.55;
      const c2y = p.y + NODE_H / 2 + r * 0.55;
      parts.push(`
        <g>
          <title>${escapeXml(`${style.label}: ${n.id}${detail ? ` — ${detail} kVA` : ""}`)}</title>
          <line x1="${cx}" y1="${p.y}" x2="${cx}" y2="${c1y - r}" stroke="${style.color}" stroke-width="2"/>
          <line x1="${cx}" y1="${c2y + r}" x2="${cx}" y2="${p.y + NODE_H}" stroke="${style.color}" stroke-width="2"/>
          <rect x="${cx - term / 2}" y="${p.y - 1}" width="${term}" height="${term}" fill="${style.color}"/>
          <rect x="${cx - term / 2}" y="${p.y + NODE_H - term + 1}" width="${term}" height="${term}" fill="${style.color}"/>
          <circle cx="${cx}" cy="${c1y}" r="${r}" fill="#FFFFFF" stroke="${style.color}" stroke-width="1.8"/>
          <circle cx="${cx}" cy="${c2y}" r="${r}" fill="none" stroke="${style.color}" stroke-width="1.8"/>
        </g>
      `);
      return;
    }

    if (n.type === "groupes_electrogenes") {
      const cx = p.x + NODE_W / 2;
      const r = 15, term = 8;
      const cy = p.y + NODE_H / 2 - 4;
      parts.push(`
        <g>
          <title>${escapeXml(`${style.label}: ${n.id}${detail ? ` — ${detail} kVA` : ""}`)}</title>
          <line x1="${cx}" y1="${cy + r}" x2="${cx}" y2="${p.y + NODE_H}" stroke="${style.color}" stroke-width="2"/>
          <rect x="${cx - term / 2}" y="${p.y + NODE_H - term + 1}" width="${term}" height="${term}" fill="${style.color}"/>
          <circle cx="${cx}" cy="${cy}" r="${r}" fill="#FFFFFF" stroke="${style.color}" stroke-width="1.8"/>
          <text x="${cx}" y="${cy + 4}" text-anchor="middle" font-size="11" fill="${style.color}" font-family="Calibri, Arial" font-weight="bold">GE</text>
        </g>
      `);
      return;
    }

    if (n.type === "tableaux") {
      const cx = p.x + NODE_W / 2;
      const textY = p.y + NODE_H / 2 + 4;
      const underlineW = Math.max(34, n.id.length * 7.2);
      parts.push(`
        <g>
          <title>${escapeXml(`${style.label}: ${n.id}`)}</title>
          <text x="${cx}" y="${textY}" text-anchor="middle" font-size="12.5" fill="#1B2A3A" font-family="Calibri, Arial" font-weight="bold">${escapeXml(n.id)}</text>
          <line x1="${cx - underlineW / 2}" y1="${textY + 6}" x2="${cx + underlineW / 2}" y2="${textY + 6}" stroke="#1B2A3A" stroke-width="1.3"/>
        </g>
      `);
      return;
    }

    parts.push(`
      <g>
        <title>${escapeXml(`${style.label}: ${n.id}${detail ? ` — ${detail}` : ""}`)}</title>
        <rect x="${p.x + 18}" y="${p.y + 18}" width="44" height="44" fill="${style.color}"/>
        <rect x="${p.x + 12}" y="${p.y + 12}" width="56" height="6" fill="${style.color}"/>
        <rect x="${p.x + 12}" y="${p.y + 62}" width="56" height="6" fill="${style.color}"/>
      </g>
    `);
  });

  wrap.innerHTML =
    `<div class="diagram-svg-canvas" id="diagram-svg-canvas"><svg viewBox="0 0 ${svgWidth} ${svgHeight}" width="${svgWidth}" height="${svgHeight}" xmlns="http://www.w3.org/2000/svg">${parts.join("")}</svg></div>`;
  applyDiagramZoom();
}

async function runCableScheduleExport() {
  const nameInput = document.getElementById("cable-export-filename");
  const folderInput = document.getElementById("cable-export-folder");
  const errorEl = document.getElementById("cable-export-error");
  const successEl = document.getElementById("cable-export-success");
  errorEl.textContent = "";
  successEl.style.display = "none";

  const filename = nameInput.value.trim();
  const folder = folderInput.value.trim();
  if (!filename) { errorEl.textContent = "Le nom du fichier est obligatoire."; return; }
  if (!folder) { errorEl.textContent = "Le dossier de destination est obligatoire."; return; }

  document.getElementById("cable-export-confirm").disabled = true;
  try {
    const r = await fetch("/api/cable-schedule/export", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ folder, filename }),
    });
    const body = await r.json();
    if (!r.ok) throw new Error(body.error || "Erreur inconnue");
    successEl.textContent = `Fichier cree : ${body.path} (${body.nb_rows} lignes)`;
    successEl.style.display = "block";
  } catch (e) {
    errorEl.textContent = e.message;
  } finally {
    document.getElementById("cable-export-confirm").disabled = false;
  }
}

// ============================================================
// Import Caneco - table de preparation (staging), avant conversion
// ============================================================

const STAGING_FIELDS = [
  "amont_normal", "amont_secours", "board_repere", "board_designation",
  "circuit_repere", "circuit_designation", "nombre", "consommation", "alimentation",
  "jdb_amont", "liaison_type", "longueur", "ame", "l_max_prot",
  "delta_u_circuit", "delta_u_totale", "cable", "neutre", "pe_pen", "separe",
  "taux_harmonique", "protection", "calibre", "i_delta_n", "ir", "im_isd",
  "affectation_phases", "type_detecte",
];
const STAGING_LABELS = {
  amont_normal: "Normal", amont_secours: "Secours",
  board_repere: "Repere (tableau)", board_designation: "Designation (tableau)",
  circuit_repere: "Repere (circuit)", circuit_designation: "Designation (circuit)",
  nombre: "Nb", consommation: "Consommation",
  alimentation: "Alimentation", jdb_amont: "JdB Amont", liaison_type: "Type",
  longueur: "Longueur", ame: "Ame", l_max_prot: "L.Max prot.",
  delta_u_circuit: "\u0394U Circuit", delta_u_totale: "\u0394U Totale", cable: "Cable",
  neutre: "Neutre", pe_pen: "PE/PEN", separe: "Separe", taux_harmonique: "Taux Harm.",
  protection: "Protection", calibre: "Calibre", i_delta_n: "I\u2206n",
  ir: "Ir", im_isd: "Im / Isd", affectation_phases: "Affectation des phases",
  type_detecte: "Type",
};

let CANECO_STAGING_ROWS = null;

function openCanecoStagingUploadModal() {
  document.getElementById("caneco-staging-file").value = "";
  document.getElementById("caneco-staging-upload-error").textContent = "";
  document.getElementById("caneco-staging-upload-progress").style.display = "none";
  openModal("modal-caneco-staging-upload");
}

async function runCanecoStagingAnalyze() {
  const fileInput = document.getElementById("caneco-staging-file");
  const errorEl = document.getElementById("caneco-staging-upload-error");
  const progressEl = document.getElementById("caneco-staging-upload-progress");
  errorEl.textContent = "";
  if (!fileInput.files.length) { errorEl.textContent = "Choisissez un fichier PDF."; return; }

  const formData = new FormData();
  formData.append("file", fileInput.files[0]);
  progressEl.style.display = "block";
  document.getElementById("caneco-staging-upload-analyze").disabled = true;
  try {
    const r = await fetch("/api/projects/import-caneco/staging-analyze", { method: "POST", body: formData });
    const body = await r.json();
    if (!r.ok) throw new Error(body.error || "Erreur inconnue");
    CANECO_STAGING_ROWS = body.rows;
    closeModal();
    openCanecoStagingReviewModal();
  } catch (e) {
    errorEl.textContent = e.message;
  } finally {
    progressEl.style.display = "none";
    document.getElementById("caneco-staging-upload-analyze").disabled = false;
  }
}

function openCanecoStagingReviewModal() {
  document.getElementById("caneco-staging-error").textContent = "";
  document.getElementById("caneco-staging-report").style.display = "none";
  document.getElementById("caneco-staging-confirm").style.display = "inline-block";
  document.getElementById("caneco-staging-table-wrap").style.display = "block";
  document.getElementById("caneco-staging-summary").textContent =
    `${CANECO_STAGING_ROWS.length} circuits extraits. Corrigez librement chaque case si besoin, puis confirmez le chargement.`;

  const headHtml = STAGING_FIELDS.map((f) => `<th>${escapeXml(STAGING_LABELS[f])}</th>`).join("");
  const bodyHtml = CANECO_STAGING_ROWS.map((row) => {
    const cells = STAGING_FIELDS
      .map((f) => `<td contenteditable="true" data-field="${f}">${escapeXml(row[f] || "")}</td>`)
      .join("");
    return `<tr>${cells}</tr>`;
  }).join("");

  const wrap = document.getElementById("caneco-staging-table-wrap");
  wrap.innerHTML = `<table><thead><tr>${headHtml}</tr></thead><tbody>${bodyHtml}</tbody></table>`;

  openModal("modal-caneco-staging");
}

async function runCanecoStagingConfirm() {
  const errorEl = document.getElementById("caneco-staging-error");
  errorEl.textContent = "";
  if (!CANECO_STAGING_ROWS) { errorEl.textContent = "Session expiree, relancez l'analyse."; return; }

  // relit les valeurs (eventuellement corrigees a la main) directement
  // depuis le tableau affiche, plutot que de garder la version d'origine
  const trs = document.querySelectorAll("#caneco-staging-table-wrap tbody tr");
  const rows = [];
  trs.forEach((tr) => {
    const row = {};
    tr.querySelectorAll("td").forEach((td) => {
      row[td.dataset.field] = td.textContent.trim();
    });
    rows.push(row);
  });

  document.getElementById("caneco-staging-progress").style.display = "block";
  document.getElementById("caneco-staging-table-wrap").style.display = "none";
  document.getElementById("caneco-staging-confirm").disabled = true;

  try {
    const r = await fetch("/api/projects/import-caneco/staging-confirm", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ rows }),
    });
    const body = await r.json();
    if (!r.ok) throw new Error(body.error || "Erreur inconnue");
    document.getElementById("caneco-staging-report").textContent =
      `${body.nb_rows} circuits charges dans la table "Import Caneco".`;
    document.getElementById("caneco-staging-report").style.display = "block";
    document.getElementById("caneco-staging-confirm").style.display = "none";
    CANECO_STAGING_ROWS = null;
  } catch (e) {
    errorEl.textContent = e.message;
    document.getElementById("caneco-staging-table-wrap").style.display = "block";
  } finally {
    document.getElementById("caneco-staging-progress").style.display = "none";
    document.getElementById("caneco-staging-confirm").disabled = false;
  }
}

// ============================================================
// Import de charges depuis un fichier Excel (avec correspondance de champs)
// ============================================================

let EXCEL_IMPORT_STATE = null; // { session_id, charge_columns, excel_columns, preview_rows }

async function openExcelImportModal() {
  document.getElementById("excel-file").value = "";
  document.getElementById("excel-import-error").textContent = "";
  document.getElementById("excel-import-progress").style.display = "none";
  openModal("modal-import-excel");

  const noReseauEl = document.getElementById("excel-no-reseau");
  const analyzeBtn = document.getElementById("excel-import-analyze");
  let reseaux = [];
  try {
    reseaux = await Api.list("reseau_ht");
  } catch (e) {
    reseaux = [];
  }
  if (!reseaux.length) {
    noReseauEl.style.display = "block";
    analyzeBtn.disabled = true;
  } else {
    noReseauEl.style.display = "none";
    analyzeBtn.disabled = false;
  }
}

async function runExcelAnalyze() {
  const fileInput = document.getElementById("excel-file");
  const errorEl = document.getElementById("excel-import-error");
  const progressEl = document.getElementById("excel-import-progress");
  errorEl.textContent = "";

  if (!fileInput.files.length) { errorEl.textContent = "Choisissez un fichier Excel."; return; }

  const formData = new FormData();
  formData.append("file", fileInput.files[0]);

  progressEl.style.display = "block";
  document.getElementById("excel-import-analyze").disabled = true;
  try {
    const r = await fetch("/api/projects/import-excel/analyze", { method: "POST", body: formData });
    const body = await r.json();
    if (!r.ok) throw new Error(body.error || body.message || "Erreur inconnue");

    EXCEL_IMPORT_STATE = body;
    closeModal();
    openExcelMappingModal();
  } catch (e) {
    errorEl.textContent = e.message;
  } finally {
    progressEl.style.display = "none";
    document.getElementById("excel-import-analyze").disabled = false;
  }
}

function openExcelMappingModal() {
  const { charge_columns, excel_columns, suggested_mapping, preview_rows, reseaux_ht, nb_data_rows } = EXCEL_IMPORT_STATE;

  document.getElementById("excel-mapping-error").textContent = "";
  document.getElementById("excel-import-report").style.display = "none";
  document.getElementById("excel-mapping-table-wrap").style.display = "block";
  document.getElementById("excel-mapping-confirm").style.display = "inline-block";

  const siteSelect = document.getElementById("excel-site-select");
  siteSelect.innerHTML = reseaux_ht.map((r) => `<option value="${r.tag_id}">${escapeXml(r.nom && r.nom !== r.tag_id ? `${r.tag_id} (${r.nom})` : r.tag_id)}</option>`).join("");

  const excelOptionsHtml = (selected) => {
    const opts = [`<option value="">-- ignorer --</option>`, ...excel_columns.map((c) => `<option value="${c.replace(/"/g, "&quot;")}">${escapeXml(c)}</option>`)];
    return opts.map((o) => (selected && o.includes(`value="${selected}"`) ? o.replace("<option ", "<option selected ") : o)).join("");
  };

  const table = document.createElement("table");
  table.innerHTML = `<thead><tr><th>Champ (table Charge)</th><th>Colonne du fichier</th></tr></thead>`;
  const tbody = document.createElement("tbody");
  charge_columns.forEach((col) => {
    const tr = document.createElement("tr");
    const label = col.name === "tag_id" ? `${col.label} *` : col.label;
    tr.innerHTML = `
      <td>${escapeXml(label)}</td>
      <td><select class="excel-mapping-select" data-field="${col.name}">${excelOptionsHtml(suggested_mapping[col.name])}</select></td>
    `;
    tbody.appendChild(tr);
  });
  table.appendChild(tbody);
  const mappingWrap = document.getElementById("excel-mapping-table-wrap");
  mappingWrap.innerHTML = "";
  mappingWrap.appendChild(table);

  const previewWrap = document.getElementById("excel-preview-table-wrap");
  if (preview_rows.length) {
    const ptable = document.createElement("table");
    ptable.innerHTML = `<thead><tr>${excel_columns.map((c) => `<th>${escapeXml(c)}</th>`).join("")}</tr></thead>`;
    const ptbody = document.createElement("tbody");
    preview_rows.forEach((row) => {
      const tr = document.createElement("tr");
      tr.innerHTML = row.map((v) => `<td>${escapeXml(v)}</td>`).join("");
      ptbody.appendChild(tr);
    });
    ptable.appendChild(ptbody);
    previewWrap.innerHTML = "";
    previewWrap.appendChild(ptable);
  } else {
    previewWrap.innerHTML = `<p class="empty">Aucune ligne de donnees a previsualiser.</p>`;
  }

  openModal("modal-excel-mapping");
}

async function runExcelImportConfirm() {
  const errorEl = document.getElementById("excel-mapping-error");
  errorEl.textContent = "";
  if (!EXCEL_IMPORT_STATE) { errorEl.textContent = "Session expiree, relancez l'analyse."; return; }

  const reseauHtTag = document.getElementById("excel-site-select").value;
  if (!reseauHtTag) { errorEl.textContent = "Choisissez un reseau HT de rattachement."; return; }

  const mapping = {};
  document.querySelectorAll(".excel-mapping-select").forEach((sel) => {
    if (sel.value) mapping[sel.dataset.field] = sel.value;
  });
  if (!mapping.tag_id) { errorEl.textContent = "Le champ Tag doit etre associe a une colonne du fichier."; return; }

  document.getElementById("excel-mapping-progress").style.display = "block";
  document.getElementById("excel-mapping-table-wrap").style.display = "none";
  document.getElementById("excel-mapping-confirm").disabled = true;

  try {
    const r = await fetch("/api/projects/import-excel/confirm", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: EXCEL_IMPORT_STATE.session_id, reseau_ht_tag: reseauHtTag, mapping }),
    });
    const body = await r.json();
    if (!r.ok) throw new Error(body.error || body.message || "Erreur inconnue");

    const rep = body.report;
    let html = `<p><strong>Import termine.</strong></p>
      <ul style="margin:0.4rem 0 0.6rem 1.1rem; padding:0;">
        <li>${rep.created} charges creees</li>
        <li>${rep.skipped} lignes ignorees</li>
      </ul>`;
    if (rep.warnings && rep.warnings.length) {
      html += `<p style="color:var(--danger); margin-top:0.6rem;"><strong>Avertissements (${rep.warnings.length}) :</strong></p>
        <ul style="margin:0.2rem 0 0 1.1rem; padding:0; color:var(--danger); font-size:0.85rem;">
          ${rep.warnings.map((w) => `<li>${escapeXml(w)}</li>`).join("")}
        </ul>`;
    }
    document.getElementById("excel-import-report").innerHTML = html;
    document.getElementById("excel-import-report").style.display = "block";
    document.getElementById("excel-mapping-confirm").style.display = "none";
    EXCEL_IMPORT_STATE = null;
    await loadEquipementsView();
  } catch (e) {
    errorEl.textContent = e.message;
    document.getElementById("excel-mapping-table-wrap").style.display = "block";
  } finally {
    document.getElementById("excel-mapping-progress").style.display = "none";
    document.getElementById("excel-mapping-confirm").disabled = false;
  }
}

// ============================================================
// Export de la base de donnees (Access .accdb / script SQL)
// ============================================================

let EXPORT_DB_KIND = "sql";

async function openExportDbModal(kind) {
  EXPORT_DB_KIND = kind;
  const titleEl = document.getElementById("export-db-title");
  const hintEl = document.getElementById("export-db-hint");
  const filenameEl = document.getElementById("export-db-filename");
  const errorEl = document.getElementById("export-db-error");
  const warningsEl = document.getElementById("export-db-warnings");
  const successEl = document.getElementById("export-db-success");

  errorEl.textContent = "";
  warningsEl.style.display = "none";
  successEl.style.display = "none";
  document.getElementById("export-db-folder").value = DEFAULT_FOLDER;

  if (kind === "accdb") {
    titleEl.textContent = "Exporter vers Microsoft Access (.accdb)";
    filenameEl.value = "NormaGrid_Export.accdb";
    hintEl.textContent = "Necessite Microsoft Access (ou le moteur Access Database Engine) installe sur ce poste.";
    hintEl.style.display = "block";
    try {
      const r = await fetch("/api/projects/export-accdb-available");
      const body = await r.json();
      if (!body.available) {
        errorEl.textContent = "Microsoft Access (ou pywin32/pyodbc) n'est pas detecte sur ce poste. L'export .accdb echouera probablement. Vous pouvez essayer quand meme, ou utiliser le script SQL universel.";
      }
    } catch (e) { /* verification indicative seulement */ }
  } else {
    titleEl.textContent = "Exporter vers un script SQL universel";
    filenameEl.value = "NormaGrid_Export.sql";
    hintEl.textContent = "Contient toutes les tables, leurs relations (cles etrangeres) et les donnees. Importable dans Access via Creer > Requete > Mode SQL.";
    hintEl.style.display = "block";
  }

  openModal("modal-export-db");
}

async function runExportDb() {
  const filenameEl = document.getElementById("export-db-filename");
  const folderEl = document.getElementById("export-db-folder");
  const errorEl = document.getElementById("export-db-error");
  const warningsEl = document.getElementById("export-db-warnings");
  const successEl = document.getElementById("export-db-success");
  errorEl.textContent = "";
  warningsEl.style.display = "none";
  successEl.style.display = "none";

  const filename = filenameEl.value.trim();
  const folder = folderEl.value.trim();
  if (!filename) { errorEl.textContent = "Le nom du fichier est obligatoire."; return; }
  if (!folder) { errorEl.textContent = "Le dossier de destination est obligatoire."; return; }

  const endpoint = EXPORT_DB_KIND === "accdb" ? "/api/projects/export-accdb" : "/api/projects/export-sql";
  document.getElementById("export-db-confirm").disabled = true;
  try {
    const r = await fetch(endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ folder, filename }),
    });
    const body = await r.json();
    if (!r.ok) throw new Error(body.error || "Erreur inconnue");

    successEl.textContent = `Fichier cree : ${body.path}`;
    successEl.style.display = "block";
    if (body.warnings && body.warnings.length) {
      warningsEl.innerHTML = `<strong>Relations non creees (${body.warnings.length}) :</strong><br>` +
        body.warnings.map((w) => escapeXml(w)).join("<br>");
      warningsEl.style.display = "block";
    }
  } catch (e) {
    errorEl.textContent = e.message;
  } finally {
    document.getElementById("export-db-confirm").disabled = false;
  }
}

// ============================================================
// Carnet de cables (tenant / aboutissant) - vue dediee avec filtre par colonne
// ============================================================

let CABLE_SCHEDULE_DATA = [];
const CABLE_SCHEDULE_COLUMNS = [
  { key: "tenant", label: "Tenant (origine)" },
  { key: "type_origine", label: "Type origine" },
  { key: "aboutissant", label: "Aboutissant (destination)" },
  { key: "type_destination", label: "Type destination" },
  { key: "designation", label: "Designation" },
  { key: "type_cable", label: "Type de cable" },
  { key: "section", label: "Section" },
  { key: "longueur_m", label: "Longueur" },
  { key: "protection_modele", label: "Protection" },
  { key: "calibre_a", label: "Calibre (A)" },
  { key: "differentiel_ma", label: "Differentiel (mA)" },
];
let CABLE_SCHEDULE_FILTERS = {};

// ============================================================
// Bilan de puissance (une ligne par charge + total general)
// ============================================================

const BILAN_COLUMNS = [
  { key: "designation", label: "Designation" },
  { key: "switchgear_mcc", label: "Switchgear / MCC" },
  { key: "equipment_tag_no", label: "Equipment Tag No" },
  { key: "e_ne", label: "E/NE" },
  { key: "pct_e", label: "% E" },
  { key: "type_equipement", label: "Type" },
  { key: "c_i", label: "Service I/C" },
  { key: "w_s", label: "W/S" },
  { key: "puissance_apparente_unitaire", label: "P. Apparente Unit. (kVA)", round: 2 },
  { key: "puissance_installee", label: "P. Installee" },
  { key: "unite", label: "Unite" },
  { key: "rendement", label: "Rendement" },
  { key: "puissance_active_unitaire", label: "P. Active Unit. (kW)", round: 2 },
  { key: "nombre", label: "Nombre" },
  { key: "cos_phi", label: "Cos \u03c6" },
  { key: "puissance_reactive_unitaire", label: "P. Reactive Unit. (kvar)", round: 2 },
  { key: "k_util", label: "K.Util" },
  { key: "k_simul", label: "K.Simul" },
  { key: "puissance_active_foisonnee", label: "P. Active Foisonnee (kW)", round: 2 },
  { key: "puissance_reactive_foisonnee", label: "P. Reactive Foisonnee (kvar)", round: 2 },
  { key: "alimentation", label: "Alimentation (V)" },
];

function bilanCellText(row, col) {
  const v = row[col.key];
  if (v === null || v === undefined || v === "") return "";
  if (typeof v === "number" && col.round !== undefined) return v.toFixed(col.round);
  return String(v);
}

async function runBilanExport() {
  const nameInput = document.getElementById("bilan-export-filename");
  const folderInput = document.getElementById("bilan-export-folder");
  const errorEl = document.getElementById("bilan-export-error");
  const successEl = document.getElementById("bilan-export-success");
  errorEl.textContent = "";
  successEl.style.display = "none";

  const filename = nameInput.value.trim();
  const folder = folderInput.value.trim();
  if (!filename) { errorEl.textContent = "Le nom du fichier est obligatoire."; return; }
  if (!folder) { errorEl.textContent = "Le dossier de destination est obligatoire."; return; }

  document.getElementById("bilan-export-confirm").disabled = true;
  try {
    const r = await fetch("/api/bilan-puissance/export", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ folder, filename }),
    });
    const body = await r.json();
    if (!r.ok) throw new Error(body.error || "Erreur inconnue");
    successEl.textContent = `Fichier cree : ${body.path} (${body.nb_sheets} feuille(s))`;
    successEl.style.display = "block";
  } catch (e) {
    errorEl.textContent = e.message;
  } finally {
    document.getElementById("bilan-export-confirm").disabled = false;
  }
}

let BILAN_DATA = null;

async function loadBilanPuissanceView() {
  const wrap = document.getElementById("bilan-table-wrap");
  wrap.innerHTML = "Chargement...";
  try {
    BILAN_DATA = await (await fetch("/api/bilan-puissance")).json();
  } catch (e) {
    wrap.innerHTML = '<p class="error">Impossible de charger le bilan de puissance.</p>';
    return;
  }

  const select = document.getElementById("bilan-switchgear-filter");
  const values = Array.from(new Set(BILAN_DATA.rows.map((r) => r.switchgear_mcc).filter((v) => v))).sort((a, b) => a.localeCompare(b));
  select.innerHTML = '<option value="">-- tous --</option>' + values.map((v) => `<option value="${v.replace(/"/g, "&quot;")}">${escapeXml(v)}</option>`).join("");

  renderBilanPuissance();
}

function renderBilanPuissance() {
  if (!BILAN_DATA) return;
  const filterVal = document.getElementById("bilan-switchgear-filter").value;
  const rows = filterVal ? BILAN_DATA.rows.filter((r) => r.switchgear_mcc === filterVal) : BILAN_DATA.rows;

  renderBilanKpiCards(rows, BILAN_DATA.tension_ht_kv);

  const wrap = document.getElementById("bilan-table-wrap");
  if (!rows.length) {
    wrap.innerHTML = '<p class="empty">Aucune charge pour cette selection.</p>';
    return;
  }

  const table = document.createElement("table");
  table.innerHTML = `<thead><tr>${BILAN_COLUMNS.map((c) => `<th>${escapeXml(c.label)}</th>`).join("")}</tr></thead>`;
  const tbody = document.createElement("tbody");
  let sumActiveFois = 0, sumReactiveFois = 0;
  rows.forEach((row) => {
    const tr = document.createElement("tr");
    tr.innerHTML = BILAN_COLUMNS.map((c) => `<td>${escapeXml(bilanCellText(row, c))}</td>`).join("");
    tbody.appendChild(tr);
    if (typeof row.puissance_active_foisonnee === "number") sumActiveFois += row.puissance_active_foisonnee;
    if (typeof row.puissance_reactive_foisonnee === "number") sumReactiveFois += row.puissance_reactive_foisonnee;
  });
  table.appendChild(tbody);

  const tfoot = document.createElement("tfoot");
  const totalTr = document.createElement("tr");
  totalTr.style.fontWeight = "700";
  totalTr.innerHTML = BILAN_COLUMNS.map((c) => {
    if (c.key === "puissance_active_foisonnee") return `<td>${sumActiveFois.toFixed(2)}</td>`;
    if (c.key === "puissance_reactive_foisonnee") return `<td>${sumReactiveFois.toFixed(2)}</td>`;
    if (c.key === "designation") return `<td>Total ${filterVal ? "(filtre)" : "general"}</td>`;
    return "<td></td>";
  }).join("");
  tfoot.appendChild(totalTr);
  table.appendChild(tfoot);

  wrap.innerHTML = "";
  wrap.appendChild(table);
}

function renderBilanKpiCards(rows, tensionHtKv) {
  const container = document.getElementById("bilan-kpi-cards");

  const kwInstalles = rows.reduce((s, r) => s + (typeof r.puissance_installee === "number" ? r.puissance_installee : 0), 0);
  const kwAbsorbes = rows.reduce((s, r) => s + (typeof r.puissance_active_foisonnee === "number" ? r.puissance_active_foisonnee : 0), 0);
  const kvarTotal = rows.reduce((s, r) => s + (typeof r.puissance_reactive_foisonnee === "number" ? r.puissance_reactive_foisonnee : 0), 0);
  const kvaReseau = Math.sqrt(kwAbsorbes * kwAbsorbes + kvarTotal * kvarTotal);
  const cosPhiGlobal = kvaReseau > 0 ? kwAbsorbes / kvaReseau : null;
  const iReseauHta = (tensionHtKv && kvaReseau > 0) ? kvaReseau / (Math.sqrt(3) * tensionHtKv) : null;

  const cards = [
    { value: kwInstalles.toFixed(0), label: "kW installes total", color: "#1F3864" },
    { value: kwAbsorbes.toFixed(0), label: "kW absorbes total", color: "#2C5F2D" },
    { value: kvaReseau.toFixed(0), label: "kVA reseau total", color: "#1F3864" },
    { value: kvarTotal.toFixed(0), label: "kVAr total", color: "#1F3864" },
    { value: cosPhiGlobal !== null ? cosPhiGlobal.toFixed(3) : "--", label: "cos \u03c6 global", color: "#2C5F2D" },
    { value: iReseauHta !== null ? iReseauHta.toFixed(1) + " A" : "--", label: "I reseau HTA (A)", color: "#B85042" },
  ];

  container.innerHTML = cards.map((c) => `
    <div class="bilan-kpi-card">
      <div class="bilan-kpi-value" style="color:${c.color}">${c.value}</div>
      <div class="bilan-kpi-label">${c.label}</div>
    </div>
  `).join("");
}

async function loadCableScheduleView() {
  const wrap = document.getElementById("cable-schedule-table-wrap");
  wrap.innerHTML = "Chargement...";
  try {
    CABLE_SCHEDULE_DATA = await (await fetch("/api/cable-schedule")).json();
  } catch (e) {
    wrap.innerHTML = '<p class="error">Impossible de charger le carnet de cables.</p>';
    return;
  }
  CABLE_SCHEDULE_FILTERS = {};
  renderCableScheduleTable();
}

function cellText(r, key) {
  const v = r[key];
  if (v === null || v === undefined || v === "") return "";
  if (key === "longueur_m") return `${v} m`;
  return String(v);
}

function renderCableScheduleTable() {
  const wrap = document.getElementById("cable-schedule-table-wrap");

  const rows = CABLE_SCHEDULE_DATA.filter((r) =>
    CABLE_SCHEDULE_COLUMNS.every((col) => {
      const filterVal = (CABLE_SCHEDULE_FILTERS[col.key] || "").trim().toLowerCase();
      if (!filterVal) return true;
      return cellText(r, col.key).toLowerCase().includes(filterVal);
    })
  );

  const table = document.createElement("table");
  const thead = document.createElement("thead");
  const trHead = document.createElement("tr");
  const trFilter = document.createElement("tr");
  CABLE_SCHEDULE_COLUMNS.forEach((col) => {
    const th = document.createElement("th");
    th.textContent = col.label;
    trHead.appendChild(th);

    const thFilter = document.createElement("th");
    const input = document.createElement("input");
    input.type = "text";
    input.placeholder = "Filtrer...";
    input.value = CABLE_SCHEDULE_FILTERS[col.key] || "";
    input.style.width = "100%";
    input.style.fontSize = "0.75rem";
    input.style.padding = "0.2rem 0.3rem";
    input.oninput = () => {
      CABLE_SCHEDULE_FILTERS[col.key] = input.value;
      renderCableScheduleTable();
      document.querySelector(`.cable-filter-input[data-key="${col.key}"]`)?.focus();
    };
    input.className = "cable-filter-input";
    input.dataset.key = col.key;
    thFilter.appendChild(input);
    trFilter.appendChild(thFilter);
  });
  thead.appendChild(trHead);
  thead.appendChild(trFilter);
  table.appendChild(thead);

  const tbody = document.createElement("tbody");
  if (!rows.length) {
    const tr = document.createElement("tr");
    const td = document.createElement("td");
    td.colSpan = CABLE_SCHEDULE_COLUMNS.length;
    td.className = "empty";
    td.textContent = "Aucun cable pour cette selection.";
    tr.appendChild(td);
    tbody.appendChild(tr);
  } else {
    rows.forEach((r) => {
      const tr = document.createElement("tr");
      CABLE_SCHEDULE_COLUMNS.forEach((col) => {
        const td = document.createElement("td");
        td.textContent = cellText(r, col.key);
        tr.appendChild(td);
      });
      tbody.appendChild(tr);
    });
  }
  table.appendChild(tbody);

  // preserver le focus/curseur pendant la frappe (re-render a chaque input)
  const activeKey = document.activeElement && document.activeElement.classList.contains("cable-filter-input")
    ? document.activeElement.dataset.key : null;
  const caret = document.activeElement ? document.activeElement.selectionStart : null;

  wrap.innerHTML = "";
  wrap.appendChild(table);

  if (activeKey) {
    const toFocus = wrap.querySelector(`.cable-filter-input[data-key="${activeKey}"]`);
    if (toFocus) {
      toFocus.focus();
      if (caret !== null) toFocus.setSelectionRange(caret, caret);
    }
  }
}

// ============================================================
// Zoom du Synoptique
// ============================================================
let DIAGRAM_ZOOM = 1;
const DIAGRAM_ZOOM_MIN = 0.2;
const DIAGRAM_ZOOM_MAX = 3;

function applyDiagramZoom() {
  const canvas = document.getElementById("diagram-svg-canvas");
  if (canvas) canvas.style.transform = `scale(${DIAGRAM_ZOOM})`;
}

function diagramZoomIn() {
  DIAGRAM_ZOOM = Math.min(DIAGRAM_ZOOM_MAX, +(DIAGRAM_ZOOM + 0.15).toFixed(2));
  applyDiagramZoom();
}

function diagramZoomOut() {
  DIAGRAM_ZOOM = Math.max(DIAGRAM_ZOOM_MIN, +(DIAGRAM_ZOOM - 0.15).toFixed(2));
  applyDiagramZoom();
}

function diagramZoomReset() {
  DIAGRAM_ZOOM = 1;
  applyDiagramZoom();
}

// ============================================================
// Vue "Saisie des donnees" (CRUD generique par table, inchange)
// ============================================================

function renderTabs() {
  const nav = document.getElementById("tabs");
  nav.innerHTML = "";
  TAB_ORDER.forEach((table) => {
    if (!SCHEMA[table]) return;
    const btn = document.createElement("button");
    btn.className = "tab-btn";
    btn.textContent = SCHEMA[table].label;
    btn.dataset.table = table;
    btn.onclick = () => selectTab(table);
    nav.appendChild(btn);
  });
}

function setActiveTab(table) {
  document.querySelectorAll(".tab-btn").forEach((b) => {
    b.classList.toggle("active", b.dataset.table === table);
  });
}

async function selectTab(table) {
  setActiveTab(table);
  const cfg = SCHEMA[table];
  document.getElementById("panel-title").textContent = cfg.label;
  document.getElementById("panel-hint").textContent = HINTS[table] || "";
  document.getElementById("form-error").textContent = "";
  await renderForm(cfg, table);
  await renderTableView(cfg, table);
}

function labelColumnFor(cfg) {
  const nonPk = cfg.columns.filter((c) => !c.pk);
  const preferred = nonPk.find((c) => ["nom", "type"].includes(c.name));
  return (preferred || nonPk[0] || cfg.columns[0]).name;
}

async function fetchOptions(refTable) {
  // `tag` is an internal registry and can retain an orphan tag after an
  // equipment deletion.  For an upstream selector, only offer components
  // that still exist and can therefore appear in the synoptic.
  if (refTable === "tag") {
    const graph = await (await fetch("/api/graph")).json();
    return graph.nodes
      .map((node) => {
        const label = (NODE_TYPE_STYLE[node.type] || {}).label || node.type;
        return { value: node.id, text: `${node.id} (${label})` };
      })
      .sort((a, b) => a.text.localeCompare(b.text));
  }

  const refCfg = SCHEMA[refTable];
  const rows = await Api.list(refTable);
  const labelCol = labelColumnFor(refCfg);
  const pkCol = refCfg.pk[0];
  return rows.map((r) => ({
    value: r[pkCol],
    text: r[labelCol] && String(r[labelCol]) !== String(r[pkCol]) ? `${r[pkCol]} (${r[labelCol]})` : `${r[pkCol]}`,
  }));
}

async function buildFieldInputs(container, cfg, idPrefix, prefillData, disablePkFields) {
  if (disablePkFields === undefined) disablePkFields = true;
  container.innerHTML = "";
  for (const col of cfg.columns) {
    const wrap = document.createElement("div");
    wrap.className = "field";

    const label = document.createElement("label");
    label.textContent = col.label + (col.optional ? " (optionnel)" : "");
    label.htmlFor = `${idPrefix}${col.name}`;
    wrap.appendChild(label);

    let input;
    const optionsTable = col.fk || col.options_table;
    if (optionsTable) {
      input = document.createElement("select");
      input.id = `${idPrefix}${col.name}`;
      input.name = col.name;
      const emptyOpt = document.createElement("option");
      emptyOpt.value = "";
      emptyOpt.textContent = col.optional ? "-- aucun --" : "-- choisir --";
      input.appendChild(emptyOpt);
      try {
        const options = await fetchOptions(optionsTable);
        options.forEach((o) => {
          const opt = document.createElement("option");
          opt.value = o.value;
          opt.textContent = o.text;
          input.appendChild(opt);
        });
      } catch (e) {
        // table referencee vide : select reste vide
      }
    } else {
      input = document.createElement("input");
      input.id = `${idPrefix}${col.name}`;
      input.name = col.name;
      input.type = col.type === "number" ? "number" : "text";
      if (col.type === "number") input.step = "any";
    }
    if (!col.optional) input.required = true;
    if (prefillData && prefillData[col.name] !== undefined && prefillData[col.name] !== null) {
      input.value = prefillData[col.name];
    }
    if (prefillData && col.pk && disablePkFields) {
      input.disabled = true; // la cle primaire ne se modifie pas en edition
    }
    wrap.appendChild(input);
    container.appendChild(wrap);
  }
}

async function renderForm(cfg, table) {
  const form = document.getElementById("entry-form");
  await buildFieldInputs(form, cfg, "f_", null);

  const submitRow = document.createElement("div");
  submitRow.className = "submit-row";
  const btn = document.createElement("button");
  btn.type = "submit";
  btn.className = "primary";
  btn.textContent = "Ajouter";
  submitRow.appendChild(btn);
  form.appendChild(submitRow);

  form.onsubmit = async (ev) => {
    ev.preventDefault();
    const errorEl = document.getElementById("form-error");
    errorEl.textContent = "";
    const data = {};
    cfg.columns.forEach((col) => {
      const el = document.getElementById(`f_${col.name}`);
      data[col.name] = el.value === "" ? null : el.value;
    });
    try {
      await Api.create(table, data);
      form.reset();
      await renderTableView(cfg, table);
      await renderForm(cfg, table);
    } catch (e) {
      errorEl.textContent = e.message;
    }
  };
}

// ============================================================
// Modale d'edition d'un equipement (depuis la Liste des equipements)
// ============================================================

let EDIT_CONTEXT = null; // { table, pkValues }

async function openEditEquipmentModal(tagId, type) {
  const cfg = SCHEMA[type];
  if (!cfg) { alert("Type d'equipement inconnu : " + type); return; }

  document.getElementById("edit-equipment-title").textContent = `Modifier : ${tagId}`;
  document.getElementById("edit-equipment-error").textContent = "";
  openModal("modal-edit-equipment");

  const form = document.getElementById("edit-equipment-form");
  form.innerHTML = "Chargement...";

  let row;
  try {
    row = await Api.getRow(type, [tagId]);
  } catch (e) {
    form.innerHTML = "";
    document.getElementById("edit-equipment-error").textContent = e.message;
    return;
  }

  await buildFieldInputs(form, cfg, "e_", row);
  EDIT_CONTEXT = { table: type, pkValues: cfg.pk.map((pkCol) => row[pkCol]) };
}

async function saveEditEquipment() {
  if (!EDIT_CONTEXT) return;
  if (!document.getElementById("edit-equipment-form").reportValidity()) return;
  const { table, pkValues } = EDIT_CONTEXT;
  const cfg = SCHEMA[table];
  const errorEl = document.getElementById("edit-equipment-error");
  errorEl.textContent = "";

  const data = {};
  cfg.columns.forEach((col) => {
    const el = document.getElementById(`e_${col.name}`);
    data[col.name] = el.value === "" ? null : el.value;
  });

  try {
    await Api.update(table, pkValues, data);
    closeModal();
    await loadEquipementsView();
  } catch (e) {
    errorEl.textContent = e.message;
  }
}

// ============================================================
// Modale de creation d'equipement par glisser-depose (palette -> arbre)
// ============================================================

let CREATE_CONTEXT = null; // { table, context: {siteTag, siteLabel, amontTag} }

async function openCreateEquipmentModal(table, context) {
  const cfg = SCHEMA[table];
  if (!cfg) { alert("Type d'equipement inconnu : " + table); return; }

  document.getElementById("create-equipment-title").textContent = `Ajouter : ${cfg.label}`;
  const ctxEl = document.getElementById("create-equipment-context");
  let ctxText = `Site : ${context.siteTag || "(a definir manuellement)"}`;
  if (context.amontTag) ctxText += `  -  Amont : ${context.amontTag}`;
  ctxEl.textContent = ctxText;
  document.getElementById("create-equipment-error").textContent = "";
  openModal("modal-create-equipment");

  const form = document.getElementById("create-equipment-form");
  const prefill = {};
  const hasSiteId = cfg.columns.some((c) => c.name === "site_id");
  const hasAmontId = cfg.columns.some((c) => c.name === "amont_id");
  if (hasSiteId && context.siteTag) prefill.site_id = context.siteTag;
  if (hasAmontId && context.amontTag) prefill.amont_id = context.amontTag;

  await buildFieldInputs(form, cfg, "c_", prefill, false); // false = ne pas desactiver la cle primaire (on cree une nouvelle entree)

  // Les champs derives automatiquement du contexte (site, amont) restent verrouilles
  ["site_id", "amont_id"].forEach((name) => {
    const el = document.getElementById(`c_${name}`);
    if (el && prefill[name] !== undefined) el.disabled = true;
  });

  CREATE_CONTEXT = { table, context };
}

async function saveCreateEquipment() {
  if (!CREATE_CONTEXT) return;
  if (!document.getElementById("create-equipment-form").reportValidity()) return;
  const { table, context } = CREATE_CONTEXT;
  const cfg = SCHEMA[table];
  const errorEl = document.getElementById("create-equipment-error");
  errorEl.textContent = "";

  const data = {};
  cfg.columns.forEach((col) => {
    const el = document.getElementById(`c_${col.name}`);
    data[col.name] = el.value === "" ? null : el.value;
  });

  try {
    await Api.create(table, data);
    closeModal();
    await loadEquipementsView();
  } catch (e) {
    errorEl.textContent = e.message;
  }
}

async function renderTableView(cfg, table) {
  const wrap = document.getElementById("table-wrap");
  wrap.innerHTML = "Chargement...";
  let rows;
  try {
    rows = await Api.list(table);
  } catch (e) {
    wrap.innerHTML = `<p class="error">${e.message}</p>`;
    return;
  }
  if (rows.length === 0) {
    wrap.innerHTML = '<p class="empty">Aucune entree pour le moment.</p>';
    return;
  }

  const tableEl = document.createElement("table");
  const thead = document.createElement("thead");
  const trh = document.createElement("tr");
  cfg.columns.forEach((c) => {
    const th = document.createElement("th");
    th.textContent = c.label;
    trh.appendChild(th);
  });
  const thActions = document.createElement("th");
  thActions.textContent = "";
  trh.appendChild(thActions);
  thead.appendChild(trh);
  tableEl.appendChild(thead);

  const tbody = document.createElement("tbody");
  rows.forEach((row) => {
    const tr = document.createElement("tr");
    cfg.columns.forEach((c) => {
      const td = document.createElement("td");
      td.textContent = row[c.name] ?? "";
      tr.appendChild(td);
    });
    const tdAction = document.createElement("td");
    const delBtn = document.createElement("button");
    delBtn.className = "btn-del";
    delBtn.textContent = "Supprimer";
    delBtn.onclick = async () => {
      const pkValues = cfg.pk.map((pkCol) => row[pkCol]);
      if (!confirm("Confirmer la suppression de cette entree ?")) return;
      try {
        await Api.remove(table, pkValues);
        await renderTableView(cfg, table);
        await renderForm(cfg, table);
      } catch (e) {
        alert(e.message);
      }
    };
    tdAction.appendChild(delBtn);
    tr.appendChild(tdAction);
    tbody.appendChild(tr);
  });
  tableEl.appendChild(tbody);

  wrap.innerHTML = "";
  wrap.appendChild(tableEl);
}

init();
