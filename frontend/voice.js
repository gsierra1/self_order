const DEFAULT_SPEECH_THRESHOLD = 0.012;
const DEFAULT_MINIMUM_SPEECH_MS = 200;
const DEFAULT_SILENCE_MS = 1400;

/**
 * Calcula la energía RMS de un bloque PCM16 mono normalizado.
 * @param {ArrayBuffer} buffer Muestras PCM16 little-endian capturadas a 16 kHz.
 * @returns {number} Energía entre cero y uno; cero cuando no hay muestras.
 */
export function calculatePcm16Rms(buffer) {
    const view = new DataView(buffer);
    const sampleCount = Math.floor(view.byteLength / 2);
    if (sampleCount === 0) return 0;
    let squareSum = 0;
    for (let offset = 0; offset < sampleCount * 2; offset += 2) {
        const normalized = view.getInt16(offset, true) / 32768;
        squareSum += normalized * normalized;
    }
    return Math.sqrt(squareSum / sampleCount);
}

/** Detecta fin de habla a partir de energía, sin interpretar el contenido. */
export class EndOfSpeechDetector {
    /**
     * Configura los umbrales de voz y silencio del turno.
     * @param {Object} [options={}] Valores opcionales para pruebas o calibración.
     * @param {number} [options.speechThreshold=0.012] Energía mínima considerada voz.
     * @param {number} [options.minimumSpeechMs=200] Voz necesaria antes de aceptar silencio.
     * @param {number} [options.silenceMs=1400] Silencio continuo que finaliza el turno.
     */
    constructor(options = {}) {
        this.speechThreshold = options.speechThreshold ?? DEFAULT_SPEECH_THRESHOLD;
        this.minimumSpeechMs = options.minimumSpeechMs ?? DEFAULT_MINIMUM_SPEECH_MS;
        this.silenceMs = options.silenceMs ?? DEFAULT_SILENCE_MS;
        this.reset();
    }

    /**
     * Reinicia la detección para un turno de voz nuevo.
     * @returns {void}
     * @effects Descarta las duraciones acumuladas y habilita un nuevo cierre.
     */
    reset() {
        this.activeSpeechMs = 0;
        this.silentMs = 0;
        this.speechDetected = false;
        this.ended = false;
    }

    /**
     * Incorpora la energía de un bloque y decide si terminó el habla.
     * @param {number} rms Energía RMS normalizada del bloque.
     * @param {number} durationMs Duración representada por el bloque.
     * @returns {boolean} `true` una sola vez al alcanzar el silencio configurado.
     * @throws {TypeError} Si la energía o la duración no son números válidos.
     */
    observe(rms, durationMs) {
        if (!Number.isFinite(rms) || !Number.isFinite(durationMs) || durationMs <= 0) {
            throw new TypeError("El bloque de actividad de voz no es válido.");
        }
        if (this.ended) return false;
        if (rms >= this.speechThreshold) {
            this.activeSpeechMs += durationMs;
            this.silentMs = 0;
            if (this.activeSpeechMs >= this.minimumSpeechMs) this.speechDetected = true;
            return false;
        }
        if (!this.speechDetected) {
            this.activeSpeechMs = 0;
            return false;
        }
        this.silentMs += durationMs;
        if (this.silentMs < this.silenceMs) return false;
        this.ended = true;
        return true;
    }
}

/** Recursos del micrófono y envío de audio; no interpreta ni modifica pedidos. */
export class VoiceInput {
    /**
     * Conserva callbacks para transmitir audio e informar fallas locales.
     * @param {Function} sendAudio Envía un ArrayBuffer al WebSocket.
     * @param {Function} fail Informa una falla y cancela el turno.
     * @param {Function} speechEnded Solicita finalizar después de detectar silencio.
     * @param {Object} [detectorOptions={}] Umbrales opcionales del detector.
     */
    constructor(sendAudio, fail, speechEnded, detectorOptions = {}) {
        this.sendAudio = sendAudio;
        this.fail = fail;
        this.speechEnded = speechEnded;
        this.detector = new EndOfSpeechDetector(detectorOptions);
        this.stream = null;
        this.context = null;
        this.node = null;
        this.source = null;
        this.generation = 0;
    }

