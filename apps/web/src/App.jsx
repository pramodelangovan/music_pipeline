import { useEffect, useMemo, useState } from "react";
import {
  Alert,
  AppBar,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  Container,
  FormControl,
  IconButton,
  InputLabel,
  LinearProgress,
  MenuItem,
  Select,
  Stack,
  Tab,
  Tabs,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  TextField,
  Toolbar,
  Typography,
} from "@mui/material";
import AddCircleOutlineIcon from "@mui/icons-material/AddCircleOutline";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";
import UploadFileIcon from "@mui/icons-material/UploadFile";

const API_BASE = import.meta.env.VITE_API_BASE || "/api";

async function parseResponse(res) {
  const contentType = res.headers.get("content-type") || "";
  if (contentType.includes("application/json")) {
    return res.json();
  }
  const text = await res.text();
  return { detail: text || `HTTP ${res.status}` };
}

function generateRowId() {
  if (typeof globalThis !== "undefined" && globalThis.crypto && typeof globalThis.crypto.randomUUID === "function") {
    return globalThis.crypto.randomUUID();
  }
  return `row-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}

function makeRow() {
  return {
    id: generateRowId(),
    url: "",
    media_type: "audio",
    folder_name: "youtube_playlist",
  };
}

export default function App() {
  const [tab, setTab] = useState(0);
  const [rows, setRows] = useState([makeRow()]);
  const [jobs, setJobs] = useState([]);
  const [historyRows, setHistoryRows] = useState([]);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const [gapSeconds, setGapSeconds] = useState(12);
  const [cookiesFile, setCookiesFile] = useState(null);
  const [cookiesStatus, setCookiesStatus] = useState(false);

  const pendingJobs = useMemo(() => jobs.filter((j) => j.status === "queued" || j.status === "downloading"), [jobs]);

  const fetchJobs = async () => {
    const res = await fetch(`${API_BASE}/jobs`);
    const payload = await parseResponse(res);
    if (!res.ok) {
      throw new Error(payload.detail || "Failed to fetch jobs");
    }
    setJobs(payload.jobs || []);
  };

  const fetchSettings = async () => {
    const res = await fetch(`${API_BASE}/settings`);
    const payload = await parseResponse(res);
    if (!res.ok) {
      throw new Error(payload.detail || "Failed to fetch settings");
    }
    setGapSeconds(payload.gap_seconds ?? 12);
    setCookiesStatus(Boolean(payload.cookies_exists));
  };

  const fetchHistory = async () => {
    const res = await fetch(`${API_BASE}/history?limit=500`);
    const payload = await parseResponse(res);
    if (!res.ok) {
      throw new Error(payload.detail || "Failed to fetch history");
    }
    setHistoryRows(payload.history || []);
  };

  useEffect(() => {
    const loadInitial = async () => {
      try {
        await fetchSettings();
        await fetchJobs();
        await fetchHistory();
      } catch (err) {
        setError(err.message || "Failed to connect to API");
      }
    };
    loadInitial();

    const timer = setInterval(async () => {
      try {
        await fetchJobs();
        if (tab === 2) {
          await fetchHistory();
        }
      } catch {
        // Keep polling without crashing the UI.
      }
    }, 5000);
    return () => clearInterval(timer);
  }, [tab]);

  const addRow = () => setRows((current) => [...current, makeRow()]);
  const removeRow = (id) => {
    setRows((current) => (current.length === 1 ? current : current.filter((row) => row.id !== id)));
  };

  const updateRow = (id, key, value) => {
    setRows((current) => current.map((row) => (row.id === id ? { ...row, [key]: value } : row)));
  };

  const submitQueue = async () => {
    setMessage("");
    setError("");
    const items = rows
      .filter((row) => row.url.trim())
      .map((row) => ({
        url: row.url.trim(),
        media_type: row.media_type,
        folder_name: row.folder_name.trim() || "youtube_playlist",
      }));

    if (items.length === 0) {
      setError("Enter at least one valid URL.");
      return;
    }

    try {
      setLoading(true);
      const res = await fetch(`${API_BASE}/queue`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ items }),
      });
      const payload = await parseResponse(res);
      if (!res.ok) {
        throw new Error(payload.detail || "Failed to queue downloads");
      }
      setMessage(`Queued ${payload.accepted} row(s). Playlist rows will expand into individual jobs.`);
      await fetchJobs();
    } catch (err) {
      setError(err.message || "Queue submission failed");
    } finally {
      setLoading(false);
    }
  };

  const saveSettings = async () => {
    setMessage("");
    setError("");
    try {
      const res = await fetch(`${API_BASE}/settings`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ gap_seconds: Number(gapSeconds) }),
      });
      const payload = await parseResponse(res);
      if (!res.ok) {
        throw new Error(payload.detail || "Failed to save settings");
      }
      setMessage(`Saved queue gap: ${payload.gap_seconds}s`);
    } catch (err) {
      setError(err.message || "Failed to save settings");
    }
  };

  const uploadCookies = async () => {
    setMessage("");
    setError("");
    if (!cookiesFile) {
      setError("Choose a cookies.txt file first.");
      return;
    }

    try {
      const form = new FormData();
      form.append("file", cookiesFile);
      const res = await fetch(`${API_BASE}/settings/cookies`, {
        method: "POST",
        body: form,
      });
      const payload = await parseResponse(res);
      if (!res.ok) {
        throw new Error(payload.detail || "Cookies upload failed");
      }
      setCookiesStatus(Boolean(payload.cookies_exists));
      setMessage("Cookies updated successfully.");
      setCookiesFile(null);
    } catch (err) {
      setError(err.message || "Cookies upload failed");
    }
  };

  const clearRecentDownloads = async () => {
    setMessage("");
    setError("");
    try {
      const res = await fetch(`${API_BASE}/jobs/clear`, {
        method: "POST",
      });
      const payload = await parseResponse(res);
      if (!res.ok) {
        throw new Error(payload.detail || "Failed to clear recent downloads");
      }
      await fetchJobs();
      await fetchHistory();
      setMessage(`Cleared ${payload.cleared || 0} recent completed rows from download page.`);
    } catch (err) {
      setError(err.message || "Failed to clear recent downloads");
    }
  };

  return (
    <Box sx={{ minHeight: "100vh", background: "radial-gradient(circle at top, #e0ecff 0%, #f4f6fb 45%, #f9fafc 100%)", py: 4 }}>
      <Container maxWidth="lg">
        <AppBar position="static" elevation={0} sx={{ borderRadius: 3, bgcolor: "white", color: "#122847" }}>
          <Toolbar>
            <Typography variant="h6" sx={{ flexGrow: 1 }}>
              Queue Download Studio
            </Typography>
            <Chip label={`${pendingJobs.length} active`} color="primary" variant="outlined" />
          </Toolbar>
        </AppBar>

        <Card sx={{ mt: 3, boxShadow: "0 16px 50px rgba(24, 55, 110, 0.12)" }}>
          <CardContent>
            <Tabs value={tab} onChange={(_, value) => setTab(value)}>
              <Tab label="Queue" />
              <Tab label="Settings" />
              <Tab label="History" />
            </Tabs>

            {tab === 0 && (
              <Box sx={{ mt: 3 }}>
                <Stack spacing={2}>
                  {rows.map((row, index) => (
                    <Card key={row.id} variant="outlined" sx={{ p: 2 }}>
                      <Stack direction={{ xs: "column", md: "row" }} spacing={2} alignItems="center">
                        <TextField
                          label={`URL ${index + 1}`}
                          value={row.url}
                          onChange={(e) => updateRow(row.id, "url", e.target.value)}
                          fullWidth
                        />
                        <FormControl sx={{ minWidth: 140 }}>
                          <InputLabel>Type</InputLabel>
                          <Select
                            label="Type"
                            value={row.media_type}
                            onChange={(e) => updateRow(row.id, "media_type", e.target.value)}
                          >
                            <MenuItem value="audio">Audio</MenuItem>
                            <MenuItem value="video">Video</MenuItem>
                          </Select>
                        </FormControl>
                        <TextField
                          label="Folder"
                          value={row.folder_name}
                          onChange={(e) => updateRow(row.id, "folder_name", e.target.value)}
                          sx={{ minWidth: 180 }}
                        />
                        <IconButton color="error" onClick={() => removeRow(row.id)}>
                          <DeleteOutlineIcon />
                        </IconButton>
                      </Stack>
                    </Card>
                  ))}

                  <Stack direction="row" spacing={2}>
                    <Button variant="outlined" startIcon={<AddCircleOutlineIcon />} onClick={addRow}>
                      Add Row
                    </Button>
                    <Button variant="contained" onClick={submitQueue} disabled={loading}>
                      Queue Downloads
                    </Button>
                  </Stack>
                </Stack>

                {loading && <LinearProgress sx={{ mt: 2 }} />}

                <Typography variant="h6" sx={{ mt: 4, mb: 1 }}>
                  Queue Status
                </Typography>
                <Stack direction="row" justifyContent="flex-end" sx={{ mb: 1 }}>
                  <Button variant="text" color="warning" onClick={clearRecentDownloads}>
                    Clear Last Downloads
                  </Button>
                </Stack>
                <Table size="small">
                  <TableHead>
                    <TableRow>
                      <TableCell>Status</TableCell>
                      <TableCell>Type</TableCell>
                      <TableCell>Folder</TableCell>
                      <TableCell>URL</TableCell>
                      <TableCell>Error</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {jobs.map((job) => (
                      <TableRow key={job.id}>
                        <TableCell>
                          <Chip
                            size="small"
                            label={job.status}
                            color={job.status === "done" ? "success" : job.status === "failed" ? "error" : "warning"}
                            variant={job.status === "done" ? "filled" : "outlined"}
                          />
                        </TableCell>
                        <TableCell>{job.media_type}</TableCell>
                        <TableCell>{job.folder_name}</TableCell>
                        <TableCell sx={{ maxWidth: 340, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                          {job.resolved_url}
                        </TableCell>
                        <TableCell sx={{ maxWidth: 280, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                          {job.error || "-"}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </Box>
            )}

            {tab === 1 && (
              <Box sx={{ mt: 3 }}>
                <Stack spacing={3}>
                  <TextField
                    label="Gap Between Downloads (seconds)"
                    type="number"
                    inputProps={{ min: 0, max: 3600 }}
                    value={gapSeconds}
                    onChange={(e) => setGapSeconds(e.target.value)}
                    sx={{ maxWidth: 320 }}
                  />
                  <Button variant="contained" onClick={saveSettings}>
                    Save Gap Setting
                  </Button>

                  <Stack direction={{ xs: "column", md: "row" }} spacing={2} alignItems={{ xs: "flex-start", md: "center" }}>
                    <Button variant="outlined" component="label" startIcon={<UploadFileIcon />}>
                      Choose cookies.txt
                      <input
                        hidden
                        type="file"
                        accept=".txt"
                        onChange={(e) => setCookiesFile(e.target.files?.[0] || null)}
                      />
                    </Button>
                    <Typography variant="body2">
                      {cookiesFile ? cookiesFile.name : "No file selected"}
                    </Typography>
                    <Chip
                      label={cookiesStatus ? "Cookies ready" : "Cookies missing"}
                      color={cookiesStatus ? "success" : "error"}
                      variant="outlined"
                    />
                    <Button variant="contained" onClick={uploadCookies}>
                      Upload Cookies
                    </Button>
                  </Stack>
                </Stack>
              </Box>
            )}

            {tab === 2 && (
              <Box sx={{ mt: 3 }}>
                <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 1 }}>
                  <Typography variant="h6">Download History</Typography>
                  <Button
                    variant="outlined"
                    onClick={async () => {
                      try {
                        await fetchHistory();
                      } catch (err) {
                        setError(err.message || "Failed to refresh history");
                      }
                    }}
                  >
                    Refresh
                  </Button>
                </Stack>

                <Table size="small">
                  <TableHead>
                    <TableRow>
                      <TableCell>Created</TableCell>
                      <TableCell>Status</TableCell>
                      <TableCell>Type</TableCell>
                      <TableCell>Folder</TableCell>
                      <TableCell>URL</TableCell>
                      <TableCell>Error</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {historyRows.map((row) => (
                      <TableRow key={row.id}>
                        <TableCell>{row.created_at ? row.created_at.replace("T", " ").slice(0, 19) : "-"}</TableCell>
                        <TableCell>
                          <Chip
                            size="small"
                            label={row.status}
                            color={row.status === "done" ? "success" : row.status === "failed" ? "error" : "warning"}
                            variant={row.cleared ? "outlined" : "filled"}
                          />
                        </TableCell>
                        <TableCell>{row.media_type}</TableCell>
                        <TableCell>{row.folder_name}</TableCell>
                        <TableCell sx={{ maxWidth: 340, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                          {row.resolved_url}
                        </TableCell>
                        <TableCell sx={{ maxWidth: 280, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                          {row.error || "-"}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </Box>
            )}

            {message && (
              <Alert sx={{ mt: 3 }} severity="success" onClose={() => setMessage("")}>
                {message}
              </Alert>
            )}
            {error && (
              <Alert sx={{ mt: 3 }} severity="error" onClose={() => setError("")}>
                {error}
              </Alert>
            )}
          </CardContent>
        </Card>
      </Container>
    </Box>
  );
}
