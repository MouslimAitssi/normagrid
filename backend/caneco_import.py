"""
Parseur pour les notes de calcul Caneco BT (export PDF du logiciel ALPI).

Methodologie (validee par analyse manuelle du fichier de reference) :
- 1 page = jusqu'a 8 departs (circuits) d'un meme tableau ; un tableau avec
  plus de 8 departs continue sur plusieurs pages consecutives (meme titre de
  folio en pied de page).
- La hierarchie amont/aval est reconstruite en recherchant, dans le texte de
  chaque tableau, si le nom d'un AUTRE tableau y apparait (comme destination
  d'un de ses circuits). Un tableau qui n'apparait jamais comme destination
  est une racine (rattachee au reseau HT choisi par l'utilisateur a l'import).
- Les donnees par circuit (destination, cable, protection) sont extraites en
  alignant les colonnes du texte (pdftotext -layout) par position de
  caractere : la ligne "Repere" du bloc CIRCUIT sert de reference de colonnes,
  les autres lignes (Cable, Type, Calibre, Protection) sont alignees sur ces
  colonnes par correspondance de position la plus proche.

Limite connue et assumee : quand une protection est differentielle ("Vigi"),
la valeur I(dn) est parfois positionnee visuellement plus proche de la
colonne du circuit suivant, et peut donc lui etre attribuee par erreur. Cette
extraction est fournie "au mieux" ; un controle manuel des protections
differentielles est recommande apres import.
"""

import re
import subprocess
import tempfile
import os


FOLIO_RE = re.compile(r"Unif\.Chantier\s+\d+\s+circuits\s+(.+)")

BOILERPLATE_PATTERNS = [
    "AFFAIRE:", "PLAN:", "Norme :", "Fichier :", "MODIFICATIONS",
    "Ind.", "Date :", "Folio", "ALPI Caneco", "Avis Technique",
]


# ---------------------------------------------------------------------------
# Extraction brute du texte
# ---------------------------------------------------------------------------

def _pdftotext_pages(pdf_path):
    with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as tmp:
        tmp_path = tmp.name
    try:
        try:
            subprocess.run(["pdftotext", "-layout", pdf_path, tmp_path], check=True,
                            capture_output=True)
        except FileNotFoundError:
            raise ValueError(
                "L'outil 'pdftotext' (poppler-utils) est introuvable sur ce PC. "
                "Installez-le : Windows (via conda/choco, ou binaires poppler dans le PATH), "
                "Mac (brew install poppler), Linux (sudo apt install poppler-utils)."
            )
        with open(tmp_path, "r", encoding="utf-8", errors="replace") as f:
            data = f.read()
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
    return [p for p in data.split("\x0c") if p.strip()]


def _clean_lines(text):
    return [ln for ln in text.splitlines() if not any(bp in ln for bp in BOILERPLATE_PATTERNS)]


def _folio_title(page_text):
    for line in page_text.splitlines():
        m = FOLIO_RE.search(line)
        if m:
            name = re.sub(r"\s+\d+\s*$", "", m.group(1)).strip()
            return name
    return None


# ---------------------------------------------------------------------------
# Reconstruction de la hierarchie (amont -> aval), par rapprochement de noms
# ---------------------------------------------------------------------------

def normalize_board_name(s):
    return _normalize(s)


def _normalize(s):
    s = s.upper().strip()
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"(^|\s)[NS](\s|$)", " ", s)  # marqueur Normal/Secours isole
    s = re.sub(r"\s+", " ", s).strip()
    return s


def extract_declared_amont(page_text):
    """
    Lit le champ DISTRIBUTION > Amont > Normal / Secours d'une page. Ce champ
    est parfois une simple continuation de busbar (le tableau se reference
    lui-meme d'une page a l'autre) : l'appelant doit comparer au nom du
    tableau lui-meme (normalise) pour ne retenir que les vraies references
    externes.
    """
    lines = page_text.splitlines()
    amont_idx = _find_line(lines, r"^\s*Amont\b")
    if amont_idx is None:
        return None, None
    normal_line = lines[amont_idx - 1] if amont_idx - 1 >= 0 else ""
    secours_line = lines[amont_idx + 1] if amont_idx + 1 < len(lines) else ""
    amont_line = lines[amont_idx]

    m_normal = re.search(r"Normal\s+(.+)", normal_line)
    normal_val = m_normal.group(1).strip() if m_normal else ""
    m_cont = re.search(r"Amont\s+(.+)", amont_line)
    if m_cont:
        normal_val = (normal_val + " " + m_cont.group(1).strip()).strip()

    m_secours = re.search(r"Secours\s+(.+)", secours_line)
    secours_val = m_secours.group(1).strip() if m_secours else ""

    return (normal_val or None), (secours_val or None)


