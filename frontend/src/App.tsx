import Layout from "./components/Layout";
import StatusCard from "./components/StatusCard";

export default function App() {
  return (
    <Layout>
      <div className="grid">
        <StatusCard />

        <section className="card">
          <h2>Getting started</h2>
          <p className="muted">
            Your fresh JTCS Final stack is running. Next steps: define business
            modules, add authentication, and connect your database models.
          </p>
          <ul className="checklist">
            <li>FastAPI backend with SQLite</li>
            <li>React frontend with Vite</li>
            <li>Health check with database seed</li>
          </ul>
        </section>
      </div>
    </Layout>
  );
}
