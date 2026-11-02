type Props = { name: string; status: string; progress: number | null; compact?: boolean };

export default function IndexingProgress({ name, status, progress, compact = false }: Props) {
  const ready = status === "ready";
  const failed = status === "failed";
  const value = ready ? 100 : status === "queued" ? 0 : Math.max(0, Math.min(99, Math.round(Number.isFinite(progress) ? progress! : 0)));
  const label = ready ? "Indexed" : failed ? "Indexing interrupted" : status === "queued" ? "Queued for indexing" : value >= 95 ? "Finalizing index" : value === 0 ? "Preparing document" : "Indexing document";
  const color = failed ? "var(--danger)" : ready ? "var(--ok)" : "var(--accent)";
  return <div className={compact ? "mt-2" : "mt-3"}>
    <div className="mb-1.5 flex items-center justify-between gap-2 text-xs">
      <span className="font-medium" style={{ color }}>{label}</span>
      <span className="font-semibold tabular-nums" style={{ color }}>{value}%</span>
    </div>
    <div role="progressbar" aria-label={`Indexing progress for ${name}`} aria-valuemin={0} aria-valuemax={100}
      aria-valuenow={value} aria-valuetext={`${label}: ${value}%`}
      className="indexing-track" data-status={status}>
      <span className="indexing-fill" style={{ width: `${value}%`, backgroundColor: color }} />
    </div>
  </div>;
}
