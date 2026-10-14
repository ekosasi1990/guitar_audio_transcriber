const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const scope = { window: {}, Blob, Float32Array, DataView, ArrayBuffer };
vm.createContext(scope);
vm.runInContext(fs.readFileSync('src/frontend/js/recorder.js', 'utf8'), scope);
const recorder = new scope.window.MicRecorder();
recorder.sampleRate = 1000;
recorder.chunks = [new Float32Array(1000).fill(0.8), new Float32Array(1000).fill(0.004)];
recorder.totalSamples = 2000;
recorder.peakRms = 0.8;
recorder.confirmPlaying(1);
assert.ok(recorder.playingRms < 0.005, 'Lead-in noise must not calibrate musical loudness');
assert.ok(recorder.silenceThreshold() < 0.004, 'Quiet music must count as sound');
assert.equal(recorder.lastSoundTime, 2);
(async () => {
  const snapshot = recorder.snapshot(0.5);
  assert.equal(snapshot.offset, 1.5);
  const header = new DataView(await snapshot.blob.arrayBuffer());
  assert.equal(header.getUint32(40, true), 1000);
  const take = new DataView(await recorder.stop(1).arrayBuffer());
  assert.equal(take.getUint32(40, true), 2000);
  assert.ok(Math.abs(take.getInt16(44, true) / 32767 - 0.004) < 0.0001);
  console.log('Recorder: quiet-take silence calibration, snapshots, and lead-in trimming passed.');
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
