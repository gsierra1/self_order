import { VoiceInput, speak } from "/static/voice.js?v=20260917-3";

let sessionId = null;
let sessionClosed = false;
let socket = null;
let phase = "connecting";
let assistantAudioEnabled = true;
let voiceTimer = null;
let voiceBackendReady = false;
let voicePrepared = false;
let paymentTimer = null;
let countdownTimer = null;
let reconnectTimer = null;
let reconnectAttempts = 0;
let currentCart = null;

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
const confirmCartButton = document.getElementById("confirm-cart-button");
const paymentPanel = document.getElementById("payment-panel");
const paymentContent = document.getElementById("payment-content");
const paymentOptions = paymentPanel.querySelector(".payment-options");
const paymentTitle = paymentPanel.querySelector("h3");

const voice = new VoiceInput(sendAudio, failVoice, finishVoiceAfterSilence);

/** Formatea un importe del carrito en pesos argentinos.
 * @param {number} value Importe entero.
 * @returns {string} Importe para pantalla. */
function formatCurrency(value) {
    const formattedValue = new Intl.NumberFormat("es-AR", {
        style: "decimal",
        maximumFractionDigits: 0,
    }).format(value);
    return `ARS ${formattedValue}`;
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
 * @param {Object} cart Líneas, total, estado y modificadores visibles.
 * @returns {void}
 * @effects Reemplaza el contenido del carrito y actualiza sus controles. */
function renderCart(cart) {
    cartItems.innerHTML = "";
    confirmCartButton.hidden = cart.state !== "ACTIVE" || cart.items.length === 0;

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
        itemElement.dataset.lineId = String(item.line_id);

        const title =
            document.createElement("h3");

        title.className =
            "cart-item-title";

        title.textContent =
            item.quantity > 1
                ? `${item.quantity} × ${item.product_name}`
                : item.product_name;

        const details = document.createElement("div");
        details.className = "cart-item-details";
        const modifierDetails = item.selected_modifier_details || [];
        const requiredDetails = modifierDetails.filter(detail => detail.required);
        const optionalDetails = modifierDetails.filter(detail => !detail.required);
        const configuration = document.createElement("div");
        configuration.className = "cart-item-configuration";
        const requiredText = requiredDetails
            .map(detail => `${detail.group_name}: ${detail.option_name}`)
            .join(" · ");
        configuration.textContent = requiredText
            ? `${requiredText} | Precio base: ${formatCurrency(item.base_price)}`
            : `Precio base: ${formatCurrency(item.base_price)}`;
        details.appendChild(configuration);

        if (optionalDetails.length > 0) {
            const extrasTitle = document.createElement("h4");
            extrasTitle.className = "cart-extras-title";
            extrasTitle.textContent = "Extras";
            details.appendChild(extrasTitle);

            for (const detail of optionalDetails) {
                const extraRow = createExtraRow(
                    item.line_id,
                    detail,
                    cart.state === "ACTIVE",
                );
                details.appendChild(extraRow);
            }
        }

        const priceRow = document.createElement("div");
        priceRow.className = "cart-item-total";
        const price = document.createElement("div");
        price.className = "cart-item-price";
        price.textContent = formatCurrency(item.unit_price * item.quantity);
        priceRow.appendChild(price);

        if (cart.state === "ACTIVE") {
            const removeButton = document.createElement("button");
            removeButton.type = "button";
            removeButton.className = "remove-item-button";
            removeButton.textContent = "🗑";
            removeButton.title = "Eliminar este producto";
            removeButton.setAttribute("aria-label", "Eliminar este producto");
            removeButton.addEventListener("click", () => removeCartItem(item.line_id));
            priceRow.appendChild(removeButton);
        }

        itemElement.appendChild(
            title
        );

        itemElement.appendChild(
            details
        );

        itemElement.appendChild(priceRow);

        cartItems.appendChild(
            itemElement
        );
    }
}



/**
 * Actualiza controles segun conexion, turno en curso y cierre del pedido.
 * @returns {void}
 * @effects Habilita o bloquea escritura y microfono segun el estado actual.
 */
function updateControls() {
    const ready = phase === "ready" && !sessionClosed;
    messageInput.disabled = !ready;
    sendButton.disabled = !ready;
    micButton.disabled = sessionClosed || !["ready", "recording"].includes(phase);
    micButton.textContent = phase === "recording"
        ? "Enviar audio"
        : ["preparing", "reconnecting"].includes(phase)
            ? "Conectando..."
            : "\u{1F3A4} Hablar";
    micButton.classList.toggle("active", phase === "recording");
    audioButton.textContent = assistantAudioEnabled ? "\u{1F50A} Voz ON" : "\u{1F507} Voz OFF";
}

