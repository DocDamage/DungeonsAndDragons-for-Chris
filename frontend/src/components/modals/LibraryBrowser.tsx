import { type FormEvent, useEffect, useRef, useState } from 'react';
import type { LibraryCatalog, SourcePassage } from '../../types';
import { api } from '../../services/api';
import './LibraryBrowser.css';

export function LibraryBrowser({ onLibraryUpdated }: { onLibraryUpdated: () => void }) {
  const [catalog, setCatalog] = useState<LibraryCatalog | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);
  const [query, setQuery] = useState('');
  const [folderId, setFolderId] = useState('');
  const [results, setResults] = useState<SourcePassage[] | null>(null);
  const [searching, setSearching] = useState(false);
  const pendingImport = useRef(false);

  useEffect(() => {
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout> | undefined;
    async function refresh() {
      try {
        const data = await api.getLibrary(controller.signal);
        if (controller.signal.aborted) return;
        setCatalog(data);
        if (data.job.running) {
          pendingImport.current = true;
          timer = setTimeout(refresh, 2000);
        } else if (pendingImport.current) {
          pendingImport.current = false;
          onLibraryUpdated();
        }
      } catch (err) {
        if (!controller.signal.aborted) setError(err instanceof Error ? err.message : 'Unable to load library');
      }
    }
    void refresh();
    return () => { controller.abort(); clearTimeout(timer); };
  }, [refreshKey, onLibraryUpdated]);

  async function importSources(folder?: string) {
    setStarting(true);
    setError(null);
    try {
      const data = await api.indexLibrary(folder);
      pendingImport.current = true;
      setCatalog(previous => previous ? { ...previous, job: data.job } : previous);
      setRefreshKey(key => key + 1);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to import sources');
    } finally {
      setStarting(false);
    }
  }

  async function search(event: FormEvent) {
    event.preventDefault();
    if (!query.trim()) return;
    setSearching(true);
    setError(null);
    try {
      setResults(await api.searchLibrary(query, folderId || undefined));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to search sources');
    } finally {
      setSearching(false);
    }
  }

  const importing = starting || Boolean(catalog?.job.running);

  return (
    <div className="source-library">
      {error && <p role="alert" className="library-error">{error}</p>}
      {!catalog ? <p role="status">Loading source folders...</p> : <>
        <div className="library-intro">
          <div>
            <h2>Campaigns & rules library</h2>
            <p>Browse your books, adventures, and vaults. Imported passages provide references for the Dungeon Master.</p>
            <code>{catalog.root}</code>
          </div>
          <button className="send-btn" disabled={importing} onClick={() => importSources()}>Import all folders</button>
        </div>
        {importing && <div role="status" className="library-progress">
          <strong>Importing {catalog.job.completed} / {catalog.job.total || '...'} sources</strong>
          <span>{catalog.job.current}</span>
          <progress value={catalog.job.completed} max={catalog.job.total || 1} aria-label="Source import progress" />
        </div>}
        {catalog.job.error && <p role="alert" className="library-error">{catalog.job.error}</p>}
        <form onSubmit={search} className="library-search">
          <input className="action-input" aria-label="Search local sources" placeholder="Search rules, rooms, characters, or monsters" value={query} onChange={event => setQuery(event.target.value)} required />
          <select className="input-field" aria-label="Source folder" value={folderId} onChange={event => setFolderId(event.target.value)}>
            <option value="">All folders</option>
            {catalog.folders.map(folder => <option key={folder.id} value={folder.id}>{folder.title}</option>)}
          </select>
          <button className="send-btn" disabled={searching}>{searching ? 'Searching...' : 'Search'}</button>
        </form>
        {results && <section aria-label="Source search results" className="library-results">
          <h3>{results.length ? `${results.length} matching passages` : 'No matching passages'}</h3>
          {!results.length && <p>Import the relevant folder first, or try a different search.</p>}
          {results.map((result, index) => <article key={`${result.source_id}-${index}`}>
            <a href={result.file_url + (/^Page (\d+)$/.test(result.section) ? `#page=${result.section.slice(5)}` : '')} target="_blank" rel="noopener noreferrer">{result.title} · {result.section}</a>
            <span className="compendium-badge">{result.edition}</span>
            <p>{result.text}</p>
          </article>)}
        </section>}
        <div className="library-folders">
          {catalog.folders.map(folder => <section key={folder.id} className="library-folder">
            <div className="library-folder-heading">
              <div><h3>{folder.title}</h3><p>{folder.directory} · {folder.source_count} {folder.source_count === 1 ? 'source' : 'sources'} · {folder.chunk_count.toLocaleString()} searchable passages</p></div>
              <button className="hp-btn" disabled={importing || !folder.available || !folder.source_count} onClick={() => importSources(folder.id)}>Import folder</button>
            </div>
            {!folder.available ? <p>Folder not found in the library directory.</p> : <details>
              <summary>View source files</summary>
              <ul>{folder.sources.map(source => <li key={source.id}>
                <a href={source.file_url} target="_blank" rel="noopener noreferrer">{source.title}</a>
                <span>{source.status === 'indexed' ? `${source.chunks.toLocaleString()} passages` : source.status === 'empty' ? (source.path.endsWith('.zip') ? 'Assets archive' : 'No extractable text; OCR needed') : source.status === 'error' ? 'Import failed' : 'Not imported'}</span>
                {source.error && <p className="library-error">{source.error}</p>}
              </li>)}</ul>
            </details>}
          </section>)}
        </div>
      </>}
    </div>
  );
}
