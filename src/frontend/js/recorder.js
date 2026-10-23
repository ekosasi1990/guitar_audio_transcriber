const CAPTURE_WORKLET = `
class PcmCapture extends AudioWorkletProcessor {
  process(inputs) {
    const ch = inputs[0];
    if (ch && ch[0]) this.port.postMessage(ch[0].slice(0));
    return true;
  }
}
registerProcessor('gat-pcm-capture', PcmCapture);
`;

class MicRecorder {
  constructor() {
    this.audioCtx = null;
    this.source = null;
    this.analyser = null;
    this.worklet = null;
    this.stream = null;
    this.chunks = [];
    this.sampleRate = 44100;
    this.isRecording = false;
    this.startTime = 0;
    this.totalSamples = 0;
    this.currentRms = 0;
    this.peakRms = 0;
    this.lastSoundTime = 0;
    this.playingRms = null;
  }

  async start() {
    this.chunks = [];
    this.totalSamples = 0;
    this.currentRms = this.peakRms = this.lastSoundTime = 0;
    this.playingRms = null;
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      throw new Error('Microphone access is not available in this context');
    }
    this.stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        echoCancellation: false,
        noiseSuppression: false,
        autoGainControl: false,
      },
    });

    this.audioCtx = new (window.AudioContext || window.webkitAudioContext)({
      sampleRate: this.sampleRate,
    });
    this.sampleRate = this.audioCtx.sampleRate;
    if (this.audioCtx.state === 'suspended') await this.audioCtx.resume();
    const workletUrl = URL.createObjectURL(
      new Blob([CAPTURE_WORKLET], { type: 'application/javascript' }),
    );
    try {
      await this.audioCtx.audioWorklet.addModule(workletUrl);
    } catch (error) {
      this.stop();
      throw error;
    } finally {
      URL.revokeObjectURL(workletUrl);
    }

    this.source = this.audioCtx.createMediaStreamSource(this.stream);
    this.analyser = this.audioCtx.createAnalyser();
    this.analyser.fftSize = 256;
    this.worklet = new AudioWorkletNode(this.audioCtx, 'gat-pcm-capture');
    this.worklet.port.onmessage = (event) => {
      this.chunks.push(event.data);
      this.totalSamples += event.data.length;
      const rms = Math.sqrt(
        event.data.reduce((sum, value) => sum + value * value, 0) / event.data.length,
      );
      this.currentRms = this.currentRms * 0.8 + rms * 0.2;
      this.peakRms = Math.max(this.peakRms, this.currentRms);
      if (this.currentRms > this.silenceThreshold())
        this.lastSoundTime = this.totalSamples / this.sampleRate;
    };
    // AudioWorkletNode only runs when connected to destination; a muted gain
    // node keeps it silent instead of playing the mic back.
    const mute = this.audioCtx.createGain();
    mute.gain.value = 0;

    this.source.connect(this.analyser);
    this.source.connect(this.worklet);
    this.worklet.connect(mute);
    mute.connect(this.audioCtx.destination);

    this.isRecording = true;
    this.startTime = Date.now();
  }

  getLevel() {
    if (!this.analyser) return 0;
    const data = new Uint8Array(this.analyser.frequencyBinCount);
    this.analyser.getByteFrequencyData(data);
    let sum = 0;
    for (let i = 0; i < data.length; i++) sum += data[i];
    return sum / data.length / 255;
  }

  getDuration() {
    return this.totalSamples / this.sampleRate;
  }

  silenceThreshold() {
    return this.playingRms === null
      ? Math.max(0.008, this.peakRms * 0.06)
      : Math.max(0.0008, this.playingRms * 0.08);
  }

  confirmPlaying(fromSeconds) {
    // Calibrate silence from the musical phrase, not a loud setup noise.
    const levels = [];
    let offset = 0;
    for (const chunk of this.chunks) {
      const end = offset + chunk.length;
      if (end > fromSeconds * this.sampleRate) {
        const body = chunk.subarray(
          Math.max(0, Math.floor(fromSeconds * this.sampleRate) - offset),
        );
        levels.push(Math.sqrt(body.reduce((sum, value) => sum + value * value, 0) / body.length));
      }
      offset = end;
    }
    levels.sort((a, b) => a - b);
    this.playingRms = levels.length
      ? levels[Math.floor((levels.length - 1) * 0.95)]
      : this.currentRms;
    this.lastSoundTime = this.getDuration();
  }

  snapshot(seconds = 4) {
    const count = Math.min(this.totalSamples, Math.floor(seconds * this.sampleRate));
    const samples = new Float32Array(count);
    let remaining = count;
    for (let i = this.chunks.length - 1; i >= 0 && remaining > 0; i--) {
      const chunk = this.chunks[i];
      const length = Math.min(remaining, chunk.length);
      remaining -= length;
      samples.set(chunk.subarray(chunk.length - length), remaining);
    }
    return {
      blob: this._encodeWav(samples, this.sampleRate, 1),
      offset: (this.totalSamples - count) / this.sampleRate,
    };
  }

  stop(fromSeconds = 0) {
    this.isRecording = false;
    if (this.worklet) {
      this.worklet.port.onmessage = null;
      this.worklet.disconnect();
      this.worklet = null;
    }
    if (this.source) {
      this.source.disconnect();
      this.source = null;
      this.analyser = null;
    }
    if (this.stream) {
      this.stream.getTracks().forEach((track) => track.stop());
      this.stream = null;
    }
    if (this.audioCtx && this.audioCtx.state !== 'closed') {
      this.audioCtx.close().catch(() => {});
      this.audioCtx = null;
    }

    // Concatenate all chunks
    const totalLength = this.chunks.reduce((sum, chunk) => sum + chunk.length, 0);
    const samples = new Float32Array(totalLength);
    let offset = 0;
    for (const chunk of this.chunks) {
      samples.set(chunk, offset);
      offset += chunk.length;
    }

    const start = Math.min(samples.length, Math.max(0, Math.floor(fromSeconds * this.sampleRate)));
    return this._encodeWav(samples.subarray(start), this.sampleRate, 1);
  }

  _encodeWav(samples, sampleRate, numChannels) {
    const buffer = new ArrayBuffer(44 + samples.length * 2);
    const view = new DataView(buffer);

    const writeString = (offset, string) => {
      for (let i = 0; i < string.length; i++) {
        view.setUint8(offset + i, string.charCodeAt(i));
      }
    };

    writeString(0, 'RIFF');
    view.setUint32(4, 36 + samples.length * 2, true);
    writeString(8, 'WAVE');
    writeString(12, 'fmt ');
    view.setUint32(16, 16, true);
    view.setUint16(20, 1, true); // PCM
    view.setUint16(22, numChannels, true);
    view.setUint32(24, sampleRate, true);
    view.setUint32(28, sampleRate * numChannels * 2, true);
    view.setUint16(32, numChannels * 2, true);
    view.setUint16(34, 16, true); // 16-bit
    writeString(36, 'data');
    view.setUint32(40, samples.length * 2, true);

    let index = 44;
    for (let i = 0; i < samples.length; i++) {
      const s = Math.max(-1, Math.min(1, samples[i]));
      view.setInt16(index, s < 0 ? s * 0x8000 : s * 0x7fff, true);
      index += 2;
    }

    return new Blob([view], { type: 'audio/wav' });
  }
}

window.MicRecorder = MicRecorder;
