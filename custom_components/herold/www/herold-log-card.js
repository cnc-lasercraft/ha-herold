class HeroldLogCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._entries = [];
    this._topicFilter = "";
    this._severityFilter = "";
    this._textSearch = "";
    this._unsubscribe = null;
    this._initialized = false;
  }

  setConfig(config) {
    this.config = config || {};
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._initialized) {
      this._initialized = true;
      this._render();
      this._loadHistory();
      this._subscribeEvents();
    }
    this._updateTopicList();
  }

  _updateTopicList() {
    const dl = this.shadowRoot?.getElementById("topic-list");
    if (!dl) return;
    const sensor = this._hass.states["sensor.herold_aktive_topics"];
    const topics = sensor?.attributes?.topics || [];

    // Prefixe aus der Slash-Hierarchie ableiten (z.B. zeekr/*)
    const prefixes = new Set();
    for (const t of topics) {
      const parts = t.id.split("/");
      if (parts.length > 1) {
        let p = "";
        for (let i = 0; i < parts.length - 1; i++) {
          p += (i > 0 ? "/" : "") + parts[i];
          prefixes.add(p + "/*");
        }
      }
    }

    const options = [
      ...Array.from(prefixes).sort(),
      ...topics.map((t) => t.id).sort(),
    ];

    dl.innerHTML = options
      .map((v) => `<option value="${v}"></option>`)
      .join("");
  }

  async _subscribeEvents() {
    try {
      this._unsubscribe = await this._hass.connection.subscribeEvents(
        () => this._loadHistory(),
        "herold_sent"
      );
      this._unsubTopics = await this._hass.connection.subscribeEvents(
        () => this._updateTopicList(),
        "herold_topic_registered"
      );
    } catch (e) {
      console.warn("Herold Log Card: Event-Abo fehlgeschlagen", e);
    }
  }

  async _loadHistory() {
    try {
      const data = { limit: this.config.limit || 200 };
      if (this._topicFilter) data.topic = this._topicFilter;
      if (this._severityFilter) data.severity = this._severityFilter;

      const result = await this._hass.connection.sendMessagePromise({
        type: "call_service",
        domain: "herold",
        service: "history_abfragen",
        service_data: data,
        return_response: true,
      });

      let entries = result.response?.eintraege || [];

      // Client-seitige Textsuche (Titel + Message)
      if (this._textSearch) {
        const q = this._textSearch.toLowerCase();
        entries = entries.filter(
          (e) =>
            e.titel.toLowerCase().includes(q) ||
            e.message.toLowerCase().includes(q) ||
            e.topic.toLowerCase().includes(q)
        );
      }

      this._entries = entries;
      this._renderTable();
    } catch (e) {
      console.error("Herold History laden fehlgeschlagen:", e);
      this._entries = [];
      this._renderTable();
    }
  }

  _render() {
    this.shadowRoot.innerHTML = `
      <style>
        :host { display: block; }
        ha-card { padding: 16px; }
        .header { font-size: 18px; font-weight: 500; margin-bottom: 16px; color: var(--primary-text-color); }

        .filters {
          display: flex; gap: 8px; margin-bottom: 12px;
          align-items: center; flex-wrap: wrap;
        }
        .filters input, .filters select {
          padding: 8px 12px;
          border: 1px solid var(--divider-color, #e0e0e0);
          border-radius: 8px;
          background: var(--card-background-color, #fff);
          color: var(--primary-text-color, #333);
          font-size: 14px;
          outline: none;
        }
        .filters input:focus, .filters select:focus {
          border-color: var(--primary-color, #03a9f4);
        }
        .filter-topic { flex: 1; min-width: 140px; }
        .filter-text { flex: 2; min-width: 180px; }
        .filters select { min-width: 110px; }
        .filters button {
          padding: 8px 16px; border: none; border-radius: 8px;
          background: var(--primary-color, #03a9f4);
          color: white; cursor: pointer; font-size: 14px;
          white-space: nowrap;
        }
        .filters button:hover { opacity: 0.85; }

        .count {
          font-size: 13px; color: var(--secondary-text-color, #666);
          margin-bottom: 8px;
        }

        table { width: 100%; border-collapse: collapse; font-size: 13px; }
        th {
          text-align: left; padding: 8px 8px 8px 0;
          border-bottom: 2px solid var(--divider-color, #e0e0e0);
          color: var(--secondary-text-color, #666);
          font-weight: 500; white-space: nowrap;
        }
        td {
          padding: 8px 8px 8px 0;
          border-bottom: 1px solid var(--divider-color, #e0e0e0);
          vertical-align: top;
        }
        tr.row:hover { background: var(--secondary-background-color, #f5f5f5); cursor: pointer; }

        .sev {
          display: inline-block; padding: 2px 8px; border-radius: 4px;
          font-size: 12px; font-weight: 500; white-space: nowrap;
        }
        .sev-info     { background: #e3f2fd; color: #1565c0; }
        .sev-warnung  { background: #fff3e0; color: #e65100; }
        .sev-kritisch { background: #ffebee; color: #c62828; }

        .status-ok      { color: #2e7d32; }
        .status-fehler  { color: #c62828; }
        .status-skipped { color: #9e9e9e; }

        .fallback { font-size: 11px; color: #e65100; margin-top: 2px; }
        .msg { font-size: 12px; color: var(--secondary-text-color, #666); margin-top: 4px; }
        .detail-row td { padding: 4px 8px 12px 0; }
        .detail-box {
          background: var(--secondary-background-color, #f5f5f5);
          border-radius: 8px; padding: 12px; font-size: 12px;
          color: var(--primary-text-color);
        }
        .detail-box dt { font-weight: 500; margin-top: 6px; }
        .detail-box dt:first-child { margin-top: 0; }
        .detail-box dd { margin: 2px 0 0 0; }
        .empty {
          text-align: center; padding: 32px;
          color: var(--secondary-text-color, #666);
        }
        .topic-path { font-family: monospace; font-size: 12px; }
        .zeit { white-space: nowrap; font-size: 12px; color: var(--secondary-text-color); }
      </style>
      <ha-card>
        <div class="header">Herold Log</div>
        <div class="filters">
          <input class="filter-topic" type="text" id="topic" list="topic-list" placeholder="Topic (z.B. zeekr/*)" />
          <datalist id="topic-list"></datalist>
          <input class="filter-text" type="text" id="text" placeholder="Suche in Titel / Nachricht" />
          <select id="severity">
            <option value="">Alle</option>
            <option value="info">Info</option>
            <option value="warnung">Warnung</option>
            <option value="kritisch">Kritisch</option>
          </select>
          <button id="search">Suchen</button>
        </div>
        <div class="count" id="count"></div>
        <div id="table"></div>
      </ha-card>
    `;

    const doSearch = () => {
      this._topicFilter = this.shadowRoot.getElementById("topic").value.trim();
      this._textSearch = this.shadowRoot.getElementById("text").value.trim();
      this._severityFilter = this.shadowRoot.getElementById("severity").value;
      this._loadHistory();
    };

    this.shadowRoot.getElementById("search").addEventListener("click", doSearch);
    for (const id of ["topic", "text"]) {
      this.shadowRoot.getElementById(id).addEventListener("keydown", (e) => {
        if (e.key === "Enter") doSearch();
      });
    }
    this.shadowRoot.getElementById("severity").addEventListener("change", doSearch);
  }

  _renderTable() {
    const container = this.shadowRoot.getElementById("table");
    const countEl = this.shadowRoot.getElementById("count");

    if (!this._entries.length) {
      container.innerHTML = '<div class="empty">Keine Einträge gefunden</div>';
      countEl.textContent = "";
      return;
    }

    countEl.textContent = this._entries.length + " Einträge";

    const rows = this._entries
      .map((e, i) => {
        const d = new Date(e.zeitstempel);
        const zeit = d.toLocaleString("de-CH", {
          day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit",
        });

        const statusParts = Object.entries(e.ausliefer_status || {})
          .map(([empf, s]) => {
            const cls = s === "ok" ? "status-ok" : s.startsWith("fehler") ? "status-fehler" : "status-skipped";
            return `<span class="${cls}">${empf}</span>`;
          })
          .join(", ");

        const fb = e.fallback_verwendet ? ' <span class="fallback">⚠ Fallback</span>' : "";
        const msg = e.message ? `<div class="msg">${this._esc(e.message).substring(0, 120)}</div>` : "";

        return `<tr class="row" data-idx="${i}">
          <td class="zeit">${zeit}</td>
          <td class="topic-path">${this._esc(e.topic)}</td>
          <td><span class="sev sev-${e.severity}">${e.severity}</span></td>
          <td>${this._esc(e.titel)}${msg}${fb}</td>
          <td>${statusParts || "—"}</td>
        </tr>`;
      })
      .join("");

    container.innerHTML = `
      <table>
        <thead><tr>
          <th>Zeit</th><th>Topic</th><th>Sev.</th><th>Titel</th><th>Status</th>
        </tr></thead>
        <tbody>${rows}</tbody>
      </table>
    `;

    // Klick auf Zeile → Detail-Toggle
    container.querySelectorAll("tr.row").forEach((tr) => {
      tr.addEventListener("click", () => {
        const idx = parseInt(tr.dataset.idx);
        const existing = tr.nextElementSibling;
        if (existing && existing.classList.contains("detail-row")) {
          existing.remove();
          return;
        }
        const e = this._entries[idx];
        if (!e) return;

        const statusDetail = Object.entries(e.ausliefer_status || {})
          .map(([empf, s]) => `${empf}: ${s}`)
          .join("\n");

        const detail = document.createElement("tr");
        detail.classList.add("detail-row");
        detail.innerHTML = `<td colspan="5"><div class="detail-box"><dl>
          <dt>Nachricht</dt><dd>${this._esc(e.message || "—")}</dd>
          <dt>Rollen</dt><dd>${(e.aufgeloste_rollen || []).join(", ") || "—"}</dd>
          <dt>Empfänger</dt><dd>${(e.aufgeloste_empfaenger || []).join(", ") || "—"}</dd>
          <dt>Zustellstatus</dt><dd><pre style="margin:0">${this._esc(statusDetail || "—")}</pre></dd>
          <dt>Zeitstempel</dt><dd>${e.zeitstempel}</dd>
          <dt>Eintrag-ID</dt><dd style="font-family:monospace">${e.id}</dd>
        </dl></div></td>`;
        tr.after(detail);
      });
    });
  }

  _esc(str) {
    const el = document.createElement("span");
    el.textContent = str;
    return el.innerHTML;
  }

  getCardSize() {
    return Math.max(4, Math.min(12, 2 + this._entries.length));
  }

  disconnectedCallback() {
    if (this._unsubscribe) {
      this._unsubscribe();
      this._unsubscribe = null;
    }
    if (this._unsubTopics) {
      this._unsubTopics();
      this._unsubTopics = null;
    }
  }
}

customElements.define("herold-log-card", HeroldLogCard);
window.customCards = window.customCards || [];
window.customCards.push({
  type: "herold-log-card",
  name: "Herold Log",
  description: "Zentrales Herold-Log mit Filter- und Suchmöglichkeiten",
});
