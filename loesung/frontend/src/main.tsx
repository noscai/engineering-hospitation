import React, { ChangeEvent, useMemo, useState } from 'react';
import { createRoot } from 'react-dom/client';
import './styles.css';

type Reference = {
  untergrenze: string | null;
  obergrenze: string | null;
  text: string[];
  flag: string | null;
};

type LabValue = {
  analyt: string | null;
  wert: string | null;
  einheit: string | null;
  quelle: 'LDT' | 'PDF';
  seite: number | null;
  confidence: number | null;
  begruendung: string | null;
  referenzen: Reference[];
};

type ApiResult = {
  document_id: string;
  dateiname: string;
  dateityp: 'LDT' | 'PDF';
  pdf_url: string | null;
  laborwerte: LabValue[];
  normalisierte_laborwerte: Array<Record<string, string | null>>;
  plausibilitaet: { meldungen: Array<Record<string, string | Record<string, string>>>; review_erforderlich: boolean };
  validierung: { meldungen: Array<Record<string, string>> } | null;
  review_erforderlich: boolean;
};

type RowState = {
  status: 'open' | 'confirmed' | 'corrected';
  corrected: LabValue;
};

const API = import.meta.env.VITE_API_BASE_URL ?? '';

function cloneValue(value: LabValue): LabValue {
  return JSON.parse(JSON.stringify(value));
}

