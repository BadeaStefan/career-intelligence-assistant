const KB = 1024;
const MB = KB * KB;

/** Renders a byte count the way an upload limit is spoken about. */
export function formatBytes(bytes: number): string {
  // Under a megabyte "0 MB" would read as "uploads are impossible", so the
  // unit drops rather than the precision.
  if (bytes < MB) return `${round(bytes / KB)} KB`;
  return `${round(bytes / MB)} MB`;
}

// Whole values carry no decimal point: "5 MB", never "5.0 MB".
function round(value: number): string {
  return value.toFixed(1).replace(/\.0$/, "");
}