def _circuit_block_text(page_text):
    """Ne garde que le bloc CIRCUIT d'une page (a partir de la 2e occurrence
    de 'Repere'), en excluant le bloc DISTRIBUTION du haut qui mentionne le
    propre amont declare du tableau (sinon la recherche croisee de noms
    detecterait une fausse arete dans les deux sens)."""
    lines = page_text.splitlines()
    first_repere = _find_line(lines, r"^\s*Repère\b")
    if first_repere is None:
        return page_text
    circuit_idx = _find_line(lines, r"^\s*Repère\b", start=first_repere + 1)
    if circuit_idx is None:
        return page_text
    return "\n".join(lines[circuit_idx:])


def _is_plausible_board_reference(val, own_name_norm):
    """
    Filtre les valeurs du champ Amont qui ne sont PAS de vraies references a
    un tableau : reperes de phase (L1/L2/L3, convention d'equilibrage entre
    les 3 phases sur des circuits monophases), abreviations trop courtes
    pour etre fiables (risque de collision entre plusieurs entites reelles
    partageant le meme repere generique, ex: "EC"), valeurs numeriques avec
    unite (ex: "30 mA", "1600 A" - des donnees de protection mal attribuees,
    pas un nom de tableau), ou lettres isolees repetees (bruit de mise en
    page issu du chevauchement de plusieurs elements du schema d'origine).
    """
    norm = _normalize(val)
    if not norm or norm == own_name_norm:
        return False
    if len(norm) < 3:
        return False
    if re.fullmatch(r"L[123]", norm):
        return False
    if re.fullmatch(r"[\d,.]+\s*(MA|A|V|KV|KVA|W|KW|%)", norm):
        return False  # valeur numerique + unite, pas un nom de tableau
    # lettres isolees repetees avec de grands ecarts ("C   C   C   C")
    tokens = norm.split()
    if tokens and all(len(t) <= 2 for t in tokens):
        return False
    return True


def _get_declared_amonts(pages, board_pages, board_norm):
    """Amonts declares (Normal/Secours) par tableau, hors auto-reference de
    continuation et hors valeurs non plausibles (reperes de phase, sigles
    trop courts), sous forme normalisee. Ces valeurs sont souvent reflechies
    comme si elles etaient des circuits sortants du tableau lui-meme (une
    convention Caneco) : il faut les exclure de ses propres avals."""
    declared = {}
    for board, idx_list in board_pages.items():
        normal, secours = extract_declared_amont(pages[idx_list[0]])
        vals = set()
        for v in (normal, secours):
            if v and v.upper() not in ("SOURCE", "SECOURS") and _is_plausible_board_reference(v, board_norm.get(board)):
                vals.add(_normalize(v))
        declared[board] = vals
    return declared


