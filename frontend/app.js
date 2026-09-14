let sessionId = null;
let sessionClosed = false;

let socket = null;

let microphoneStream = null;
let microphoneEnabled = false;

let assistantAudioEnabled = true;

let audioContext = null;
let audioSource = null;
let audioProcessor = null;


const conversation =
    document.getElementById("conversation");

const messageForm =
    document.getElementById("message-form");

const messageInput =
    document.getElementById("message-input");

const sendButton =
    document.getElementById("send-button");

const cartItems =
    document.getElementById("cart-items");

const cartTotal =
    document.getElementById("cart-total");

const sessionState =
    document.getElementById("session-state");

const systemStatus =
    document.getElementById("system-status");

const micButton =
    document.getElementById("mic-button");

const audioButton =
    document.getElementById("audio-button");


function downsampleTo16K(
    inputBuffer,
    inputSampleRate
) {
    const targetSampleRate = 16000;

    if (inputSampleRate === targetSampleRate) {
        return inputBuffer;
    }

    const ratio =
        inputSampleRate / targetSampleRate;

    const outputLength = Math.round(
        inputBuffer.length / ratio
    );

    const outputBuffer =
        new Float32Array(outputLength);

    for (
        let outputIndex = 0;
        outputIndex < outputLength;
        outputIndex++
    ) {
        const inputIndex = Math.floor(
            outputIndex * ratio
        );

        outputBuffer[outputIndex] =
            inputBuffer[inputIndex];
    }

    return outputBuffer;
}


function convertFloat32ToInt16(
    floatBuffer
) {
    const int16Buffer =
        new Int16Array(floatBuffer.length);

    for (
        let index = 0;
        index < floatBuffer.length;
        index++
    ) {
        const sample = Math.max(
            -1,
            Math.min(
                1,
                floatBuffer[index]
            )
        );

        int16Buffer[index] =
            sample < 0
                ? sample * 32768
                : sample * 32767;
    }

    return int16Buffer;
}


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


function setInteractionEnabled(
    enabled
) {
    messageInput.disabled =
        !enabled;

    sendButton.disabled =
        !enabled;
}


async function enableMicrophone() {
    try {
        microphoneStream =
            await navigator.mediaDevices.getUserMedia(
                {
                    audio: true,
                }
            );

        microphoneEnabled = true;

        audioContext =
            new AudioContext();

        audioSource =
            audioContext.createMediaStreamSource(
                microphoneStream
            );

        audioProcessor =
            audioContext.createScriptProcessor(
                4096,
                1,
                1
            );

        audioProcessor.onaudioprocess =
            (event) => {
                if (
                    !microphoneEnabled
                    || !socket
                    || socket.readyState
                    !== WebSocket.OPEN
                ) {
                    return;
                }

                const inputData =
                    event.inputBuffer.getChannelData(
                        0
                    );

                const downsampled =
                    downsampleTo16K(
                        inputData,
                        audioContext.sampleRate
                    );

                const pcm16 =
                    convertFloat32ToInt16(
                        downsampled
                    );

                socket.send(
                    pcm16.buffer
                );
            };

        audioSource.connect(
            audioProcessor
        );

        audioProcessor.connect(
            audioContext.destination
        );

        micButton.textContent =
            "🎤 Mic ON";

        micButton.classList.add(
            "active"
        );

        console.log(
            "Micrófono habilitado.",
            microphoneStream
        );

    } catch (error) {
        console.error(
            "No se pudo acceder al micrófono:",
            error
        );

        microphoneEnabled = false;

        micButton.textContent =
            "🎤 Mic OFF";

        micButton.classList.remove(
            "active"
        );

        appendMessage(
            "Sistema",
            "No se pudo acceder al micrófono. Revisá los permisos del navegador.",
            "error"
        );
    }
}


function disableMicrophone() {
    microphoneEnabled = false;

    if (audioProcessor) {
        audioProcessor.disconnect();

        audioProcessor.onaudioprocess =
            null;

        audioProcessor = null;
    }

    if (audioSource) {
        audioSource.disconnect();
        audioSource = null;
    }

    if (audioContext) {
        audioContext.close();
        audioContext = null;
    }

    if (microphoneStream) {
        for (
            const track
            of microphoneStream.getTracks()
        ) {
            track.stop();
        }
    }

    microphoneStream = null;

    micButton.textContent =
        "🎤 Mic OFF";

    micButton.classList.remove(
        "active"
    );

    console.log(
        "Micrófono deshabilitado."
    );
}


async function toggleMicrophone() {
    if (microphoneEnabled) {
        disableMicrophone();
        return;
    }

    await enableMicrophone();
}


function toggleAssistantAudio() {
    assistantAudioEnabled =
        !assistantAudioEnabled;

    if (assistantAudioEnabled) {
        audioButton.textContent =
            "🔊 Voz ON";

        audioButton.classList.add(
            "active"
        );
    } else {
        audioButton.textContent =
            "🔇 Voz OFF";

        audioButton.classList.remove(
            "active"
        );
    }

    console.log(
        "Audio del asistente:",
        assistantAudioEnabled
    );
}


