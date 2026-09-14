import { VoiceInput, speak } from "/static/voice.js";

let sessionId = null;
let sessionClosed = false;
let socket = null;
let phase = "connecting";
let assistantAudioEnabled = true;
let voiceTimer = null;

const conversation = document.getElementById("conversation");
const messageForm = document.getElementById("message-form");
const messageInput = document.getElementById("message-input");
const sendButton = document.getElementById("send-button");
const cartItems = document.getElementById("cart-items");
const cartTotal = document.getElementById("cart-total");
const sessionState = document.getElementById("session-state");
const systemStatus = document.getElementById("system-status");
const micButton = document.getElementById("mic-button");
const audioButton = document.getElementById("audio-button");
const transcript = document.getElementById("voice-transcript");

const voice = new VoiceInput(sendAudio, failVoice);

/** Formatea un importe del carrito en pesos argentinos.
 * @param {number} value Importe entero.
 * @returns {string} Importe para pantalla. */
function formatCurrency(value) {
    return new Intl.NumberFormat(
        "es-AR",
        {
            style: "currency",
            currency: "ARS",
            maximumFractionDigits: 0,
        }
    ).format(value);
}


/** Actualiza el indicador del estado de interacción.
 * @param {string} text Mensaje visible.
 * @param {string} type Tipo visual del estado. */
function setStatus(
    text,
    type = "ready"
) {
    systemStatus.textContent = text;

    systemStatus.className = "status";

    if (type === "processing") {
        systemStatus.classList.add(
            "status-processing"
        );

        return;
    }

    if (type === "error") {
        systemStatus.classList.add(
            "status-error"
        );

        return;
    }

    systemStatus.classList.add(
        "status-ready"
    );
}


/** Agrega un mensaje usando texto seguro y desplaza la conversación.
 * @param {string} author Autor visible.
 * @param {string} text Contenido textual.
 * @param {string} type Tipo visual del mensaje. */
function appendMessage(
    author,
    text,
    type
) {
    const messageElement =
        document.createElement("div");

    messageElement.classList.add(
        "message"
    );

    if (type === "user") {
        messageElement.classList.add(
            "user-message"
        );
    } else if (type === "error") {
        messageElement.classList.add(
            "error-message"
        );
    } else {
        messageElement.classList.add(
            "assistant-message"
        );
    }

    const authorElement =
        document.createElement("span");

    authorElement.className =
        "message-author";

    authorElement.textContent =
        author;

    const textElement =
        document.createElement("p");

    textElement.textContent =
        text;

    messageElement.appendChild(
        authorElement
    );

    messageElement.appendChild(
        textElement
    );

    conversation.appendChild(
        messageElement
    );

    conversation.scrollTop =
        conversation.scrollHeight;
}


/** Muestra exclusivamente el snapshot validado del backend.
 * @param {Object} cart Líneas, total y estado del pedido. */
function renderCart(cart) {
    cartItems.innerHTML = "";

    sessionState.textContent =
        cart.state;

    cartTotal.textContent =
        formatCurrency(cart.total);

    if (cart.items.length === 0) {
        const emptyMessage =
            document.createElement("p");

        emptyMessage.className =
            "empty-cart";

        emptyMessage.textContent =
            "Tu carrito está vacío.";

        cartItems.appendChild(
            emptyMessage
        );

        return;
    }

    for (const item of cart.items) {
        const itemElement =
            document.createElement("article");

        itemElement.className =
            "cart-item";

        const title =
            document.createElement("h3");

        title.className =
            "cart-item-title";

        title.textContent =
            item.quantity > 1
                ? `${item.quantity} × ${item.product_name}`
                : item.product_name;

        const details =
            document.createElement("p");

        details.className =
            "cart-item-details";

        const size =
            item.selected_modifiers.size;

        const drink =
            item.selected_modifiers.drink;

        const detailParts = [];

        if (size) {
            detailParts.push(
                size === "LARGE"
                    ? "Grande"
                    : "Mediano"
            );
        }

        if (drink) {
            detailParts.push(
                drink === "COCA"
                    ? "Coca"
                    : "Sprite"
            );
        }

        details.textContent =
            detailParts.join(" · ");

        const price =
            document.createElement("div");

        price.className =
            "cart-item-price";

        price.textContent =
            formatCurrency(
                item.unit_price
                * item.quantity
            );

        itemElement.appendChild(
            title
        );

        itemElement.appendChild(
            details
        );

        itemElement.appendChild(
            price
        );

        cartItems.appendChild(
            itemElement
        );
    }
}



