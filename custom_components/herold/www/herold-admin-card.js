/**
 * Herold Admin Card
 *
 * Lovelace Custom Card zur Verwaltung von Topics, Rollen, Empfängern,
 * Mapping und Einstellungen in einem einzigen Panel.
 *
 * Liest Daten aus den Sensor-Attributen:
 *   - sensor.herold_aktive_topics      (Topics + log_only)
 *   - sensor.herold_rollen              (Rollen + Mitglieder)
 *   - sensor.herold_empfaenger          (Empfänger + welche Rollen)
 *   - sensor.herold_mapping             (Topic → wirksame Rollen)
 *   - sensor.herold_einstellungen       (Fallback + Retention)
 *   - sensor.herold_unzugeordnete_topics (Warn-Zähler)
 *
 * Änderungen gehen direkt über die herold.*-Services und werden durch
 * das `herold_config_updated`-Event live reflektiert.
 */

const TABS = [
  { id: "topics", label: "Topics", icon: "🏷️" },
  { id: "rollen", label: "Rollen", icon: "👥" },
  { id: "empfaenger", label: "Empfänger", icon: "📱" },
  { id: "mapping", label: "Mapping", icon: "🔀" },
  { id: "einstellungen", label: "Einstellungen", icon: "⚙️" },
];

const SEVERITIES = ["info", "warnung", "kritisch"];
const INTERRUPTION_LEVELS = ["passive", "active", "time-sensitive", "critical"];

class HeroldAdminCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._activeTab = "topics";
    this._editing = null; // { typ: 'topic'|'rolle'|..., id, daten, isNeu }
    this._unsubscribe = null;
    this._initialized = false;
    this._lastSig = "";
  }

  setConfig(config) {
    this.config = config || {};
  }

  set hass(hass) {
    const first = !this._hass;
    this._hass = hass;

    if (first) {
      this._initialized = true;
      this._subscribe();
      this._render();
      this._lastSig = this._dataSignature();
      return;
    }

    // Während Edit-Dialog offen ist: keine Re-Renders durch State-Updates
    // (würde Form-Eingaben verwerfen und Click-Handler neu binden).
    if (this._editing) return;

    // Nur re-rendern wenn sich Herold-relevante Daten geändert haben.
    const sig = this._dataSignature();
    if (sig !== this._lastSig) {
      this._lastSig = sig;
      this._render();
    }
  }

  _dataSignature() {
    const keys = [
      "sensor.herold_aktive_topics",
      "sensor.herold_rollen",
      "sensor.herold_empfanger",
      "sensor.herold_topic_mapping",
      "sensor.herold_einstellungen",
      "sensor.herold_unzugeordnete_topics",
    ];
    return keys
      .map((k) => this._hass?.states?.[k]?.last_updated || "")
      .join("|");
  }

  async _subscribe() {
    const handler = () => {
      if (this._editing) return;
      this._render();
    };
    try {
      this._unsubscribe = await this._hass.connection.subscribeEvents(
        handler,
        "herold_config_updated"
      );
      this._unsubTopics = await this._hass.connection.subscribeEvents(
        handler,
        "herold_topic_registered"
      );
    } catch (e) {
      console.warn("Herold Admin Card: Event-Abo fehlgeschlagen", e);
    }
  }

  disconnectedCallback() {
    if (this._unsubscribe) this._unsubscribe();
    if (this._unsubTopics) this._unsubTopics();
  }

  // ------------------------------------------------------------------
  // Daten aus Sensoren
  // ------------------------------------------------------------------

  _topics() {
    return this._hass.states["sensor.herold_aktive_topics"]?.attributes?.topics || [];
  }
  _rollen() {
    return this._hass.states["sensor.herold_rollen"]?.attributes?.rollen || [];
  }
  _empfaenger() {
    // HA slugify: "Empfänger" → "empfanger" (Umlaut-Strip)
    return this._hass.states["sensor.herold_empfanger"]?.attributes?.empfaenger || [];
  }
  _mapping() {
    // HA slugify: "Topic-Mapping" → "topic_mapping"
    return this._hass.states["sensor.herold_topic_mapping"]?.attributes?.mapping || [];
  }
  _einstellungen() {
    const a = this._hass.states["sensor.herold_einstellungen"]?.attributes || {};
    return {
      fallback_rolle: a.fallback_rolle || null,
      retention_eintraege: a.retention_eintraege ?? 2000,
      retention_tage: a.retention_tage ?? 30,
    };
  }
  _unzugeordnete() {
    return this._hass.states["sensor.herold_unzugeordnete_topics"]?.attributes?.topics || [];
  }

  // ------------------------------------------------------------------
  // Service-Calls
  // ------------------------------------------------------------------

  async _callService(service, data) {
    try {
      await this._hass.connection.sendMessagePromise({
        type: "call_service",
        domain: "herold",
        service,
        service_data: data,
      });
      return { ok: true };
    } catch (e) {
      console.error(`Herold Admin Card: ${service} fehlgeschlagen`, e);
      return { ok: false, error: e.message || String(e) };
    }
  }

  // ------------------------------------------------------------------
  // Rendering
  // ------------------------------------------------------------------

  _render() {
    if (!this.shadowRoot) return;
    this.shadowRoot.innerHTML = `
      <style>${this._css()}</style>
      <ha-card>
        <div class="root">
          ${this._renderQuickActions()}
          ${this._renderTabs()}
          <div class="content">${this._renderActiveTab()}</div>
        </div>
        ${this._editing ? this._renderEditDialog() : ""}
      </ha-card>
    `;
    this._bindEvents();
  }

  _renderQuickActions() {
    const topicsOhneRollen = this._unzugeordnete();
    const rollenOhneMitglieder = this._rollen().filter((r) => !r.mitglieder?.length);
    const empfOhneRollen = this._empfaenger().filter((e) => !e.rollen?.length);
    const warnungen = [];
    if (topicsOhneRollen.length)
      warnungen.push({
        text: `${topicsOhneRollen.length} Topic(s) ohne Rollen`,
        tab: "mapping",
      });
    if (rollenOhneMitglieder.length)
      warnungen.push({
        text: `${rollenOhneMitglieder.length} Rolle(n) ohne Mitglieder`,
        tab: "rollen",
      });
    if (empfOhneRollen.length)
      warnungen.push({
        text: `${empfOhneRollen.length} Empfänger ohne Rolle`,
        tab: "empfaenger",
      });
    if (!warnungen.length) {
      return `<div class="qa ok">✓ Alles zugeordnet — keine Warnungen</div>`;
    }
    return `
      <div class="qa warn">
        ⚠ ${warnungen.map((w) => `<a data-goto="${w.tab}">${w.text}</a>`).join(" · ")}
      </div>
    `;
  }

  _renderTabs() {
    return `
      <div class="tabs">
        ${TABS.map(
          (t) => `
          <button class="tab ${t.id === this._activeTab ? "active" : ""}"
                  data-tab="${t.id}">
            <span class="tab-icon">${t.icon}</span>${t.label}
            <span class="tab-count">${this._tabCount(t.id)}</span>
          </button>
        `
        ).join("")}
      </div>
    `;
  }

  _tabCount(tabId) {
    switch (tabId) {
      case "topics":
        return this._topics().length;
      case "rollen":
        return this._rollen().length;
      case "empfaenger":
        return this._empfaenger().length;
      case "mapping":
        return this._mapping().filter((m) => m.override !== null).length;
      case "einstellungen":
        return "";
    }
    return "";
  }

  _renderActiveTab() {
    switch (this._activeTab) {
      case "topics":
        return this._renderTopics();
      case "rollen":
        return this._renderRollen();
      case "empfaenger":
        return this._renderEmpfaenger();
      case "mapping":
        return this._renderMapping();
      case "einstellungen":
        return this._renderEinstellungen();
    }
    return "";
  }

  // ---------- Topics ----------
  _renderTopics() {
    const topics = [...this._topics()].sort((a, b) => a.id.localeCompare(b.id));
    const mapping = new Map(this._mapping().map((m) => [m.topic, m]));
    const rows = topics
      .map((t) => {
        const m = mapping.get(t.id);
        const wirksam = m?.wirksam || [];
        const hasOverride = m?.override !== null && m?.override !== undefined;
        const rollenHtml = wirksam.length
          ? wirksam
              .map(
                (r) =>
                  `<span class="chip ${hasOverride ? "override" : "default"}">${r}</span>`
              )
              .join("")
          : `<span class="chip warn">— keine —</span>`;
        const flags = [];
        if (t.log_only) flags.push(`<span class="chip">🔇 log</span>`);
        if (t.interruption_level)
          flags.push(`<span class="chip override" title="iOS Interruption-Level">🔔 ${t.interruption_level}</span>`);
        return `
          <tr data-edit-topic="${t.id}">
            <td class="mono">${t.id}</td>
            <td>${t.name || "—"}</td>
            <td><span class="sev sev-${t.severity}">${t.severity}</span></td>
            <td>${flags.join(" ") || ""}</td>
            <td>${rollenHtml}</td>
          </tr>`;
      })
      .join("");
    return `
      <div class="toolbar">
        <button class="btn-new" data-new="topic">➕ Neues Topic</button>
      </div>
      <table class="list">
        <thead><tr>
          <th>ID</th><th>Name</th><th>Severity</th><th>Flags</th><th>Wirksame Rollen</th>
        </tr></thead>
        <tbody>${rows || `<tr><td colspan="5" class="empty">Keine Topics</td></tr>`}</tbody>
      </table>
    `;
  }

  // ---------- Rollen ----------
  _renderRollen() {
    const empf = new Map(this._empfaenger().map((e) => [e.id, e]));
    const rollen = this._rollen();
    const rows = rollen
      .map((r) => {
        const mitglieder = (r.mitglieder || [])
          .map((mid) => {
            const e = empf.get(mid);
            const label = e ? `${e.name || e.id}` : mid;
            const known = e ? "" : " unbekannt";
            return `<span class="chip${known}">${label}</span>`;
          })
          .join("");
        return `
          <tr data-edit-rolle="${r.id}">
            <td class="mono">${r.id}${r.ist_fallback ? ' <span class="badge">Fallback</span>' : ""}</td>
            <td>${r.name || "—"}</td>
            <td>${mitglieder || '<span class="chip warn">— leer —</span>'}</td>
            <td class="num">${r.mitglieder?.length || 0}</td>
          </tr>`;
      })
      .join("");
    return `
      <div class="toolbar">
        <button class="btn-new" data-new="rolle">➕ Neue Rolle</button>
      </div>
      <table class="list">
        <thead><tr>
          <th>ID</th><th>Name</th><th>Mitglieder</th><th>Anzahl</th>
        </tr></thead>
        <tbody>${rows || `<tr><td colspan="4" class="empty">Keine Rollen</td></tr>`}</tbody>
      </table>
    `;
  }

  // ---------- Empfänger ----------
  _renderEmpfaenger() {
    const empf = this._empfaenger();
    const rows = empf
      .map((e) => {
        const rollen = (e.rollen || [])
          .map((r) => `<span class="chip">${r}</span>`)
          .join("");
        return `
          <tr data-edit-empfaenger="${e.id}">
            <td class="mono">${e.id}</td>
            <td>${e.name || "—"}</td>
            <td><code>${e.typ}</code></td>
            <td class="mono">${e.ziel}</td>
            <td>${rollen || '<span class="chip warn">— keine Rolle —</span>'}</td>
          </tr>`;
      })
      .join("");
    return `
      <div class="toolbar">
        <button class="btn-new" data-new="empfaenger">➕ Neuer Empfänger</button>
      </div>
      <table class="list">
        <thead><tr>
          <th>ID</th><th>Name</th><th>Typ</th><th>Ziel</th><th>In Rollen</th>
        </tr></thead>
        <tbody>${rows || `<tr><td colspan="5" class="empty">Keine Empfänger</td></tr>`}</tbody>
      </table>
    `;
  }

  // ---------- Mapping ----------
  _renderMapping() {
    const mapping = this._mapping();
    const rows = mapping
      .map((m) => {
        // Sensor-Format: m.rollen = {producer_default, override, wirksam}
        // m.log_only / m.interruption_level / m.default_severity analog.
        const rTri = m.rollen || { producer_default: [], override: null, wirksam: [] };
        const logEff = m.wirksam_log_only !== undefined
          ? m.wirksam_log_only
          : m.log_only?.wirksam ?? false;

        const prod = (rTri.producer_default || [])
          .map((r) => `<span class="chip default">${r}</span>`)
          .join("");
        const over = rTri.override
          ? rTri.override.map((r) => `<span class="chip override">${r}</span>`).join("")
          : '<span class="dim">— kein Override —</span>';
        let wirksam;
        if (rTri.wirksam && rTri.wirksam.length) {
          wirksam = rTri.wirksam.map((r) => `<span class="chip">${r}</span>`).join("");
        } else if (logEff) {
          wirksam = `<span class="chip">🔇 log_only</span>`;
        } else {
          wirksam = `<span class="chip warn">⚠ keine Rollen</span>`;
        }
        return `
          <tr data-edit-mapping="${m.topic}" class="${logEff ? "dimmed" : ""}">
            <td class="mono">${m.topic}</td>
            <td>${prod || '<span class="dim">—</span>'}</td>
            <td>${over}</td>
            <td>${wirksam}</td>
          </tr>`;
      })
      .join("");
    return `
      <div class="info">
        Override hat Vorrang vor Producer-Default. Klick auf eine Zeile zum Ändern.
        <br>Log-only-Topics brauchen keine Rollen (werden nicht als Warnung gezählt).
      </div>
      <table class="list">
        <thead><tr>
          <th>Topic</th><th>Producer-Default</th><th>Admin-Override</th><th>Wirksam</th>
        </tr></thead>
        <tbody>${rows || `<tr><td colspan="4" class="empty">Keine Topics</td></tr>`}</tbody>
      </table>
    `;
  }

  // ---------- Einstellungen ----------
  _renderEinstellungen() {
    const e = this._einstellungen();
    const rollenOpts = this._rollen()
      .map((r) => `<option value="${r.id}" ${e.fallback_rolle === r.id ? "selected" : ""}>${r.id} — ${r.name || ""}</option>`)
      .join("");
    return `
      <div class="form">
        <label>Fallback-Rolle
          <select id="fb">
            <option value="" ${!e.fallback_rolle ? "selected" : ""}>— keine —</option>
            ${rollenOpts}
          </select>
        </label>
        <label>Retention — Max. Einträge
          <input id="re" type="number" min="1" max="100000" value="${e.retention_eintraege}">
        </label>
        <label>Retention — Max. Alter in Tagen
          <input id="rt" type="number" min="1" max="3650" value="${e.retention_tage}">
        </label>
        <div class="form-actions">
          <button id="save-einstellungen">Speichern</button>
          <button id="cleanup-jetzt" class="secondary">🧹 Cleanup jetzt ausführen</button>
        </div>
      </div>
    `;
  }

  // ---------- Edit-Dialog ----------
  _renderEditDialog() {
    const e = this._editing;
    let form = "";
    let titel = "";
    switch (e.typ) {
      case "topic": {
        titel = e.isNeu ? "Neues Topic anlegen" : `Topic: ${e.id}`;
        const d = e.daten;
        if (e.isNeu) {
          // Neuer Topic = User ist Producer. Werte gehen direkt als Producer-Defaults.
          const rollenOpts = this._rollen()
            .map(
              (r) => `<option value="${r.id}" ${(d.default_rollen || []).includes(r.id) ? "selected" : ""}>${r.id} — ${r.name || ""}</option>`
            )
            .join("");
          form = `
            <label><span class="lbl-text">Topic-ID</span> <span class="hint">(Kleinbuchstaben, Ziffern, _ und /)</span>
              <input id="f-id" type="text" value="${d.id || ""}" required>
            </label>
            <label><span class="lbl-text">Name</span><input id="f-name" type="text" value="${d.name || ""}"></label>
            <label><span class="lbl-text">Beschreibung</span><textarea id="f-beschreibung">${d.beschreibung || ""}</textarea></label>
            <label><span class="lbl-text">Quelle</span><input id="f-quelle" type="text" value="${d.quelle || ""}" placeholder="z.B. custom_components.pool"></label>
            <label><span class="lbl-text">Default-Severity</span>
              <select id="f-severity">
                ${SEVERITIES.map((s) => `<option ${d.default_severity === s ? "selected" : ""}>${s}</option>`).join("")}
              </select>
            </label>
            <label><span class="lbl-text">Default-Rollen</span> <span class="hint">(Ctrl/Cmd+Klick für mehrere)</span>
              <select id="f-rollen" multiple size="4">${rollenOpts}</select>
            </label>
            <label class="checkbox">
              <input id="f-log-only" type="checkbox" ${d.log_only ? "checked" : ""}>
              <span>Nur Log (keine Zustellung — weder Push noch Last-Resort)</span>
            </label>
            <label><span class="lbl-text">iOS Interruption-Level</span>
              <select id="f-interruption">
                <option value="" ${!d.interruption_level ? "selected" : ""}>— kein Override (Empfänger-Default) —</option>
                ${INTERRUPTION_LEVELS.map(
                  (lv) => `<option value="${lv}" ${d.interruption_level === lv ? "selected" : ""}>${lv}</option>`
                ).join("")}
              </select>
            </label>
          `;
        } else {
          // Existierendes Topic: Producer-Felder (name/beschr/quelle) editierbar,
          // andere als User-Override mit Producer-Default-Anzeige + Reset.
          const sevTri = d.default_severity;
          const rollenTri = d.rollen;
          const logTri = d.log_only;
          const ilTri = d.interruption_level;

          const dim = (val) =>
            val === null || val === undefined || val === ""
              ? '<span class="dim">—</span>'
              : `<span class="mono">${val}</span>`;
          const dimList = (arr) =>
            !arr || arr.length === 0
              ? '<span class="dim">—</span>'
              : arr.map((r) => `<span class="chip default">${r}</span>`).join(" ");

          // Override-Wert für Vorbelegung der Inputs
          const sevOv = sevTri.override;
          const ilOv = ilTri.override;
          const logOv = logTri.override; // null = kein Override, true/false = Override

          const rollenOpts = this._rollen()
            .map(
              (r) =>
                `<option value="${r.id}" ${(rollenTri.override || []).includes(r.id) ? "selected" : ""}>${r.id} — ${r.name || ""}</option>`
            )
            .join("");

          form = `
            <div class="readonly"><span class="lbl">ID</span> <span class="mono">${d.id}</span></div>
            <label><span class="lbl-text">Name</span><input id="f-name" type="text" value="${d.name || ""}"></label>
            <label><span class="lbl-text">Beschreibung</span><textarea id="f-beschreibung">${d.beschreibung || ""}</textarea></label>
            <label><span class="lbl-text">Quelle</span><input id="f-quelle" type="text" value="${d.quelle || ""}" placeholder="z.B. custom_components.pool"></label>

            <div class="section-head">User-Overrides <span class="hint">(leer = Producer-Default greift)</span></div>

            <label><span class="lbl-text">Default-Severity</span> <span class="hint">Producer: ${dim(sevTri.producer_default)}</span>
              <select id="f-sev-override">
                <option value="" ${!sevOv ? "selected" : ""}>— kein Override —</option>
                ${SEVERITIES.map((s) => `<option value="${s}" ${sevOv === s ? "selected" : ""}>${s}</option>`).join("")}
              </select>
            </label>

            <label><span class="lbl-text">Default-Rollen</span> <span class="hint">Producer: ${dimList(rollenTri.producer_default)}</span>
              <select id="f-rollen-override" multiple size="4">${rollenOpts}</select>
              <span class="hint">leere Auswahl = kein Override (Producer-Default greift)</span>
            </label>

            <label><span class="lbl-text">log_only</span> <span class="hint">Producer: ${dim(String(logTri.producer_default))}</span>
              <select id="f-log-override">
                <option value="" ${logOv === null || logOv === undefined ? "selected" : ""}>— kein Override —</option>
                <option value="true" ${logOv === true ? "selected" : ""}>true (nur Log)</option>
                <option value="false" ${logOv === false ? "selected" : ""}>false (Push aktiv)</option>
              </select>
            </label>

            <label><span class="lbl-text">iOS Interruption-Level</span> <span class="hint">Producer: ${dim(ilTri.producer_default)}</span>
              <select id="f-il-override">
                <option value="" ${!ilOv ? "selected" : ""}>— kein Override —</option>
                ${INTERRUPTION_LEVELS.map(
                  (lv) => `<option value="${lv}" ${ilOv === lv ? "selected" : ""}>${lv}</option>`
                ).join("")}
              </select>
            </label>

            <button class="secondary" data-reset-overrides>↺ Alle Overrides zurücksetzen</button>
          `;
        }
        break;
      }
      case "rolle": {
        titel = e.isNeu ? "Neue Rolle anlegen" : `Rolle: ${e.id}`;
        const d = e.daten;
        const empfOpts = this._empfaenger()
          .map(
            (ep) =>
              `<option value="${ep.id}" ${(d.mitglieder || []).includes(ep.id) ? "selected" : ""}>${ep.id} — ${ep.name || ""} (${ep.ziel})</option>`
          )
          .join("");
        form = `
          ${
            e.isNeu
              ? `<label><span class="lbl-text">Rollen-ID</span> <span class="hint">(kleingeschrieben, z.B. <code>erwachsener</code>)</span><input id="f-id" type="text" value="${d.id || ""}" required></label>`
              : `<div class="readonly"><span class="lbl">ID</span> <span class="mono">${d.id}</span>${d.ist_fallback ? ' <span class="badge">Fallback</span>' : ""}</div>`
          }
          <label><span class="lbl-text">Name</span><input id="f-name" type="text" value="${d.name || ""}"></label>
          <label><span class="lbl-text">Mitglieder (Empfänger)</span> <span class="hint">(Ctrl/Cmd+Klick)</span>
            <select id="f-mitglieder" multiple size="6">${empfOpts}</select>
          </label>
        `;
        break;
      }
      case "empfaenger": {
        titel = e.isNeu ? "Neuen Empfänger anlegen" : `Empfänger: ${e.id}`;
        const d = e.daten;
        form = `
          ${
            e.isNeu
              ? `<label><span class="lbl-text">Empfänger-ID</span><input id="f-id" type="text" value="${d.id || ""}" required></label>`
              : `<div class="readonly"><span class="lbl">ID</span> <span class="mono">${d.id}</span></div>`
          }
          <label><span class="lbl-text">Typ</span>
            <select id="f-typ">
              <option value="notify_service" ${d.typ === "notify_service" ? "selected" : ""}>notify_service</option>
            </select>
          </label>
          <label><span class="lbl-text">Ziel</span> <span class="hint">(domain.service, z.B. notify.mobile_app_iphone_17_ul)</span>
            <input id="f-ziel" type="text" value="${d.ziel || ""}" required>
          </label>
          <label><span class="lbl-text">Name</span><input id="f-name" type="text" value="${d.name || ""}"></label>
        `;
        break;
      }
      case "mapping": {
        titel = `Mapping: ${e.id}`;
        const d = e.daten;
        const rollenOpts = this._rollen()
          .map(
            (r) =>
              `<option value="${r.id}" ${(d.override_rollen || d.wirksam || []).includes(r.id) ? "selected" : ""}>${r.id} — ${r.name || ""}</option>`
          )
          .join("");
        const producerDefault =
          d.producer_default?.length > 0
            ? d.producer_default.map((r) => `<span class="chip default">${r}</span>`).join("")
            : '<span class="dim">—</span>';
        // Topic-Eigenschaften als Read-Only-Info anzeigen
        const t = this._topics().find((x) => x.id === d.id);
        const topicFlags = [];
        if (t?.severity)
          topicFlags.push(`<span class="sev sev-${t.severity}">${t.severity}</span>`);
        if (t?.log_only) topicFlags.push(`<span class="chip">🔇 log_only</span>`);
        if (t?.interruption_level)
          topicFlags.push(`<span class="chip override">🔔 ${t.interruption_level}</span>`);
        const flagsHtml = topicFlags.length
          ? topicFlags.join(" ")
          : '<span class="dim">—</span>';
        form = `
          <div class="readonly">
            <span class="lbl">Topic</span> <span class="mono">${d.id}</span>
          </div>
          <div class="readonly">
            <span class="lbl">Topic-Eigenschaften</span> ${flagsHtml}
          </div>
          <div class="readonly">
            <span class="lbl">Producer-Default</span> ${producerDefault}
          </div>
          <label><span class="lbl-text">Admin-Override</span> <span class="hint">(leere Auswahl = kein Override, Producer-Default greift)</span>
            <select id="f-override" multiple size="6">${rollenOpts}</select>
          </label>
          <div class="hint-link">
            Severity, log_only und iOS Interruption-Level werden im
            <a data-open-topic="${d.id}">Topic-Editor</a> gesetzt.
          </div>
        `;
        break;
      }
    }
    const kannLoeschen = !e.isNeu && e.typ !== "mapping";
    return `
      <dialog class="modal" data-overlay>
        <div class="dialog" data-dialog>
          <div class="dialog-head">
            <h3>${titel}</h3>
            <button class="close" data-close>✕</button>
          </div>
          <div class="dialog-body">
            ${form}
          </div>
          <div class="dialog-actions">
            ${kannLoeschen ? `<button class="danger" data-delete>🗑 Löschen</button>` : ""}
            <div class="grow"></div>
            <button class="secondary" data-close>Abbrechen</button>
            <button class="primary" data-save>${e.isNeu ? "Anlegen" : "Speichern"}</button>
          </div>
        </div>
      </dialog>
    `;
  }

  // ------------------------------------------------------------------
  // Events
  // ------------------------------------------------------------------

  _bindEvents() {
    const sr = this.shadowRoot;
    if (!sr) return;

    sr.querySelectorAll(".tab").forEach((btn) =>
      btn.addEventListener("click", () => {
        this._activeTab = btn.dataset.tab;
        this._render();
      })
    );
    sr.querySelectorAll("[data-goto]").forEach((a) =>
      a.addEventListener("click", () => {
        this._activeTab = a.dataset.goto;
        this._render();
      })
    );
    sr.querySelectorAll("[data-edit-topic]").forEach((tr) =>
      tr.addEventListener("click", () => this._openTopicEdit(tr.dataset.editTopic))
    );
    sr.querySelectorAll("[data-edit-rolle]").forEach((tr) =>
      tr.addEventListener("click", () => this._openRolleEdit(tr.dataset.editRolle))
    );
    sr.querySelectorAll("[data-edit-empfaenger]").forEach((tr) =>
      tr.addEventListener("click", () =>
        this._openEmpfaengerEdit(tr.dataset.editEmpfaenger)
      )
    );
    sr.querySelectorAll("[data-edit-mapping]").forEach((tr) =>
      tr.addEventListener("click", () =>
        this._openMappingEdit(tr.dataset.editMapping)
      )
    );
    sr.querySelectorAll("[data-new]").forEach((btn) =>
      btn.addEventListener("click", () => this._openNeu(btn.dataset.new))
    );

    const saveSettings = sr.querySelector("#save-einstellungen");
    if (saveSettings) saveSettings.addEventListener("click", () => this._saveEinstellungen());
    const cleanup = sr.querySelector("#cleanup-jetzt");
    if (cleanup) cleanup.addEventListener("click", () => this._cleanupJetzt());

    // Dialog-Buttons
    sr.querySelectorAll("[data-close]").forEach((b) =>
      b.addEventListener("click", () => {
        this._editing = null;
        this._render();
      })
    );
    const overlay = sr.querySelector("[data-overlay]");
    if (overlay) {
      // Native <dialog>: Top-Layer rendering ignoriert Shadow-DOM-/Transform-
      // Container — funktioniert auch wenn Lovelace-Wrapper transform setzen.
      if (typeof overlay.showModal === "function" && !overlay.open) {
        overlay.showModal();
      }
      // Klick ausserhalb des Dialog-Inhalts (= auf Backdrop) → schliessen.
      // Bei <dialog> trifft der Klick das dialog-Element selbst, wenn auf den
      // ::backdrop geklickt wird.
      overlay.addEventListener("click", (ev) => {
        if (ev.target === overlay) {
          this._editing = null;
          this._render();
        }
      });
      // ESC-Taste schliesst dialog nativ → wir müssen state syncen.
      overlay.addEventListener("close", () => {
        if (this._editing) {
          this._editing = null;
          this._render();
        }
      });
    }
    const saveBtn = sr.querySelector("[data-save]");
    if (saveBtn) saveBtn.addEventListener("click", () => this._saveCurrentEdit());
    const delBtn = sr.querySelector("[data-delete]");
    if (delBtn) delBtn.addEventListener("click", () => this._deleteCurrentEdit());
    const resetOvBtn = sr.querySelector("[data-reset-overrides]");
    if (resetOvBtn)
      resetOvBtn.addEventListener("click", async () => {
        if (!this._editing || this._editing.typ !== "topic" || this._editing.isNeu) return;
        const r = await this._callService("topic_override_setzen", {
          topic: this._editing.id,
          zuruecksetzen: true,
        });
        if (r.ok) {
          this._editing = null;
          this._render();
          this._flash("Alle Overrides zurückgesetzt");
        } else {
          this._flash(`Fehler: ${r.error || "unbekannt"}`, true);
        }
      });
    sr.querySelectorAll("[data-open-topic]").forEach((a) =>
      a.addEventListener("click", () => {
        const topicId = a.dataset.openTopic;
        this._editing = null;
        this._activeTab = "topics";
        this._openTopicEdit(topicId);
      })
    );
  }

  // ------------------------------------------------------------------
  // Edit-Handler
  // ------------------------------------------------------------------

  _openNeu(typ) {
    this._editing = { typ, isNeu: true, id: null, daten: this._leereDaten(typ) };
    this._render();
  }

  _leereDaten(typ) {
    if (typ === "topic")
      return {
        id: "",
        name: "",
        beschreibung: "",
        quelle: "",
        default_severity: "info",
        default_rollen: [],
        log_only: false,
        interruption_level: null,
      };
    if (typ === "rolle") return { id: "", name: "", mitglieder: [] };
    if (typ === "empfaenger")
      return { id: "", typ: "notify_service", ziel: "", name: "" };
    return {};
  }

  _openTopicEdit(id) {
    const t = this._topics().find((x) => x.id === id);
    if (!t) return;
    // Tripel-Felder aus Mapping-Sensor (producer_default | override | wirksam)
    const map = this._mapping().find((m) => m.topic === id) || {};
    const tri = (key, fallback) => {
      const x = map[key];
      if (x && typeof x === "object") return x;
      return { producer_default: fallback, override: null, wirksam: fallback };
    };
    this._editing = {
      typ: "topic",
      isNeu: false,
      id,
      daten: {
        id,
        name: t.name || "",
        beschreibung: t.beschreibung || "",
        quelle: t.quelle || "",
        rollen: tri("rollen", []),
        log_only: tri("log_only", !!t.log_only),
        interruption_level: tri("interruption_level", t.interruption_level || null),
        default_severity: tri("default_severity", t.severity || "info"),
      },
    };
    this._render();
  }

  _openRolleEdit(id) {
    const r = this._rollen().find((x) => x.id === id);
    if (!r) return;
    this._editing = {
      typ: "rolle",
      isNeu: false,
      id,
      daten: {
        id,
        name: r.name || "",
        mitglieder: r.mitglieder || [],
        ist_fallback: !!r.ist_fallback,
      },
    };
    this._render();
  }

  _openEmpfaengerEdit(id) {
    const e = this._empfaenger().find((x) => x.id === id);
    if (!e) return;
    this._editing = {
      typ: "empfaenger",
      isNeu: false,
      id,
      daten: {
        id,
        typ: e.typ || "notify_service",
        ziel: e.ziel || "",
        name: e.name || "",
      },
    };
    this._render();
  }

  _openMappingEdit(id) {
    const m = this._mapping().find((x) => x.topic === id);
    if (!m) return;
    const rTri = m.rollen || { producer_default: [], override: null, wirksam: [] };
    this._editing = {
      typ: "mapping",
      isNeu: false,
      id,
      daten: {
        id,
        producer_default: rTri.producer_default || [],
        override_rollen: rTri.override || rTri.wirksam || [],
        wirksam: rTri.wirksam || [],
      },
    };
    this._render();
  }

  // ------------------------------------------------------------------
  // Save / Delete
  // ------------------------------------------------------------------

  async _saveCurrentEdit() {
    const e = this._editing;
    if (!e) return;
    const sr = this.shadowRoot;
    const get = (sel) => sr.querySelector(sel);
    const multi = (sel) =>
      Array.from(sr.querySelectorAll(`${sel} option:checked`)).map((o) => o.value);

    let res = { ok: false };

    if (e.typ === "topic") {
      const id = e.isNeu ? get("#f-id")?.value.trim() : e.id;
      if (!id) return this._flash("ID ist ein Pflichtfeld", true);
      if (e.isNeu && !/^[a-z0-9_/]+$/.test(id))
        return this._flash("Ungültige Topic-ID (a-z 0-9 _ /)", true);

      if (e.isNeu) {
        // Neuer Topic: alles als Producer-Default via topic_registrieren
        const interruption = get("#f-interruption")?.value || "";
        res = await this._callService("topic_registrieren", {
          topic: id,
          name: get("#f-name")?.value || "",
          beschreibung: get("#f-beschreibung")?.value || "",
          quelle: get("#f-quelle")?.value || "",
          default_severity: get("#f-severity")?.value || "info",
          default_rollen: multi("#f-rollen"),
          log_only: !!get("#f-log-only")?.checked,
          interruption_level: interruption || null,
        });
      } else {
        // Existierend: Producer-Felder via topic_registrieren, Override-Felder via topic_override_setzen
        const r1 = await this._callService("topic_registrieren", {
          topic: id,
          name: get("#f-name")?.value || "",
          beschreibung: get("#f-beschreibung")?.value || "",
          quelle: get("#f-quelle")?.value || "",
        });
        if (!r1.ok) {
          this._flash(`Fehler (Topic): ${r1.error || "unbekannt"}`, true);
          return;
        }
        // Override-Werte einsammeln. Leerer Select = explizit null = Override löschen.
        const sevVal = get("#f-sev-override")?.value || "";
        const ilVal = get("#f-il-override")?.value || "";
        const logVal = get("#f-log-override")?.value || ""; // "", "true", "false"
        const rollenVal = multi("#f-rollen-override");
        const ovPayload = {
          topic: id,
          default_severity: sevVal || null,
          interruption_level: ilVal || null,
          log_only: logVal === "" ? null : logVal === "true",
          default_rollen: rollenVal.length === 0 ? null : rollenVal,
        };
        res = await this._callService("topic_override_setzen", ovPayload);
      }
    } else if (e.typ === "rolle") {
      const id = e.isNeu ? get("#f-id")?.value.trim() : e.id;
      if (!id) return this._flash("ID ist ein Pflichtfeld", true);
      res = await this._callService("rolle_setzen", {
        rolle: id,
        name: get("#f-name")?.value || "",
        mitglieder: multi("#f-mitglieder"),
      });
    } else if (e.typ === "empfaenger") {
      const id = e.isNeu ? get("#f-id")?.value.trim() : e.id;
      if (!id) return this._flash("ID ist ein Pflichtfeld", true);
      const ziel = get("#f-ziel")?.value.trim() || "";
      if (!ziel.includes(".")) return this._flash("Ziel muss domain.service sein", true);
      res = await this._callService("empfaenger_setzen", {
        empfaenger: id,
        typ: get("#f-typ")?.value || "notify_service",
        ziel,
        name: get("#f-name")?.value || "",
      });
    } else if (e.typ === "mapping") {
      const rollen = multi("#f-override");
      if (rollen.length === 0) {
        res = await this._callService("topic_rolle_mapping", {
          topic: e.id,
          zuruecksetzen: true,
        });
      } else {
        res = await this._callService("topic_rolle_mapping", {
          topic: e.id,
          rollen,
        });
      }
    }

    if (res.ok) {
      this._editing = null;
      this._render();
    } else {
      this._flash(`Fehler: ${res.error || "unbekannt"}`, true);
    }
  }

  async _deleteCurrentEdit() {
    const e = this._editing;
    if (!e || e.isNeu) return;
    if (!confirm(`${e.typ.toUpperCase()} "${e.id}" wirklich löschen?`)) return;
    let svc = null;
    let data = {};
    if (e.typ === "topic") {
      svc = "topic_entfernen";
      data = { topic: e.id };
    } else if (e.typ === "rolle") {
      svc = "rolle_entfernen";
      data = { rolle: e.id };
    } else if (e.typ === "empfaenger") {
      svc = "empfaenger_entfernen";
      data = { empfaenger: e.id };
    }
    if (!svc) return;
    const res = await this._callService(svc, data);
    if (res.ok) {
      this._editing = null;
      this._render();
    } else {
      this._flash(`Fehler: ${res.error || "unbekannt"}`, true);
    }
  }

  async _saveEinstellungen() {
    const sr = this.shadowRoot;
    const fb = sr.querySelector("#fb")?.value || "";
    const re = parseInt(sr.querySelector("#re")?.value || "2000", 10);
    const rt = parseInt(sr.querySelector("#rt")?.value || "30", 10);
    const res = await this._callService("einstellungen_setzen", {
      fallback_rolle: fb || null,
      retention_eintraege: re,
      retention_tage: rt,
    });
    this._flash(res.ok ? "Gespeichert ✓" : `Fehler: ${res.error}`, !res.ok);
  }

  async _cleanupJetzt() {
    const res = await this._callService("history_aufraeumen", {});
    this._flash(res.ok ? "Cleanup läuft…" : `Fehler: ${res.error}`, !res.ok);
  }

  _flash(msg, isError = false) {
    const el = document.createElement("div");
    el.className = `flash ${isError ? "error" : "ok"}`;
    el.textContent = msg;
    this.shadowRoot.querySelector(".root")?.prepend(el);
    setTimeout(() => el.remove(), 3500);
  }

  // ------------------------------------------------------------------
  // Styles
  // ------------------------------------------------------------------

  _css() {
    return `
      :host { display: block; }
      ha-card { padding: 16px; }
      .root { position: relative; }

      .qa { padding: 8px 12px; border-radius: 8px; margin-bottom: 12px; font-size: 14px; }
      .qa.ok { background: rgba(76, 175, 80, 0.15); color: var(--success-color, #2e7d32); }
      .qa.warn { background: rgba(255, 152, 0, 0.15); color: var(--warning-color, #e65100); }
      .qa a { cursor: pointer; text-decoration: underline; color: inherit; }

      .tabs { display: flex; gap: 4px; border-bottom: 2px solid var(--divider-color, #e0e0e0); margin-bottom: 16px; flex-wrap: wrap; }
      .tab {
        background: transparent; border: none; padding: 10px 16px; cursor: pointer;
        font-size: 14px; color: var(--primary-text-color, #333);
        border-bottom: 2px solid transparent; margin-bottom: -2px;
        display: inline-flex; align-items: center; gap: 6px;
      }
      .tab:hover { background: var(--secondary-background-color, #f5f5f5); }
      .tab.active { color: var(--primary-color, #03a9f4); border-bottom-color: var(--primary-color, #03a9f4); font-weight: 500; }
      .tab-count { background: var(--secondary-background-color, #eee); padding: 1px 8px; border-radius: 10px; font-size: 12px; min-width: 20px; text-align: center; }
      .tab.active .tab-count { background: var(--primary-color, #03a9f4); color: #fff; }

      .toolbar { margin-bottom: 12px; display: flex; justify-content: flex-end; }
      .btn-new {
        background: var(--primary-color, #03a9f4); color: #fff;
        border: none; border-radius: 6px; padding: 8px 14px; cursor: pointer; font-size: 14px;
      }
      .btn-new:hover { filter: brightness(1.1); }

      .info { font-size: 13px; color: var(--secondary-text-color, #666); margin-bottom: 10px; }

      table.list { width: 100%; border-collapse: collapse; font-size: 14px; }
      table.list th { text-align: left; padding: 8px; color: var(--secondary-text-color, #666); border-bottom: 1px solid var(--divider-color, #e0e0e0); font-weight: 500; }
      table.list td { padding: 8px; border-bottom: 1px solid var(--divider-color, #eee); vertical-align: top; }
      table.list tbody tr { cursor: pointer; transition: background 0.15s; }
      table.list tbody tr:hover { background: var(--secondary-background-color, #f5f5f5); }
      table.list tbody tr.dimmed { opacity: 0.65; }
      table.list tbody tr.dimmed:hover { opacity: 1; }
      table.list td.empty { text-align: center; color: var(--secondary-text-color, #999); padding: 24px; }
      table.list td.num { text-align: right; color: var(--secondary-text-color); }

      .mono { font-family: ui-monospace, 'SF Mono', Menlo, monospace; font-size: 13px; }
      .chip { display: inline-block; background: var(--secondary-background-color, #eee); padding: 2px 8px; border-radius: 10px; font-size: 12px; margin: 2px; }
      .chip.override { background: rgba(3, 169, 244, 0.2); color: var(--primary-color, #03a9f4); font-weight: 500; }
      .chip.default { background: rgba(76, 175, 80, 0.15); color: var(--success-color, #2e7d32); }
      .chip.warn { background: rgba(255, 152, 0, 0.2); color: var(--warning-color, #e65100); }
      .chip.unbekannt { background: rgba(244, 67, 54, 0.2); color: var(--error-color, #c62828); }
      .dim { color: var(--secondary-text-color, #999); font-size: 13px; }

      .badge { background: var(--primary-color, #03a9f4); color: #fff; font-size: 10px; padding: 1px 6px; border-radius: 4px; vertical-align: middle; margin-left: 4px; }

      .sev { padding: 2px 8px; border-radius: 4px; font-size: 12px; font-weight: 500; }
      .sev-info { background: rgba(3, 169, 244, 0.15); color: var(--primary-color, #03a9f4); }
      .sev-warnung { background: rgba(255, 152, 0, 0.2); color: var(--warning-color, #e65100); }
      .sev-kritisch { background: rgba(244, 67, 54, 0.2); color: var(--error-color, #c62828); font-weight: bold; }

      .form { display: grid; gap: 14px; max-width: 520px; }
      .form label { display: flex; flex-direction: column; gap: 4px; font-size: 13px; color: var(--secondary-text-color); }
      .form input, .form select, .form textarea {
        padding: 8px 10px; border: 1px solid var(--divider-color, #ddd); border-radius: 6px;
        background: var(--card-background-color, #fff); color: var(--primary-text-color, #333);
        font-size: 14px; outline: none; font-family: inherit;
      }
      .form input:focus, .form select:focus, .form textarea:focus { border-color: var(--primary-color, #03a9f4); }
      .form textarea { min-height: 60px; resize: vertical; }
      .form-actions { display: flex; gap: 8px; margin-top: 8px; }
      .form button {
        padding: 8px 14px; border-radius: 6px; border: none; cursor: pointer;
        background: var(--primary-color, #03a9f4); color: #fff; font-size: 14px;
      }
      .form button.secondary { background: var(--secondary-background-color, #eee); color: var(--primary-text-color); }

      /* Dialog (native <dialog> — Top-Layer ignoriert Shadow-DOM/transform-Container) */
      dialog.modal {
        border: none;
        padding: 0;
        background: transparent;
        width: min(520px, 92vw);
        max-width: 92vw;
        max-height: 90vh;
        overflow: visible;
        color: var(--primary-text-color);
      }
      dialog.modal::backdrop {
        background: rgba(0, 0, 0, 0.5);
      }
      .dialog {
        background: var(--card-background-color, #fff); border-radius: 12px;
        max-height: 90vh; overflow: auto;
        box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
        display: flex; flex-direction: column;
      }
      .dialog-head { display: flex; align-items: center; padding: 16px 20px; border-bottom: 1px solid var(--divider-color, #eee); }
      .dialog-head h3 { margin: 0; flex: 1; font-size: 16px; color: var(--primary-text-color); }
      .dialog-head .close { background: none; border: none; font-size: 20px; cursor: pointer; color: var(--secondary-text-color); padding: 4px 8px; border-radius: 6px; }
      .dialog-head .close:hover { background: var(--secondary-background-color, #f5f5f5); }
      .dialog-body { padding: 16px 20px; display: grid; gap: 14px; }
      .dialog-body label { display: flex; flex-direction: column; gap: 4px; font-size: 13px; color: var(--secondary-text-color); }
      .dialog-body label .lbl-text { font-weight: 500; color: var(--primary-text-color); font-size: 13px; }
      .dialog-body label code { background: var(--secondary-background-color, #2a2a2a); padding: 1px 5px; border-radius: 3px; font-size: 11px; }
      .dialog-body label.checkbox { flex-direction: row; align-items: center; gap: 8px; color: var(--primary-text-color); font-size: 14px; }
      .dialog-body input, .dialog-body select, .dialog-body textarea {
        padding: 8px 10px; border: 1px solid var(--divider-color, #ddd); border-radius: 6px;
        background: var(--card-background-color, #fff); color: var(--primary-text-color, #333);
        font-size: 14px; outline: none; font-family: inherit;
      }
      .dialog-body textarea { min-height: 60px; resize: vertical; }
      .dialog-body .hint { color: var(--secondary-text-color); font-weight: 400; font-size: 11px; font-style: italic; }
      .dialog-body .readonly { background: var(--secondary-background-color, #f5f5f5); padding: 8px 10px; border-radius: 6px; }
      .dialog-body .readonly .lbl { color: var(--secondary-text-color); font-size: 12px; margin-right: 6px; }
      .dialog-body .hint-link { font-size: 12px; color: var(--secondary-text-color); font-style: italic; padding-top: 4px; }
      .dialog-body .hint-link a { color: var(--primary-color, #03a9f4); cursor: pointer; text-decoration: underline; }

      .dialog-actions { display: flex; gap: 8px; padding: 12px 20px; border-top: 1px solid var(--divider-color, #eee); align-items: center; }
      .dialog-actions .grow { flex: 1; }
      .dialog-actions button { padding: 8px 14px; border-radius: 6px; border: none; cursor: pointer; font-size: 14px; }
      .dialog-actions button.primary { background: var(--primary-color, #03a9f4); color: #fff; }
      .dialog-actions button.secondary { background: var(--secondary-background-color, #eee); color: var(--primary-text-color); }
      .dialog-actions button.danger { background: var(--error-color, #c62828); color: #fff; }

      .flash { padding: 8px 14px; border-radius: 6px; margin-bottom: 12px; font-size: 14px; }
      .flash.ok { background: rgba(76, 175, 80, 0.2); color: var(--success-color, #2e7d32); }
      .flash.error { background: rgba(244, 67, 54, 0.2); color: var(--error-color, #c62828); }
    `;
  }

  getCardSize() {
    return 8;
  }

  static getConfigElement() {
    return undefined;
  }

  static getStubConfig() {
    return { type: "custom:herold-admin-card" };
  }
}

customElements.define("herold-admin-card", HeroldAdminCard);

window.customCards = window.customCards || [];
window.customCards.push({
  type: "herold-admin-card",
  name: "Herold Admin",
  description: "Verwaltung von Topics, Rollen, Empfängern und Mapping",
});
