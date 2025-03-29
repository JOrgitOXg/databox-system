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
    
    // Manejar navegación con AJAX para una experiencia más fluida
// En tu main.js, modifica el manejador de clicks para links
document.addEventListener('click', function(e) {
    const link = e.target.closest('a');
    if (link && link.href && !link.href.startsWith('javascript:') && 
        !link.href.startsWith('#') && !link.classList.contains('no-ajax') &&
        !e.ctrlKey && !e.metaKey && (!link.target || link.target !== '_blank')) {
        
        // Solo manejar AJAX para links que no son de logout o acciones críticas
        if (!link.href.includes('logout') && !link.href.includes('delete')) {
            e.preventDefault();
            showLoading();
            
            fetch(link.href, {
                headers: { 'X-Requested-With': 'XMLHttpRequest' }
            })
            .then(response => response.text())
            .then(html => {
                document.open();
                document.write(html);
                document.close();
            })
            .catch(() => {
                window.location.href = link.href;
            })
            .finally(() => {
                hideLoading();
            });
        }
    }
});