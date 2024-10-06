from flask import Flask, render_template, request, url_for, redirect, jsonify, session
from flask_cors import CORS
from PIL import Image
import tensorflow as tf
import numpy as np
import pandas as pd
import os
from langchain_community.llms import Ollama
from database.models import Users
from database.conexion import db, init_app
from flask_bcrypt import Bcrypt

csv_file = 'dataset_clean_one_hot.csv'
df = pd.read_csv(csv_file)
class_labels = df.columns[1:] # La primera columna es 'image', el resto son las etiquetas one-hot

app = Flask(__name__)
cors = CORS(app, origins='*')
bcrypt = Bcrypt(app)

# Inicializar la base de datos
init_app(app)

model_path = '/home/erich/Universidad/CookingWithAI/server/modeloEntrenado'
if os.path.exists(model_path):
    print(f'La ruta {model_path} es válida y existe.')
    # Cargar el modelo
    model = tf.keras.models.load_model(model_path)
    print("Modelo cargado correctamente.")
else:
    print(f'La ruta {model_path} no existe o es incorrecta.')

ollama = Ollama(
    base_url='http://localhost:11434',
    model="gemma2:2b"
)

# Función para preprocesar la imagen
def preprocess_image(image):
    # Convertir cualquier imagen a RGB para garantizar que tenga 3 canales
    if image.mode != 'RGB':
        image = image.convert('RGB')
        
    # Redimensionar la imagen al tamaño usado en el entrenamiento
    image = image.resize((224, 224))
    
    # Convertir la imagen a un array de NumPy
    img_array = np.array(image)
    
    # Asegurar que la imagen tenga las dimensiones correctas (224, 224, 3)
    img_array = np.expand_dims(img_array, axis=0)  # Añadir una dimensión extra para el batch
    
    # Normalizar los valores de píxeles (0 a 255) a (0.0 a 1.0)
    img_array = img_array / 255.0
    
    return img_array


# # Obtener los ingredientes a partir de la imagen utilizando el modelo entrenado
# def get_ingredients_from_image(image):
#     img_array = preprocess_image(image)
    
#     # Realizar la predicción del modelo
#     predictions = model.predict(img_array)
    
#     # Imprimir las predicciones para depurar
#     print(f"Predicciones: {predictions}")
    
#     # Reducir el umbral a 0.3 para ver si el modelo detecta más ingredientes
#     threshold = 0.01
    
#     # Convertir las probabilidades a etiquetas binarias (1 si la probabilidad es mayor que el umbral, 0 si no)
#     predicted_labels = (predictions > threshold).astype(int)
    
#     # Imprimir las etiquetas predichas
#     print(f"Etiquetas predichas: {predicted_labels}")
    
#     # Obtener los ingredientes correspondientes a las etiquetas con valor 1
#     ingredients = [class_labels[i] for i in range(len(predicted_labels[0])) if predicted_labels[0][i] == 1]
    
#     # Si no se detectan ingredientes, imprimir un mensaje adicional para depuración
#     if not ingredients:
#         print("No se detectaron ingredientes con el umbral actual.")
    
#     return ingredients

def get_ingredients_from_image(image):
    img_array = preprocess_image(image)
    predictions = model.predict(img_array)  # Hacer la predicción
    
    # Obtener las etiquetas predichas usando un umbral
    predicted_labels = (predictions > 0.1).astype(int)  # Umbral de 0.5 para convertir a etiquetas
    print(f"Predicciones: {predictions}")
    print(f"Etiquetas predichas: {predicted_labels}")

    # Obtener los ingredientes correspondientes a las etiquetas predichas
    ingredients = [class_labels[i] for i in range(len(predicted_labels[0])) if predicted_labels[0][i] == 1]
    return ingredients  # Devolver la lista de ingredientes


# Ruta principal de la app
@app.route('/')
def index():
    return "Falta hacer el front..."

app.secret_key = os.urandom(24)

