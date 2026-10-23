const API_URL = window.gtrApi ? window.gtrApi.url : 'http://127.0.0.1:8000';
let lastTakeFilename = 'recording.wav';
const $ = (id) => document.getElementById(id);
const recorder = new MicRecorder();
const canvas = $('pianoRoll'),
  ctx = canvas.getContext('2d'),
  viewport = $('graphViewport');
const audio = $('mixAudio');
let projectId = null,
  tracks = { Guitar: [] },
  tabEvents = [],
  bpm = 120,
  bpmOverride = false;
let rhythm = null,
  canUndo = false,
  selectedNote = null,
  busy = false,
  recording = false;
let lastTakeBlob = null,
  liveTimer = null,
  captureTimer = null,
  livePending = false,
  liveAbort = null,
  liveGeneration = 0;
let liveOrigin = null,
  view = 'tab',
  playTime = 0,
  audioDirty = true,
  pendingSeek = 0;
let dragging = false,
  resumeAfterDrag = false,
  waitingToPlay = false;
let drawnDuration = 0;
const dataButtons = [
  'playbackBtn',
  'playBtn',
  'stopPlaybackBtn',
  'exportMidiBtn',
  'exportSheetBtn',
  'exportTabBtn',
  'applyTimingBtn',
  'fitRhythmBtn',
];