/**
 * Reemplaza temporalmente los botones de pago mientras se procesa la voz.
 * @returns {void} Actualiza el contenido visible del panel de pago.
 * @effects Evita que la persona elija otra opción durante el turno.
 */
function showPaymentProcessing() {
    if (currentCart?.state === "PAYMENT_PENDING" && !currentCart.payment_method) {
        paymentOptions.hidden = true;
        paymentTitle.hidden = true;
        paymentContent.innerHTML = "<p>Procesando tu elección de pago...</p>";
    }
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
    voiceBackendReady = false;
    voicePrepared = false;
    voice.dispose();
    try { sendEvent("audio.cancel"); } catch (_) { /* La conexión ya está cerrada. */ }
    transcript.textContent = "Audio cancelado; el pedido no fue enviado.";
    appendMessage("Sistema", error.message, "error");
    phase = socket?.readyState === WebSocket.OPEN ? "ready" : "disconnected";
    setStatus("No se pudo enviar el audio", "error");
    updateControls();
}


/** Construye una fila de extra con su control de eliminación cuando está habilitado.
 * @param {number} lineId Identificador de la línea que contiene el extra.
 * @param {Object} detail Detalle visible y técnico del modificador opcional.
 * @param {boolean} editable Indica si el pedido permite cambios.
 * @returns {HTMLDivElement} Fila lista para insertarse en el carrito.
 * @effects El botón solicita al backend quitar exclusivamente ese extra. */
function createExtraRow(lineId, detail, editable) {
    const extraRow = document.createElement("div");
    extraRow.className = "cart-extra";
    const extraText = document.createElement("span");
    extraText.textContent = `${detail.option_name} · + ${formatCurrency(detail.price_delta)}`;
    extraRow.appendChild(extraText);

    if (editable) {
        const removeExtraButton = document.createElement("button");
        removeExtraButton.type = "button";
        removeExtraButton.className = "remove-extra-button";
        removeExtraButton.textContent = "🗑";
        removeExtraButton.title = `Quitar ${detail.option_name}`;
        removeExtraButton.setAttribute("aria-label", `Quitar ${detail.option_name}`);
        removeExtraButton.addEventListener(
            "click",
            () => removeCartModifier(lineId, detail.group_id, detail.option_name),
        );
        extraRow.appendChild(removeExtraButton);
    }

    return extraRow;
}

/** Muestra el selector y el estado del pago de demostracion.
 * @param {Object} cart Snapshot validado con estado y metodo de pago.
 * @returns {void} Actualiza el panel de pago y sus controles.
 * @effects Muestra un QR escaneable que contiene solo texto de demostracion,
 * sin URL ni instruccion de pago real. */
