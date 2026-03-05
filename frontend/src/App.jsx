import { useState, useRef, useEffect, useCallback } from 'react';
import ReactMarkdown from 'react-markdown';
import {
  Dna, Search, Send, User, Bot, Loader2,
  AlertTriangle, CheckCircle, Info, Beaker,
  ExternalLink, Sun, Moon, BookOpen, MessageSquare,
  FlaskConical, ShieldCheck, FileText, Lightbulb, ArrowRight
} from 'lucide-react';
/* ─────────────────── Variant Reports View ─────────────────── */
function VariantReports() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    fetch('/api/variants')
      .then(r => { if (!r.ok) throw new Error(r.status); return r.json(); })
      .then(setData)
      .catch(e => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <div className="page-loader"><Loader2 className="animate-spin" size={32} /><span>Scanning indexed literature for variants…</span></div>;
  if (error) return <div className="page-error">Failed to load variants: {error}</div>;

  return (
    <div className="page-content">
      <div className="page-header">
        <h2>Variant Reports</h2>
        <span className="badge success">{data.total} variant{data.total !== 1 ? 's' : ''} found</span>
      </div>
      <p className="page-subtitle">HGVS variants extracted from {data.total > 0 ? 'the indexed PubMed and preprint corpus' : 'no sources'}.</p>

      {data.total === 0 ? (
        <div className="empty-state">
          <Dna size={48} />
          <p>No genomic entities were found in the current corpus. Try ingesting more literature.</p>
        </div>
      ) : (
        <div className="table-wrapper">
          <table className="data-table">
            <thead>
              <tr>
                <th>Entity</th>
                <th>Type</th>
                <th>Co-occurring Phenotypes</th>
                <th>Sources</th>
              </tr>
            </thead>
            <tbody>
              {data.variants.map((v, i) => (
                <tr key={i}>
                  <td><code className="variant-code">{v.variant}</code></td>
                  <td>
                    <span className={`badge ${v.type === 'gene' ? 'success' : v.type === 'hgvs' ? 'error' : 'warning'}`}>
                      {v.type === 'gene' ? 'Gene' : v.type === 'hgvs' ? 'HGVS Variant' : 'Mutation Term'}
                    </span>
                  </td>
                  <td>
                    <div className="phenotype-tags">
                      {v.phenotypes.length > 0 ? v.phenotypes.map((p, j) => (
                        <span key={j} className="badge warning">{p}</span>
                      )) : <span style={{ color: 'var(--text-muted)' }}>—</span>}
                    </div>
                  </td>
                  <td>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
                      {v.sources.map((src, k) => {
                        const url = src.startsWith('10.') ? `https://doi.org/${src}` : `https://pubmed.ncbi.nlm.nih.gov/${src}/`;
                        const label = src.startsWith('10.') ? `DOI: ${src}` : `PMID: ${src}`;
                        return (
                          <a key={k} href={url} target="_blank" rel="noreferrer" className="citation-id" style={{ fontSize: '0.8rem' }}>
                            {label}
                          </a>
                        );
                      })}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

/* ─────────────────── Gene Information View ─────────────────── */
function GeneInformation() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch('/api/gene-info')
      .then(r => r.json())
      .then(setData)
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <div className="page-loader"><Loader2 className="animate-spin" size={32} /><span>Loading gene data…</span></div>;
  if (!data) return null;

  const { gene, disease, corpus } = data;

  return (
    <div className="page-content">
      <div className="page-header">
        <h2>{gene.symbol}</h2>
        <span className="badge success">Gene Overview</span>
      </div>
      <p className="page-subtitle">{gene.name}</p>

      <div className="info-grid">
        {/* Gene Card */}
        <div className="dashboard-card">
          <div className="card-header"><Dna size={14} /> Gene Details</div>
          <div className="card-body">
            <div className="info-rows">
              <div className="info-row"><span className="info-label">Symbol</span><span>{gene.symbol}</span></div>
              <div className="info-row"><span className="info-label">Full Name</span><span>{gene.name}</span></div>
              <div className="info-row"><span className="info-label">Aliases</span><span>{gene.aliases.join(', ')}</span></div>
              <div className="info-row"><span className="info-label">Chromosome</span><span>{gene.chromosome}</span></div>
              <div className="info-row"><span className="info-label">NCBI Gene ID</span><span>{gene.gene_id}</span></div>
              <div className="info-row"><span className="info-label">UniProt</span><span>{gene.uniprot}</span></div>
            </div>
            <p style={{ marginTop: '1rem', fontSize: '0.9rem', color: 'var(--text-muted)' }}>{gene.function}</p>
          </div>
        </div>

        {/* Disease Card */}
        <div className="dashboard-card">
          <div className="card-header"><AlertTriangle size={14} /> Associated Disease</div>
          <div className="card-body">
            <div className="info-rows">
              <div className="info-row"><span className="info-label">Disease</span><span>{disease.name}</span></div>
              <div className="info-row"><span className="info-label">OMIM</span><span>{disease.omim}</span></div>
              <div className="info-row"><span className="info-label">Inheritance</span><span>{disease.inheritance}</span></div>
              <div className="info-row"><span className="info-label">Onset</span><span>{disease.onset}</span></div>
              <div className="info-row"><span className="info-label">Prevalence</span><span>{disease.prevalence}</span></div>
            </div>
            <div style={{ marginTop: '1rem' }}>
              <span className="info-label" style={{ display: 'block', marginBottom: '0.5rem' }}>Key Phenotypes</span>
              <div className="phenotype-tags">
                {disease.key_phenotypes.map((p, i) => <span key={i} className="badge warning">{p}</span>)}
              </div>
            </div>
          </div>
        </div>

        {/* Corpus Card */}
        <div className="dashboard-card">
          <div className="card-header"><Search size={14} /> Corpus Statistics</div>
          <div className="card-body">
            <div className="info-rows">
              <div className="info-row"><span className="info-label">Indexed Chunks</span><span>{corpus.indexed_chunks}</span></div>
              <div className="info-row"><span className="info-label">Embedding Model</span><span style={{ fontSize: '0.8rem' }}>{corpus.embedding_model}</span></div>
              <div className="info-row"><span className="info-label">Sources</span><span>{corpus.sources}</span></div>
            </div>
          </div>
        </div>

        {/* Links Card */}
        <div className="dashboard-card">
          <div className="card-header"><ExternalLink size={14} /> External Resources</div>
          <div className="card-body">
            <div className="link-list">
              {Object.entries(gene.links).map(([name, url]) => (
                <a key={name} href={url} target="_blank" rel="noreferrer" className="external-link">
                  <ExternalLink size={14} />
                  <span>{name.charAt(0).toUpperCase() + name.slice(1)}</span>
                </a>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

/* ─────────────────── How To Use Guide ─────────────────── */
function Guide() {
  const sampleQueries = [
    'What HGVS variants in RARS1 are associated with hypomyelinating leukodystrophy?',
    'What are the key clinical phenotypes reported in HLD9 patients?',
    'Are there any compound heterozygous mutations described in RARS1?',
    'What is the role of RARS1 in myelination and white matter development?',
    'Which RARS1 variants have been reported with nystagmus or spasticity?',
  ];

  const steps = [
    {
      icon: <MessageSquare size={22} />,
      title: 'Literature Search',
      color: 'var(--primary)',
      description:
        'Use the chat interface to ask natural-language questions about RARS1 variants, clinical phenotypes, and disease associations. The system retrieves relevant PubMed abstracts and uses an LLM to synthesise a cited answer.',
    },
    {
      icon: <FlaskConical size={22} />,
      title: 'Variant Reports',
      color: 'var(--danger)',
      description:
        'Browse automatically extracted HGVS variants, gene mentions, and co-occurring phenotypes from the indexed corpus. Each entity links back to its source PMID or DOI.',
    },
    {
      icon: <Dna size={22} />,
      title: 'Gene Information',
      color: 'var(--success)',
      description:
        'View structured reference data for RARS1 — chromosome location, UniProt entry, OMIM disease link, inheritance pattern, and direct links to NCBI, ClinVar, and Orphanet.',
    },
    {
      icon: <ShieldCheck size={22} />,
      title: 'Hallucination Guardrail',
      color: 'var(--warning)',
      description:
        'Every AI answer is cross-checked against the retrieved source chunks. If a claim cannot be grounded in the indexed literature, a yellow guardrail alert is shown below the response.',
    },
  ];

  return (
    <div className="page-content">
      <div className="page-header">
        <h2>How to Use</h2>
        <span className="badge success">Quick Guide</span>
      </div>
      <p className="page-subtitle">
        A reference-grade genomic RAG system for RARS1 / Hypomyelinating Leukodystrophy 9 (HLD9).
      </p>

      {/* What is this? */}
      <div className="dashboard-card" style={{ marginBottom: '1.5rem' }}>
        <div className="card-header"><Info size={14} /> What is ILYOME Genomic Intelligence?</div>
        <div className="card-body">
          <p style={{ fontSize: '0.9rem', lineHeight: '1.7', color: 'var(--body-color)' }}>
            This platform indexes PubMed abstracts and preprints related to <strong>RARS1</strong> (Arginyl-tRNA
            Synthetase 1) and its associated rare disease <strong>HLD9</strong>. It combines dense
            vector retrieval (PubMedBERT embeddings stored in ChromaDB) with a locally-running
            Llama language model to answer questions strictly grounded in the indexed literature.
          </p>
        </div>
      </div>

      {/* Steps */}
      <h3 className="guide-section-title">Core Features</h3>
      <div className="guide-steps">
        {steps.map((s, i) => (
          <div key={i} className="guide-step-card">
            <div className="guide-step-icon" style={{ background: s.color + '18', color: s.color }}>
              {s.icon}
            </div>
            <div className="guide-step-body">
              <div className="guide-step-title">{s.title}</div>
              <p className="guide-step-desc">{s.description}</p>
            </div>
          </div>
        ))}
      </div>

      {/* Sample Queries */}
      <h3 className="guide-section-title" style={{ marginTop: '2rem' }}>
        <Lightbulb size={16} style={{ marginRight: '0.4rem', verticalAlign: 'middle', color: 'var(--warning)' }} />
        Sample Queries to Try
      </h3>
      <div className="dashboard-card">
        <div className="card-body" style={{ padding: '0.5rem 0.75rem' }}>
          {sampleQueries.map((q, i) => (
            <div key={i} className="guide-query-row">
              <ArrowRight size={14} style={{ color: 'var(--primary)', flexShrink: 0 }} />
              <span>{q}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Tips */}
      <h3 className="guide-section-title" style={{ marginTop: '2rem' }}>Tips</h3>
      <div className="guide-tips-grid">
        {[
          ['Use HGVS notation', 'Queries like "c.5A>G" or "p.Met1Thr" return more precise variant results.'],
          ['Cite-check every answer', 'Click any PMID citation link to verify the source abstract on PubMed.'],
          ['Guardrail warnings', 'A yellow alert means the LLM may have added detail not in retrieved chunks — treat those claims with caution.'],
          ['Re-ingest for new data', 'Run the ingest pipeline periodically to keep the corpus up to date with new publications.'],
        ].map(([title, body], i) => (
          <div key={i} className="guide-tip-card">
            <div className="guide-tip-title">{title}</div>
            <div className="guide-tip-body">{body}</div>
          </div>
        ))}
      </div>

      {/* Data sources */}
      <h3 className="guide-section-title" style={{ marginTop: '2rem' }}>
        <FileText size={16} style={{ marginRight: '0.4rem', verticalAlign: 'middle' }} />
        Data Sources
      </h3>
      <div className="dashboard-card">
        <div className="card-body">
          <div className="info-rows">
            <div className="info-row"><span className="info-label">PubMed / NCBI Entrez</span><span>Peer-reviewed abstracts (RARS1, HLD9 queries)</span></div>
            <div className="info-row"><span className="info-label">Europe PMC</span><span>Preprints — bioRxiv &amp; medRxiv</span></div>
            <div className="info-row"><span className="info-label">Embedding model</span><span>pritamdeka/S-PubMedBert-MS-MARCO</span></div>
            <div className="info-row"><span className="info-label">LLM</span><span>Llama 3.2 via Ollama (local, no data leaves the server)</span></div>
            <div className="info-row"><span className="info-label">Vector store</span><span>ChromaDB (persistent)</span></div>
          </div>
        </div>
      </div>
    </div>
  );
}

/* ─────────────────── Main App ─────────────────── */
function App() {
  const [activeView, setActiveView] = useState('search');
  const [messages, setMessages] = useState([
    {
      role: 'assistant',
      content: 'Welcome to the **RARS1 Genomic Intelligence Dashboard**. You can search current medical literature for variants, clinical phenotypes, and disease associations. What would you like to investigate?',
      citations: [],
      guardrail: null
    }
  ]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const messagesEndRef = useRef(null);

  // Theme state — light is default; .dark-mode class drives dark overrides
  const [isDark, setIsDark] = useState(() => {
    const saved = localStorage.getItem('theme');
    return saved ? saved === 'dark' : false;
  });

  const toggleTheme = useCallback(() => {
    setIsDark(prev => {
      const next = !prev;
      localStorage.setItem('theme', next ? 'dark' : 'light');
      document.documentElement.classList.toggle('dark-mode', next);
      return next;
    });
  }, []);

  // Apply theme on mount
  useEffect(() => {
    document.documentElement.classList.toggle('dark-mode', isDark);
  }, []);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => { scrollToBottom(); }, [messages, isLoading]);

  const handleSubmit = useCallback(async (e) => {
    e.preventDefault();
    if (!input.trim() || isLoading) return;

    const userQuery = input.trim();
    setInput('');
    setMessages(prev => [...prev, { role: 'user', content: userQuery }]);
    setIsLoading(true);
    setMessages(prev => [...prev, {
      role: 'assistant', content: '', citations: [], guardrail: null,
      inScope: true, isStreaming: true
    }]);

    try {
      const response = await fetch('/api/query/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: userQuery })
      });
      if (!response.ok) throw new Error(`API Error: ${response.status}`);

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = '';
        let eventName = '';

        for (let i = 0; i < lines.length; i++) {
          const line = lines[i];
          if (line.startsWith('event: ')) {
            eventName = line.slice(7).trim();
          } else if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.slice(6));
              const update = (fn) => setMessages(prev => {
                const updated = [...prev];
                const last = updated[updated.length - 1];
                if (last?.role === 'assistant') updated[updated.length - 1] = fn(last);
                return updated;
              });

              if (eventName === 'token') update(l => ({ ...l, content: l.content + data }));
              else if (eventName === 'citations') update(l => ({ ...l, citations: data }));
              else if (eventName === 'scope') update(l => ({ ...l, inScope: data.in_scope }));
              else if (eventName === 'guardrail') update(l => ({ ...l, guardrail: data }));
              else if (eventName === 'done') update(l => ({ ...l, isStreaming: false }));
              else if (eventName === 'error') update(l => ({ ...l, content: `Error: ${data.error}`, isStreaming: false, isError: true }));
            } catch {
              buffer = lines.slice(i).join('\n');
              break;
            }
          } else if (line === '') {
            eventName = '';
          } else {
            buffer += line;
            if (i < lines.length - 1) buffer += '\n';
          }
        }
      }
    } catch (err) {
      setMessages(prev => {
        const updated = [...prev];
        const last = updated[updated.length - 1];
        if (last?.role === 'assistant') {
          updated[updated.length - 1] = { ...last, content: `Error: ${err.message}`, isStreaming: false, isError: true };
        }
        return updated;
      });
    } finally {
      setIsLoading(false);
    }
  }, [input, isLoading]);

  return (
    <div className="app-container">
      {/* Sidebar */}
      <aside className="sidebar">
        <div className="brand">
          <img src="/logo-light.png" alt="ILYOME" />
        </div>
        <div className="nav-section">
          <div className={`nav-item ${activeView === 'search' ? 'active' : ''}`} onClick={() => setActiveView('search')}>
            <Search size={18} /><span>Literature Search</span>
          </div>
          <div className={`nav-item ${activeView === 'variants' ? 'active' : ''}`} onClick={() => setActiveView('variants')}>
            <Beaker size={18} /><span>Variant Reports</span>
          </div>
          <div className={`nav-item ${activeView === 'gene-info' ? 'active' : ''}`} onClick={() => setActiveView('gene-info')}>
            <Info size={18} /><span>Gene Information</span>
          </div>
          <div className={`nav-item ${activeView === 'guide' ? 'active' : ''}`} onClick={() => setActiveView('guide')}>
            <BookOpen size={18} /><span>How to Use</span>
          </div>
        </div>
        <button className="theme-toggle" onClick={toggleTheme}>
          {isDark ? <Sun size={16} /> : <Moon size={16} />}
          <span>{isDark ? 'Light Mode' : 'Dark Mode'}</span>
        </button>
        <div className="sidebar-footer">
          Powered by PubMedBERT &amp; Llama
        </div>
      </aside>

      {/* Main */}
      <main className="main-content">
        <header className="header">
          <div className="header-title">
            {activeView === 'search' && 'Genomic Knowledge Assistant'}
            {activeView === 'variants' && 'Variant Reports'}
            {activeView === 'gene-info' && 'Gene Information'}
            {activeView === 'guide' && 'How to Use'}
          </div>
        </header>

        {/* ─── Search / Chat View ─── */}
        {activeView === 'search' && (
          <div className="chat-container">
            <div className="messages-area">
              {messages.map((msg, idx) => (
                <div key={idx} className={`message ${msg.role}`}>
                  <div className={`avatar ${msg.role}`}>
                    {msg.role === 'user' ? <User /> : <Bot />}
                  </div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem', flexGrow: 1, maxWidth: '100%' }}>
                    <div className="message-content">
                      {msg.isError ? (
                        <span style={{ color: 'var(--status-error)' }}>{msg.content}</span>
                      ) : (
                        <div className="markdown">
                          <ReactMarkdown>{msg.content}</ReactMarkdown>
                          {msg.isStreaming && <span className="streaming-cursor">▊</span>}
                        </div>
                      )}
                    </div>
                    {!msg.isStreaming && msg.guardrail && !msg.guardrail.passed && msg.role === 'assistant' && (
                      <div className="guardrail-alert">
                        <AlertTriangle className="guardrail-icon" size={20} />
                        <div className="guardrail-content">
                          <h4>Hallucination Guardrail Alert</h4>
                          <ul>{Array.isArray(msg.guardrail.warnings) && msg.guardrail.warnings.map((w, i) => <li key={i}>{w}</li>)}</ul>
                        </div>
                      </div>
                    )}
                    {!msg.isStreaming && msg.guardrail && msg.guardrail.passed && msg.role === 'assistant' && (
                      <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '0.8rem', color: 'var(--status-success)', opacity: 0.8 }}>
                        <CheckCircle size={14} /><span>All claims verified against retrieved sources</span>
                      </div>
                    )}
                    {!msg.isStreaming && msg.citations?.length > 0 && msg.role === 'assistant' && (
                      <div className="dashboard-card">
                        <div className="card-header"><CheckCircle size={14} color="var(--status-success)" />Clinical Evidence &amp; Citations</div>
                        <div className="card-body">
                          <ul className="citation-list">
                            {msg.citations.map((cit, i) => (
                              <li key={i} className="citation-item">
                                <span style={{ color: 'var(--text-muted)' }}>[{i + 1}]</span>
                                <span>
                                  <a href={cit.url} target="_blank" rel="noreferrer" className="citation-id">PMID: {cit.pmid}</a>
                                  {' — ' + cit.title}
                                </span>
                              </li>
                            ))}
                          </ul>
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              ))}
              {isLoading && messages[messages.length - 1]?.content === '' && (
                <div className="message assistant" style={{ marginTop: '-1rem' }}>
                  <div className="avatar assistant"><Bot /></div>
                  <div className="message-content">
                    <div className="typing-indicator">
                      <div className="typing-dot"></div><div className="typing-dot"></div><div className="typing-dot"></div>
                    </div>
                  </div>
                </div>
              )}
              <div ref={messagesEndRef} />
            </div>
            <div className="input-area">
              <form onSubmit={handleSubmit} className="input-wrapper">
                <input type="text" className="chat-input" placeholder="Query RARS1 variants, clinical phenotypes, or recent literature…" value={input} onChange={e => setInput(e.target.value)} disabled={isLoading} />
                <button type="submit" className="send-button" disabled={!input.trim() || isLoading}>
                  {isLoading ? <Loader2 className="animate-spin" size={20} /> : <Send size={20} />}
                </button>
              </form>
            </div>
          </div>
        )}

        {/* ─── Variant Reports View ─── */}
        {activeView === 'variants' && <VariantReports />}

        {/* ─── Gene Information View ─── */}
        {activeView === 'gene-info' && <GeneInformation />}

        {/* ─── Guide View ─── */}
        {activeView === 'guide' && <Guide />}
      </main>
    </div>
  );
}

export default App;
