from backend.ai.errors import AIProviderError
from backend.ai.orchestrator import OrderConversationOrchestrator
from backend.domain.menu import load_menu
from backend.domain.session import Session, SessionState
from backend.services.order_service import OrderService
from config.settings import get_chat_model


def print_cart(service: OrderService) -> None:
    """
    Muestra en terminal el estado real del carrito.

    Esta función se utiliza únicamente para debugging y no forma parte de
    la respuesta entregada al usuario.

    Args:
        service: Servicio de pedidos cuya sesión se desea inspeccionar.
    """
    cart = service.get_cart()

    print("\n[DEBUG - CARRITO REAL]")

    if not cart.items:
        print("Carrito vacío.")
    else:
        for item in cart.items:
            print(
                item.line_id,
                "-",
                item.product_name,
                "- cantidad:",
                item.quantity,
                "- modifiers:",
                item.selected_modifiers,
                "- precio:",
                item.unit_price,
            )

    print("Total:", cart.total)
    print("Estado:", service.session.state.value)


def print_ai_error(exc: AIProviderError) -> None:
    """
    Muestra un error de Gemini de forma legible y diagnóstica.

    Se separa el mensaje destinado al usuario de la información técnica que
    permite identificar proveedor, modelo, código HTTP y etapa del fallo.

    Args:
        exc: Error estructurado producido durante la comunicación con Gemini.
    """
    print("\n[ERROR IA]")

    print("Proveedor:", exc.provider)
    print("Modelo:", exc.model)
    print("Tipo:", exc.error_type)

    if exc.status_code is not None:
        print("HTTP:", exc.status_code)

    if exc.api_status:
        print("Estado API:", exc.api_status)

    print("Etapa:", exc.stage)
    print(
        "Operación aplicada:",
        "Sí" if exc.transaction_applied else "No",
    )

    if exc.last_tool:
        print("Última tool:", exc.last_tool)

    print(
        "Reintentable:",
        "Sí" if exc.retryable else "No",
    )

    print("Detalle Gemini:", exc.technical_message)

    print("\nMENSAJE PARA EL USUARIO:")
    print(exc.user_message)


def main() -> None:
    """
    Inicia una interfaz conversacional de terminal para probar el pedido.

    Mantiene una única sesión, un carrito y una conversación con Gemini.
    Los errores propios del proveedor se muestran por separado de errores
    internos del código. La ejecución finaliza cuando el usuario escribe
    "salir" o cuando el pedido queda confirmado.
    """
    menu = load_menu("config/menu.json")
    session = Session()
    service = OrderService(menu, session)

    assistant = OrderConversationOrchestrator(
        service=service,
        model=get_chat_model(),
    )

    print("Asistente de pedidos iniciado.")
    print(f"Session ID: {session.session_id}")
    print('Escribí "salir" para finalizar la prueba.')

    while True:
        print()

        message = input("USUARIO: ").strip()

        if message.lower() in {
            "salir",
            "exit",
            "quit",
        }:
            print("Prueba finalizada.")
            break

        if not message:
            continue

        try:
            response = assistant.send_message(
                message
            )

            print("\nGEMINI:")
            print(response)

        except AIProviderError as exc:
            print_ai_error(exc)

        except Exception as exc:
            print("\n[ERROR INTERNO]")
            print(
                "Este error no fue identificado como un error "
                "reportado por Gemini."
            )
            print("Tipo:", type(exc).__name__)
            print("Detalle:", exc)

        print_cart(service)

        if session.state == SessionState.CONFIRMED:
            print(
                "\nPedido confirmado. "
                "La sesión queda cerrada y no admite más modificaciones."
            )
            break


if __name__ == "__main__":
    main()
