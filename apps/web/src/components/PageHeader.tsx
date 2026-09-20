export function PageHeader({ title, desc }: { title: string; desc?: string }) {
  return (
    <header className="page-header">
      <h1 className="page-title">{title}</h1>
      {desc && <p className="page-desc">{desc}</p>}
    </header>
  );
}
