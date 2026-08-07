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
const canvas = document.getElementById('pianoRoll');
const ctx = canvas.getContext('2d');

const recorder = new MicRecorder();

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
  const form = new FormData();
  form.append('file', file, filename);

  const res = await fetch(`${API_URL}/upload`, { method: 'POST', body: form });
  const data = await res.json();
  projectId = data.project_id;
  projectIdSpan.textContent = projectId;
  infoSection.classList.remove('hidden');
  transcribeBtn.disabled = false;
}

async function uploadAudio() {
  const file = uploadInput.files[0];
  if (!file) return;
  await uploadFile(file, file.name);
}

async function startRecording() {
  try {
    await recorder.start();
    recordBtn.disabled = true;
    stopRecordBtn.disabled = false;
    recordedAudio.classList.add('hidden');
  } catch (err) {
    alert('Could not start microphone: ' + err.message);
  }
}

async function stopRecording() {
  const wavBlob = recorder.stop();
  recordBtn.disabled = false;
  stopRecordBtn.disabled = true;

  const url = URL.createObjectURL(wavBlob);
  recordedAudio.src = url;
  recordedAudio.classList.remove('hidden');

  await uploadFile(wavBlob, 'recording.wav');
}

async function transcribeAudio() {
  const res = await fetch(`${API_URL}/transcribe/${projectId}`, { method: 'POST' });
  const data = await res.json();
  bpm = data.bpm;
  tracks = data.tracks;
  bpmDisplay.textContent = bpm;
  editorSection.classList.remove('hidden');
  renderTrackList();
  drawPianoRoll();
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
  const res = await fetch(`${API_URL}/export/${projectId}`, { method: 'POST' });
  const data = await res.json();
  alert(`MIDI exported to: ${data.midi_path}`);
}

async function exportSheet(format) {
  const res = await fetch(`${API_URL}/sheet/${projectId}?format=${format}`);
  const data = await res.json();
  alert(`${format === 'tab' ? 'Tablature' : 'Sheet music'} exported to: ${data.sheet_path}`);
}

async function generatePlayback() {
  const res = await fetch(`${API_URL}/playback/${projectId}`, { method: 'POST' });
  const data = await res.json();
  alert(`Playback mix exported to: ${data.audio_path}`);
}