def build_hierarchy(pages):
    """Retourne (boards, edges, board_pages) a partir des pages brutes."""
    page_board = [_folio_title(p) for p in pages]
    boards = sorted(set(b for b in page_board if b))

    board_pages = {}
    for i, b in enumerate(page_board):
        if b:
            board_pages.setdefault(b, []).append(i)

    board_norm = {b: _normalize(b) for b in boards}
    boards_valid = [b for b in boards if len(board_norm[b]) >= 3]
    declared_amonts = _get_declared_amonts(pages, board_pages, board_norm)

    edges = set()
    for board, idx_list in board_pages.items():
        combined = "\n".join(_circuit_block_text("\n".join(_clean_lines(pages[i]))) for i in idx_list)
        norm_text = _normalize(combined)
        own_amonts = declared_amonts.get(board, set())
        for other in boards_valid:
            if other == board or board_norm[other] in own_amonts:
                continue  # reflet de l'amont declare (convention Caneco), pas un vrai aval
            pattern = r"(?<![A-Z0-9-])" + re.escape(board_norm[other]) + r"(?![A-Z0-9-])"
            if board_norm[other] and re.search(pattern, norm_text):
                edges.add((board, other))

    # Complement par le champ DISTRIBUTION > Amont > Normal/Secours, une
    # source explicite et authentique qui rattrape les cas rates par la
    # recherche croisee (ex: un tableau alimente par un repere qui n'a pas
    # sa propre page, comme "TGBT ATS 2"). On filtre l'auto-reference qui
    # ne fait qu'indiquer la continuation d'un meme jeu de barres.
    extra_boards = set()
    for board, idx_list in board_pages.items():
        normal, secours = extract_declared_amont(pages[idx_list[0]])
        for val in (normal, secours):
            if not val:
                continue
            if val.upper() in ("SOURCE", "SECOURS"):
                continue  # deja gere par les cas particuliers dedies
            if not _is_plausible_board_reference(val, board_norm.get(board)):
                continue  # repere de phase (L1/L2/L3) ou sigle trop court, pas un vrai tableau
            if classify_board_type(board) == "groupes_electrogenes":
                continue  # un groupe electrogene est toujours une source autonome

            matched = next((b for b in boards if board_norm.get(b) == _normalize(val)), None)
            amont_name = matched or val
            if not matched:
                extra_boards.add(val)
            edges.add((amont_name, board))

    boards = sorted(set(boards) | extra_boards)

    # Deuxieme passe : les tableaux "virtuels" ajoutes ci-dessus (sans page
    # dediee, ex: "TGBT ATS 2") n'ont pas encore ete recherches comme
    # destination possible dans le texte des autres pages (ils n'existaient
    # pas encore lors de la premiere passe). On complete cette recherche
    # pour retrouver leur propre amont.
    board_norm.update({b: _normalize(b) for b in extra_boards})
    if extra_boards:
        already_has_amont = set(dst for _, dst in edges)
        for board, idx_list in board_pages.items():
            combined = "\n".join(_circuit_block_text("\n".join(_clean_lines(pages[i]))) for i in idx_list)
            norm_text = _normalize(combined)
            own_amonts = declared_amonts.get(board, set())
            for other in extra_boards:
                if other == board or other in already_has_amont or board_norm[other] in own_amonts:
                    continue
                pattern = r"(?<![A-Z0-9-])" + re.escape(board_norm[other]) + r"(?![A-Z0-9-])"
                if board_norm[other] and re.search(pattern, norm_text):
                    edges.add((board, other))

    return boards, edges, board_pages


def clean_longueur(text):
    """Reconstruit proprement 'N m (Materiau)' a partir d'un texte parfois
    desordonne (ex: 'Cu 40 m Cu' -> '40 m (Cu)')."""
    if not text:
        return ""
    m_len = re.search(r"(\d+(?:[.,]\d+)?)\s*m\b", text)
    m_mat = re.search(r"\b(Cu|Al)\b", text)
    if not m_len:
        return text.strip()
    out = f"{m_len.group(1)} m"
    if m_mat:
        out += f" ({m_mat.group(1)})"
    return out


def parse_length_m(text):
    """Extrait la longueur en metres depuis le texte nettoye (ex: '20 m (Cu)' -> 20.0)."""
    if not text:
        return None
    m = re.search(r"([\d]+(?:[.,]\d+)?)\s*m\b", text)
    if m:
        return float(m.group(1).replace(",", "."))
    return None


def parse_power_kva(text):
    """Extrait une puissance en kVA depuis le texte 'Consommation' (ex: '1000KVA' -> 1000)."""
    if not text:
        return None
    m = re.search(r"([\d]+(?:[.,]\d+)?)\s*K\s*VA\b", text, re.IGNORECASE)
    if m:
        return float(m.group(1).replace(",", "."))
    return None


def classify_board_type(name):
    """Devine le type d'equipement NormaGrid a partir du nom du tableau."""
    n = name.upper()
    if re.search(r"\bGE\b", n) or "GROUPE" in n or n.startswith("TGR"):
        return "groupes_electrogenes"
    if re.search(r"\bTR[-_ ]", n) or "TRANSFO" in n:
        return "transfos"
    return "tableaux"


# ---------------------------------------------------------------------------
# Extraction des circuits (destination, cable, protection) par alignement
# de colonnes sur la ligne "Repere" du bloc CIRCUIT.
# ---------------------------------------------------------------------------

def _tokenize_columns(line, min_gap=6):
    groups = []
    for m in re.finditer(r"\S+(?:\s{1,%d}\S+)*" % (min_gap - 1), line):
        groups.append((m.start(), m.group().strip()))
    return groups


