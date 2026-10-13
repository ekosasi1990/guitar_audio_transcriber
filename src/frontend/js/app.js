const API_URL = window.gtrApi ? window.gtrApi.url : 'http://127.0.0.1:8000';

let projectId = null;
let tracks = {};
let bpm = 120;
let selectedNote = null;
let selectedTrack = null;

const uploadInput = document.getElementById('audioInput');
const uploadBtn = document.getElementById('uploadBtn');
const recordBtn = document.getElementById('recordBtn');
const stopRecordBtn = document.getElementById('stopRecordBtn');
const transcribeBtn = document.getElementById('transcribeBtn');
const editorSection = document.getElementById('editor-section');
const infoSection = document.getElementById('info-section');
const projectIdSpan = document.getElementById('projectId');
const bpmDisplay = document.getElementById('bpmDisplay');
const trackList = document.getElementById('trackList');
const recordedAudio = document.getElementById('recordedAudio');
const levelMeter = document.getElementById('levelMeter');
const levelCtx = levelMeter.getContext('2d');
const recordTimer = document.getElementById('recordTimer');
const statusMsg = document.getElementById('statusMsg');
const mixAudio = document.getElementById('mixAudio');
const playbackSection = document.getElementById('playbackSection');
const canvas = document.getElementById('pianoRoll');
const ctx = canvas.getContext('2d');

const recorder = new MicRecorder();
let meterInterval = null;
let timerInterval = null;

function setStatus(text) {
  statusMsg.textContent = text;
}

uploadBtn.addEventListener('click', uploadAudio);
recordBtn.addEventListener('click', startRecording);
stopRecordBtn.addEventListener('click', stopRecording);
transcribeBtn.addEventListener('click', transcribeAudio);
document.getElementById('updateNoteBtn').addEventListener('click', updateNote);
document.getElementById('addAccompanimentBtn').addEventListener('click', addAccompaniment);
document.getElementById('exportMidiBtn').addEventListener('click', exportMIDI);
document.getElementById('exportSheetBtn').addEventListener('click', () => exportSheet('musicxml'));
document.getElementById('exportTabBtn').addEventListener('click', () => exportSheet('tab'));
document.getElementById('playbackBtn').addEventListener('click', generatePlayback);

async function uploadFile(file, filename) {
  setStatus('Uploading audio...');
  const form = new FormData();
  form.append('file', file, filename);

  const res = await fetch(`${API_URL}/upload`, { method: 'POST', body: form });
  const data = await res.json();
  projectId = data.project_id;
  projectIdSpan.textContent = projectId;
  infoSection.classList.remove('hidden');
  transcribeBtn.disabled = false;
  setStatus(`Audio loaded. Duration: ${data.duration.toFixed(2)}s. Click Transcribe.`);
}

async function uploadAudio() {
  const file = uploadInput.files[0];
  if (!file) return;
  await uploadFile(file, file.name);
}

function drawLevelMeter() {
  const level = recorder.getLevel();
  levelCtx.clearRect(0, 0, levelMeter.width, levelMeter.height);
  levelCtx.fillStyle = '#00d4ff';
  levelCtx.fillRect(0, 0, levelMeter.width * level, levelMeter.height);
}

function updateRecordTimer() {
  recordTimer.textContent = recorder.getDuration().toFixed(1) + 's';
}

async function startRecording() {
  try {
    await recorder.start();
    recordBtn.disabled = true;
    stopRecordBtn.disabled = false;
    recordedAudio.classList.add('hidden');
    levelMeter.classList.remove('hidden');
    recordTimer.classList.remove('hidden');
    setStatus('Recording... play your guitar');
    meterInterval = setInterval(drawLevelMeter, 50);
    timerInterval = setInterval(updateRecordTimer, 100);
  } catch (err) {
    alert('Could not start microphone: ' + err.message);
    setStatus('Microphone access denied or unavailable');
  }
}

async function stopRecording() {
  const wavBlob = recorder.stop();
  recordBtn.disabled = false;
  stopRecordBtn.disabled = true;
  clearInterval(meterInterval);
  clearInterval(timerInterval);
  levelMeter.classList.add('hidden');

  const url = URL.createObjectURL(wavBlob);
  recordedAudio.src = url;
  recordedAudio.classList.remove('hidden');

  setStatus('Processing recording...');
  await uploadFile(wavBlob, 'recording.wav');
}

async function transcribeAudio() {
  setStatus('Transcribing... please wait');
  const res = await fetch(`${API_URL}/transcribe/${projectId}`, { method: 'POST' });
  const data = await res.json();
  bpm = data.bpm;
  tracks = data.tracks;
  bpmDisplay.textContent = bpm;
  editorSection.classList.remove('hidden');
  playbackSection.classList.remove('hidden');
  renderTrackList();
  if (!selectedTrack || !tracks[selectedTrack]) {
    selectedTrack = Object.keys(tracks)[0] || null;
  }
  drawPianoRoll();
  setStatus(`Transcribed ${Object.values(tracks).flat().length} notes. Select a track to edit.`);
}

