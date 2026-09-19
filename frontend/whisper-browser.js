import { EndOfSpeechDetector, calculatePcm16Rms } from "/static/voice.js?v=20260919-1";

const SAMPLE_RATE = 16000;
const MAXIMUM_AUDIO_SECONDS = 60;
const MODEL_LOAD_TIMEOUT_MS = 180000;
const TRANSCRIPTION_TIMEOUT_MS = 90000;

/**
 * Convierte muestras Float32 a PCM16 para reutilizar la detección local de silencio.
 * @param {Float32Array} samples Muestras mono normalizadas entre menos uno y uno.
 * @returns {ArrayBuffer} Muestras PCM16 little-endian equivalentes.
 */
function float32ToPcm16(samples) {
    const output = new Int16Array(samples.length);
    for (let index = 0; index < samples.length; index += 1) {
        const sample = Math.max(-1, Math.min(1, samples[index]));
        output[index] = sample < 0 ? sample * 32768 : sample * 32767;
    }
    return output.buffer;
}

/**
 * Reduce o conserva audio mono para entregarlo al modelo Whisper a 16 kHz.
 * @param {Float32Array} samples Muestras originales del navegador.
 * @param {number} sourceRate Frecuencia de muestreo del AudioContext.
 * @returns {Float32Array} Audio mono remuestreado a 16 kHz.
 */
function resampleToWhisperRate(samples, sourceRate) {
    if (sourceRate === SAMPLE_RATE) return new Float32Array(samples);
    const ratio = sourceRate / SAMPLE_RATE;
    const targetLength = Math.floor(samples.length / ratio);
    const target = new Float32Array(targetLength);
    for (let index = 0; index < targetLength; index += 1) {
        const sourceIndex = index * ratio;
        const before = Math.floor(sourceIndex);
        const after = Math.min(before + 1, samples.length - 1);
        const fraction = sourceIndex - before;
        target[index] = samples[before] * (1 - fraction) + samples[after] * fraction;
    }
    return target;
}

/**
 * Une los fragmentos de un turno en un único audio continuo para Whisper.
 * @param {Float32Array[]} chunks Fragmentos remuestreados del mismo turno.
 * @param {number} totalLength Cantidad total de muestras esperadas.
 * @returns {Float32Array} Audio concatenado en orden cronológico.
 */
function joinAudioChunks(chunks, totalLength) {
    const audio = new Float32Array(totalLength);
    let offset = 0;
    for (const chunk of chunks) {
        audio.set(chunk, offset);
        offset += chunk.length;
    }
    return audio;
}

/**
 * Encapsula Whisper local en un Worker y es dueño exclusivo del micrófono del turno.
 *
 * El texto final se devuelve al frontend, que lo envía al backend mediante
 * ``voice.text``. No envía PCM al WebSocket ni conoce reglas del pedido.
 */
export class BrowserWhisperInput {
    /**
     * Inicializa la captura local y los callbacks visuales de Whisper.
     * @param {Object} options Configuración recibida desde el backend.
     * @param {string} [options.model="onnx-community/whisper-tiny"] Modelo publicado por Hugging Face.
     * @param {"auto"|"webgpu"|"wasm"} [options.device="auto"] Aceleración solicitada.
     * @param {Function} options.onProgress Informa carga, disponibilidad y transcripción local.
     * @param {Function} options.onError Informa fallas de micrófono, Worker o modelo.
     * @param {Function} options.onSpeechEnded Solicita cerrar la captura al detectar silencio.
     */
    constructor({
        model = "onnx-community/whisper-tiny",
        device = "auto",
        onProgress,
        onError,
        onSpeechEnded,
    }) {
        this.model = model;
        this.device = device;
        this.onProgress = onProgress;
        this.onError = onError;
        this.onSpeechEnded = onSpeechEnded;
        this.detector = new EndOfSpeechDetector();
        this.worker = null;
        this.stream = null;
        this.context = null;
        this.source = null;
        this.processor = null;
        this.audioChunks = [];
        this.audioLength = 0;
        this.recording = false;
        this.ready = false;
        this.generation = 0;
        this.pendingLoad = null;
        this.pendingTranscription = null;
    }

