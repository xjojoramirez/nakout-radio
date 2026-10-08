export function OfflineNotice() {
  return (
    <div className="offline-notice" role="status">
      <span className="power-led" aria-hidden="true" />
      <span className="offline-text">Radio offline</span>
    </div>
  );
}
