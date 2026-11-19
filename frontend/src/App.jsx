import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "./api.js";

const EXAMPLE =
  "Bonjour, je m'appelle Sami Ben Ali, de la société Medtech Sfax. Nous voulons un CRM, " +
  "budget 25 000 DT, c'est urgent. Email : sami@medtech.tn, tél 98 123 456.";

const CATEGORY = { chaud: "Chaud", tiede: "Tiède", froid: "Froid" };
const STATUS = {
  a_rappeler_24h: "À rappeler sous 24 h",
  a_qualifier: "À qualifier",
  nurturing: "Nurturing",
};
const TIMELINE = {
  urgent: "Urgent",
  court_terme: "Court terme",
  moyen_terme: "Moyen terme",
  non_precise: "Non précisée",
};

const money = (v) => (v ? `${Math.round(v).toLocaleString("fr-FR")} TND` : null);

function Value({ children }) {
  return children ? <>{children}</> : <span className="none">Non renseigné</span>;
}

function Category({ value }) {
  return (
    <span className={`category ${value}`}>
      <span className="dot" aria-hidden="true" />
      {CATEGORY[value]}
    </span>
  );
}

function Score({ score, category }) {
  return (
    <span className="score">
      <strong>{score}</strong>
      <span className="of">/100</span>
      <span className={`bar ${category}`} aria-hidden="true">
        <span style={{ width: `${score}%` }} />
      </span>
    </span>
  );
}

function Field({ label, children }) {
  return (
    <div className="field">
      <dt>{label}</dt>
      <dd><Value>{children}</Value></dd>
    </div>
  );
}

/* ---------- File d'attente et détail ---------- */

function Queue({ rows, selectedId, onSelect }) {
  return (
    <ul className="queue" aria-label="Propositions à valider">
      {rows.map((r) => (
        <li key={r.thread_id}>
          <button
            type="button"
            className={r.thread_id === selectedId ? "queue-item selected" : "queue-item"}
            onClick={() => onSelect(r.thread_id)}
          >
            <span className="queue-top">
              <span className="queue-name">{r.info.name || r.info.email || r.info.phone}</span>
              <Score score={r.score} category={r.category} />
            </span>
            <span className="queue-sub">{r.info.company || r.info.need || "Entreprise non renseignée"}</span>
            <Category value={r.category} />
          </button>
        </li>
      ))}
    </ul>
  );
}

function Detail({ review, busy, onDecide }) {
  const [copied, setCopied] = useState(false);
  const info = review.info;
  const followUp =
    "Bonjour" + (info.name ? ` ${info.name}` : "") +
    ", merci pour votre message. Pour avancer, pouvez-vous nous préciser :\n- " +
    review.questions.join("\n- ");

  async function copy() {
    try {
      await navigator.clipboard.writeText(followUp);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      /* presse-papiers indisponible : l'utilisateur peut sélectionner le texte */
    }
  }

  return (
    <article className="detail">
      <header className="detail-head">
        <div>
          <h2>{info.name || "Contact sans nom"}</h2>
          <p className="muted">{info.company || "Entreprise non renseignée"}</p>
        </div>
        <div className="detail-score">
          <Category value={review.category} />
          <Score score={review.score} category={review.category} />
        </div>
      </header>

      <section>
        <h3>Message reçu</h3>
        <blockquote>{review.message}</blockquote>
      </section>

      <section>
        <h3>Informations extraites</h3>
        <dl className="fields">
          <Field label="Email">{info.email}</Field>
          <Field label="Téléphone">{info.phone}</Field>
          <Field label="Besoin">{info.need}</Field>
          <Field label="Budget">{money(info.budget_tnd)}</Field>
          <Field label="Échéance">{info.timeline !== "non_precise" ? TIMELINE[info.timeline] : null}</Field>
          <Field label="Effectif">{info.employees ? `${info.employees} personnes` : null}</Field>
        </dl>
      </section>

      <section>
        <h3>Détail du score</h3>
        <ul className="reasons">
{(review.reasons || []).map((reason) => <li key={reason}>{reason}</li>)}        </ul>
        <p className="muted">{review.summary}</p>
      </section>

      <section>
        <h3>Questions de relance</h3>
        {review.questions.length ? (
          <>
            <ul className="plain">{review.questions.map((q) => <li key={q}>{q}</li>)}</ul>
            <button type="button" className="secondary" onClick={copy}>
              {copied ? "Message copié" : "Copier le message de relance"}
            </button>
          </>
        ) : (
          <p className="muted">Toutes les informations utiles sont présentes.</p>
        )}
      </section>

      <footer className="decision">
        <button type="button" className="secondary" disabled={busy} onClick={() => onDecide(review.thread_id, "reject")}>
          Rejeter
        </button>
        <button type="button" className="primary" disabled={busy} onClick={() => onDecide(review.thread_id, "approve")}>
          Valider et ajouter au CRM
        </button>
      </footer>
    </article>
  );
}

/* ---------- Tableaux ---------- */