function notes() {
  return tracks.Guitar || [];
}
function events() {
  const result = [];
  for (const n of [...notes()].sort((a, b) => a.start - b.start || a.pitch - b.pitch)) {
    const last = result.at(-1);
    if (last && n.start - last.start <= 0.06) {
      last.notes.push(n);
      last.end = Math.max(last.end, n.end);
    } else result.push({ start: n.start, end: n.end, notes: [n] });
  }
  return result;
}
function timeLabel(seconds) {
  seconds = Math.max(0, seconds || 0);
  return `${Math.floor(seconds / 60)}:${String(Math.floor(seconds % 60)).padStart(2, '0')}`;
}
function noteName(pitch) {
  return (
    ['C', 'C♯', 'D', 'D♯', 'E', 'F', 'F♯', 'G', 'G♯', 'A', 'A♯', 'B'][pitch % 12] +
    (Math.floor(pitch / 12) - 1)
  );
}
function setStatus(message, error = false) {
  $('statusMsg').textContent = message;
  $('statusMsg').classList.toggle('error', error);
}
function refreshButtons() {
  const haveNotes = notes().length > 0 && projectId;
  dataButtons.forEach((id) => {
    $(id).disabled = busy || recording || !haveNotes;
  });
  $('openBtn').disabled = $('recordBtn').disabled = busy || recording;
  $('stopRecordBtn').disabled = busy || !recording;
  $('transcribeBtn').disabled = $('detectTempoBtn').disabled = busy || recording || !projectId;
  $('saveTakeBtn').disabled = busy || recording || !lastTakeBlob;
  $('undoRhythmBtn').disabled = busy || recording || !canUndo;
  $('editControls').disabled = busy || recording || !selectedNote;
  $('targetBpm').disabled = $('transcriptionMode').disabled = busy || recording;
  $('stringSet').disabled = busy || recording;
  $('seekInput').disabled = !haveNotes || recording;
  $('playbackBpm').disabled = busy || !haveNotes || recording;
}
async function action(task) {
  if (busy) return;
  busy = true;
  refreshButtons();
  $('sheet').setAttribute('aria-busy', 'true');
  try {
    await task();
  } catch (error) {
    setStatus(
      error.message === 'Failed to fetch'
        ? 'Audio service unavailable. Start the app with start.bat.'
        : error.message,
      true,
    );
  } finally {
    busy = false;
    refreshButtons();
    $('sheet').removeAttribute('aria-busy');
  }
}
async function request(path, options = {}) {
  const response = await fetch(`${API_URL}${path}`, options);
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(
      typeof data.detail === 'string'
        ? data.detail
        : `Could not complete the request (${response.status}). Check the settings and try again.`,
    );
  }
  return response;
}
function audioPreview(element, blob) {
  if (element.src.startsWith('blob:')) URL.revokeObjectURL(element.src);
  element.src = URL.createObjectURL(blob);
}
function download(blob, filename) {
  const url = URL.createObjectURL(blob),
    link = document.createElement('a');
  link.href = url;
  link.download = filename;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
function invalidatePlayback() {
  audio.pause();
  audioDirty = true;
  waitingToPlay = false;
  playTime = pendingSeek = 0;
  $('playBtn').textContent = 'Play';
  updatePlayhead();
}
function applyData(data) {
  tracks = data.tracks;
  bpm = data.bpm;
  rhythm = data.rhythm || null;
  tabEvents = data.tablature || [];
  canUndo = !!data.can_undo_rhythm;
  selectedNote = null;
  $('targetBpm').value = Number(bpm.toFixed(1));
  $('playbackBpm').placeholder = String(Number(bpm.toFixed(1)));
  applyPlaybackTempo();
  $('playbackMix').options[1].disabled = !!rhythm || !!data.timing_changed;
  if ($('playbackMix').options[1].disabled) $('playbackMix').value = '1';
  invalidatePlayback();
  renderNotes();
  refreshButtons();
}
async function uploadFile(blob, filename) {
  setStatus('Opening audio…');
  audio.pause();
  const form = new FormData();
  form.append('file', blob, filename);
  const data = await (await request('/upload', { method: 'POST', body: form })).json();
  projectId = data.project_id;
  lastTakeBlob = blob;
  lastTakeFilename = filename;
  $('fileName').textContent = filename;
  audioPreview($('recordedAudio'), blob);
  await transcribe();
}
async function transcribe() {
  if (!projectId) return;
  setStatus('Transcribing attacks and pitches…');
  const mode =
    $('transcriptionMode').value === 'chords' && $('neuralChords').checked
      ? 'neural'
      : $('transcriptionMode').value;
  const params = new URLSearchParams({
    mode,
    noise_floor: $('noiseFloor').value,
    trim: true,
    tidy: $('automaticRhythm').checked,
    subdivisions: $('gridInput').value,
    beats_per_measure: $('fitBeats').value,
    recognize_patterns: $('recognizePatterns').checked,
    string_set: $('stringSet').value,
  });
  if (bpmOverride && $('targetBpm').value) params.set('target_bpm', $('targetBpm').value);
  const data = await (
    await request(`/transcribe/${projectId}?${params}`, { method: 'POST' })
  ).json();
  applyData(data);
  viewport.scrollLeft = 0;
  setStatus(
    notes().length
      ? `${events().length} attacks transcribed. ${rhythm?.pattern ? 'Repeated groups fitted together in each bar.' : rhythm ? 'Timing tidied to the BPM grid.' : 'Performed timing preserved.'} Click the sheet to choose a playback position.`
      : 'No clear notes detected. Try Light cleanup or a clearer recording.',
  );
}
$('openBtn').addEventListener('click', () => $('audioInput').click());
$('audioInput').addEventListener('change', () =>
  action(async () => {
    const file = $('audioInput').files[0];
    if (!file) return;
    lastTakeBlob = null;
    await uploadFile(file, file.name);
    $('audioInput').value = '';
  }),
);
$('transcribeBtn').addEventListener('click', () => action(transcribe));
$('stringSet').addEventListener('change', () => {
  if (projectId) action(transcribe);
  else
    setStatus(
      'String selection applies to your next take. Top means high e, B, G; bottom means low E, A, D.',
    );
});

// Live snapshots are bounded and sequential. They never accumulate uploaded projects.
async function livePreview() {
  if (
    !recording ||
    livePending ||
    (!$('liveNotes').checked && liveOrigin !== null) ||
    recorder.getDuration() < 0.3
  )
    return;
  livePending = true;
  const generation = liveGeneration,
    snapshot = recorder.snapshot(4);
  liveAbort = new AbortController();
  try {
    const form = new FormData();
    form.append('file', snapshot.blob, 'live.wav');
    const params = new URLSearchParams({
      mode: $('transcriptionMode').value,
      noise_floor: $('noiseFloor').value,
      string_set: $('stringSet').value,
      window_offset: snapshot.offset,
      playing_started: liveOrigin !== null,
    });
    const result = await (
      await request(`/live?${params}`, { method: 'POST', body: form, signal: liveAbort.signal })
    ).json();
    if (!recording || generation !== liveGeneration) return;
    if (liveOrigin === null && !result.playing_confirmed) return;
    const detected = result.notes.map((n) => ({
      ...n,
      start: n.start + snapshot.offset,
      end: n.end + snapshot.offset,
    }));
    if (liveOrigin === null && result.music_start !== null) {
      liveOrigin = snapshot.offset + result.music_start;
      recorder.confirmPlaying(liveOrigin);
    }
    if (liveOrigin === null) return;
    if (!$('liveNotes').checked) {
      setStatus('Guitar playing confirmed. Recording your take…');
      return;
    }
    const revisionStart = Math.max(0, snapshot.offset + result.analysis_start - liveOrigin);
    const revisionEnd = snapshot.offset + result.analysis_end - liveOrigin;
    // Replace the reliable overlap, including guesses whose pitch changed.
    // Keep older notes and boundary notes for the next snapshot to resolve.
    const outsideRevision = (n) => n.start < revisionStart - 0.045 || n.start > revisionEnd + 0.045;
    const current = notes().filter(outsideRevision);
    tabEvents = tabEvents.filter(outsideRevision);
    for (const n of detected) {
      const event = { ...n, start: Math.max(0, n.start - liveOrigin), end: n.end - liveOrigin };
      const existing = current.find(
        (old) => old.pitch === event.pitch && Math.abs(old.start - event.start) < 0.045,
      );
      if (existing) existing.end = event.end;
      else if (event.end > event.start) current.push(event);
    }
    tracks.Guitar = current.sort((a, b) => a.start - b.start || a.pitch - b.pitch);
    for (const event of result.tablature || []) {
      const mapped = {
        ...event,
        start: Math.max(0, event.start + snapshot.offset - liveOrigin),
        end: event.end + snapshot.offset - liveOrigin,
      };
      const index = tabEvents.findIndex((old) => Math.abs(old.start - mapped.start) < 0.045);
      if (index >= 0) tabEvents[index] = mapped;
      else tabEvents.push(mapped);
    }
    renderNotes();
    setStatus(
      'Recording · live notes are provisional. Stop when finished, or let silence end the take.',
    );
  } catch (error) {
    if (error.name !== 'AbortError' && recording)
      setStatus(
        'Live preview unavailable. Recording continues; the full take will be transcribed when stopped.',
        true,
      );
  } finally {
    if (generation === liveGeneration) livePending = false;
  }
}
$('recordBtn').addEventListener('click', () =>
  action(async () => {
    audio.pause();
    $('recordedAudio').pause();
    await recorder.start();
    recording = true;
    liveGeneration++;
    livePending = false;
    projectId = null;
    tracks = { Guitar: [] };
    tabEvents = [];
    rhythm = null;
    canUndo = false;
    selectedNote = null;
    liveOrigin = null;
    lastTakeBlob = null;
    invalidatePlayback();
    $('fileName').textContent = 'New recording';
    $('recordedAudio').pause();
    $('followPlayback').checked = true;
    $('followCursorBtn').textContent = 'Follow live';
    $('recordTimer').classList.remove('hidden');
    $('levelMeter').classList.remove('hidden');
    renderNotes();
    viewport.scrollLeft = 0;
    setStatus('Listening. Start playing; the note sheet begins with your first note.');
    liveTimer = setInterval(livePreview, 700);
    captureTimer = setInterval(() => {
      $('levelMeter').value = Math.min(1, recorder.currentRms * 8);
      $('recordTimer').textContent = timeLabel(
        liveOrigin === null ? 0 : recorder.getDuration() - liveOrigin,
      );
      const haveMusic = liveOrigin !== null;
      if (
        $('autoStop').checked &&
        haveMusic &&
        recorder.getDuration() - recorder.lastSoundTime > 3 &&
        !busy
      )
        action(stopRecording);
    }, 100);
  }),
);
async function stopRecording() {
  if (!recording) return;
  recording = false;
  liveGeneration++;
  liveAbort?.abort();
  $('followCursorBtn').textContent = 'Follow cursor';
  livePending = false;
  clearInterval(liveTimer);
  clearInterval(captureTimer);
  $('recordTimer').classList.add('hidden');
  $('levelMeter').classList.add('hidden');
  const captured = await recorder.stop(Math.max(0, (liveOrigin || 0) - 0.04));
  if (liveOrigin === null) {
    lastTakeBlob = null;
    tracks = { Guitar: [] };
    tabEvents = [];
    renderNotes();
    setStatus('No clear guitar phrase confirmed. Press Record and start playing.');
    return;
  }
  lastTakeBlob = captured;
  setStatus('Recording complete. Refining the full take…');
  await uploadFile(lastTakeBlob, 'recording.wav');
}
$('stopRecordBtn').addEventListener('click', () => action(stopRecording));
$('saveTakeBtn').addEventListener('click', () =>
  action(async () => {
    if (!lastTakeBlob) return;
    const form = new FormData();
    form.append('file', lastTakeBlob, lastTakeFilename);
    const data = await (await request('/recordings', { method: 'POST', body: form })).json();
    setStatus(`Recording saved to ${data.path}`);
  }),
);

// A single scrollable sheet owns both the visible note positions and playback.
function layout() {
  const contentDuration = Math.max(...notes().map((n) => n.end), 0);
  const liveDuration =
    recording && liveOrigin !== null ? recorder.getDuration() - liveOrigin + 0.4 : 0;
  const beatsPerBar = rhythm?.beats_per_measure || Number($('fitBeats').value) || 4;
  const duration = Math.max(contentDuration, liveDuration, (beatsPerBar * 60) / bpm);
  const pps = (Number($('zoomInput').value) * bpm) / 60;
  const min = Math.min(...notes().map((n) => n.pitch), 52) - 2,
    max = Math.max(...notes().map((n) => n.pitch), 59) + 2;
  return {
    duration,
    contentDuration,
    pps,
    left: 60,
    width: Math.max(viewport.clientWidth, Math.ceil(duration * pps + 90)),
    height: 360,
    min,
    max,
    beatsPerBar,
  };
}
function drawGraph() {
  const r = layout(),
    dpr = window.devicePixelRatio || 1;
  drawnDuration = r.duration;
  canvas.width = Math.ceil(r.width * dpr);
  canvas.height = r.height * dpr;
  canvas.style.width = `${r.width}px`;
  canvas.style.height = `${r.height}px`;
  $('graphContent').style.width = `${r.width}px`;
  $('graphContent').style.height = `${r.height}px`;
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.fillStyle = '#fff';
  ctx.fillRect(0, 0, r.width, r.height);
  ctx.font = '12px Segoe UI';
  function drawRuler() {
    for (let beat = 0; (beat * 60) / bpm <= r.duration; beat++) {
      const x = r.left + ((beat * 60) / bpm) * r.pps,
        bar = beat % r.beatsPerBar === 0;
      ctx.strokeStyle = bar ? '#b0b8c2' : '#edf0f3';
      ctx.lineWidth = bar ? 1.5 : 1;
      ctx.beginPath();
      ctx.moveTo(x, 30);
      ctx.lineTo(x, r.height - 20);
      ctx.stroke();
      ctx.fillStyle = '#626974';
      if (bar) ctx.fillText(`Bar ${beat / r.beatsPerBar + 1}`, x + 4, 20);
    }
    ctx.lineWidth = 1;
  }
  if (view === 'tab') {
    const names = ['e', 'B', 'G', 'D', 'A', 'E'];
    for (let string = 1; string <= 6; string++) {
      const y = 70 + (string - 1) * 47;
      ctx.fillStyle = '#20242a';
      ctx.fillText(names[string - 1], 20, y + 4);
      ctx.strokeStyle = '#aeb6c1';
      ctx.beginPath();
      ctx.moveTo(r.left - 12, y);
      ctx.lineTo(r.width - 15, y);
      ctx.stroke();
    }
    drawRuler();
    ctx.font = '600 14px Segoe UI';
    for (const event of tabEvents)
      for (const position of event.positions) {
        const x = r.left + event.start * r.pps,
          y = 70 + (position.string - 1) * 47;
        const end = r.left + event.end * r.pps;
        ctx.strokeStyle = '#8c9eb3';
        ctx.lineWidth = 3;
        ctx.beginPath();
        ctx.moveTo(x + 12, y + 12);
        ctx.lineTo(Math.max(x + 13, end - 2), y + 12);
        ctx.stroke();
        const label = String(position.fret),
          width = ctx.measureText(label).width + 8;
        ctx.fillStyle = '#fff';
        ctx.fillRect(x - 2, y - 12, width, 22);
        ctx.fillStyle =
          selectedNote &&
          selectedNote.pitch === position.pitch &&
          Math.abs(selectedNote.start - event.start) < 0.06
            ? '#a44b22'
            : '#20242a';
        ctx.fillText(label, x + 2, y + 5);
      }
  } else {
    const row = (r.height - 55) / (r.max - r.min + 1);
    ctx.font = '12px Segoe UI';
    for (let pitch = r.min; pitch <= r.max; pitch++) {
      const y = 35 + (r.max - pitch) * row;
      ctx.fillStyle = pitch % 12 === 0 ? '#edf0f4' : '#fff';
      ctx.fillRect(0, y, r.width, row);
      ctx.fillStyle = '#626974';
      ctx.fillText(noteName(pitch), 7, y + row * 0.7);
      ctx.strokeStyle = '#e4e8ed';
      ctx.beginPath();
      ctx.moveTo(r.left, y);
      ctx.lineTo(r.width, y);
      ctx.stroke();
    }
    drawRuler();
    for (const n of notes()) {
      const x = r.left + n.start * r.pps,
        y = 35 + (r.max - n.pitch) * row + 2;
      ctx.fillStyle = n === selectedNote ? '#a44b22' : '#244a79';
      ctx.fillRect(x + 1, y, Math.max(3, (n.end - n.start) * r.pps - 2), Math.max(5, row - 4));
    }
  }
  $('seekInput').max = Math.max(0.01, r.contentDuration);
  updatePlayhead();
  syncSheetScroll();
}
function syncSheetScroll() {
  const max = Math.max(0, viewport.scrollWidth - viewport.clientWidth);
  $('sheetScroll').max = max;
  $('sheetScroll').value = viewport.scrollLeft;
  $('sheetScroll').disabled = max === 0;
  $('scrollLeftBtn').disabled = viewport.scrollLeft <= 0;
  $('scrollRightBtn').disabled = viewport.scrollLeft >= max;
  $('followCursorBtn').setAttribute('aria-pressed', String($('followPlayback').checked));
}
function manualScroll(position) {
  $('followPlayback').checked = false;
  viewport.scrollLeft = position;
  syncSheetScroll();
}
viewport.addEventListener('scroll', syncSheetScroll);
$('sheetScroll').addEventListener('input', () => manualScroll(Number($('sheetScroll').value)));
$('scrollLeftBtn').addEventListener('click', () =>
  manualScroll(viewport.scrollLeft - viewport.clientWidth * 0.75),
);
$('scrollRightBtn').addEventListener('click', () =>
  manualScroll(viewport.scrollLeft + viewport.clientWidth * 0.75),
);
$('followCursorBtn').addEventListener('click', () => {
  $('followPlayback').checked = true;
  drawGraph();
  const r = layout();
  viewport.scrollLeft = Math.max(0, r.left + playTime * r.pps - viewport.clientWidth * 0.35);
  syncSheetScroll();
});
$('followPlayback').addEventListener('change', () => {
  followHead();
  syncSheetScroll();
});
function updatePlayhead() {
  const r = layout();
  $('playhead').style.left = `${r.left + Math.min(Math.max(0, playTime), r.duration) * r.pps}px`;
  $('seekInput').value = Math.min(playTime, r.contentDuration);
  const rate = recording ? 1 : audio.playbackRate;
  $('playbackTime').textContent =
    `${timeLabel(playTime / rate)} / ${timeLabel(r.contentDuration / rate)}`;
}
function followHead() {
  if (!$('followPlayback').checked || dragging) return;
  const r = layout(),
    x = r.left + playTime * r.pps;
  if (x > viewport.scrollLeft + viewport.clientWidth - 70 || x < viewport.scrollLeft + 20)
    viewport.scrollLeft = Math.max(0, x - viewport.clientWidth * 0.35);
}
function animate() {
  if (recording && liveOrigin !== null) {
    playTime = recorder.getDuration() - liveOrigin;
    if (playTime > drawnDuration - 0.15) drawGraph();
    updatePlayhead();
    followHead();
  } else if (!audio.paused && !dragging) {
    playTime = pendingSeek = audio.currentTime;
    updatePlayhead();
    followHead();
  }
  requestAnimationFrame(animate);
}
function selectNote(note) {
  selectedNote = note;
  if (note) {
    $('editPitch').value = note.pitch;
    $('editStart').value = note.start.toFixed(3);
    $('editEnd').value = note.end.toFixed(3);
    $('editVelocity').value = note.velocity;
  }
  $('noteSelect').value = String(notes().indexOf(note));
  refreshButtons();
  drawGraph();
}
function renderNotes() {
  $('noteCount').textContent = recording
    ? `${events().length} attacks · live preview`
    : `${events().length} attacks · ${notes().length} pitches`;
  $('noteSelect').replaceChildren();
  notes().forEach((n, index) => {
    const option = document.createElement('option');
    option.value = String(index);
    option.textContent = `${index + 1} · ${noteName(n.pitch)} · ${n.start.toFixed(2)}–${n.end.toFixed(2)} s`;
    $('noteSelect').appendChild(option);
  });
  updateRhythmSummary();
  drawGraph();
}
$('noteSelect').addEventListener('change', () =>
  selectNote(notes()[Number($('noteSelect').value)]),
);
for (const [id, mode] of [
  ['tabViewBtn', 'tab'],
  ['notesViewBtn', 'notes'],
])
  $(id).addEventListener('click', () => {
    view = mode;
    $('tabViewBtn').setAttribute('aria-pressed', String(view === 'tab'));
    $('notesViewBtn').setAttribute('aria-pressed', String(view === 'notes'));
    drawGraph();
  });
$('zoomInput').addEventListener('input', () => {
  drawGraph();
  followHead();
});
new ResizeObserver(drawGraph).observe(viewport);
viewport.addEventListener(
  'wheel',
  (event) => {
    if (!audio.paused || recording) {
      $('followPlayback').checked = false;
      syncSheetScroll();
    }
    if (
      !event.ctrlKey &&
      Math.abs(event.deltaX) < 1 &&
      viewport.scrollWidth > viewport.clientWidth
    ) {
      const before = viewport.scrollLeft;
      viewport.scrollLeft += event.deltaY;
      if (viewport.scrollLeft !== before) event.preventDefault();
    }
  },
  { passive: false },
);
function seek(time) {
  playTime = pendingSeek = Math.min(Math.max(0, time), layout().contentDuration);
  if (!audioDirty && Number.isFinite(audio.duration))
    audio.currentTime = Math.min(playTime, audio.duration);
  updatePlayhead();
}
function pointerTime(event) {
  const r = layout();
  return (event.clientX - canvas.getBoundingClientRect().left - r.left) / r.pps;
}
canvas.addEventListener('pointerdown', (event) => {
  if (recording || !notes().length) return;
  if ($('advanced').open && $('noteEditor').open) {
    const time = pointerTime(event),
      r = layout(),
      y = event.clientY - canvas.getBoundingClientRect().top;
    const pitch =
      view === 'notes'
        ? r.max - Math.floor((y - 35) / ((r.height - 55) / (r.max - r.min + 1)))
        : null;
    const position =
      view === 'tab'
        ? tabEvents
            .find((e) => time >= e.start - 0.03 && time <= e.end)
            ?.positions.find((p) => Math.abs(y - (70 + (p.string - 1) * 47)) < 20)
        : null;
    selectNote(
      notes().find(
        (n) => n.pitch === (pitch ?? position?.pitch) && time >= n.start - 0.03 && time <= n.end,
      ) || null,
    );
  }
  dragging = true;
  resumeAfterDrag = !audio.paused;
  audio.pause();
  canvas.setPointerCapture(event.pointerId);
  seek(pointerTime(event));
});
canvas.addEventListener('pointermove', (event) => {
  if (dragging) seek(pointerTime(event));
});
function finishDrag() {
  if (!dragging) return;
  dragging = false;
  if (resumeAfterDrag && !audioDirty) audio.play().catch(() => {});
}
canvas.addEventListener('pointerup', finishDrag);
canvas.addEventListener('pointercancel', finishDrag);
$('seekInput').addEventListener('input', () => seek(Number($('seekInput').value)));
$('stopPlaybackBtn').addEventListener('click', () => {
  audio.pause();
  seek(0);
  viewport.scrollLeft = 0;
});

function applyPlaybackTempo() {
  const input = $('playbackBpm');
  const tempo = input.value && input.checkValidity() ? Number(input.value) : bpm;
  audio.preservesPitch = true;
  audio.defaultPlaybackRate = audio.playbackRate = tempo / bpm;
  updatePlayhead();
}
$('playbackBpm').addEventListener('input', () => {
  if ($('playbackBpm').checkValidity()) applyPlaybackTempo();
});
$('playbackBpm').addEventListener('change', () => {
  if (!$('playbackBpm').checkValidity()) {
    $('playbackBpm').reportValidity();
    return;
  }
  applyPlaybackTempo();
  const tempo = Number($('playbackBpm').value) || bpm;
  setStatus(`Playback at ${tempo.toFixed(1)} BPM. Transcription stays at ${bpm.toFixed(1)} BPM.`);
});

async function generatePlayback(play = false) {
  setStatus('Creating playback from the note sheet…');
  const result = await request(`/playback/${projectId}?mix_ratio=${$('playbackMix').value}`, {
    method: 'POST',
  });
  const position = pendingSeek;
  waitingToPlay = play;
  audio.pause();
  audioPreview(audio, await result.blob());
  pendingSeek = position;
  audioDirty = false;
  setStatus('Playback ready. Click the sheet or use the playback slider to move through it.');
}
audio.addEventListener('loadedmetadata', () => {
  applyPlaybackTempo();
  audio.currentTime = Math.min(pendingSeek, audio.duration || 0);
  if (waitingToPlay) {
    waitingToPlay = false;
    audio.play().catch((error) => setStatus(error.message, true));
  }
});
audio.addEventListener('play', () => {
  $('playBtn').textContent = 'Pause';
});
audio.addEventListener('pause', () => {
  $('playBtn').textContent = 'Play';
});
audio.addEventListener('ended', () => {
  playTime = audio.currentTime;
  updatePlayhead();
  $('playBtn').textContent = 'Play';
});
$('playBtn').addEventListener('click', () =>
  action(async () => {
    if (!audio.paused) {
      audio.pause();
      return;
    }
    if (audioDirty) await generatePlayback(true);
    else {
      if (audio.ended) seek(0);
      await audio.play();
    }
  }),
);
$('playbackBtn').addEventListener('click', () => action(() => generatePlayback(false)));
$('playbackMix').addEventListener('change', invalidatePlayback);
$('exportMidiBtn').addEventListener('click', () =>
  action(async () => {
    download(
      await (await request(`/export/${projectId}`, { method: 'POST' })).blob(),
      'guitar.mid',
    );
    setStatus('MIDI downloaded.');
  }),
);
for (const [id, format] of [
  ['exportSheetBtn', 'musicxml'],
  ['exportTabBtn', 'tab'],
])
  $(id).addEventListener('click', () =>
    action(async () => {
      download(
        await (await request(`/sheet/${projectId}?format=${format}&download=true`)).blob(),
        format === 'tab' ? 'tablature.musicxml' : 'sheet.musicxml',
      );
      setStatus('MusicXML downloaded. Open it in a notation app.');
    }),
  );
async function fetchTracks() {
  applyData(await (await request(`/tracks/${projectId}`)).json());
}
$('targetBpm').addEventListener('change', () =>
  action(async () => {
    if (!$('targetBpm').value || !$('targetBpm').checkValidity())
      throw new Error('Choose a target tempo from 20 to 300 BPM.');
    bpmOverride = true;
    if (projectId && notes().length) {
      const data = await (
        await request(`/tempo/${projectId}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ bpm: Number($('targetBpm').value) }),
        })
      ).json();
      applyData(data);
      setStatus(
        `Playback tempo changed to ${bpm.toFixed(1)} BPM. Note positions within bars are preserved.`,
      );
    } else {
      bpm = Number($('targetBpm').value);
      drawGraph();
    }
  }),
);
$('detectTempoBtn').addEventListener('click', () =>
  action(async () => {
    const data = await (await request(`/tempo/${projectId}`)).json();
    bpmOverride = false;
    if (notes().length)
      await request(`/tempo/${projectId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ bpm: data.bpm }),
      });
    await fetchTracks();
    setStatus(
      `Estimated tempo: ${data.bpm.toFixed(1)} BPM. Adjust it if the beat interpretation is wrong.`,
    );
  }),
);
$('applyTimingBtn').addEventListener('click', () =>
  action(async () => {
    await request(`/timing/${projectId}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        bpm,
        automatic: $('automaticRhythm').checked,
        subdivisions: Number($('gridInput').value),
        beats_per_measure: Number($('fitBeats').value),
        recognize_patterns: $('recognizePatterns').checked,
      }),
    });
    await fetchTracks();
    setStatus(rhythm ? 'Timing tidied to the selected grid.' : 'Performed timing restored.');
  }),
);
function updateRhythmSummary() {
  const text = $('fitPattern').value.trim(),
    perBar = text ? text.split(',').length : Number($('fitNotes').value);
  $('fitNotes').disabled = !!text;
  $('rhythmSummary').textContent =
    `${Number($('fitMeasures').value)} bars × ${perBar} attacks = ${Number($('fitMeasures').value) * perBar}. The sheet has ${events().length} attacks.`;
}
for (const id of ['fitMeasures', 'fitNotes', 'fitPattern'])
  $(id).addEventListener('input', updateRhythmSummary);
$('fitRhythmBtn').addEventListener('click', () =>
  action(async () => {
    const text = $('fitPattern').value.trim();
    const settings = {
      bpm,
      measures: Number($('fitMeasures').value),
      beats_per_measure: Number($('fitBeats').value),
      notes_per_measure: Number($('fitNotes').value),
      articulation: $('fitArticulation').value,
      pattern: text ? text.split(',').map((v) => Number(v.trim())) : null,
    };
    await request(`/rhythm/${projectId}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(settings),
    });
    await fetchTracks();
    setStatus('Attacks assigned to the intended rhythm.');
  }),
);
$('undoRhythmBtn').addEventListener('click', () =>
  action(async () => {
    await request(`/rhythm/${projectId}/undo`, { method: 'POST' });
    await fetchTracks();
    setStatus('Previous timing restored.');
  }),
);
$('updateNoteBtn').addEventListener('click', () =>
  action(async () => {
    if (!selectedNote) return;
    if (
      ['editPitch', 'editStart', 'editEnd', 'editVelocity'].some(
        (id) => !$(id).value || !$(id).checkValidity(),
      )
    )
      throw new Error('Enter valid pitch, timing, and loudness values.');
    const start = Number($('editStart').value),
      end = Number($('editEnd').value);
    if (end <= start) throw new Error('The note end must be after its start.');
    await request(`/edit/${projectId}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        track: 'Guitar',
        old_pitch: selectedNote.pitch,
        old_start: selectedNote.start,
        new_pitch: Number($('editPitch').value),
        new_start: start,
        new_end: end,
        new_velocity: Number($('editVelocity').value),
      }),
    });
    await fetchTracks();
    setStatus('Note updated. Playback will use the updated sheet.');
  }),
);
window.addEventListener('beforeunload', () => {
  liveAbort?.abort();
  if (recording) recorder.stop();
});
renderNotes();
refreshButtons();
requestAnimationFrame(animate);