def _assign_column(token_start, col_starts, tolerance=15):
    best_idx, best_dist = None, None
    for i, cs in enumerate(col_starts):
        dist = abs(token_start - cs)
        if best_dist is None or dist < best_dist:
            best_dist, best_idx = dist, i
    if best_dist is not None and best_dist <= tolerance:
        return best_idx
    return None


def _extract_row_values(lines, line_idx, col_starts, label=None):
    if line_idx is None or line_idx >= len(lines):
        return {}
    cols = _tokenize_columns(lines[line_idx])
    result = {}
    for start, text in cols:
        if label and text == label:
            continue
        idx = _assign_column(start, col_starts)
        if idx is not None:
            result.setdefault(idx, []).append(text)
    return result


def _find_line(lines, pattern, start=0):
    for i in range(start, len(lines)):
        if re.match(pattern, lines[i]):
            return i
    return None


TYPE_KEYWORDS = [
    ("Transformateur", [r"transfo"]),
    ("Groupe", [r"groupe\s*electrogene", r"\bge\b"]),
    ("Moteur", [r"moteur", r"pompe", r"ventilateur", r"compresseur", r"extracteur", r"surpresseur", r"\bvmc\b"]),
    ("Clim", [r"\bclim", r"\bcta\b", r"climatisation", r"ventilo.?convecteur", r"gainable", r"echangeur", r"\bhvac\b", r"m3/h"]),
    ("Eclairage", [r"eclairage", r"luminaire", r"\becl\d", r"\becl[^a-z]"]),
    ("PC", [r"prise de courant", r"\bprises?\b", r"\bpc\d", r"\bpc[^a-z]"]),
]


def classify_circuit_type(designation, repere):
    """
    Devine le type d'equipement standard (Moteur/Eclairage/Clim/Divers/PC/
    Groupe/Transformateur) a partir du texte de designation/repere, pour
    correspondre aux symboles unifilaires normalises. Si aucun mot-cle ne
    correspond avec confiance, la case est laissee vide plutot que de
    forcer une valeur par defaut (l'utilisateur complete a la main si besoin).
    """
    import unicodedata
    raw = f"{designation or ''} {repere or ''}"
    raw = unicodedata.normalize("NFKD", raw).encode("ascii", "ignore").decode("ascii")
    text = _normalize(raw)
    for label, patterns in TYPE_KEYWORDS:
        for pat in patterns:
            if re.search(pat, text, re.IGNORECASE):
                return label
    return ""