function Crm({ rows }) {
  if (!rows.length) {
    return <p className="empty">Le CRM est vide. Les fiches apparaissent ici après validation d'une proposition.</p>;
  }
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Score</th><th>Contact</th><th>Entreprise</th><th>Besoin</th><th>Budget</th><th>Statut</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((l) => (
            <tr key={l.id}>
              <td><Score score={l.score} category={l.category} /></td>
              <td>
                <div>{l.name || <span className="none">Sans nom</span>}</div>
                <div className="muted">{l.email || l.phone}</div>
              </td>
              <td><Value>{l.company}</Value></td>
              <td><Value>{l.need}</Value></td>
              <td className="num"><Value>{money(l.budget_tnd)}</Value></td>
              <td>{STATUS[l.status] || l.status}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Rejected({ rows }) {
  if (!rows.length) return <p className="empty">Aucune proposition rejetée.</p>;
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr><th>Score</th><th>Contact</th><th>Résumé</th></tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.thread_id}>
              <td><Score score={r.score} category={r.category} /></td>
              <td>{r.info.name || r.info.email || r.info.phone}</td>
              <td className="wide">{r.summary}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/* ---------- Application ---------- */

export default function App() {
  const [message, setMessage] = useState("");
  const [tab, setTab] = useState("pending");
  const [pending, setPending] = useState([]);
  const [rejected, setRejected] = useState([]);
  const [leads, setLeads] = useState([]);
  const [health, setHealth] = useState(null);
  const [notice, setNotice] = useState(null);
  const [selectedId, setSelectedId] = useState(null);
  const [busy, setBusy] = useState(false);
  const [sending, setSending] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const [p, r, l] = await Promise.all([api.reviews("en_attente"), api.reviews("rejete"), api.leads()]);
      setPending(p);
      setRejected(r);
      setLeads(l);
    } catch (e) {
      setNotice({ type: "error", text: `Le serveur ne répond pas (${e.message}). Vérifie que l'API est démarrée.` });
    }
  }, []);

  useEffect(() => {
    refresh();
    api.health().then(setHealth).catch(() => {});
  }, [refresh]);

  const selected = useMemo(
    () => pending.find((r) => r.thread_id === selectedId) || pending[0] || null,
    [pending, selectedId]
  );

  async function submit(e) {
    e.preventDefault();
    if (!message.trim()) return;
    setSending(true);
    try {
      const res = await api.submitMessage(message);
      if (res.status === "contact_requis") {
        setNotice({
          type: "warning",
          text: "Ce message ne contient ni email ni téléphone, aucune proposition n'a été créée. Demander au client : " +
            res.questions[0],
        });
      } else {
        setNotice({ type: "success", text: "Proposition ajoutée à la file de validation." });
        setMessage("");
        setTab("pending");
        setSelectedId(res.thread_id);
      }
      await refresh();
    } catch (err) {
      setNotice({ type: "error", text: err.message });
    } finally {
      setSending(false);
    }
  }

  async function decide(id, decision) {
    setBusy(true);
    try {
      await (decision === "approve" ? api.approve(id) : api.reject(id));
      setNotice({
        type: "success",
        text: decision === "approve" ? "Fiche ajoutée au CRM." : "Proposition rejetée, rien n'a été écrit dans le CRM.",
      });
      setSelectedId(null);
      await refresh();
    } catch (err) {
      setNotice({ type: "error", text: err.message });
    } finally {
      setBusy(false);
    }
  }

  const tabs = [
    { id: "pending", label: "À valider", count: pending.length },
    { id: "crm", label: "CRM", count: leads.length },
    { id: "rejected", label: "Rejetés", count: rejected.length },
  ];

  return (
    <>
      <header className="topbar">
        <div className="topbar-inner">
          <h1>Qualification des leads</h1>
          {health && (
            <span className="engine">
              Extraction : {health.llm === "groq" ? "Groq, Llama 3.3 70B" : "règles locales"}
            </span>
          )}
        </div>
      </header>

      <main>
        <form onSubmit={submit} className="compose">
          <label htmlFor="msg">Nouveau message client</label>
          <textarea
            id="msg"
            rows={3}
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            placeholder="Collez un email ou un message reçu d'un prospect."
          />
          <div className="compose-actions">
            <button type="submit" className="primary" disabled={sending || !message.trim()}>
              {sending ? "Analyse en cours" : "Analyser le message"}
            </button>
            <button type="button" className="text-button" onClick={() => setMessage(EXAMPLE)}>
              Utiliser un message d'exemple
            </button>
          </div>
        </form>

        {notice && (
          <div className={`notice ${notice.type}`} role="status">
            <span>{notice.text}</span>
            <button type="button" className="text-button" onClick={() => setNotice(null)}>Fermer</button>
          </div>
        )}

        <div className="tabs" role="tablist">
          {tabs.map((t) => (
            <button
              key={t.id}
              type="button"
              role="tab"
              aria-selected={tab === t.id}
              className={tab === t.id ? "tab active" : "tab"}
              onClick={() => setTab(t.id)}
            >
              {t.label}
              <span className="count">{t.count}</span>
            </button>
          ))}
        </div>

        {tab === "pending" &&
          (selected ? (
            <div className="workspace">
              <Queue rows={pending} selectedId={selected.thread_id} onSelect={setSelectedId} />
              <Detail key={selected.thread_id} review={selected} busy={busy} onDecide={decide} />
            </div>
          ) : (
            <p className="empty">Aucune proposition en attente. Analysez un message pour en créer une.</p>
          ))}
        {tab === "crm" && <Crm rows={leads} />}
        {tab === "rejected" && <Rejected rows={rejected} />}
      </main>
    </>
  );
}