function App() {
  const [file, setFile] = useState<File | null>(null);
  const [useLlm, setUseLlm] = useState(false);
  const [result, setResult] = useState<ApiResult | null>(null);
  const [rows, setRows] = useState<RowState[]>([]);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');

  const issueByAnalyt = useMemo(() => {
    const map = new Map<string, string[]>();
    result?.plausibilitaet.meldungen.forEach((msg) => {
      const key = String(msg.analyt ?? '');
      map.set(key, [...(map.get(key) ?? []), String(msg.regel)]);
    });
    result?.validierung?.meldungen.forEach((msg) => {
      const key = String(msg.feldkennung ?? 'LDT');
      map.set(key, [...(map.get(key) ?? []), String(msg.regel)]);
    });
    return map;
  }, [result]);

  async function upload() {
    if (!file) return;
    setBusy(true);
    setMessage('');
    const form = new FormData();
    form.append('file', file);
    const response = await fetch(`${API}/befunde/extrahieren?use_llm=${useLlm}&prompt=kurz`, {
      method: 'POST',
      body: form
    });
    if (!response.ok) {
      setBusy(false);
      setMessage(`Upload fehlgeschlagen: ${response.status}`);
      return;
    }
    const data: ApiResult = await response.json();
    setResult(data);
    setRows(data.laborwerte.map((value) => ({ status: 'open', corrected: cloneValue(value) })));
    setBusy(false);
  }

  function updateValue(index: number, field: keyof LabValue, value: string) {
    setRows((current) => current.map((row, i) => {
      if (i !== index) return row;
      return { status: 'corrected', corrected: { ...row.corrected, [field]: value || null } };
    }));
  }

  function mark(index: number, status: RowState['status']) {
    setRows((current) => current.map((row, i) => i === index ? { ...row, status } : row));
  }

  async function saveCorrections() {
    if (!result) return;
    const payload = {
      dateiname: result.dateiname,
      dateityp: result.dateityp,
      laborwerte: rows.map((row) => row.corrected),
      corrections: rows
        .map((row, index) => ({ index, original: result.laborwerte[index], corrected: row.corrected, status: row.status }))
        .filter((row) => row.status !== 'open')
    };
    const response = await fetch(`${API}/review/faelle`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    const data = await response.json();
    setMessage(response.ok ? `Review-Fall gespeichert: ${data.case_id}` : `Speichern fehlgeschlagen: ${response.status}`);
  }

  const flaggedCount = rows.filter((row) => {
    const issues = issueByAnalyt.get(row.corrected.analyt ?? '') ?? [];
    return issues.length > 0 || (row.corrected.confidence !== null && row.corrected.confidence < 0.85);
  }).length;
  const confirmedCount = rows.filter((row) => row.status === 'confirmed').length;
  const correctedCount = rows.filter((row) => row.status === 'corrected').length;
  const messageTone = message.includes('fehlgeschlagen') ? 'error' : 'success';

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <span className="brand-mark"><IconFlask /></span>
          <div>
            <h1>Laborbefund Review</h1>
            <p>Extraktion · Prüfung · Korrektur</p>
          </div>
        </div>
      </header>

      <main className="content">
        <section className="upload-bar">
          <label className={`dropzone ${file ? 'has-file' : ''}`}>
            <input type="file" accept=".ldt,.ldtx,.pdf,application/pdf" onChange={(event: ChangeEvent<HTMLInputElement>) => setFile(event.target.files?.[0] ?? null)} />
            <span className="dropzone-icon"><IconUpload /></span>
            <span className="dropzone-text">
              <strong>{file ? file.name : 'Befund auswählen'}</strong>
              <span>{file ? 'Klicken, um eine andere Datei zu wählen' : 'LDT, LDTX oder PDF'}</span>
            </span>
          </label>
          <div className="upload-actions">
            <label className="switch">
              <input type="checkbox" role="switch" checked={useLlm} onChange={(event) => setUseLlm(event.target.checked)} />
              <span className="switch-track" aria-hidden="true" />
              <span className="switch-label">PDF per LLM</span>
            </label>
            <button className="btn btn-primary" onClick={upload} disabled={!file || busy}>
              {busy ? <><span className="spinner" aria-hidden="true" />Lade…</> : 'Extrahieren'}
            </button>
          </div>
        </section>

        {message && (
          <div className={`message message-${messageTone}`} role="status">
            {messageTone === 'error' ? <IconAlert /> : <IconCheck />}
            <span>{message}</span>
          </div>
        )}

        {!result && (
          <section className="placeholder">
            <span className="placeholder-icon"><IconDocument /></span>
            <h2>Noch kein Befund geladen</h2>
            <p>Lade eine LDT- oder PDF-Datei hoch, um die Werte zu prüfen.</p>
            <ol className="steps">
              <li><span>1</span>Datei hochladen</li>
              <li><span>2</span>Werte prüfen und korrigieren</li>
              <li><span>3</span>Als Eval-Fall speichern</li>
            </ol>
          </section>
        )}

        {result && (
          <div className="workspace">
            <section className="panel document">
              <div className="panel-header">
                <div className="doc-title">
                  <span className="doc-icon"><IconDocument /></span>
                  <h2 title={result.dateiname}>{result.dateiname}</h2>
                </div>
                <div className="badges">
                  <span className="badge">{result.dateityp}</span>
                  <span className={`badge ${result.review_erforderlich ? 'badge-warn' : 'badge-ok'}`}>
                    <span className="dot" />
                    {result.review_erforderlich ? 'Review nötig' : 'Keine Review-Meldung'}
                  </span>
                </div>
              </div>
              <div className="panel-body">
                {result.pdf_url ? <iframe title="Befund PDF" src={`${API}${result.pdf_url}`} /> : <div className="empty"><IconDocument />Kein eingebettetes PDF vorhanden.</div>}
              </div>
            </section>

            <section className="panel values">
              <div className="panel-header">
                <h2>Extrahierte Werte</h2>
                <button className="btn btn-primary" onClick={saveCorrections}><IconSave />Korrekturen speichern</button>
              </div>

              <div className="stats">
                <div className="stat"><span className="stat-value">{rows.length}</span><span className="stat-label">Werte</span></div>
                <div className="stat stat-warn"><span className="stat-value">{flaggedCount}</span><span className="stat-label">Auffällig</span></div>
                <div className="stat stat-ok"><span className="stat-value">{confirmedCount}</span><span className="stat-label">Bestätigt</span></div>
                <div className="stat stat-info"><span className="stat-value">{correctedCount}</span><span className="stat-label">Korrigiert</span></div>
              </div>

              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Quelle</th>
                      <th>Analyt</th>
                      <th>Wert</th>
                      <th>Einheit</th>
                      <th>Referenz / Flag</th>
                      <th>Confidence</th>
                      <th>Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((row, index) => {
                      const value = row.corrected;
                      const issues = issueByAnalyt.get(value.analyt ?? '') ?? [];
                      const lowConfidence = value.confidence !== null && value.confidence < 0.85;
                      const flagged = issues.length > 0 || lowConfidence;
                      const ref = value.referenzen[0];
                      return (
                        <tr key={`${value.analyt}-${index}`} className={flagged ? 'flagged' : row.status}>
                          <td><span className="source-pill">{result.dateityp === 'PDF' ? (useLlm ? 'LLM' : 'PDF') : value.quelle}</span></td>
                          <td><input aria-label="Analyt" value={value.analyt ?? ''} onChange={(event) => updateValue(index, 'analyt', event.target.value)} /></td>
                          <td><input aria-label="Wert" className="num strong" value={value.wert ?? ''} onChange={(event) => updateValue(index, 'wert', event.target.value)} /></td>
                          <td><input aria-label="Einheit" value={value.einheit ?? ''} onChange={(event) => updateValue(index, 'einheit', event.target.value)} /></td>
                          <td>
                            {ref ? (
                              <span className="ref">
                                <span className="num">{`${ref.untergrenze ?? ref.text.join(', ')}-${ref.obergrenze ?? ''}`}</span>
                                {ref.flag && <span className="flag">{ref.flag}</span>}
                              </span>
                            ) : <span className="muted">—</span>}
                          </td>
                          <td>
                            {value.confidence !== null ? (
                              <span className={`confidence ${lowConfidence ? 'low' : ''}`}>
                                <span className="meter"><span style={{ width: `${Math.min(Math.max(value.confidence, 0), 1) * 100}%` }} /></span>
                                <span className="num">{value.confidence}</span>
                              </span>
                            ) : <span className="det">det.</span>}
                          </td>
                          <td>
                            <div className="segmented">
                              <button className={row.status === 'confirmed' ? 'active ok' : ''} onClick={() => mark(index, 'confirmed')}>Bestätigen</button>
                              <button className={row.status === 'corrected' ? 'active info' : ''} onClick={() => mark(index, 'corrected')}>Korrigiert</button>
                            </div>
                            {issues.length > 0 && (
                              <div className="issues">
                                {issues.map((issue, i) => <span key={`${issue}-${i}`} className="issue">{issue}</span>)}
                              </div>
                            )}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </section>
          </div>
        )}
      </main>
    </div>
  );
}

type IconProps = { size?: number };

function Svg({ size = 18, children }: IconProps & { children: React.ReactNode }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      {children}
    </svg>
  );
}

function IconFlask() {
  return <Svg><path d="M9 3h6M10 3v6L4.5 18.5A1.7 1.7 0 0 0 6 21h12a1.7 1.7 0 0 0 1.5-2.5L14 9V3" /><path d="M7 15h10" /></Svg>;
}

function IconUpload() {
  return <Svg size={20}><path d="M12 16V4M7 9l5-5 5 5" /><path d="M4 16v3a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-3" /></Svg>;
}

function IconDocument() {
  return <Svg><path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z" /><path d="M14 3v5h5M9 13h6M9 17h4" /></Svg>;
}

function IconSave() {
  return <Svg size={16}><path d="M5 3h11l3 3v13a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2z" /><path d="M8 3v5h7V3M8 21v-7h8v7" /></Svg>;
}

function IconCheck() {
  return <Svg size={16}><circle cx="12" cy="12" r="9" /><path d="m8 12 3 3 5-6" /></Svg>;
}

function IconAlert() {
  return <Svg size={16}><circle cx="12" cy="12" r="9" /><path d="M12 8v5M12 16h.01" /></Svg>;
}

createRoot(document.getElementById('root')!).render(<App />);
