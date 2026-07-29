const Api = {
  async getSchema() {
    const r = await fetch("/api/schema");
    return r.json();
  },
  async list(table) {
    const r = await fetch(`/api/${table}`);
    if (!r.ok) throw new Error(`Erreur chargement ${table}`);
    return r.json();
  },
  async create(table, data) {
    const r = await fetch(`/api/${table}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    });
    const body = await r.json();
    if (!r.ok) throw new Error(body.error || "Erreur inconnue");
    return body;
  },
  async getRow(table, pkParts) {
    const pk = pkParts.map(encodeURIComponent).join("|");
    const r = await fetch(`/api/${table}/${pk}`);
    const body = await r.json();
    if (!r.ok) throw new Error(body.error || "Erreur inconnue");
    return body;
  },
  async update(table, pkParts, data) {
    const pk = pkParts.map(encodeURIComponent).join("|");
    const r = await fetch(`/api/${table}/${pk}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    });
    const body = await r.json();
    if (!r.ok) throw new Error(body.error || "Erreur inconnue");
    return body;
  },
  async remove(table, pkParts) {
    const pk = pkParts.map(encodeURIComponent).join("|");
    const r = await fetch(`/api/${table}/${pk}`, { method: "DELETE" });
    const body = await r.json();
    if (!r.ok) throw new Error(body.error || "Erreur suppression");
    return body;
  },
};