def extract_staging_circuits_from_page(page_text):
    """
    Extraction complete (au plus proche du PDF brut) d'UNE page, pour la
    table de preparation "Import Caneco" : toutes les valeurs sont
    conservees en texte, sans conversion/calcul, pour permettre une revue
    et une correction manuelle completes avant tout chargement en base.
    """
    lines = page_text.splitlines()

    first_repere = _find_line(lines, r"^\s*Repère\b")
    if first_repere is None:
        return []
    circuit_repere_idx = _find_line(lines, r"^\s*Repère\b", start=first_repere + 1)
    if circuit_repere_idx is None:
        return []

    repere_cols = _tokenize_columns(lines[circuit_repere_idx])
    if repere_cols and repere_cols[0][1] == "Repère":
        repere_cols = repere_cols[1:]
    col_starts = [c[0] for c in repere_cols]
    if not col_starts:
        return []

    board_normal, board_secours = extract_declared_amont(page_text)
    # Les valeurs non plausibles (reperes de phase L1/L2/L3, sigles trop
    # courts) ne sont pas de vrais noms de tableaux amont : on les laisse
    # vides plutot que d'afficher un bruit trompeur dans la table.
    board_repere_line = lines[first_repere]
    board_repere_cols = _tokenize_columns(board_repere_line)
    board_repere = board_repere_cols[1][1] if len(board_repere_cols) > 1 else ""
    board_repere_norm = _normalize(board_repere)
    if board_normal and not _is_plausible_board_reference(board_normal, board_repere_norm):
        board_normal = ""
    if board_secours and not _is_plausible_board_reference(board_secours, board_repere_norm):
        board_secours = ""

    # La 1ere occurrence de "Designation" (avant le bloc CIRCUIT) correspond
    # a la designation propre du tableau (bloc DISTRIBUTION).
    first_designation_idx = _find_line(lines, r"^\s*Désignation\b", start=first_repere)
    board_designation = ""
    if first_designation_idx is not None and first_designation_idx < circuit_repere_idx:
        desig_cols = _tokenize_columns(lines[first_designation_idx])
        if len(desig_cols) > 1:
            board_designation = desig_cols[1][1]

    def line_idx(label):
        suffix = r"\b" if re.search(r"\w$", label) else ""
        return _find_line(lines, r"^\s*" + label + suffix, start=circuit_repere_idx)

    idx_nb = line_idx("Nb")
    idx_designation = line_idx("Désignation")
    idx_alimentation = line_idx("Alimentation")
    idx_jdb_amont = line_idx("JdB Amont")
    idx_type = line_idx("Type")
    idx_longueur = line_idx("Longueur")
    idx_lmax = line_idx(r"L\.Max prot\.")
    idx_du = line_idx(r"∆U Circuit")
    idx_cable = line_idx("Câble")
    idx_neutre = line_idx("Neutre")
    idx_pepen = line_idx("PE/PEN")
    idx_separe = _find_line(lines, r"^\s*Séparé\b", start=circuit_repere_idx)
    idx_harmonique = line_idx(r"Taux d'Harmonique")
    idx_protection_label = _find_line(lines, r"^\s*Protection\s*$", start=circuit_repere_idx)
    idx_calibre = line_idx("Calibre")
    idx_ir = line_idx("Ir")
    idx_affectation = _find_line(lines, r"^\s*Affectation des phases\b", start=circuit_repere_idx)

    def vals(idx, label=None):
        return _extract_row_values(lines, idx, col_starts, label) if idx is not None else {}

    v_nb = vals(idx_nb, "Nb")
    v_designation = vals(idx_designation, "Désignation")
    v_alimentation = vals(idx_alimentation, "Alimentation")
    v_jdb_amont = vals(idx_jdb_amont, "JdB Amont")
    v_type = vals(idx_type, "Type")
    v_longueur = vals(idx_longueur, "Longueur")
    v_lmax = vals(idx_lmax)
    v_du = vals(idx_du)
    v_cable = vals(idx_cable, "Câble")
    v_neutre = vals(idx_neutre, "Neutre")
    v_pepen = vals(idx_pepen, "PE/PEN")
    v_separe = vals(idx_separe, "Séparé")
    v_harmonique = vals(idx_harmonique)
    v_calibre = vals(idx_calibre)
    v_ir = vals(idx_ir)
    v_affectation = vals(idx_affectation, "Affectation des phases")

    v_protection = {}
    if idx_protection_label is not None:
        for back in range(1, 4):
            li = idx_protection_label - back
            if li <= circuit_repere_idx:
                break
            if lines[li].strip():
                v_protection = vals(li)
                break

    rows = []
    for i, (start, name) in enumerate(repere_cols):
        nb_text = " ".join(v_nb.get(i, []))
        if re.match(r"^0(\D|$)", nb_text.strip()) and not v_cable.get(i) and not v_protection.get(i):
            continue  # circuit non installe (quantite 0, aucune donnee)

        designation = " ".join(v_designation.get(i, []))
        longueur_ame = " ".join(v_longueur.get(i, []))
        longueur_clean = clean_longueur(re.sub(r"\bAme\b", "", longueur_ame))
        m_ame = re.search(r"\b(Cu|Al)\b", longueur_ame)

        du_text = " ".join(v_du.get(i, []))
        du_pairs = re.findall(r"[\d,.]+\s*%", du_text)

        # Nb / Consommation : le 1er nombre isole = quantite, le reste = consommation
        m_nb = re.match(r"^\s*(\d+)\s*(.*)$", nb_text)
        nombre = m_nb.group(1) if m_nb else nb_text.strip()
        consommation = m_nb.group(2).strip() if m_nb else ""

        # Calibre / I(dn) : "1600 A" (calibre) et une eventuelle valeur "500 mA" (I dn)
        calibre_text = " ".join(v_calibre.get(i, []))
        m_calibre = re.search(r"([\d,.]+)\s*A\b", calibre_text)
        m_idn = re.search(r"([\d,.]+)\s*mA\b", calibre_text)
        calibre_val = f"{m_calibre.group(1)} A" if m_calibre else ""
        i_delta_n_val = f"{m_idn.group(1)} mA" if m_idn else ""

        # Ir / Im-Isd : 2 valeurs numeriques successives au mieux (Ir puis Im/Isd)
        ir_text = " ".join(v_ir.get(i, []))
        ir_numbers = re.findall(r"[\d,.]+\s*A", ir_text)
        ir_val = ir_numbers[0] if len(ir_numbers) > 0 else ""
        im_isd_val = ir_numbers[1] if len(ir_numbers) > 1 else (ir_numbers[0] if len(ir_numbers) == 1 else "")
        if len(ir_numbers) == 1:
            ir_val = ""  # valeur unique : le plus souvent Im/Isd seul est renseigne

        rows.append({
            "board_repere": board_repere,
            "board_designation": board_designation,
            "amont_normal": board_normal or "",
            "amont_secours": board_secours or "",
            "circuit_repere": name,
            "circuit_designation": designation,
            "nombre": nombre,
            "consommation": consommation,
            "alimentation": " ".join(v_alimentation.get(i, [])),
            "jdb_amont": " ".join(v_jdb_amont.get(i, [])),
            "liaison_type": " ".join(v_type.get(i, [])),
            "longueur": longueur_clean,
            "ame": m_ame.group(1) if m_ame else "",
            "l_max_prot": " ".join(v_lmax.get(i, [])),
            "delta_u_circuit": du_pairs[0] if len(du_pairs) > 0 else "",
            "delta_u_totale": du_pairs[1] if len(du_pairs) > 1 else "",
            "cable": " ".join(v_cable.get(i, [])),
            "neutre": " ".join(v_neutre.get(i, [])),
            "pe_pen": " ".join(v_pepen.get(i, [])),
            "separe": " ".join(v_separe.get(i, [])),
            "taux_harmonique": " ".join(v_harmonique.get(i, [])),
            "protection": " ".join(v_protection.get(i, [])),
            "calibre": calibre_val,
            "i_delta_n": i_delta_n_val,
            "ir": ir_val,
            "im_isd": im_isd_val,
            "affectation_phases": " ".join(v_affectation.get(i, [])),
            "type_detecte": classify_circuit_type(designation, name),
        })
    return rows


