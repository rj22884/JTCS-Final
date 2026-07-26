import { useEffect, useState } from "react";
import { fetchHealth, type HealthResponse } from "../api/client";

export default function StatusCard() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchHealth().then(setHealth).catch((err: Error) => setError(err.message));
  }, []);

  return (
    <section className="card">
      <h2>System status</h2>
      <p className="muted">Backend API and database connectivity.</p>

      {health && (
        <div className="status-grid">
          <div>
            <span className="label">Service</span>
            <strong>{health.service}</strong>
          </div>
          <div>
            <span className="label">API</span>
            <strong className="status ok">{health.status}</strong>
          </div>
          <div>
            <span className="label">Version</span>
            <strong>{health.version}</strong>
          </div>
        </div>
      )}

      {error && <p className="status error">Backend unavailable: {error}</p>}
      {!health && !error && <p>Checking backend...</p>}
    </section>
  );
}
