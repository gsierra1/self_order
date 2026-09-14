/** Captura mono a 16 kHz y entrega bloques PCM16 de 100 ms. */
class PCMProcessor extends AudioWorkletProcessor {
    /** Inicializa el acumulador y el protocolo de vaciado del último bloque. */
    constructor() {
        super();
        this.samples = [];
        this.active = true;
        this.port.onmessage = () => {
            this.active = false;
            this.flush();
            this.port.postMessage({ stopped: true });
        };
    }

    /** Envía las muestras pendientes como PCM16 little-endian y vacía el bloque. */
    flush() {
        if (!this.samples.length) return;
        const buffer = new ArrayBuffer(this.samples.length * 2);
        const view = new DataView(buffer);
        this.samples.forEach((value, index) => {
            const sample = Math.max(-1, Math.min(1, value));
            view.setInt16(index * 2, sample < 0 ? sample * 32768 : sample * 32767, true);
        });
        this.port.postMessage(buffer, [buffer]);
        this.samples = [];
    }

    /**
     * Acumula entrada sin reproducir el micrófono por los parlantes.
     * @param {Float32Array[][]} inputs Canales del micrófono.
     * @returns {boolean} Mantiene activo el procesador.
     */
    process(inputs) {
        if (this.active && inputs[0]?.[0]) {
            for (const value of inputs[0][0]) {
                this.samples.push(value);
                if (this.samples.length === 1600) this.flush();
            }
        }
        return true;
    }
}
registerProcessor("pcm-capture", PCMProcessor);