def extract_circuits_from_page(page_text):
    """Extrait les circuits (departs) d'UNE page (jusqu'a 8)."""
    lines = page_text.splitlines()

    # la 1ere occurrence de "Repere" = identite du tableau lui-meme (bloc
    # DISTRIBUTION) ; la 2eme = destinations des circuits (bloc CIRCUIT).
    first_repere = _find_line(lines, r"^\s*Repère\b")
    if first_repere is None:
        return []
    circuit_repere_idx = _find_line(lines, r"^\s*Repère\b", start=first_repere + 1)
    if circuit_repere_idx is None:
        return []

    repere_cols = _tokenize_columns(lines[circuit_repere_idx])
    if repere_cols and repere_cols[0][1] == "Repère":
        repere_cols = repere_cols[1:]
    col_starts = [c[0] for c in repere_cols]
    if not col_starts:
        return []

    nb_idx = _find_line(lines, r"^\s*Nb\b", start=circuit_repere_idx)
    designation_idx = _find_line(lines, r"^\s*Désignation\b", start=circuit_repere_idx)
    type_idx = _find_line(lines, r"^\s*Type\b", start=circuit_repere_idx)
    cable_idx = _find_line(lines, r"^\s*Câble\b", start=circuit_repere_idx)
    longueur_idx = _find_line(lines, r"^\s*Longueur\b", start=circuit_repere_idx)
    calibre_idx = _find_line(lines, r"^\s*Calibre\b", start=circuit_repere_idx)
    protection_label_idx = _find_line(lines, r"^\s*Protection\s*$", start=circuit_repere_idx)

    nb_vals = _extract_row_values(lines, nb_idx, col_starts, "Nb")
    designation_vals = _extract_row_values(lines, designation_idx, col_starts, "Désignation")
    type_vals = _extract_row_values(lines, type_idx, col_starts, "Type")
    cable_vals = _extract_row_values(lines, cable_idx, col_starts, "Câble")
    longueur_vals = _extract_row_values(lines, longueur_idx, col_starts, "Longueur")
    calibre_vals = _extract_row_values(lines, calibre_idx, col_starts)

    protection_vals = {}
    if protection_label_idx is not None:
        for back in range(1, 4):
            li = protection_label_idx - back
            if li <= circuit_repere_idx:
                break
            if lines[li].strip():
                protection_vals = _extract_row_values(lines, li, col_starts)
                break

    circuits = []
    for i, (start, name) in enumerate(repere_cols):
        nb_text = " ".join(nb_vals.get(i, []))
        # circuit non installe (quantite 0, aucune donnee) -> on l'ignore
        if re.match(r"^0(\D|$)", nb_text.strip()) and not cable_vals.get(i) and not protection_vals.get(i):
            continue

        cal_text = " ".join(calibre_vals.get(i, []))
        calibre_a, diff_ma = None, None
        m_a = re.search(r"([\d,.]+)\s*A\b", cal_text)
        if m_a:
            calibre_a = float(m_a.group(1).replace(",", "."))
        m_ma = re.search(r"([\d,.]+)\s*mA\b", cal_text)
        if m_ma:
            diff_ma = float(m_ma.group(1).replace(",", "."))

        circuits.append({
            "repere": name,
            "designation": " ".join(designation_vals.get(i, [])),
            "consommation": " ".join(nb_vals.get(i, [])),
            "cable_type": " ".join(type_vals.get(i, [])),
            "cable_section": " ".join(cable_vals.get(i, [])),
            "longueur": clean_longueur(re.sub(r"\bAme\b", "", " ".join(longueur_vals.get(i, [])))),
            "protection_modele": " ".join(protection_vals.get(i, [])),
            "calibre_a": calibre_a,
            "differentiel_ma": diff_ma,
        })
    return circuits


