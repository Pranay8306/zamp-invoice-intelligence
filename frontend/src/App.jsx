
import { useEffect, useState } from "react";
import {
  LayoutDashboard, FileText, UploadCloud, CheckCircle2,
  XCircle, Clock, RefreshCw, Search, Activity,
  FileCheck2, AlertCircle, ArrowUpRight, LoaderCircle
} from "lucide-react";
import {
  ResponsiveContainer, PieChart, Pie, Cell, Tooltip
} from "recharts";
import "./index.css";

const API = import.meta.env.VITE_API_URL || "http://127.0.0.1:8000";

function App() {
  const [dashboard, setDashboard] = useState({});
  const [invoices, setInvoices] = useState([]);
  const [selected, setSelected] = useState(null);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("");
  const [filter, setFilter] = useState("ALL");
  const [search, setSearch] = useState("");

  async function loadData() {
    try {
      const [d, i] = await Promise.all([
        fetch(`${API}/api/dashboard`),
        fetch(`${API}/api/invoices`)
      ]);
      if (!d.ok || !i.ok) throw new Error("API unavailable");
      setDashboard(await d.json());
      setInvoices(await i.json());
    } catch {
      setMessage("Cannot connect to backend. Check that the backend is running.");
    }
  }

  useEffect(() => {
    loadData();
  }, []);

  async function uploadFile(event) {
    const file = event.target.files[0];
    if (!file) return;

    if (!file.name.toLowerCase().endsWith(".pdf")) {
      setMessage("Please upload a PDF file.");
      return;
    }

    setLoading(true);
    setMessage("");
    setSelected(null);

    const form = new FormData();
    form.append("file", file);

    try {
      const response = await fetch(`${API}/api/invoices/upload`, {
        method: "POST",
        body: form
      });

      const result = await response.json();

      if (!response.ok) throw new Error(result.detail || "Upload failed");

      setSelected(result);
      setMessage("Invoice processed successfully.");
      await loadData();
    } catch (error) {
      setMessage(error.message);
    } finally {
      setLoading(false);
      event.target.value = "";
    }
  }

  const filteredInvoices = invoices.filter((invoice) => {
    const matchesStatus = filter === "ALL" || invoice.status === filter;
    const matchesSearch =
      `${invoice.invoice_number || ""} ${invoice.vendor_name || ""} ${invoice.po_reference || ""}`
        .toLowerCase().includes(search.toLowerCase());
    return matchesStatus && matchesSearch;
  });

  const chartData = [
    { name: "Approved", value: dashboard.approved || 0, color: "#16a36a" },
    { name: "Rejected", value: dashboard.rejected || 0, color: "#e05252" },
    { name: "Review", value: dashboard.manual_review || 0, color: "#e6a23c" }
  ].filter(x => x.value > 0);

  function statusClass(status) {
    if (status === "APPROVED") return "approved";
    if (status === "REJECTED") return "rejected";
    return "review";
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-icon"><FileCheck2 size={23} /></div>
          <div>
            <h2>Zamp<span>AI</span></h2>
            <small>INVOICE INTELLIGENCE</small>
          </div>
        </div>

        <div className="nav-label">WORKSPACE</div>
        <div className="nav-item active"><LayoutDashboard size={18}/> Overview</div>
        <div className="nav-item"><FileText size={18}/> Invoice processing</div>
        <div className="nav-label second">SYSTEM</div>
        <div className="nav-item"><Activity size={18}/> Processing activity</div>

        <div className="sidebar-bottom">
          <div className="online-dot"></div>
          <div><strong>System operational</strong><small>Connected to API</small></div>
        </div>
      </aside>

      <main className="main">
        <header className="topbar">
          <div>
            <div className="breadcrumb">Workspace / <strong>Overview</strong></div>
            <h1>Invoice overview</h1>
            <p>Monitor, process and reconcile incoming invoices.</p>
          </div>
          <button className="refresh-btn" onClick={loadData}>
            <RefreshCw size={16}/> Refresh
          </button>
        </header>

        <section className="stats-grid">
          <Stat icon={<FileText/>} label="Total invoices" value={dashboard.total_invoices ?? 0} color="blue"/>
          <Stat icon={<CheckCircle2/>} label="Approved" value={dashboard.approved ?? 0} color="green"/>
          <Stat icon={<XCircle/>} label="Rejected" value={dashboard.rejected ?? 0} color="red"/>
          <Stat icon={<Clock/>} label="Manual review" value={dashboard.manual_review ?? 0} color="amber"/>
        </section>

        <section className="content-grid">
          <div className="panel upload-panel">
            <div className="panel-heading">
              <div><h3>Process an invoice</h3><p>Upload a PDF to extract and reconcile its details.</p></div>
              <div className="heading-icon"><UploadCloud size={20}/></div>
            </div>

            <label className={`dropzone ${loading ? "disabled" : ""}`}>
              {loading ? <LoaderCircle className="spin" size={34}/> : <UploadCloud size={35}/>}
              <strong>{loading ? "Processing invoice..." : "Choose an invoice PDF"}</strong>
              <span>Drag and drop is not enabled. Click to browse.</span>
              <span className="file-limit">PDF format · Maximum 15 MB</span>
              <input type="file" accept=".pdf,application/pdf" onChange={uploadFile} disabled={loading}/>
            </label>

            {message && <div className="message"><AlertCircle size={16}/>{message}</div>}

            <div className="process-steps">
              <div><span>01</span> Extract</div>
              <ArrowUpRight size={15}/>
              <div><span>02</span> Validate</div>
              <ArrowUpRight size={15}/>
              <div><span>03</span> Reconcile</div>
            </div>
          </div>

          <div className="panel distribution-panel">
            <div className="panel-heading">
              <div><h3>Decision distribution</h3><p>Invoice processing outcomes</p></div>
            </div>
            {chartData.length ? (
              <>
                <div className="chart-wrap">
                  <ResponsiveContainer width="100%" height={165}>
                    <PieChart>
                      <Pie data={chartData} dataKey="value" nameKey="name" innerRadius={48} outerRadius={72} paddingAngle={4}>
                        {chartData.map((entry, index) => <Cell key={index} fill={entry.color}/>)}
                      </Pie>
                      <Tooltip/>
                    </PieChart>
                  </ResponsiveContainer>
                  <div className="chart-center">
                    <strong>{dashboard.total_invoices || 0}</strong>
                    <span>Invoices</span>
                  </div>
                </div>
                <div className="legend">
                  {chartData.map(item => <div key={item.name}>
                    <span style={{background:item.color}}/>
                    {item.name}<strong>{item.value}</strong>
                  </div>)}
                </div>
              </>
            ) : <div className="empty-chart">No processed invoices yet.</div>}
          </div>
        </section>

        {selected && (
          <section className="panel result-panel">
            <div className="panel-heading">
              <div><h3>Latest processing result</h3><p>{selected.original_filename}</p></div>
              <span className={`status ${statusClass(selected.decision.status)}`}>
                {selected.decision.status.replace("_", " ")}
              </span>
            </div>
            <div className="result-grid">
              <Result label="Vendor" value={selected.invoice_data.vendor_name}/>
              <Result label="Invoice number" value={selected.invoice_data.invoice_number || "Missing"}/>
              <Result label="PO reference" value={selected.invoice_data.po_reference}/>
              <Result label="Invoice total" value={selected.invoice_data.total != null ? `₹${selected.invoice_data.total.toLocaleString("en-IN")}` : "Unavailable"}/>
            </div>
            <div className="reasons">
              <strong>Decision explanation</strong>
              {selected.decision.reasons.map((reason, i) => <p key={i}>• {reason}</p>)}
            </div>
          </section>
        )}

        <section className="panel history-panel">
          <div className="panel-heading history-heading">
            <div><h3>Invoice history</h3><p>Previously processed invoices</p></div>
            <div className="history-tools">
              <div className="search-box">
                <Search size={15}/>
                <input placeholder="Search invoices..." value={search} onChange={e=>setSearch(e.target.value)}/>
              </div>
              <select value={filter} onChange={e=>setFilter(e.target.value)}>
                <option value="ALL">All statuses</option>
                <option value="APPROVED">Approved</option>
                <option value="REJECTED">Rejected</option>
                <option value="MANUAL_REVIEW">Manual review</option>
              </select>
            </div>
          </div>

          <div className="table-wrap">
            <table>
              <thead><tr><th>INVOICE</th><th>VENDOR</th><th>PO NUMBER</th><th>AMOUNT</th><th>STATUS</th></tr></thead>
              <tbody>
                {filteredInvoices.map(invoice => (
                  <tr key={invoice.invoice_id}>
                    <td><strong>{invoice.invoice_number || "—"}</strong><small>{invoice.file_name}</small></td>
                    <td>{invoice.vendor_name || "—"}</td>
                    <td>{invoice.po_reference || "—"}</td>
                    <td>{invoice.total != null ? `₹${invoice.total.toLocaleString("en-IN")}` : "—"}</td>
                    <td><span className={`status ${statusClass(invoice.status)}`}>{invoice.status.replace("_"," ")}</span></td>
                  </tr>
                ))}
                {!filteredInvoices.length && <tr><td colSpan="5" className="empty-row">No invoices match your search.</td></tr>}
              </tbody>
            </table>
          </div>
          <div className="table-footer">Showing {filteredInvoices.length} of {invoices.length} invoices</div>
        </section>

        <footer>Zamp Invoice Intelligence <span>·</span> Automated invoice processing and reconciliation</footer>
      </main>
    </div>
  );
}

function Stat({icon,label,value,color}) {
  return <div className="stat-card">
    <div className={`stat-icon ${color}`}>{icon}</div>
    <div><span>{label}</span><strong>{value}</strong></div>
  </div>;
}

function Result({label,value}) {
  return <div className="result-item"><span>{label}</span><strong>{value || "—"}</strong></div>;
}

export default App;