async function fetchTracks() {
  const res = await fetch(`${API_URL}/tracks/${projectId}`);
  const data = await res.json();
  bpm = data.bpm;
  tracks = data.tracks;
  drawPianoRoll();
}

function renderTrackList() {
  trackList.innerHTML = '';
  Object.keys(tracks).forEach(name => {
    const btn = document.createElement('button');
    btn.textContent = name;
    btn.addEventListener('click', () => { selectedTrack = name; drawPianoRoll(); });
    trackList.appendChild(btn);
  });
}

function drawPianoRoll() {
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  if (!selectedTrack || !tracks[selectedTrack]) return;

  const notes = tracks[selectedTrack];
  const maxTime = Math.max(...notes.map(n => n.end), 10);
  const xScale = canvas.width / maxTime;
  const yBase = canvas.height - 20;
  const yScale = (canvas.height - 40) / 84;

  // Grid lines
  for (let beat = 0; beat < maxTime; beat += 60 / bpm) {
    const x = beat * xScale;
    ctx.strokeStyle = '#333';
    ctx.beginPath();
    ctx.moveTo(x, 0);
    ctx.lineTo(x, canvas.height);
    ctx.stroke();
  }

  notes.forEach(note => {
    const x = note.start * xScale;
    const w = Math.max(2, (note.end - note.start) * xScale);
    const y = yBase - (note.pitch - 24) * yScale;
    const isSelected = selectedNote && selectedNote.pitch === note.pitch && selectedNote.start === note.start;
    ctx.fillStyle = isSelected ? '#00d4ff' : '#ff6b6b';
    ctx.fillRect(x, y - 6, w, 12);
    ctx.strokeStyle = '#fff';
    ctx.strokeRect(x, y - 6, w, 12);
  });
}

canvas.addEventListener('click', (e) => {
  if (!selectedTrack || !tracks[selectedTrack]) return;
  const rect = canvas.getBoundingClientRect();
  const x = (e.clientX - rect.left) * (canvas.width / rect.width);
  const y = (e.clientY - rect.top) * (canvas.height / rect.height);
  const maxTime = Math.max(...tracks[selectedTrack].map(n => n.end), 10);
  const xScale = canvas.width / maxTime;
  const yBase = canvas.height - 20;
  const yScale = (canvas.height - 40) / 84;

  const clickTime = x / xScale;
  const clickPitch = Math.round((yBase - y) / yScale + 24);

  selectedNote = tracks[selectedTrack].find(n =>
    Math.abs(n.pitch - clickPitch) <= 1 &&
    clickTime >= n.start && clickTime <= n.end
  ) || null;

  if (selectedNote) {
    document.getElementById('editPitch').value = selectedNote.pitch;
    document.getElementById('editStart').value = selectedNote.start;
    document.getElementById('editEnd').value = selectedNote.end;
    document.getElementById('editVelocity').value = selectedNote.velocity;
  }
  drawPianoRoll();
});

async function updateNote() {
  if (!projectId || !selectedNote || !selectedTrack) return;
  const body = {
    track: selectedTrack,
    old_pitch: selectedNote.pitch,
    old_start: selectedNote.start,
    new_pitch: parseInt(document.getElementById('editPitch').value),
    new_start: parseFloat(document.getElementById('editStart').value),
    new_end: parseFloat(document.getElementById('editEnd').value),
    new_velocity: parseInt(document.getElementById('editVelocity').value),
  };
  await fetch(`${API_URL}/edit/${projectId}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  await fetchTracks();
}

async function addAccompaniment() {
  const chords = JSON.parse(document.getElementById('chordsInput').value);
  await fetch(`${API_URL}/accompaniment/${projectId}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ chords }),
  });
  await fetchTracks();
  renderTrackList();
}

async function exportMIDI() {
  setStatus('Exporting MIDI...');
  const res = await fetch(`${API_URL}/export/${projectId}`, { method: 'POST' });
  if (!res.ok) {
    setStatus('MIDI export failed.');
    return;
  }
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = 'export.mid';
  a.click();
  URL.revokeObjectURL(url);
  setStatus('MIDI exported.');
}

async function exportSheet(format) {
  setStatus('Exporting notation...');
  const res = await fetch(`${API_URL}/sheet/${projectId}?format=${format}`);
  const data = await res.json();
  setStatus(`${format === 'tab' ? 'Tablature' : 'Sheet music'} saved: ${data.sheet_path}`);
}

async function generatePlayback() {
  setStatus('Generating playback mix...');
  const res = await fetch(`${API_URL}/playback/${projectId}`, { method: 'POST' });
  if (!res.ok) {
    setStatus('Playback mix failed.');
    return;
  }
  const blob = await res.blob();
  mixAudio.src = URL.createObjectURL(blob);
  playbackSection.classList.remove('hidden');
  setStatus('Playback mix ready. Press play below to listen.');
}
