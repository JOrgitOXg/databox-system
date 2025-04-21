# 📊 DataVox - Plataforma de Encuestas Inteligentes

![DataVox Logo](static/images/datavox-version-final-azul.svg)

DataVox es una plataforma web moderna para crear, gestionar y analizar encuestas con visualización de datos en tiempo real. Desarrollada con Flask y Firebase, ofrece autenticación segura, estadísticas avanzadas y compartir encuestas públicamente.

## ✨ Características Principales

- 🔐 **Autenticación segura** con Firebase Authentication
- 📝 **Creación de encuestas** con diferentes tipos de preguntas (abiertas, opción múltiple, rating)
- 📊 **Visualización de resultados** con gráficos interactivos (Chart.js)
- 🌐 **Compartir encuestas** públicamente o restringir a usuarios registrados
- 📱 **Diseño responsive** que funciona en cualquier dispositivo
- 📈 **Estadísticas avanzadas** con procesamiento de respuestas
- 🔄 **Sincronización en tiempo real** con Firestore

## 🛠️ Tecnologías Utilizadas

- **Frontend**: HTML5, CSS3, Tailwind CSS, JavaScript
- **Backend**: Python, Flask
- **Base de Datos**: Firebase Firestore
- **Autenticación**: Firebase Authentication
- **Gráficos**: Chart.js
- **Despliegue**: Render/Firebase Hosting (configurable)

## 🚀 Instalación y Configuración

### Requisitos Previos

- Python 3.9 o superior
- Pip (gestor de paquetes de Python)
- Cuenta de Firebase con proyecto configurado
- Navegador web moderno (Chrome, Firefox, Edge)

### Pasos para Instalación

1. **Clonar el repositorio**:
   ```bash
   git clone https://github.com/tuusuario/datavox.git
   cd datavox

## 🛠️ Configuración y Ejecución

### Instalación de dependencias
```bash
pip install -r requirements.txt
Configurar Firebase:

Descargar el archivo serviceAccountKey.json desde Firebase Console

Colocarlo en el directorio raíz del proyecto

SECRET_KEY=tu_clave_secreta_aqui
FIREBASE_WEB_API_KEY=tu_api_key_de_firebase
Ejecutar la aplicación:

bash
python run.py