function connectWebSocket() {
    if (!sessionId) {
        return;
    }

    const protocol =
        window.location.protocol === "https:"
            ? "wss"
            : "ws";

    const socketUrl =
        `${protocol}://${window.location.host}`
        + `/ws/sessions/${sessionId}`;

    socket =
        new WebSocket(socketUrl);

    socket.addEventListener(
        "open",
        () => {
            console.log(
                "WebSocket conectado."
            );

            setStatus(
                "Listo",
                "ready"
            );

            setInteractionEnabled(
                true
            );

            messageInput.focus();
        }
    );

    socket.addEventListener(
        "message",
        (event) => {
            const message =
                JSON.parse(event.data);

            console.log(
                "Evento WebSocket:",
                message
            );

            if (
                message.type
                === "connection.ready"
            ) {
                return;
            }

            // -----------------------------------------
            // TEST TEMPORAL DE AUDIO
            // -----------------------------------------

            if (
                message.type
                === "audio.received"
            ) {
                console.log(
                    "Audio recibido por backend:",
                    message.data.bytes,
                    "bytes"
                );

                return;
            }

            // -----------------------------------------
            // ACTUALIZACIÓN DEL CARRITO
            // -----------------------------------------

            if (
                message.type
                === "cart.updated"
            ) {
                renderCart(
                    message.data.cart
                );

                return;
            }

            // -----------------------------------------
            // CONFIRMACIÓN DEL PEDIDO
            // -----------------------------------------

            if (
                message.type
                === "order.confirmed"
            ) {
                renderCart(
                    message.data.cart
                );

                sessionClosed = true;

                setStatus(
                    "Pedido confirmado",
                    "ready"
                );

                setInteractionEnabled(
                    false
                );

                messageInput.placeholder =
                    "El pedido ya fue confirmado.";

                return;
            }

            // -----------------------------------------
            // RESPUESTA DEL ASISTENTE
            // -----------------------------------------

            if (
                message.type
                === "assistant.text"
            ) {
                appendMessage(
                    "Asistente",
                    message.data.text,
                    "assistant"
                );

                if (!sessionClosed) {
                    setStatus(
                        "Listo",
                        "ready"
                    );

                    setInteractionEnabled(
                        true
                    );

                    messageInput.focus();
                }

                return;
            }

            // -----------------------------------------
            // ERROR DE GEMINI
            // -----------------------------------------

            if (
                message.type
                === "ai.error"
            ) {
                appendMessage(
                    "Sistema",
                    message.data.message,
                    "error"
                );

                setStatus(
                    `Error Gemini ${message.data.status_code || ""
                    }`,
                    "error"
                );

                if (!sessionClosed) {
                    setInteractionEnabled(
                        true
                    );

                    messageInput.focus();
                }

                return;
            }

            // -----------------------------------------
            // ERROR DEL BACKEND O DEL CLIENTE
            // -----------------------------------------

            if (
                message.type
                === "backend.error"
                || message.type
                === "client.error"
            ) {
                appendMessage(
                    "Sistema",
                    message.data.message,
                    "error"
                );

                setStatus(
                    "Error",
                    "error"
                );

                if (!sessionClosed) {
                    setInteractionEnabled(
                        true
                    );

                    messageInput.focus();
                }
            }
        }
    );

    socket.addEventListener(
        "close",
        () => {
            console.log(
                "WebSocket desconectado."
            );

            if (!sessionClosed) {
                setStatus(
                    "Sin conexión",
                    "error"
                );

                setInteractionEnabled(
                    false
                );
            }
        }
    );

    socket.addEventListener(
        "error",
        (error) => {
            console.error(
                "Error WebSocket:",
                error
            );

            setStatus(
                "Error de conexión",
                "error"
            );
        }
    );
}


async function createSession() {
    setStatus(
        "Iniciando...",
        "processing"
    );

    setInteractionEnabled(
        false
    );

    try {
        const response =
            await fetch(
                "/api/sessions",
                {
                    method: "POST",
                }
            );

        if (!response.ok) {
            throw new Error(
                `No se pudo crear la sesión (${response.status}).`
            );
        }

        const data =
            await response.json();

        sessionId =
            data.session_id;

        renderCart(
            data.cart
        );

        connectWebSocket();

    } catch (error) {
        console.error(
            error
        );

        setStatus(
            "Error interno",
            "error"
        );

        appendMessage(
            "Sistema",
            "No se pudo iniciar una nueva sesión de pedido.",
            "error"
        );
    }
}


function sendMessage(message) {
    if (
        !sessionId
        || sessionClosed
    ) {
        return;
    }

    if (
        !socket
        || socket.readyState
        !== WebSocket.OPEN
    ) {
        appendMessage(
            "Sistema",
            "La conexión con el backend no está disponible.",
            "error"
        );

        setStatus(
            "Sin conexión",
            "error"
        );

        return;
    }

    appendMessage(
        "Vos",
        message,
        "user"
    );

    setStatus(
        "Procesando...",
        "processing"
    );

    setInteractionEnabled(
        false
    );

    socket.send(
        JSON.stringify(
            {
                type: "user.text",
                data: {
                    message: message,
                },
            }
        )
    );
}


messageForm.addEventListener(
    "submit",
    (event) => {
        event.preventDefault();

        const message =
            messageInput.value.trim();

        if (!message) {
            return;
        }

        messageInput.value =
            "";

        sendMessage(
            message
        );
    }
);


micButton.addEventListener(
    "click",
    toggleMicrophone
);


audioButton.addEventListener(
    "click",
    toggleAssistantAudio
);


audioButton.classList.add(
    "active"
);


createSession();