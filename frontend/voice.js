/** Recursos del micrófono y envío de audio; no interpreta ni modifica pedidos. */
export class VoiceInput {
    /**
     * Conserva callbacks para transmitir audio e informar fallas locales.
     * @param {Function} sendAudio Envía un ArrayBuffer al WebSocket.
     * @param {Function} fail Informa una falla y cancela el turno.
     */
    constructor(sendAudio, fail) {
        this.sendAudio = sendAudio;
        this.fail = fail;
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
                try { this.sendAudio(event.data); }
                catch (error) { this.fail(error); }
            } else if (event.data.stopped) {
                this.onFlushed?.();
            }
        };
    }

    /** Conecta el micrófono solo después de que el backend informa voice.ready. */
    start() {
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

    /** Cancela la captura y libera micrófono, conexiones y contexto de audio. */
    dispose() {
        this.generation++;
        if (this.node) { this.node.port.onmessage = null; this.node.disconnect(); }
        this.source?.disconnect();
        this.stream?.getTracks().forEach(track => track.stop());
        this.context?.close().catch(() => {});
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
 * @returns {string} Texto preparado para síntesis, sin puntos de miles ni Markdown.
 */
function prepareSpeechText(text) {
    return text
        .replace(/\b(\d{1,3}(?:\.\d{3})+)\b/g, (_, amount) => amount.replace(/\./g, " "))
        .replace(/[|*_`]/g, " ")
        .replace(/\s{2,}/g, " ")
        .trim();
}