def extract_all_circuits(pages, board_pages):
    """Extrait tous les circuits de chaque tableau (toutes ses pages)."""
    result = {}
    for board, idx_list in board_pages.items():
        circuits = []
        for i in idx_list:
            circuits.extend(extract_circuits_from_page(pages[i]))
        result[board] = circuits
    return result


# ---------------------------------------------------------------------------
# Point d'entree haut niveau : analyse complete d'un PDF
# ---------------------------------------------------------------------------

def extract_all_staging_rows(pdf_path):
    """
    Extraction complete (staging) de tout le fichier PDF : une ligne par
    circuit, tous champs en texte brut, prete pour revue/correction par
    l'utilisateur avant chargement dans la table de preparation.
    """
    pages = _pdftotext_pages(pdf_path)
    boards, edges, board_pages = build_hierarchy(pages)
    rows = []
    for board, idx_list in board_pages.items():
        for i in idx_list:
            rows.extend(extract_staging_circuits_from_page(pages[i]))
    return rows


def _parse_calibre_a_from_staging(text):
    """Extrait le calibre en A depuis le texte deja formate de la table de
    preparation (ex: '1600 A' -> 1600.0)."""
    if not text:
        return None
    m = re.search(r"([\d,.]+)\s*A\b", text)
    if m:
        return float(m.group(1).replace(",", "."))
    return None


def _parse_diff_ma_from_staging(text):
    """Extrait le differentiel en mA depuis le texte deja formate de la
    table de preparation (ex: '30 mA' -> 30.0)."""
    if not text:
        return None
    m = re.search(r"([\d,.]+)\s*mA\b", text)
    if m:
        return float(m.group(1).replace(",", "."))
    return None


