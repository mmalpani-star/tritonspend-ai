/** Fixed, theme-tinted atmosphere behind every page: slow spectrum light and speckled corners. */
export function AmbientBackdrop() {
  return (
    <div className="ambient-backdrop" aria-hidden="true">
      <span className="ambient-blob ambient-blob-a" />
      <span className="ambient-blob ambient-blob-b" />
      <span className="ambient-blob ambient-blob-c" />
      <span className="ambient-speckles ambient-speckles-tl speckle-mask speckle-corner" />
      <span className="ambient-speckles ambient-speckles-br speckle-mask speckle-corner" />
    </div>
  );
}
