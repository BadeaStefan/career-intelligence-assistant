export function WorkspaceEmptyState({ onChooseFile, onFile, onPaste }: { onChooseFile: () => void; onFile: (file: File) => void; onPaste: () => void }) {
  return (
    <section className="empty-state">
      <div className="empty-card">
        <h1>Start with the resume</h1>
        <p>Every verdict cites actual resume text, so nothing can run until one is indexed. Add jobs after the resume is ready.</p>
        <div className="dropzone" data-testid="resume-dropzone" onDragOver={(event) => event.preventDefault()} onDrop={(event) => { event.preventDefault(); const file = event.dataTransfer.files[0]; if (file) onFile(file); }}>
          <p>Drop a PDF or DOCX here</p>
          <span>or <button type="button" onClick={onChooseFile}>choose a file</button> · max 5 MB</span>
        </div>
        <div className="or-divider"><span /><em>or</em><span /></div>
        <button type="button" className="paste-option" onClick={onPaste}><strong>Paste resume text</strong><span>Plain text works too. Citations will reference line numbers instead of pages.</span></button>
      </div>
    </section>
  );
}