function renderPayment(cart) {
    clearTimeout(paymentTimer);
    clearInterval(countdownTimer);
    paymentPanel.hidden = cart.state !== "PAYMENT_PENDING";
    if (paymentPanel.hidden) {
        paymentOptions.hidden = true;
        paymentTitle.hidden = true;
        paymentContent.innerHTML = "";
        return;
    }
    const method = cart.payment_method;
    const showSelector = !method && phase === "ready";
    paymentOptions.hidden = !showSelector;
    paymentTitle.hidden = !showSelector;
    if (!method) {
        if (phase !== "ready") {
            paymentContent.innerHTML = "<p>Procesando tu elección de pago...</p>";
            return;
        }
        paymentContent.innerHTML = "<p>Elegí una opción para continuar.</p><button type=\"button\" class=\"payment-action\" id=\"payment-back\">ATRÁS</button>";
        document.getElementById("payment-back").addEventListener("click", returnToOrder);
        return;
    }
    if (method === "QR") {
        paymentContent.innerHTML = `
            <p>Escane\u00e1 este QR de demostraci\u00f3n. Al leerlo muestra texto, no abre
                una URL ni inicia un pago real.</p>
            <img class="demo-qr" src="/static/assets/qr-demostracion.svg"
                alt="C\u00f3digo QR de demostraci\u00f3n sin pago real">
            <p>Procesando pago...</p>
            <button type="button" class="payment-action" id="payment-back">ATR\u00c1S</button>`;
        document.getElementById("payment-back").addEventListener("click", returnToPaymentMethods);
        paymentTimer = setTimeout(() => completePayment(), 5000);
    } else if (method === "CARD") {
        paymentContent.innerHTML = `
            <label for="card-number">Ingresá el número de tu tarjeta (demo)</label>
            <input id="card-number" class="card-input" inputmode="numeric"
                autocomplete="off" placeholder="Escribí cualquier número">
            <button type="button" class="payment-action" id="card-confirm">Continuar</button>
            <button type="button" class="payment-action" id="payment-back">ATRÁS</button>`;
        document.getElementById("card-confirm").addEventListener("click", () => {
            const value = document.getElementById("card-number").value.trim();
            if (!value) {
                appendMessage("Sistema", "Ingresá un número para continuar con la demo.", "error");
                return;
            }
            completePayment();
        });
        document.getElementById("payment-back").addEventListener("click", returnToPaymentMethods);
    } else {
        paymentContent.innerHTML = `
            <p>Pago en caja seleccionado.</p>
            <p>Tu número de pedido es <strong>${cart.order_number}</strong>.</p>
            <p>Acercate a caja, indicá ese número y realizá el pago.</p>
            <p id="cash-countdown">Esta sesión finalizará en 15.</p>
            <button type="button" class="payment-action" id="payment-back">ATRÁS</button>`;
        document.getElementById("payment-back").addEventListener("click", returnToPaymentMethods);
        let remaining = 15;
        paymentTimer = setInterval(() => {
            remaining -= 1;
            const element = document.getElementById("cash-countdown");
            if (remaining <= 0) {
                clearInterval(paymentTimer);
                completePayment({ resetImmediately: true });
            } else if (element) {
                element.textContent = `Esta sesión finalizará en ${remaining}.`;
            }
        }, 1000);
    }
}

/** Vuelve al carrito y permite corregirlo antes de elegir otro método.
 * @returns {Promise<void>} Actualiza la pantalla con el carrito editable. */
async function returnToOrder() {
    clearTimeout(paymentTimer);
    try {
        const response = await fetch(`/api/sessions/${sessionId}/payment/back`, { method: "POST" });
        const data = await response.json();
        if (!response.ok) throw new Error(data.detail || "No se pudo volver al pedido.");
        applyCart(data.cart);
        phase = "ready";
        setStatus("Listo");
        updateControls();
    } catch (error) {
        appendMessage("Sistema", error.message, "error");
    }
}

/** Elimina una línea mediante el endpoint respaldado por OrderService.
 * @param {number} lineId Identificador de la línea a eliminar.
 * @returns {Promise<void>} Actualiza el carrito o informa el error. */
async function removeCartItem(lineId) {
    const currentItem = [...document.querySelectorAll(".cart-item")]
        .find(element => element.dataset.lineId === String(lineId));
    const itemName = currentItem?.querySelector(".cart-item-title")?.textContent || "el producto";
    try {
        const response = await fetch(`/api/sessions/${sessionId}/cart/items/${lineId}`, { method: "DELETE" });
        const data = await response.json();
        if (!response.ok) throw new Error(data.detail || "No se pudo eliminar el producto.");
        applyCart(data.cart);
        appendMessage("Sistema", `Eliminé ${itemName} del carrito.`, "assistant");
    } catch (error) {
        appendMessage("Sistema", error.message, "error");
    }
}

/** Quita un extra opcional mediante la misma validación que usa la conversación.
 * @param {number} lineId Identificador de la línea que contiene el extra.
 * @param {string} modifierGroupId Grupo opcional que se desea quitar.
 * @param {string} optionName Nombre visible usado para informar el resultado.
 * @returns {Promise<void>} Actualiza el carrito o informa el error recibido.
 * @effects Cambia el carrito validado por OrderService sin eliminar la línea. */
async function removeCartModifier(lineId, modifierGroupId, optionName) {
    try {
        const response = await fetch(
            `/api/sessions/${sessionId}/cart/items/${lineId}/modifiers/${modifierGroupId}`,
            { method: "DELETE" },
        );
        const data = await response.json();
        if (!response.ok) throw new Error(data.detail || "No se pudo quitar el extra.");
        applyCart(data.cart);
        appendMessage("Sistema", `Eliminé ${optionName} del producto.`, "assistant");
    } catch (error) {
        appendMessage("Sistema", error.message, "error");
    }
}

/** Confirma el carrito sin enviar una intención al modelo.
 * @returns {Promise<void>} Abre directamente la selección de pago. */
