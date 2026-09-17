/** Intervalo entre avisos consecutivos de inactividad. */
export const INACTIVITY_INTERVAL_MS = 20000;

/** Coordina avisos escalonados y el cierre de una sesión sin actividad. */
export class InactivityMonitor {
    /**
     * Configura las acciones de cada etapa y el mecanismo de temporización.
     * @param {Object} options Configuración del monitor.
     * @param {() => void} options.onPrompt Acción del primer intervalo.
     * @param {() => void} options.onWarning Acción del segundo intervalo.
     * @param {() => void} options.onTimeout Acción del tercer intervalo.
     * @param {number} [options.intervalMs=INACTIVITY_INTERVAL_MS] Duración de cada etapa.
     * @param {(callback: () => void, delay: number) => number} [options.schedule]
     *     Función utilizada para programar una etapa.
     * @param {(timerId: number) => void} [options.cancel] Función que cancela una etapa.
     */
    constructor({
        onPrompt,
        onWarning,
        onTimeout,
        intervalMs = INACTIVITY_INTERVAL_MS,
        schedule = (callback, delay) => window.setTimeout(callback, delay),
        cancel = timerId => window.clearTimeout(timerId),
    }) {
        this.onPrompt = onPrompt;
        this.onWarning = onWarning;
        this.onTimeout = onTimeout;
        this.intervalMs = intervalMs;
        this.schedule = schedule;
        this.cancel = cancel;
        this.stage = 0;
        this.timerId = null;
    }

    /**
     * Reinicia la secuencia desde el primer aviso.
     * @returns {void}
     * @effects Cancela la espera anterior y programa un intervalo completo.
     */
    restart() {
        this.stop();
        this.scheduleNext();
    }

    /**
     * Detiene el conteo sin ejecutar avisos.
     * @returns {void}
     * @effects Cancela el temporizador activo y reinicia la etapa interna.
     */
    stop() {
        if (this.timerId !== null) this.cancel(this.timerId);
        this.timerId = null;
        this.stage = 0;
    }

    /**
     * Programa la siguiente transición del monitor.
     * @returns {void}
     * @effects Conserva el identificador necesario para cancelar la espera.
     */
    scheduleNext() {
        this.timerId = this.schedule(() => this.advance(), this.intervalMs);
    }

    /**
     * Ejecuta la etapa vencida y continúa la secuencia cuando corresponde.
     * @returns {void}
     * @effects Emite la pregunta, la advertencia o el cierre configurado.
     */
    advance() {
        this.timerId = null;
        this.stage += 1;
        if (this.stage === 1) {
            this.onPrompt();
            this.scheduleNext();
        } else if (this.stage === 2) {
            this.onWarning();
            this.scheduleNext();
        } else {
            this.onTimeout();
        }
    }
}