    /**
     * Solicita permiso y prepara el worklet sin empezar a enviar audio.
     * @returns {Promise<void>} Se resuelve cuando puede iniciarse la captura.
     */
    async prepare() {
        const generation = ++this.generation;
        const stream = await navigator.mediaDevices.getUserMedia({
            audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true },
        });
        if (generation !== this.generation) {
            stream.getTracks().forEach(track => track.stop());
            throw new Error("La captura fue cancelada.");
        }
        this.stream = stream;
        this.context = new AudioContext({ sampleRate: 16000 });
        if (this.context.sampleRate !== 16000) throw new Error("El navegador no admite audio a 16 kHz.");
        await this.context.audioWorklet.addModule("/static/pcm-worklet.js");
        if (generation !== this.generation) throw new Error("La captura fue cancelada.");
        await this.context.resume();
        this.source = this.context.createMediaStreamSource(stream);
        this.node = new AudioWorkletNode(this.context, "pcm-capture");
        this.node.port.onmessage = event => {
            if (event.data instanceof ArrayBuffer) {
                try {
                    this.sendAudio(event.data);
                    const durationMs = event.data.byteLength / 2 / 16000 * 1000;
                    if (this.detector.observe(calculatePcm16Rms(event.data), durationMs)) {
                        this.speechEnded();
                    }
                }
                catch (error) { this.fail(error); }
            } else if (event.data?.stopped) {
                this.onFlushed?.();
            }
        };
    }

    /**
     * Conecta el micrófono solo después de que el backend informa `voice.ready`.
     * @returns {void}
     * @effects Reinicia el detector y comienza a producir bloques PCM.
     */
    start() {
        this.detector.reset();
        this.source.connect(this.node);
        this.node.connect(this.context.destination);
    }

    /**
     * Envía el último bloque antes de liberar los recursos del micrófono.
     * @returns {Promise<void>} Se resuelve tras vaciar el audio pendiente.
     */
    async finish() {
        if (!this.node) return;
        try {
            await new Promise((resolve, reject) => {
                const timer = setTimeout(() => reject(new Error("No se pudo finalizar la captura.")), 2000);
                this.onFlushed = () => { clearTimeout(timer); resolve(); };
                this.node.port.postMessage({ stop: true });
            });
        } finally {
            this.dispose();
        }
    }

    /**
     * Cancela la captura y libera micrófono, conexiones y contexto de audio.
     * @returns {void}
     * @effects Invalida preparaciones anteriores y detiene las pistas físicas.
     */
    dispose() {
        this.generation++;
        if (this.node) { this.node.port.onmessage = null; this.node.disconnect(); }
        this.source?.disconnect();
        this.stream?.getTracks().forEach(track => track.stop());
        this.context?.close().catch(() => {});
        this.onFlushed = null;
        this.node = this.source = this.stream = this.context = null;
    }
}

/**
 * Lee únicamente el texto final del asistente con una voz española disponible.
 * @param {string} text Respuesta validada por el flujo conversacional.
 * @param {Function} onError Informa problemas de reproducción sin afectar el pedido.
 */
export function speak(text, onError) {
    if (!("speechSynthesis" in window)) {
        onError("Este navegador no dispone de lectura por voz.");
        return;
    }
    speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(prepareSpeechText(text));
    const voices = speechSynthesis.getVoices();
    utterance.voice = voices.find(voice => voice.lang === "es-AR")
        || voices.find(voice => voice.lang.startsWith("es")) || null;
    utterance.lang = utterance.voice?.lang || "es-AR";
    utterance.onerror = event => {
        if (!["canceled", "interrupted"].includes(event.error)) {
            onError("No se pudo reproducir la voz. La respuesta está escrita en pantalla.");
        }
    };
    speechSynthesis.speak(utterance);
}

/**
 * Adapta importes y marcas de formato para que la voz del navegador los lea naturalmente.
 * @param {string} text Texto visible generado por el asistente.
 * @returns {string} Texto preparado para síntesis, con importes enteros continuos y sin Markdown.
 */
function prepareSpeechText(text) {
    return text
        .replace(
            /\$\s*(\d+(?:\.\d{3})*)\s+pesos argentinos/gi,
            (_, amount) => `${amount.replace(/\./g, "")} pesos argentinos`
        )
        .replace(/\b(\d{1,3}(?:\.\d{3})+)\b/g, (_, amount) => amount.replace(/\./g, ""))
        .replace(/\betc\.?\b/gi, "etcétera")
        .replace(/[|*_`]/g, " ")
        .replace(/\s{2,}/g, " ")
        .trim();
}