/** Actualiza controles según conexión, turno en curso y cierre del pedido. */
function updateControls() {
    const ready = phase === "ready" && !sessionClosed;
    messageInput.disabled = !ready;
    sendButton.disabled = !ready;
    micButton.disabled = sessionClosed || !["ready", "recording"].includes(phase);
    micButton.textContent = phase === "recording" ? "Enviar audio" : "🎤 Hablar";
    micButton.classList.toggle("active", phase === "recording");
    audioButton.textContent = assistantAudioEnabled ? "🔊 Voz ON" : "🔇 Voz OFF";
}

/**
 * Envía un evento JSON por la conexión abierta.
 * @param {string} type Tipo del evento.
 * @param {Object} data Datos del evento.
 */
function sendEvent(type, data = {}) {
    if (socket?.readyState !== WebSocket.OPEN) throw new Error("No hay conexión con el backend.");
    socket.send(JSON.stringify({ type, data }));
}

/**
 * Envía PCM sin acumular una cola ilimitada en el navegador.
 * @param {ArrayBuffer} buffer Audio mono PCM16.
 */
function sendAudio(buffer) {
    if (socket?.readyState !== WebSocket.OPEN || socket.bufferedAmount > 256000) {
        throw new Error("La conexión no permite enviar el audio a tiempo.");
    }
    socket.send(buffer);
}

/**
 * Cancela el turno de audio ante un error local y conserva la opción de escribir.
 * @param {Error} error Error de captura o transporte.
 */
function failVoice(error) {
    clearTimeout(voiceTimer);
    voice.dispose();
    try { sendEvent("audio.cancel"); } catch (_) { /* La conexión ya está cerrada. */ }
    transcript.textContent = "Audio cancelado; el pedido no fue enviado.";
    appendMessage("Sistema", error.message, "error");
    phase = socket?.readyState === WebSocket.OPEN ? "ready" : "disconnected";
    setStatus("No se pudo enviar el audio", "error");
    updateControls();
}

/**
 * Prepara un turno o termina la grabación actual con un segundo clic.
 * @returns {Promise<void>} Se resuelve al preparar o finalizar la captura.
 */
async function toggleMicrophone() {
    if (phase === "recording") {
        phase = "processing";
        clearTimeout(voiceTimer);
        updateControls();
        setStatus("Procesando audio...", "processing");
        try { await voice.finish(); sendEvent("audio.stop"); }
        catch (error) { failVoice(error); }
        return;
    }
    if (phase !== "ready" || sessionClosed) return;
    phase = "preparing";
    updateControls();
    window.speechSynthesis?.cancel();
    setStatus("Preparando micrófono...", "processing");
    transcript.textContent = "Preparando la escucha...";
    try {
        await voice.prepare();
        sendEvent("audio.start");
        voiceTimer = setTimeout(() => failVoice(new Error("La conexión de voz tardó demasiado.")), 20000);
    } catch (error) { failVoice(error); }
}

/** Alterna la lectura del asistente y detiene inmediatamente el audio al apagarla. */
function toggleAssistantAudio() {
    assistantAudioEnabled = !assistantAudioEnabled;
    if (!assistantAudioEnabled) window.speechSynthesis?.cancel();
    updateControls();
}

/**
 * Aplica el estado real recibido, incluyendo el cierre de la sesión.
 * @param {Object} cart Snapshot del carrito.
 */
function applyCart(cart) {
    renderCart(cart);
    sessionClosed = cart.state === "CONFIRMED";
    if (sessionClosed) {
        voice.dispose();
        clearTimeout(voiceTimer);
        setStatus("Pedido confirmado");
        messageInput.placeholder = "El pedido ya fue confirmado.";
    }
    updateControls();
}

