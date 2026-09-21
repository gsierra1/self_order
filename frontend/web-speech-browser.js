const FINALIZATION_TIMEOUT_MS = 15000;

/**
 * Encapsula Web Speech API y entrega únicamente texto final al flujo del pedido.
 *
 * El navegador controla el motor de reconocimiento y el acceso al micrófono.
 * Esta clase no conoce el menú, el carrito ni las operaciones de OrderService.
 */
export class BrowserSpeechApiInput {
    /**
     * Inicializa el capturador nativo del navegador.
     * @param {Object} options Configuración pública recibida desde el backend.
     * @param {string} [options.language="es-AR"] Idioma BCP 47 solicitado.
     * @param {Function} options.onProgress Publica transcripción provisional.
     * @param {Function} options.onError Informa fallas del reconocimiento.
     * @param {Function} options.onSpeechEnded Solicita finalizar el turno cuando el navegador deja de escuchar.
     */
    constructor({ language = "es-AR", onProgress, onError, onSpeechEnded }) {
        this.language = language;
        this.onProgress = onProgress;
        this.onError = onError;
        this.onSpeechEnded = onSpeechEnded;
        this.recognition = null;
        this.pendingResult = null;
        this.finalSegments = [];
        this.recording = false;
        this.ended = false;
        this.disposed = false;
    }

    /**
     * Comprueba compatibilidad y construye una sesión de reconocimiento.
     * @returns {Promise<void>} Se resuelve cuando el capturador está preparado.
     * @throws {Error} Si el navegador no implementa Web Speech API.
     */
    async prepare() {
        const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
        if (!Recognition) {
            throw new Error(
                "Este navegador no admite Web Speech API. Probá con Chrome o Edge, o elegí otro STT.",
            );
        }
        this.disposed = false;
        this.recognition = new Recognition();
        this.recognition.lang = this.language;
        this.recognition.continuous = false;
        this.recognition.interimResults = true;
        this.recognition.maxAlternatives = 1;
        this.recognition.onresult = event => this.handleResult(event);
        this.recognition.onerror = event => this.handleError(event);
        this.recognition.onend = () => this.handleEnd();
    }

    /**
     * Inicia un turno y solicita al navegador acceso al micrófono.
     * @returns {void}
     * @throws {Error} Si el capturador todavía no fue preparado.
     * @effects Abre una única escucha nativa y crea la promesa del texto final.
     */
    start() {
        if (!this.recognition) {
            throw new Error("Web Speech API todavía no está preparada.");
        }
        this.finalSegments = [];
        this.recording = true;
        this.ended = false;
        let resolveResult;
        let rejectResult;
        const promise = new Promise((resolve, reject) => {
            resolveResult = resolve;
            rejectResult = reject;
        });
        this.pendingResult = { resolve: resolveResult, reject: rejectResult, promise };
        promise.catch(() => {});
        try {
            this.recognition.start();
        } catch (error) {
            this.recording = false;
            this.pendingResult = null;
            throw error;
        }
    }

    /**
     * Detiene la escucha y espera el texto final del navegador.
     * @returns {Promise<string>} Transcripción definitiva del turno.
     * @throws {Error} Si no hubo voz o el navegador no finaliza a tiempo.
     * @effects Cierra la captura actual sin iniciar otra automáticamente.
     */
    async finish() {
        const pending = this.pendingResult;
        if (!pending) {
            throw new Error("Web Speech API no tiene un turno de voz activo.");
        }
        this.recording = false;
        if (!this.ended) {
            try {
                this.recognition?.stop();
            } catch (_) {
                // El navegador puede haber cerrado la escucha justo antes.
            }
        }
        let timeout;
        try {
            return await Promise.race([
                pending.promise,
                new Promise((_, reject) => {
                    timeout = setTimeout(
                        () => reject(new Error("Web Speech API tardó demasiado en entregar el texto final.")),
                        FINALIZATION_TIMEOUT_MS,
                    );
                }),
            ]);
        } finally {
            clearTimeout(timeout);
            if (this.pendingResult === pending) this.pendingResult = null;
        }
    }

    /**
     * Cancela la escucha y libera los callbacks del reconocedor.
     * @returns {void}
     * @effects Descarta cualquier transcripción provisional sin enviarla al backend.
     */
    dispose() {
        this.disposed = true;
        this.recording = false;
        const pending = this.pendingResult;
        this.pendingResult = null;
        pending?.reject(new Error("La transcripción fue cancelada."));
        if (this.recognition) {
            this.recognition.onresult = null;
            this.recognition.onerror = null;
            this.recognition.onend = null;
            try {
                this.recognition.abort();
            } catch (_) {
                // No hay una sesión activa que cancelar.
            }
        }
        this.recognition = null;
        this.finalSegments = [];
        this.ended = true;
    }

    /**
     * Separa hipótesis visibles de segmentos definitivos.
     * @param {SpeechRecognitionEvent} event Resultado entregado por el navegador.
     * @returns {void}
     * @effects Acumula solo resultados finales y muestra los provisionales en pantalla.
     */
    handleResult(event) {
        let interim = "";
        for (let index = event.resultIndex; index < event.results.length; index += 1) {
            const text = event.results[index][0]?.transcript?.trim() || "";
            if (!text) continue;
            if (event.results[index].isFinal) {
                this.finalSegments.push(text);
            } else {
                interim = `${interim} ${text}`.trim();
            }
        }
        const visible = [...this.finalSegments, interim].filter(Boolean).join(" ");
        if (visible) this.onProgress(`Escuchando (provisional): ${visible}`);
    }

    /**
     * Traduce los códigos nativos a un error comprensible para la interfaz.
     * @param {SpeechRecognitionErrorEvent} event Error publicado por el navegador.
     * @returns {void}
     * @effects Rechaza el turno activo sin modificar el pedido.
     */
    handleError(event) {
        if (this.disposed) return;
        const messages = {
            "not-allowed": "El navegador no permitió usar el micrófono.",
            "audio-capture": "No se encontró un micrófono disponible.",
            network: "Web Speech API no pudo conectarse al servicio de reconocimiento.",
            "no-speech": "Web Speech API no detectó voz. Podés volver a hablar o escribir.",
        };
        const error = new Error(messages[event.error] || `Web Speech API falló: ${event.error}.`);
        this.recording = false;
        this.pendingResult?.reject(error);
        this.pendingResult = null;
        this.onError(error);
    }

    /**
     * Completa el turno cuando el navegador deja de escuchar.
     * @returns {void}
     * @effects Resuelve el texto final y solicita al flujo principal que lo envíe.
     */
    handleEnd() {
        if (this.disposed) return;
        const endedWhileRecording = this.recording;
        this.recording = false;
        this.ended = true;
        const text = this.finalSegments.join(" ").trim();
        const pending = this.pendingResult;
        if (text) {
            pending?.resolve(text);
        } else {
            pending?.reject(new Error("Web Speech API no reconoció voz. Podés volver a hablar o escribir."));
        }
        if (endedWhileRecording) this.onSpeechEnded();
    }
}
