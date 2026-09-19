const TRANSFORMERS_MODULE_URL = "https://cdn.jsdelivr.net/npm/@huggingface/transformers@4.2.0/+esm";

let pipelineFactory = null;
let transcriber = null;
let activeModel = null;
let activeDevice = null;

/**
 * Importa Transformers.js únicamente dentro del Worker local.
 * @returns {Promise<Object>} API de Transformers.js necesaria para Whisper.
 * @throws {Error} Si el navegador no puede descargar el módulo de ejecución.
 */
async function loadTransformers() {
    if (pipelineFactory) return pipelineFactory;
    const module = await import(TRANSFORMERS_MODULE_URL);
    module.env.allowLocalModels = false;
    module.env.useBrowserCache = true;
    pipelineFactory = module.pipeline;
    return pipelineFactory;
}

/**
 * Carga o reutiliza la tubería de Whisper en WebGPU o WebAssembly.
 * @param {string} model Identificador del modelo de Whisper.
 * @param {"auto"|"webgpu"|"wasm"} device Aceleración elegida por configuración.
 * @returns {Promise<string>} Dispositivo realmente usado.
 * @throws {Error} Si el modelo no puede inicializarse en el navegador.
 */
async function getTranscriber(model, device) {
    if (transcriber && activeModel === model && activeDevice === device) return activeDevice;
    const pipeline = await loadTransformers();
    const requestedDevice = device === "auto"
        ? (self.navigator.gpu ? "webgpu" : "wasm")
        : device;
    const options = {
        device: requestedDevice,
        progress_callback: progress => {
            const percent = typeof progress.progress === "number"
                ? ` ${Math.round(progress.progress)}%`
                : "";
            self.postMessage({ type: "progress", message: `Descargando modelo Whisper${percent}` });
        },
    };
    try {
        transcriber = await pipeline("automatic-speech-recognition", model, options);
        activeModel = model;
        activeDevice = requestedDevice;
        return activeDevice;
    } catch (error) {
        if (requestedDevice !== "webgpu") throw error;
        self.postMessage({ type: "progress", message: "WebGPU no está disponible; Whisper usará CPU." });
        transcriber = await pipeline("automatic-speech-recognition", model, {
            ...options,
            device: "wasm",
        });
        activeModel = model;
        activeDevice = "wasm";
        return activeDevice;
    }
}

/**
 * Atiende carga y transcripción sin comunicar audio fuera del navegador.
 * @param {MessageEvent} event Mensaje del módulo de captura local.
 * @returns {Promise<void>} Publica el resultado o un error serializable.
 */
self.addEventListener("message", async event => {
    const { type, model = "onnx-community/whisper-tiny", device = "auto", audio, language } = event.data;
    try {
        if (type === "load") {
            const activeDeviceName = await getTranscriber(model, device);
            self.postMessage({ type: "ready", device: activeDeviceName });
            return;
        }
        if (type === "transcribe") {
            await getTranscriber(model, device);
            const output = await transcriber(audio, {
                task: "transcribe",
                language: language || "spanish",
                chunk_length_s: 30,
                stride_length_s: 5,
                return_timestamps: false,
            });
            self.postMessage({ type: "complete", text: typeof output === "string" ? output : output?.text || "" });
        }
    } catch (error) {
        self.postMessage({ type: "error", message: error?.message || "Whisper local no pudo completar la operación." });
    }
});