    /**
     * Descarga o recupera el modelo y solicita permiso del micrófono sin grabar todavía.
     * @returns {Promise<void>} Se resuelve cuando Worker y micrófono están listos.
     * @throws {Error} Si no se puede cargar Whisper o abrir el micrófono.
     * @effects Puede descargar y guardar el modelo en la caché del navegador.
     */
    async prepare() {
        const generation = ++this.generation;
        await this.ensureWorker();
        if (generation !== this.generation) throw new Error("La captura fue cancelada.");
        const stream = await navigator.mediaDevices.getUserMedia({
            audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true },
        });
        if (generation !== this.generation) {
            stream.getTracks().forEach(track => track.stop());
            throw new Error("La captura fue cancelada.");
        }
        this.stream = stream;
        this.context = new AudioContext();
        await this.context.resume();
        this.source = this.context.createMediaStreamSource(stream);
        this.processor = this.context.createScriptProcessor(4096, 1, 1);
        this.processor.onaudioprocess = event => this.capture(event);
    }

    /**
     * Conecta el flujo local después de preparar modelo y micrófono.
     * @returns {void}
     * @effects Reinicia el audio acumulado y la detección de silencio.
     */
    start() {
        if (!this.source || !this.processor || !this.context) {
            throw new Error("Whisper local todavía no está preparado.");
        }
        this.detector.reset();
        this.audioChunks = [];
        this.audioLength = 0;
        this.recording = true;
        this.source.connect(this.processor);
        this.processor.connect(this.context.destination);
    }

    /**
     * Cierra la captura, transcribe localmente el turno y conserva el modelo para reutilizarlo.
     * @returns {Promise<string>} Texto final reconocido por Whisper.
     * @throws {Error} Si no hubo voz o Whisper no devuelve texto a tiempo.
     * @effects Detiene el micrófono del turno, pero no termina el Worker ni elimina la caché.
     */
    async finish() {
        this.stopCapture();
        const audio = joinAudioChunks(this.audioChunks, this.audioLength);
        this.audioChunks = [];
        this.audioLength = 0;
        if (audio.length === 0) throw new Error("No se detectó audio. Podés volver a hablar o escribir.");
        this.onProgress("Whisper local está transcribiendo…");
        return this.requestTranscription(audio);
    }

    /**
     * Libera el micrófono, cancela esperas y termina el Worker local si existe.
     * @returns {void}
     * @effects Descarta un turno pendiente sin enviar texto ni audio al backend.
     */
    dispose() {
        this.generation += 1;
        this.stopCapture();
        this.audioChunks = [];
        this.audioLength = 0;
        this.pendingLoad?.reject(new Error("La carga de Whisper fue cancelada."));
        this.pendingTranscription?.reject(new Error("La transcripción fue cancelada."));
        this.pendingLoad = null;
        this.pendingTranscription = null;
        this.worker?.terminate();
        this.worker = null;
        this.ready = false;
    }

    /**
     * Crea el Worker y espera una vez la carga del modelo configurado.
     * @returns {Promise<void>} Se resuelve con el modelo listo para transcribir.
     * @throws {Error} Si el Worker no está disponible o el modelo no carga a tiempo.
     */
    async ensureWorker() {
        if (this.ready) return;
        if (this.pendingLoad) return this.pendingLoad.promise;
        if (!("Worker" in window)) throw new Error("Este navegador no admite Workers para Whisper local.");
        this.worker = new Worker("/static/whisper-browser-worker.js?v=20260919-1", { type: "module" });
        this.worker.onmessage = event => this.handleWorkerMessage(event.data);
        this.worker.onerror = event => this.handleWorkerFailure(event.message || "El Worker de Whisper falló.");
        let timeout;
        const promise = new Promise((resolve, reject) => {
            timeout = setTimeout(
                () => reject(new Error("Whisper local tardó demasiado en cargar el modelo.")),
                MODEL_LOAD_TIMEOUT_MS,
            );
            this.pendingLoad = { resolve, reject, timeout, promise: null };
        });
        this.pendingLoad.promise = promise;
        this.onProgress("Cargando Whisper local… la primera vez puede demorar.");
        this.worker.postMessage({ type: "load", model: this.model, device: this.device });
        try {
            await promise;
        } finally {
            clearTimeout(timeout);
        }
    }

    /**
     * Registra un bloque del micrófono y detecta el silencio final sin subir audio.
     * @param {AudioProcessingEvent} event Bloque producido por ScriptProcessorNode.
     * @returns {void}
     * @effects Acumula hasta sesenta segundos de audio local del turno actual.
     */
    capture(event) {
        const output = event.outputBuffer.getChannelData(0);
        output.fill(0);
        if (!this.recording) return;
        const samples = resampleToWhisperRate(
            event.inputBuffer.getChannelData(0),
            this.context.sampleRate,
        );
        if (this.audioLength + samples.length > SAMPLE_RATE * MAXIMUM_AUDIO_SECONDS) {
            this.onError(new Error("El turno de voz supera los 60 segundos."));
            return;
        }
        this.audioChunks.push(samples);
        this.audioLength += samples.length;
        const durationMs = samples.length / SAMPLE_RATE * 1000;
        if (this.detector.observe(calculatePcm16Rms(float32ToPcm16(samples)), durationMs)) {
            this.onSpeechEnded();
        }
    }

    /**
     * Envía un único audio final al Worker y espera la transcripción local.
     * @param {Float32Array} audio Audio mono a 16 kHz.
     * @returns {Promise<string>} Texto final limpio.
     * @throws {Error} Si Whisper no responde o devuelve una transcripción vacía.
     */
    requestTranscription(audio) {
        if (!this.worker || !this.ready) {
            throw new Error("Whisper local no está listo para transcribir.");
        }
        let timeout;
        const promise = new Promise((resolve, reject) => {
            timeout = setTimeout(
                () => reject(new Error("Whisper local tardó demasiado en transcribir.")),
                TRANSCRIPTION_TIMEOUT_MS,
            );
            this.pendingTranscription = { resolve, reject, timeout };
        });
        this.worker.postMessage({
            type: "transcribe",
            audio,
            language: "spanish",
            model: this.model,
            device: this.device,
        }, [audio.buffer]);
        return promise.finally(() => clearTimeout(timeout));
    }

    /**
     * Procesa los estados del Worker sin exponer detalles de IA al pedido.
     * @param {Object} message Evento publicado por whisper-browser-worker.js.
     * @returns {void}
     * @effects Resuelve la carga o la transcripción pendiente cuando corresponde.
     */
    handleWorkerMessage(message) {
        if (message.type === "progress") {
            this.onProgress(message.message);
            return;
        }
        if (message.type === "ready") {
            this.ready = true;
            const pending = this.pendingLoad;
            this.pendingLoad = null;
            pending?.resolve();
            return;
        }
        if (message.type === "complete") {
            const text = (message.text || "").trim();
            const pending = this.pendingTranscription;
            this.pendingTranscription = null;
            if (!text) {
                pending?.reject(new Error("Whisper local no reconoció voz. Podés volver a hablar o escribir."));
            } else {
                pending?.resolve(text);
            }
            return;
        }
        if (message.type === "error") {
            this.handleWorkerFailure(message.message || "Whisper local no pudo transcribir.");
        }
    }

    /**
     * Rechaza una carga o transcripción pendiente ante un error del Worker.
     * @param {string} message Detalle técnico seguro para mostrar a la persona.
     * @returns {void}
     * @effects Conserva la posibilidad de volver a abrir Whisper en otro turno.
     */
    handleWorkerFailure(message) {
        const error = new Error(message);
        const load = this.pendingLoad;
        const transcription = this.pendingTranscription;
        this.pendingLoad = null;
        this.pendingTranscription = null;
        load?.reject(error);
        transcription?.reject(error);
    }

    /**
     * Desconecta y libera solo los recursos del micrófono del turno actual.
     * @returns {void}
     * @effects Mantiene el Worker y el modelo vivo para el próximo turno.
     */
    stopCapture() {
        this.recording = false;
        this.processor?.disconnect();
        this.source?.disconnect();
        this.stream?.getTracks().forEach(track => track.stop());
        this.context?.close().catch(() => {});
        this.processor = null;
        this.source = null;
        this.stream = null;
        this.context = null;
    }
}