/**
 * Maneja eventos de transcripción, carrito, respuestas y errores.
 * @param {MessageEvent} event Mensaje JSON del backend.
 */
function onServerMessage(event) {
    const { type, data } = JSON.parse(event.data);
    if (data.cart) applyCart(data.cart);
    if (type === "connection.ready") {
        phase = "ready";
        if (!sessionClosed) setStatus("Listo");
    } else if (type === "voice.ready" && phase === "preparing") {
        clearTimeout(voiceTimer);
        voice.start();
        phase = "recording";
        transcript.textContent = "Escuchando… tocá Enviar audio cuando termines.";
        setStatus("Escuchando", "processing");
        voiceTimer = setTimeout(toggleMicrophone, 55000);
    } else if (type === "voice.transcript") {
        transcript.textContent = data.final ? "Audio enviado." : `Escuchando (provisional): ${data.text}`;
        if (data.final) appendMessage("Vos (voz)", data.text, "user");
    } else if (type === "assistant.text") {
        appendMessage("Asistente", data.text, "assistant");
        phase = "ready";
        if (!sessionClosed) setStatus("Listo");
        if (assistantAudioEnabled) speak(data.text, text => appendMessage("Sistema", text, "error"));
    } else if (["voice.error", "backend.error", "ai.error", "client.error", "voice.cancelled"].includes(type)) {
        clearTimeout(voiceTimer);
        voice.dispose();
        phase = "ready";
        transcript.textContent = "";
        if (data.message) appendMessage("Sistema", data.message, "error");
        if (!sessionClosed) setStatus(type === "voice.cancelled" ? "Listo" : "Error", type === "voice.cancelled" ? "ready" : "error");
    }
    updateControls();
}

/** Abre el canal y restaura controles desde el snapshot inicial del backend. */
function connectWebSocket() {
    const protocol = location.protocol === "https:" ? "wss" : "ws";
    socket = new WebSocket(`${protocol}://${location.host}/ws/sessions/${sessionId}`);
    socket.addEventListener("message", onServerMessage);
    socket.addEventListener("close", () => {
        phase = "disconnected";
        clearTimeout(voiceTimer);
        voice.dispose();
        window.speechSynthesis?.cancel();
        setStatus("Sin conexión. Recargá para iniciar otra sesión.", "error");
        updateControls();
    });
    socket.addEventListener("error", () => setStatus("Error de conexión", "error"));
}

/**
 * Crea la sesión de pedido y conecta el canal de conversación.
 * @returns {Promise<void>} Se resuelve después de solicitar la conexión.
 */
async function createSession() {
    updateControls();
    setStatus("Iniciando...", "processing");
    try {
        const response = await fetch("/api/sessions", { method: "POST" });
        if (!response.ok) throw new Error("No se pudo iniciar una sesión de pedido.");
        const data = await response.json();
        sessionId = data.session_id;
        applyCart(data.cart);
        connectWebSocket();
    } catch (error) {
        setStatus("Error de inicio", "error");
        appendMessage("Sistema", error.message, "error");
    }
}

/**
 * Envía texto solo cuando no hay un turno hablado o escrito pendiente.
 * @param {string} message Mensaje del usuario.
 */
function sendMessage(message) {
    if (phase !== "ready" || sessionClosed) return;
    window.speechSynthesis?.cancel();
    sendEvent("user.text", { message });
    appendMessage("Vos", message, "user");
    phase = "processing";
    setStatus("Procesando...", "processing");
    updateControls();
}

messageForm.addEventListener("submit", event => {
    event.preventDefault();
    const message = messageInput.value.trim();
    if (message) { sendMessage(message); messageInput.value = ""; }
});
micButton.addEventListener("click", toggleMicrophone);
audioButton.addEventListener("click", toggleAssistantAudio);
window.addEventListener("pagehide", () => { voice.dispose(); window.speechSynthesis?.cancel(); socket?.close(); });
createSession();
