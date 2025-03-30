document.addEventListener('DOMContentLoaded', function() {
    // Cerrar mensajes flash
    document.querySelectorAll('.close-flash').forEach(button => {
        button.addEventListener('click', function() {
            const flashMessage = this.closest('.flash-message');
            flashMessage.style.animation = 'slideOut 0.5s forwards';
            setTimeout(() => flashMessage.remove(), 500);
            });
        });
    });

    // Cerrar mensajes flash automáticamente después de 5 segundos
    const flashMessages = document.querySelectorAll('.flash-message');
    flashMessages.forEach(message => {
        setTimeout(() => {
            message.style.animation = 'slideOut 0.5s forwards';
            setTimeout(() => message.remove(), 500);
        }, 5000);
    });