def build_analysis_from_staging_rows(rows):
    """
    Reconstruit une structure d'analyse (boards / board_types /
    circuits_by_board / declared_amonts), au meme format que celui produit
    par analyze_pdf(), mais a partir des lignes DEJA VALIDEES/CORRIGEES par
    l'utilisateur dans la table de preparation import_caneco_staging --
    sans re-parser le PDF d'origine. Ceci permet de reutiliser telle quelle
    la logique de conversion existante (models.import_caneco_with_overrides).

    Ajoute egalement "boards_preview" : la liste {name, type,
    proposed_amonts} utilisee pour l'apercu/correction des amonts avant
    confirmation, reconstruite en recherchant, parmi les circuits PROPRES a
    chaque tableau, ceux dont le repere correspond au nom d'un autre
    tableau (meme methodologie que build_hierarchy, mais appliquee aux
    donnees deja structurees plutot qu'au texte brut des pages).
    """
    boards = []
    seen = set()
    board_amonts = {}
    circuits_by_board = {}

    for r in rows:
        board = (r.get("board_repere") or "").strip()
        if not board:
            continue
        if board not in seen:
            seen.add(board)
            boards.append(board)
            board_amonts[board] = (r.get("amont_normal") or "", r.get("amont_secours") or "")
            circuits_by_board[board] = []
        repere = (r.get("circuit_repere") or "").strip()
        if not repere:
            continue
        circuits_by_board[board].append({
            "repere": repere,
            "designation": r.get("circuit_designation") or "",
            "consommation": r.get("consommation") or "",
            "cable_type": r.get("liaison_type") or "",
            "cable_section": r.get("cable") or "",
            "longueur": r.get("longueur") or "",
            "protection_modele": r.get("protection") or "",
            "calibre_a": _parse_calibre_a_from_staging(r.get("calibre")),
            "differentiel_ma": _parse_diff_ma_from_staging(r.get("i_delta_n")),
        })

    board_types = {b: classify_board_type(b) for b in boards}
    board_norm = {b: _normalize(b) for b in boards}

    # Tableaux "virtuels" : references en amont (Normal/Secours) qui n'ont
    # pas leurs propres lignes de circuits dans la table de preparation
    # (ex: continuation d'un jeu de barres non detaille dans le fichier).
    extra_boards = []
    for b in boards:
        for val in board_amonts[b]:
            val = (val or "").strip()
            if not val or val.upper() in ("SOURCE", "SECOURS"):
                continue
            norm_val = _normalize(val)
            if any(board_norm[ob] == norm_val for ob in boards):
                continue
            if any(_normalize(x) == norm_val for x in extra_boards):
                continue
            extra_boards.append(val)

    for eb in extra_boards:
        boards.append(eb)
        board_types[eb] = classify_board_type(eb)
        board_norm[eb] = _normalize(eb)
        circuits_by_board[eb] = []

    declared_amonts = {}
    for b in boards:
        normal, secours = board_amonts.get(b, ("", ""))
        vals = set()
        for v in (normal, secours):
            v = (v or "").strip()
            if v and v.upper() not in ("SOURCE", "SECOURS"):
                vals.add(_normalize(v))
        declared_amonts[b] = vals

    # Reconstruction amont/aval, par recherche croisee des noms de tableaux
    # parmi les reperes de circuits propres a chaque tableau.
    edges = set()
    for board in boards:
        own_amonts = declared_amonts.get(board, set())
        for c in circuits_by_board.get(board, []):
            repere = (c.get("repere") or "").strip()
            if not repere or repere.upper() in ("SOURCE", "SECOURS"):
                continue
            norm_repere = _normalize(repere)
            if norm_repere in own_amonts:
                continue  # reflet de son propre amont declare (convention Caneco)
            match = next((ob for ob in boards if ob != board and board_norm[ob] == norm_repere), None)
            if match:
                edges.add((board, match))

    # Complement par le champ Amont declare (Normal/Secours), plus fiable
    # quand aucun circuit sortant ne nomme explicitement le tableau amont.
    for b in boards:
        normal, secours = board_amonts.get(b, ("", ""))
        for val in (normal, secours):
            val = (val or "").strip()
            if not val or val.upper() in ("SOURCE", "SECOURS"):
                continue
            norm_val = _normalize(val)
            match = next((ob for ob in boards if board_norm[ob] == norm_val), None)
            amont_name = match or val
            edges.add((amont_name, b))

    all_dest = set(dst for _, dst in edges)
    amont_of = {}
    for src, dst in edges:
        amont_of.setdefault(dst, []).append(src)

    boards_preview = []
    for b in boards:
        proposed = amont_of.get(b, [])
        if not proposed and b not in all_dest and board_types[b] != "groupes_electrogenes":
            proposed = ["__RESEAU_HT__"]
        boards_preview.append({"name": b, "type": board_types[b], "proposed_amonts": proposed})

    return {
        "boards": boards,
        "board_types": board_types,
        "circuits_by_board": circuits_by_board,
        "declared_amonts": declared_amonts,
        "boards_preview": boards_preview,
    }


def analyze_pdf(pdf_path):
    """
    Analyse complete d'un export Caneco : renvoie un dict structure pret a
    etre importe (sans toucher a la base de donnees).
    """
    pages = _pdftotext_pages(pdf_path)
    boards, edges, board_pages = build_hierarchy(pages)
    circuits_by_board = extract_all_circuits(pages, board_pages)

    board_norm = {b: _normalize(b) for b in boards}
    declared_amonts = _get_declared_amonts(pages, board_pages, board_norm)

    children = {}
    for src, dst in edges:
        children.setdefault(src, []).append(dst)
    all_dest = set(dst for _, dst in edges)
    roots = [b for b in boards if b not in all_dest]

    board_types = {b: classify_board_type(b) for b in boards}

    return {
        "boards": boards,
        "board_types": board_types,
        "edges": sorted(edges),
        "roots": roots,
        "circuits_by_board": circuits_by_board,
        "declared_amonts": declared_amonts,
        "nb_pages": len(pages),
    }
