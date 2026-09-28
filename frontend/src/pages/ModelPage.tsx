import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "../api";
import { ErrorState, Skeleton, pct, useAsync } from "../components/ui";

const f3 = (x: number | null | undefined) => (x == null ? "—" : x.toFixed(3));

export default function ModelPage() {
  const { data, error, loading, reload } = useAsync(() => api.model(), []);
  if (loading) return <div className="content"><Skeleton h={300} /></div>;
  if (error || !data) return <ErrorState message={error || "No model"} onRetry={reload} />;
  const { card, metrics } = data;
  const test = metrics.test || {};
  const sel = test.selected_model || {};
  const base = test.heuristic_baseline || {};
  const cc = test.calibration_curve;
  const calib = cc ? cc.mean_predicted.map((p: number, i: number) => ({ p, observed: cc.observed_late_rate[i], ideal: p })) : [];
  const importance = Object.entries(metrics.global_importance || {}) as [string, number][];
  const maxImp = Math.max(0.001, ...importance.map(([, v]) => v));
  const cm = sel.confusion_matrix || {};
  const lpo = metrics.leave_project_out;

  return (
    <>
      <header className="topbar">
        <div>
          <h1>Model & evaluation</h1>
          <div className="muted small">How the delay model was trained and how well it works on data it never saw.</div>
        </div>
        <span className={`badge ${card.is_synthetic ? "synthetic" : "brand"}`}>{card.data_source}</span>
      </header>
      <div className="content stack">
        {card.is_synthetic && (
          <div className="banner">
            ⚠ {card.warning} Run the TAWOS pipeline (docs/ML.md) to replace it with the real model.
          </div>
        )}
        <div className="grid grid-dash">
          <section className="card span-6 card-pad stack" style={{ gap: 6 }}>
            <h2>Model card</h2>
            <table className="tbl small">
              <tbody>
                <tr><th>Target</th><td>{card.target}</td></tr>
                <tr><th>Dataset</th><td>{card.dataset || card.data_source}</td></tr>
                <tr><th>Selected algorithm</th><td>{card.algorithm} ({card.calibration} calibration)</td></tr>
                <tr><th>Rows</th><td className="num">{card.n_train} train · {card.n_valid} valid · {card.n_test} test</td></tr>
                <tr><th>Split</th><td>chronological by sprint/window (no future data in training)</td></tr>
                <tr><th>Risk thresholds</th><td>high ≥ {pct(data.thresholds.high)} · medium ≥ {pct(data.thresholds.medium)} (chosen on validation)</td></tr>
                <tr><th>Trained</th><td>{card.trained_at}</td></tr>
              </tbody>
            </table>
            {card.limitations && (
              <><h3 style={{ marginTop: 8 }}>Known limitations</h3>
                <ul className="small" style={{ margin: 0, paddingLeft: 18 }}>{card.limitations.map((l: string) => <li key={l}>{l}</li>)}</ul></>
            )}
          </section>

          <section className="card span-6 card-pad stack">
            <h2>Test-set results vs. baseline</h2>
            <table className="tbl small">
              <thead><tr><th>Metric</th><th>Model</th><th>Heuristic baseline</th></tr></thead>
              <tbody>
                <tr><td className="tip" data-tip="Area under precision-recall curve: best single number when the 'late' class matters most.">PR-AUC</td><td className="num"><strong>{f3(sel.pr_auc)}</strong></td><td className="num">{f3(base.pr_auc)}</td></tr>
                <tr><td>ROC-AUC</td><td className="num">{f3(sel.roc_auc)}</td><td className="num">{f3(base.roc_auc)}</td></tr>
                <tr><td className="tip" data-tip="Mean squared error of probabilities. Lower = the % shown in the UI is more trustworthy.">Brier score</td><td className="num">{f3(sel.brier)}</td><td className="num">{f3(base.brier)}</td></tr>
                <tr><td>Precision @ high</td><td className="num">{f3(sel.precision)}</td><td className="num">{f3(base.precision)}</td></tr>
                <tr><td>Recall @ high</td><td className="num">{f3(sel.recall)}</td><td className="num">{f3(base.recall)}</td></tr>
                <tr><td>F1 @ high</td><td className="num">{f3(sel.f1)}</td><td className="num">{f3(base.f1)}</td></tr>
                <tr><td>Accuracy</td><td className="num">{f3(sel.accuracy)}</td><td className="num">{f3(base.accuracy)}</td></tr>
              </tbody>
            </table>
            <div className="small muted">Late rate in test set: {pct(sel.late_rate, 1)} · always-predict-majority accuracy: {pct(test.majority_class_accuracy, 1)}</div>
            <div className="row" style={{ gap: 20 }}>
              <div>
                <div className="small muted">Confusion matrix @ high threshold</div>
                <table className="tbl small num" style={{ width: 220 }}>
                  <thead><tr><th></th><th>pred on-time</th><th>pred late</th></tr></thead>
                  <tbody>
                    <tr><th>on time</th><td>{cm.tn}</td><td>{cm.fp}</td></tr>
                    <tr><th>late</th><td>{cm.fn}</td><td>{cm.tp}</td></tr>
                  </tbody>
                </table>
              </div>
            </div>
          </section>

          <section className="card span-6">
            <div className="card-head"><h2>Calibration</h2><span className="hint">does “70%” really mean 70%?</span></div>
            <div style={{ height: 260, padding: "10px 16px 4px 0" }}>
              <ResponsiveContainer>
                <LineChart data={calib}>
                  <CartesianGrid stroke="var(--line)" />
                  <XAxis dataKey="p" type="number" domain={[0, 1]} tickFormatter={(v) => `${Math.round(v * 100)}%`} tick={{ fontSize: 11 }} />
                  <YAxis domain={[0, 1]} tickFormatter={(v) => `${Math.round(v * 100)}%`} tick={{ fontSize: 11 }} width={40} />
                  <Tooltip formatter={(v: unknown) => pct(Number(v))} labelFormatter={(v) => `predicted ${pct(Number(v))}`} />
                  <Line dataKey="ideal" name="perfect" stroke="var(--ink-3)" strokeDasharray="4 4" dot={false} />
                  <Line dataKey="observed" name="observed late rate" stroke="var(--brand)" strokeWidth={2} dot={{ r: 4 }} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </section>

          <section className="card span-6">
            <div className="card-head"><h2>What drives predictions</h2><span className="hint">mean change in probability vs. typical value</span></div>
            <div className="card-pad stack" style={{ gap: 6 }}>
              {importance.slice(0, 10).map(([k, v]) => (
                <div key={k} className="factor" style={{ gridTemplateColumns: "190px 1fr" }}>
                  <span className="small num">{k}</span>
                  <div className="row" style={{ gap: 6 }}>
                    <div className="impact" style={{ background: "var(--brand)", width: `${(v / maxImp) * 100}%` }} />
                    <span className="small num">{(v * 100).toFixed(1)}</span>
                  </div>
                </div>
              ))}
            </div>
          </section>

          <section className="card span-12 card-pad stack">
            <h2>Model comparison (validation set)</h2>
            <table className="tbl small">
              <thead><tr><th>Candidate</th><th>PR-AUC</th><th>ROC-AUC</th><th>Brier</th></tr></thead>
              <tbody>
                {Object.entries(metrics.model_comparison_validation || {}).map(([k, v]: [string, any]) => (
                  <tr key={k} style={k === card.algorithm ? { fontWeight: 700 } : undefined}>
                    <td>{k}{k === card.algorithm ? " ✓ selected" : ""}</td>
                    <td className="num">{f3(v.valid_pr_auc)}</td><td className="num">{f3(v.valid_roc_auc)}</td><td className="num">{f3(v.valid_brier)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {lpo && (
              <div className="small">
                <strong>Generalisation to unseen projects</strong> (leave-one-project-out): mean PR-AUC {f3(lpo.mean_pr_auc)}, mean ROC-AUC {f3(lpo.mean_roc_auc)} across {lpo.per_project.length} held-out projects.
              </div>
            )}
          </section>
        </div>
      </div>
    </>
  );
}
