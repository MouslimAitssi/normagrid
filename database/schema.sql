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

CREATE TABLE IF NOT EXISTS reference_puissances_transfos_kva (
    value REAL PRIMARY KEY,
    label TEXT NOT NULL
);
INSERT OR IGNORE INTO reference_puissances_transfos_kva (value, label) VALUES
    (250, '250'), (400, '400'), (630, '630'), (800, '800');

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