async function startPaymentFromCart() {
    try {
        const response = await fetch(`/api/sessions/${sessionId}/payment/start`, { method: "POST" });
        const data = await response.json();
        if (!response.ok) throw new Error(data.detail || "No se pudo confirmar el carrito.");
        applyCart(data.cart);
        appendMessage("Sistema", "Carrito confirmado. Elegí cómo pagar.", "assistant");
    } catch (error) {
        appendMessage("Sistema", error.message, "error");
    }
}

/** Completa el pago demo y muestra el número para retirar en caja.
 * @param {Object} options Opciones de cierre de la sesión.
 * @param {boolean} [options.resetImmediately=false] Reinicia al completar el pago.
 * @returns {Promise<void>} Finaliza el pedido o muestra el error recibido.
 * @effects Para QR conserva la pantalla final durante quince segundos; para
 * caja, el contador previo ya controla el reinicio. */
async function completePayment(options = {}) {
    clearTimeout(paymentTimer);
    try {
        const response = await fetch(`/api/sessions/${sessionId}/payment/complete`, { method: "POST" });
        const data = await response.json();
        if (!response.ok) throw new Error(data.detail || "No se pudo completar el pago.");
        if (options.resetImmediately) {
            await startNewSession();
            return;
        }
        sessionClosed = true;
        voice.dispose();
        const resetSeconds = data.payment_method === "QR" ? 15 : 5;
        paymentPanel.hidden = false;
        paymentContent.innerHTML = `
            <p class="payment-success">Pago confirmado.</p>
            <p>Tu número de pedido es <strong>${data.order_number}</strong>.</p>
            <p>Acercate a caja para retirarlo.</p>
            <p id="session-countdown">Esta sesión finalizará en ${resetSeconds}.</p>`;
        sessionState.textContent = "CONFIRMED";
        setStatus("Pago confirmado");
        updateControls();
        let remaining = resetSeconds;
        countdownTimer = setInterval(() => {
            remaining -= 1;
            const element = document.getElementById("session-countdown");
            if (remaining <= 0) {
                clearInterval(countdownTimer);
                startNewSession();
            } else if (element) {
                element.textContent = `Esta sesión finalizará en ${remaining}.`;
            }
        }, 1000);
    } catch (error) {
        appendMessage("Sistema", error.message, "error");
    }
}

/** Inicia la captura solo cuando backend y navegador están preparados.
 * @returns {void} No devuelve valor.
 */
function maybeStartRecording() {
    if (phase !== "preparing" || !voiceBackendReady || !voicePrepared) return;
    clearTimeout(voiceTimer);
    voice.start();
    phase = "recording";
    showPaymentProcessing();
    transcript.textContent = "Escuchando… el audio se enviará cuando termines de hablar.";
    setStatus("Escuchando", "processing");
    updateControls();
    voiceTimer = setTimeout(() => failVoice(new Error("El turno de voz superó los 55 segundos.")), 55000);
}

/**
 * Finaliza el turno al detectar silencio o por solicitud manual.
 * @param {"silence"|"manual"} trigger Motivo que cerró la captura.
 * @returns {Promise<void>} Se resuelve después de vaciar PCM y enviar `audio.stop`.
 * @effects Cambia la interfaz a procesamiento y solicita una única transcripción final.
 */
async function finishVoiceTurn(trigger) {
    if (phase !== "recording") return;
    phase = "processing";
    showPaymentProcessing();
    clearTimeout(voiceTimer);
    updateControls();
    if (trigger === "silence") {
        transcript.textContent = "Silencio detectado. Enviando audio…";
    }
    setStatus("Procesando audio...", "processing");
    try {
        await voice.finish();
        sendEvent("audio.stop");
    } catch (error) {
        failVoice(error);
    }
}

/**
 * Atiende el fin de habla detectado por `VoiceInput`.
 * @returns {void}
 * @effects Inicia el cierre asíncrono solo si el turno continúa grabando.
 */
function finishVoiceAfterSilence() {
    void finishVoiceTurn("silence");
}

/**
 * Prepara un turno o termina la grabación actual con un segundo clic.
 * @returns {Promise<void>} Se resuelve al preparar o finalizar la captura.
 */