@app.route('/consulta_ollama', methods=['POST'])
def consulta_ollama():
    try:
        # Verificar si hay texto en la solicitud
        text = request.form.get('text', '')
        
        # Verificar si hay una imagen en la solicitud
        images = request.files.getlist('images')

        if text:
            prompt = f"Dame una receta sencilla con el/los siguientes ingredientes: {text}. Evita incluir elementos no relacionados o creativos."
            generated_text = ollama.invoke(prompt)
            return jsonify({'results': f'Receta generada para los ingredientes: {generated_text}'})

        elif images:
            all_ingredients = []
            
            for image_file in images:
                image = Image.open(image_file)
                ingredients = get_ingredients_from_image(image)
                print(f"Ingredientes predichos: {ingredients}")

                if not ingredients:
                    return jsonify({'error': 'No se detectaron ingredientes en una o más imágenes.'})

                # Agregar ingredientes detectados a la lista total
                all_ingredients.extend(ingredients)
            
            # Eliminar duplicados
            all_ingredients = list(set(all_ingredients))

            if all_ingredients:
                prompt = f"Dame una receta sencilla con los siguientes ingredientes: {', '.join(all_ingredients)}. Evita incluir elementos no relacionados o creativos."
                generated_text = ollama.invoke(prompt)
                return jsonify({'response': generated_text})
            else:
                return jsonify({'error': 'No se detectaron ingredientes en las imágenes.'})

        else:
            return jsonify({'error': 'No se recibió ni texto ni imágenes.'})

    except Exception as e:
        return jsonify({'error': str(e)})


@app.route('/register', methods=['POST'])
def register():
    data = request.get_json()  # Obtener los datos en formato JSON desde el frontend
    
    username = data.get('username')
    email = data.get('email')
    password = data.get('password')
    
    # Encriptamos la contraseña
    password_hash = bcrypt.generate_password_hash(password).decode('utf-8')
    
    # Verificamos si el usuario ya existe
    if Users.query.filter_by(username=username).first() is not None:
        return jsonify({'message': 'El nombre de usuario ya existe'}), 400
    if Users.query.filter_by(email=email).first() is not None:
        return jsonify({'message': 'El correo electrónico ya está registrado'}), 400
    
    # Creamos y agregamos el nuevo usuario a la base de datos
    new_user = Users(username=username, email=email, password=password_hash)
    db.session.add(new_user)
    db.session.commit()

    return jsonify({'message': 'Usuario registrado exitosamente'}), 200


# Ruta para listar los usuarios registrados dentro de la bdd
# no tiene uso, sirve para verificar que los usuarios se crean
# y se agregan de manera correcta
@app.route('/usuarios')
def get_usuarios():
    try:
        usuarios = Users.query.all()
        return f"Usuarios: {[usuario.username for usuario in usuarios]}"
    except Exception as e:
        return str(e), 500

# Si el usuario quiere ingresar a cualquier pagina que no este
# definida, se lo redirecciona al inicio
def pagina_no_encotrada(error):
    # return render_template('404.html'), 404 (opcion para mostrar un index personalizado en vez de solo redireccionar)
    return redirect(url_for('index'))

# Ruta para manejar el inicio de sesión
@app.route('/login', methods=['POST'])
def login():
    data = request.get_json()  # Recibe los datos en formato JSON
    email = data.get('email')
    password = data.get('password')
    
    # Verificar si el usuario existe en la base de datos
    user = Users.query.filter_by(email=email).first()
    
    if user is None:
        return jsonify({'message': 'El usuario no existe'}), 401  # Usuario no encontrado
    
    # Verificar si la contraseña es correcta
    if not bcrypt.check_password_hash(user.password, password):
        return jsonify({'message': 'Las credenciales no coinciden'}), 401  # Contraseña incorrecta
    
    # Si las credenciales son correctas, iniciar sesión
    session['user_id'] = user.id
    return jsonify({'message': 'Inicio de sesión exitoso'}), 200


@app.route('/logout', methods=['POST'])
def logout():
    session.pop('user_id', None)
    session['logged_in'] = False
    return jsonify({'message': 'Cierre de sesión exitoso'}), 200

@app.route('/check_session', methods=['GET'])
def check_session():
    if 'logged_in' in session and session['logged_in']:
        return jsonify({'logged_in': True}), 200
    else:
        return jsonify({'logged_in': False}), 200


if __name__ == "__main__":
    from database.conexion import create_db
    create_db()
    # Manejamos los errores con el metodo que creamos
    app.register_error_handler(404, pagina_no_encotrada)
    app.run(debug=True)