import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { Chart as ChartJS, ArcElement, Tooltip, Legend, CategoryScale, LinearScale, PointElement, LineElement } from 'chart.js';
import { Pie, Line } from 'react-chartjs-2';
import './App.css';

ChartJS.register(ArcElement, Tooltip, Legend, CategoryScale, LinearScale, PointElement, LineElement);

const API_URL = "http://localhost:8000";

function App() {
  const [trades, setTrades] = useState([]);
  const [analytics, setAnalytics] = useState(null);
  const [file, setFile] = useState(null);
  const [note, setNote] = useState("");
  const [selectedTrade, setSelectedTrade] = useState(null);
  const [loading, setLoading] = useState(false);
  const [activeTab, setActiveTab] = useState("dashboard");

  const fetchData = async () => {
    try {
      const tRes = await axios.get(`${API_URL}/trades/`);
      const aRes = await axios.get(`${API_URL}/analytics/`);
      setTrades(tRes.data);
      setAnalytics(aRes.data);
    } catch (err) {
      console.error("Error fetching data", err);
    }
  };

  useEffect(() => { fetchData(); }, []);

  const handleFileUpload = async () => {
    if (!file) return alert("Select a file first");
    setLoading(true);
    const formData = new FormData();
    formData.append("file", file);
    
    try {
      await axios.post(`${API_URL}/upload-history/`, formData);
      alert("Trades Imported!");
      fetchData();
    } catch (err) {
      alert("Error importing file");
    }
    setLoading(false);
  };

  const saveNote = async () => {
    if (!selectedTrade) return;
    try {
      await axios.post(`${API_URL}/trades/${selectedTrade}/note/`, `note=${note}`);
      alert("Note saved!");
      fetchData();
    } catch (err) { console.error(err); }
  };

  const handleScreenshot = async (e) => {
    const imgFile = e.target.files[0];
    if (!selectedTrade || !imgFile) return;
    const formData = new FormData();
    formData.append("file", imgFile);
    try {
      await axios.post(`${API_URL}/trades/${selectedTrade}/screenshot/`, formData);
      alert("Screenshot uploaded!");
    } catch (err) { alert("Upload failed"); }
  };

  const winLossData = {
    labels: ['Wins', 'Losses'],
    datasets: [{
      data: analytics ? [analytics.wins, analytics.losses] : [0, 0],
      backgroundColor: ['#4caf50', '#f44336'],
    }],
  };

  const pnlData = {
    labels: trades.map((t, i) => i + 1),
    datasets: [{
      label: 'Cumulative P&L',
      data: trades.map((t, i) => {
        const prev = trades.slice(0, i).reduce((a, b) => a + b.profit_loss, 0);
        return prev + t.profit_loss;
      }),
      borderColor: '#2196f3', tension: 0.1
    }]
  };

  return (
    <div className="App">
      <header className="header">
        <h1>📈 Trading Journal</h1>
        <div className="tabs">
          <button onClick={() => setActiveTab("dashboard")}>Dashboard</button>
          <button onClick={() => setActiveTab("trades")}>Trade List</button>
          <button onClick={() => setActiveTab("upload")}>Import MT5</button>
        </div>
      </header>

      <div className="content">
        {activeTab === "upload" && (
          <div className="card">
            <h2>Import MT5 History</h2>
            <p>Upload .html or .csv exported from MT5</p>
            <input type="file" onChange={e => setFile(e.target.files[0])} />
            <button onClick={handleFileUpload} disabled={loading}>
              {loading ? "Importing..." : "Upload & Parse"}
            </button>
          </div>
        )}

        {activeTab === "dashboard" && analytics && (
          <div className="dashboard">
            <div className="stats-grid">
              <div className="stat-card">
                <h3>Total P&L</h3>
                <p className={analytics.total_pnl >= 0 ? "green" : "red"}>
                  ${analytics.total_pnl}
                </p>
              </div>
              <div className="stat-card">
                <h3>Win Rate</h3>
                <p>{analytics.win_rate}%</p>
              </div>
              <div className="stat-card">
                <h3>Profit Factor</h3>
                <p>{analytics.profit_factor}</p>
              </div>
              <div className="stat-card">
                <h3>Max Drawdown</h3>
                <p className="red">${analytics.max_drawdown}</p>
              </div>
            </div>

            <div className="charts">
              <div className="chart-box"><h3>Wins vs Losses</h3><Pie data={winLossData} /></div>
              <div className="chart-box"><h3>Equity Curve</h3><Line data={pnlData} /></div>
            </div>
          </div>
        )}

        {activeTab === "trades" && (
          <div className="trades-list">
            <table>
              <thead>
                <tr>
                  <th>Symbol</th>
                  <th>Type</th>
                  <th>Entry</th>
                  <th>Exit</th>
                  <th>P&L</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                {trades.map((t) => (
                  <tr key={t.id} onClick={() => setSelectedTrade(t.id)} className={selectedTrade === t.id ? "selected-row": ""}>
                    <td>{t.symbol}</td>
                    <td>{t.trade_type}</td>
                    <td>{new Date(t.entry_time).toLocaleDateString()}</td>
                    <td>{new Date(t.exit_time).toLocaleDateString()}</td>
                    <td className={t.profit_loss >= 0 ? "green" : "red"}>${t.profit_loss}</td>
                    <td><button onClick={(e) => {e.stopPropagation(); setSelectedTrade(t.id); setNote(t.notes || "");}}>Edit</button></td>
                  </tr>
                ))}
              </tbody>
            </table>
            
            {selectedTrade && (
              <div className="trade-details">
                <h3>Trade #{selectedTrade} Details</h3>
                <textarea placeholder="Add journal notes..." value={note} onChange={e => setNote(e.target.value)} />
                <button onClick={saveNote}>Save Notes</button>
                <div className