async function toggleMicrophone() {
    if (phase === "recording") {
        await finishVoiceTurn("manual");
        return;
    }
    if (phase !== "ready" || sessionClosed) return;
    phase = "preparing";
    showPaymentProcessing();
    voiceBackendReady = false;
    voicePrepared = false;
    updateControls();
    window.speechSynthesis?.cancel();
    setStatus("Preparando micrófono y conexión...", "processing");
    transcript.textContent = "No hables hasta que aparezca «Escuchando».";
    try {
        sendEvent("audio.start");
        voiceTimer = setTimeout(() => failVoice(new Error("La conexión de voz tardó demasiado.")), 20000);
        await voice.prepare();
        voicePrepared = true;
        maybeStartRecording();
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
    currentCart = cart;
    renderCart(cart);
    renderPayment(cart);
    sessionClosed = cart.state === "CONFIRMED";
    if (sessionClosed) {
        voice.dispose();
        clearTimeout(voiceTimer);
        setStatus("Pedido confirmado");
        messageInput.placeholder = "El pedido ya fue confirmado.";
    }
    updateControls();
}

/** Vuelve desde QR, tarjeta o caja al selector sin habilitar el carrito.
 * @returns {Promise<void>} Muestra nuevamente los métodos de pago disponibles.
 * @effects Conserva `PAYMENT_PENDING`, el carrito y el número de pedido, pero
 * descarta el método seleccionado. */
async function returnToPaymentMethods() {
    clearTimeout(paymentTimer);
    clearInterval(paymentTimer);
    try {
        const response = await fetch(
            `/api/sessions/${sessionId}/payment/method/back`,
            { method: "POST" },
        );
        const data = await response.json();
        if (!response.ok) throw new Error(data.detail || "No se pudo cambiar el método de pago.");
        phase = "ready";
        applyCart(data.cart);
        setStatus("Elegí cómo pagar");
        updateControls();
    } catch (error) {
        appendMessage("Sistema", error.message, "error");
    }
}

/**
 * Muestra inmediatamente el método de pago confirmado por el backend.
 *
 * El evento contiene un snapshot validado por OrderService y puede llegar antes
 * que la respuesta narrativa del intérprete LLM. Procesarlo por separado evita
 * que la interfaz espere esa respuesta para mostrar caja, QR o tarjeta.
 *
 * @param {Object} data Datos del evento `payment.method_selected`.
 * @returns {void} Actualiza el carrito y los controles de pago.
 * @effects Para `CASH`, inicia inmediatamente la cuenta regresiva visible.
 */
function handlePaymentMethodSelected(data) {
    if (!data?.cart) return;
    const paymentCart = {
        ...data.cart,
        payment_method: data.method ?? data.cart.payment_method,
        order_number: data.order_number ?? data.cart.order_number,
    };
    applyCart(paymentCart);
    phase = "ready";
    if (data.method === "CASH") {
        setStatus("Pedido listo para retirar en caja");
    }
    updateControls();
}

/**
 * Maneja eventos de transcripcion, carrito, respuestas y errores.
 * @param {MessageEvent} event Mensaje JSON del backend.
 * @returns {void}
 * @effects Sincroniza el carrito, el estado de controles y los mensajes visibles.
 */
function onServerMessage(event) {
    const { type, data } = JSON.parse(event.data);
    if (type === "payment.method_selected") {
        handlePaymentMethodSelected(data);
    } else if (data.cart) {
        applyCart(data.cart);
    }
    if (type === "connection.ready") {
        const restored = phase === "reconnecting";
        reconnectAttempts = 0;
        phase = "ready";
        if (!sessionClosed) setStatus(restored ? "Conexi\u00f3n restablecida" : "Listo");
    } else if (type === "voice.ready" && phase === "preparing") {
        voiceBackendReady = true;
        maybeStartRecording();
    } else if (type === "voice.transcript") {
        transcript.textContent = data.final ? "Audio enviado." : `Escuchando (provisional): ${data.text}`;
        if (data.final) appendMessage("Vos (voz)", data.text, "user");
    } else if (type === "assistant.text") {
        appendMessage("Asistente", data.text, "assistant");
        phase = "ready";
        if (data.cart?.state === "PAYMENT_PENDING" && !data.cart.payment_method) {
            renderPayment(data.cart);
        }
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

/**
 * Cancela un reintento pendiente de conexion.
 * @returns {void}
 * @effects Evita que un socket anterior vuelva a conectarse despues de cerrar
 * intencionalmente la sesion o abrir una nueva.
 */
function clearReconnectTimer() {
    clearTimeout(reconnectTimer);
    reconnectTimer = null;
}

/**
 * Cierra el socket sin programar una reconexion.
 * @returns {void}
 * @effects Desvincula los listeners del socket actual antes de cerrarlo.
 */
function closeSocketIntentionally() {
    clearReconnectTimer();
    const previousSocket = socket;
    socket = null;
    previousSocket?.close();
}

/**
 * Programa un reintento progresivo para la misma sesion.
 * @returns {void}
 * @effects Mantiene la interfaz bloqueada hasta recibir `connection.ready`.
 */
function scheduleReconnect() {
    if (sessionClosed || !sessionId || reconnectTimer) return;
    const delay = Math.min(1000 * (2 ** reconnectAttempts), 15000);
    reconnectAttempts += 1;
    setStatus(`Reconectando en ${Math.ceil(delay / 1000)} segundos...`, "processing");
    reconnectTimer = setTimeout(() => {
        reconnectTimer = null;
        connectWebSocket();
    }, delay);
}

/**
 * Trata el cierre inesperado de la conexion actual.
 * @param {CloseEvent} event Informacion de cierre enviada por el navegador.
 * @param {WebSocket} closedSocket Socket que genero el evento.
 * @returns {void}
 * @effects Cancela audio local, conserva el pedido y programa la reconexion o
 * inicia una sesion nueva cuando el backend ya no conserva la anterior.
 */
function handleSocketClose(event, closedSocket) {
    if (socket !== closedSocket) return;
    socket = null;
    clearTimeout(voiceTimer);
    const voiceWasInProgress = ["preparing", "recording", "processing"].includes(phase);
    voiceBackendReady = false;
    voicePrepared = false;
    voice.dispose();
    window.speechSynthesis?.cancel();
    if (voiceWasInProgress) {
        transcript.textContent = "La conexi\u00f3n se interrumpi\u00f3; el audio no ser\u00e1 reenviado.";
    }
    if (event.code === 4404) {
        appendMessage("Sistema", "La sesi\u00f3n anterior ya no est\u00e1 disponible. Inicio un pedido nuevo.", "error");
        startNewSession();
        return;
    }
    if (sessionClosed) return;
    phase = "reconnecting";
    updateControls();
    scheduleReconnect();
}

/**
 * Abre o recupera el canal de la sesion actual.
 * @returns {void}
 * @effects Reemplaza el socket anterior y espera el snapshot `connection.ready`
 * antes de habilitar nuevamente las entradas de la persona.
 */
function connectWebSocket() {
    if (!sessionId || socket?.readyState === WebSocket.OPEN || socket?.readyState === WebSocket.CONNECTING) return;
    const protocol = location.protocol === "https:" ? "wss" : "ws";
    const currentSocket = new WebSocket(`${protocol}://${location.host}/ws/sessions/${sessionId}`);
    socket = currentSocket;
    currentSocket.addEventListener("message", event => {
        if (socket === currentSocket) onServerMessage(event);
    });
    currentSocket.addEventListener("close", event => handleSocketClose(event, currentSocket));
    currentSocket.addEventListener("error", () => {
        if (socket === currentSocket) setStatus("Reconectando...", "processing");
    });
}

/**
 * Crea la sesion de pedido y conecta el canal de conversacion.
 * @returns {Promise<void>} Se resuelve despues de solicitar la conexion.
 * @effects Reinicia los reintentos previos y prepara una sesion editable.
 */
async function createSession() {
    clearReconnectTimer();
    reconnectAttempts = 0;
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
 * Cierra la interfaz anterior y comienza automaticamente otro pedido.
 * @returns {Promise<void>} Crea y conecta una nueva sesion.
 * @effects Cancela el socket anterior sin reconectarlo y limpia la pantalla.
 */
async function startNewSession() {
    clearTimeout(paymentTimer);
    clearInterval(countdownTimer);
    voice.dispose();
    window.speechSynthesis?.cancel();
    closeSocketIntentionally();
    conversation.innerHTML = `<div class="message assistant-message"><span class="message-author">Asistente</span><p>Hola. Podés escribir tu pedido o tocar Hablar para comenzar.</p></div>`;
    sessionClosed = false;
    phase = "connecting";
    paymentContent.innerHTML = "";
    await createSession();
}

for (const button of document.querySelectorAll("[data-payment-method]")) {
    button.addEventListener("click", () => {
        const method = button.dataset.paymentMethod;
        const labels = { QR: "QR", CARD: "tarjeta", CASH: "caja" };
        sendMessage(`Quiero pagar con ${labels[method]}.`);
    });
}
confirmCartButton.addEventListener("click", startPaymentFromCart);

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
window.addEventListener("pagehide", () => { voice.dispose(); window.speechSynthesis?.cancel(); closeSocketIntentionally(); });
createSession();
