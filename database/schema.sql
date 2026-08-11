PRAGMA foreign_keys = ON;

-- Hierarchie organisationnelle
CREATE TABLE IF NOT EXISTS client (
    tag  TEXT PRIMARY KEY,
    nom  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS projet (
    tag         TEXT PRIMARY KEY,
    client_tag  TEXT NOT NULL,
    nom         TEXT NOT NULL,
    FOREIGN KEY (client_tag) REFERENCES client(tag)
);

CREATE TABLE IF NOT EXISTS site (
    tag         TEXT PRIMARY KEY,
    client_tag  TEXT NOT NULL,   -- reference le Projet (nommage historique conserve)
    nom         TEXT NOT NULL,
    FOREIGN KEY (client_tag) REFERENCES projet(tag)
);

-- Registre central des tags (anti-doublon + typage polymorphe)
CREATE TABLE IF NOT EXISTS tag (
    tag   TEXT PRIMARY KEY,
    type  TEXT NOT NULL
);

-- Listes de reference utilisees dans les formulaires de saisie
CREATE TABLE IF NOT EXISTS reference_charge_types (
    value TEXT PRIMARY KEY
);
INSERT OR IGNORE INTO reference_charge_types (value) VALUES
    ('U1000R2V 4G10'), ('U1000R2V 4G16'), ('U1000R2V 4G25'),
    ('U1000R2V 4G35'), ('U1000R2V 4G50');

CREATE TABLE IF NOT EXISTS reference_charges (
    id INTEGER PRIMARY KEY,
    designation TEXT NOT NULL,
    type_conso TEXT,
    consom TEXT,
    typ_recept REAL,
    p_electrique_w REAL,
    polarite REAL,
    rendement REAL,
    i_nominal REAL,
    is_50hz INTEGER,
    is_60hz INTEGER,
    is_dc INTEGER,
    k_utilisation REAL,
    k_foison REAL,
    cos_phi REAL,
    cos_phi_dem REAL,
    id_sur_in REAL,
    un_min REAL,
    un_max REAL
);

CREATE TABLE IF NOT EXISTS reference_cables (
    id INTEGER PRIMARY KEY,
    designation TEXT NOT NULL,
    famille_cable TEXT,
    section TEXT,
    section_txt TEXT,
    section_reelle REAL,
    nb_conducteur REAL,
    metal_ame REAL,
    is_arme INTEGER,
    type_conduct REAL,
    vert_jaune INTEGER,
    famille_cu_al TEXT,
    temp_max REAL,
    diametre REAL,
    poids REAL,
    iz_air REAL,
    un REAL,
    un_max REAL,
    raw_data_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS reference_puissances_transfos_kva (
    puissance_kva REAL PRIMARY KEY,
    hta_kv REAL,
    bt_v REAL,
    couplage TEXT,
    isolant TEXT,
    uk_ute_pct REAL,
    p0_ute_w REAL,
    pk_ute_w REAL,
    i0_ute_pct REAL,
    p0_tier2_max_w REAL,
    pk_tier2_max_w REAL,
    gain_p0_w REAL,
    reduction_p0_pct REAL,
    gain_pk_w REAL,
    reduction_pk_pct REAL,
    in_bt_a REAL,
    ik3_ute_approx_ka REAL
);
INSERT OR REPLACE INTO reference_puissances_transfos_kva (
    puissance_kva, hta_kv, bt_v, couplage, isolant, uk_ute_pct,
    p0_ute_w, pk_ute_w, i0_ute_pct, p0_tier2_max_w, pk_tier2_max_w,
    gain_p0_w, reduction_p0_pct, gain_pk_w, reduction_pk_pct, in_bt_a,
    ik3_ute_approx_ka
) VALUES
    (100, 20, 400, 'Dyn11', 'Huile / ONAN', 4, 210, 2150, 2.5, 130, 1250, 80, 0.38095238095238093, 900, 0.4186046511627907, 144.33756729740645, 3.608439182435161),
    (160, 20, 400, 'Dyn11', 'Huile / ONAN', 4, 460, 2350, 2.3, 189, 1750, 271, 0.5891304347826087, 600, 0.2553191489361702, 230.9401076758503, 5.773502691896257),
    (250, 20, 400, 'Dyn11', 'Huile / ONAN', 4, 650, 3250, 2.1, 270, 2350, 380, 0.5846153846153846, 900, 0.27692307692307694, 360.8439182435161, 9.021097956087901),
    (315, 20, 400, 'Dyn11', 'Huile / ONAN', 4, 800, 3900, 2, 324, 2800, 476, 0.595, 1100, 0.28205128205128205, 454.6633369868303, 11.366583424670758),
    (400, 20, 400, 'Dyn11', 'Huile / ONAN', 4, 930, 4600, 1.9, 387, 3250, 543, 0.5838709677419355, 1350, 0.29347826086956524, 577.3502691896258, 14.433756729740644),
    (500, 20, 400, 'Dyn11', 'Huile / ONAN', 4, 1100, 5500, 1.9, 459, 3900, 641, 0.5827272727272728, 1600, 0.2909090909090909, 721.6878364870322, 18.042195912175803),
    (630, 20, 400, 'Dyn11', 'Huile / ONAN', 4, 1300, 6500, 1.8, 540, 4600, 760, 0.5846153846153846, 1900, 0.2923076923076923, 909.3266739736606, 22.733166849341515),
    (800, 20, 400, 'Dyn11', 'Huile / ONAN', 6, 1220, 10700, 2.5, 585, 6000, 635, 0.5204918032786885, 4700, 0.4392523364485981, 1154.7005383792516, 19.245008972987527),
    (1000, 20, 400, 'Dyn11', 'Huile / ONAN', 6, 1470, 13000, 2.4, 693, 7600, 777, 0.5285714285714286, 5400, 0.4153846153846154, 1443.3756729740644, 24.056261216234407),
    (1250, 20, 400, 'Dyn11', 'Huile / ONAN', 6, 1800, 16000, 2.2, 855, 9500, 945, 0.525, 6500, 0.40625, 1804.2195912175805, 30.07032652029301),
    (1600, 20, 400, 'Dyn11', 'Huile / ONAN', 6, 2300, 20000, 2, 1080, 12000, 1220, 0.5304347826086957, 8000, 0.4, 2309.401076758503, 38.490017945975055),
    (2000, 20, 400, 'Dyn11', 'Huile / ONAN', 6, 2750, 25500, 1.9, 1305, 15000, 1445, 0.5254545454545455, 10500, 0.4117647058823529, 2886.751345948129, 48.112522432468815),
    (2500, 20, 400, 'Dyn11', 'Huile / ONAN', 6, 3350, 32000, 1.8, 1575, 18500, 1775, 0.5298507462686567, 13500, 0.421875, 3608.439182435161, 60.14065304058602),
    (3150, 20, 400, 'Dyn11', 'Huile / ONAN', 7, 4380, 33000, 1.7, 1980, 23000, 2400, 0.547945205479452, 10000, 0.30303030303030304, 4546.633369868303, 64.9519052838329);

CREATE TABLE IF NOT EXISTS reference_puissances_groupes_electrogenes_kva (
    value REAL PRIMARY KEY,
    label TEXT NOT NULL
);
INSERT OR IGNORE INTO reference_puissances_groupes_electrogenes_kva (value, label) VALUES
    (250, '250'), (400, '400'), (630, '630'), (800, '800');

-- Equipements
CREATE TABLE IF NOT EXISTS tableaux (
    tag_id      TEXT PRIMARY KEY,
    site_id     TEXT NOT NULL,
    amont_id    TEXT,
    type        TEXT,
    tension_v   REAL,
    FOREIGN KEY (tag_id)  REFERENCES tag(tag),
    FOREIGN KEY (site_id) REFERENCES site(tag),
    FOREIGN KEY (amont_id) REFERENCES tag(tag)
);

CREATE TABLE IF NOT EXISTS transfos (
    tag_id           TEXT PRIMARY KEY,
    site_id          TEXT NOT NULL,
    amont_id         TEXT,
    puissance_kva    REAL,
    protection_modele  TEXT,
    calibre_a          REAL,
    differentiel_ma    REAL,
    FOREIGN KEY (tag_id)   REFERENCES tag(tag),
    FOREIGN KEY (site_id)  REFERENCES site(tag),
    FOREIGN KEY (amont_id) REFERENCES tag(tag)
);

CREATE TABLE IF NOT EXISTS groupes_electrogenes (
    tag_id         TEXT PRIMARY KEY,
    site_id        TEXT NOT NULL,
    puissance_kva  REAL,
    FOREIGN KEY (tag_id)  REFERENCES tag(tag),
    FOREIGN KEY (site_id) REFERENCES site(tag)
);

CREATE TABLE IF NOT EXISTS reseau_ht (
    tag_id        TEXT PRIMARY KEY,
    site_id       TEXT NOT NULL,
    nom           TEXT,
    tension_kv    REAL,
    pcc_max_mva   REAL,
    x_r_max       REAL,
    pcc_min_mva   REAL,
    x_r_min       REAL,
    FOREIGN KEY (tag_id)  REFERENCES tag(tag),
    FOREIGN KEY (site_id) REFERENCES site(tag)
);

CREATE TABLE IF NOT EXISTS cable (
    tag_id           TEXT PRIMARY KEY,
    site_id          TEXT NOT NULL,
    amont_id         TEXT,
    type             TEXT,
    section          TEXT,
    longueur_m         REAL,
    protection_modele  TEXT,
    calibre_a          REAL,
    differentiel_ma    REAL,
    FOREIGN KEY (tag_id)   REFERENCES tag(tag),
    FOREIGN KEY (site_id)  REFERENCES site(tag),
    FOREIGN KEY (amont_id) REFERENCES tag(tag)
);

CREATE TABLE IF NOT EXISTS charge (
    tag_id           TEXT PRIMARY KEY,
    site_id          TEXT NOT NULL,
    amont_id         TEXT,
    type             TEXT,
    puissance        REAL,
    protection_modele  TEXT,
    calibre_a          REAL,
    differentiel_ma    REAL,
    rev                TEXT,
    system_area        TEXT,
    equipment_name     TEXT,
    installed_power_kw REAL,
    absorbed_power     REAL,
    voltage            REAL,
    phase              TEXT,
    freq               REAL,
    special_reqts      TEXT,
    w_s                TEXT,
    c_i                TEXT,
    e_ne               TEXT,
    pct_e              REAL,
    unite              TEXT,
    type_equipement    TEXT,
    vitesse            REAL,
    contenu            TEXT,
    nombre             REAL,
    p_vfd              REAL,
    cos_phi_vfd        REAL,
    rend_vfd           REAL,
    longueur           REAL,
    mode_de_pose       TEXT,
    k_util             REAL,
    k_simul            REAL,
    cos_phi            REAL,
    rendement          REAL,
    switchgear_mcc     TEXT,
    equipment_tag_no   TEXT,
    FOREIGN KEY (tag_id)   REFERENCES tag(tag),
    FOREIGN KEY (site_id)  REFERENCES site(tag),
    FOREIGN KEY (amont_id) REFERENCES tag(tag)
);

-- Table de jointure : un tableau peut avoir plusieurs amonts
CREATE TABLE IF NOT EXISTS tableau_jointure (
    tableau_tag      TEXT NOT NULL,
    amont_tag        TEXT NOT NULL,
    protection_modele  TEXT,
    calibre_a          REAL,
    differentiel_ma    REAL,
    PRIMARY KEY (tableau_tag, amont_tag),
    FOREIGN KEY (tableau_tag) REFERENCES tableaux(tag_id),
    FOREIGN KEY (amont_tag)   REFERENCES tag(tag)
);

-- Table de preparation (staging) de l'import Caneco : une ligne par circuit
-- brut extrait du PDF, modifiable par l'utilisateur avant toute conversion
-- en equipements reels (tableaux/transfos/cables/charges).
CREATE TABLE IF NOT EXISTS import_caneco_staging (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    board_repere        TEXT,
    board_designation   TEXT,
    amont_normal        TEXT,
    amont_secours       TEXT,
    circuit_repere      TEXT,
    circuit_designation TEXT,
    nombre              TEXT,
    consommation        TEXT,
    alimentation        TEXT,
    jdb_amont           TEXT,
    liaison_type        TEXT,
    longueur            TEXT,
    ame                 TEXT,
    l_max_prot          TEXT,
    delta_u_circuit     TEXT,
    delta_u_totale      TEXT,
    cable               TEXT,
    neutre              TEXT,
    pe_pen              TEXT,
    separe              TEXT,
    taux_harmonique     TEXT,
    protection          TEXT,
    calibre             TEXT,
    i_delta_n           TEXT,
    ir                  TEXT,
    im_isd              TEXT,
    affectation_phases  TEXT,
    type_detecte        TEXT,
    converti            INTEGER DEFAULT 0
);
