import { formatBytes } from "../view-models/format";

/**
 * `maxUploadBytes` is optional because the limit belongs to the server and
 * arrives asynchronously from /config. While it is unknown the clause is
 * dropped entirely -- a hardcoded fallback is what previously left this
 * component announcing "max 5 MB" long after the configured limit had moved.
 */
export function WorkspaceEmptyState({ onChooseFile, onFile, onPaste, maxUploadBytes }: { onChooseFile: () => void; onFile: (file: File) => void; onPaste: () => void; maxUploadBytes?: number }) {
  return (
    <section className="empty-state">
      <div className="empty-card">
        <h1>Start with the resume</h1>
        <p>Every verdict cites actual resume text, so nothing can run until one is indexed. Add jobs after the resume is ready.</p>
        <div className="dropzone" data-testid="resume-dropzone" onDragOver={(event) => event.preventDefault()} onDrop={(event) => { event.preventDefault(); const file = event.dataTransfer.files[0]; if (file) onFile(file); }}>
          <p>Drop a PDF or DOCX here</p>
          <span>or <button type="button" onClick={onChooseFile}>choose a file</button>{maxUploadBytes !== undefined && ` · max ${formatBytes(maxUploadBytes)}`}</span>
        </div>
        <div className="or-divider"><span /><em>or</em><span /></div>
        <button type="button" className="paste-option" onClick={onPaste}><strong>Paste resume text</strong><span>Plain text works too. Citations will reference line numbers instead of pages.</span></button>
      </div>
    </section>
  );
}
