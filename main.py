from flask import Flask, request, jsonify, Response
from io import BytesIO
from PIL import Image
from google.cloud.sql.connector import Connector, IPTypes
import pg8000
import sqlalchemy
from werkzeug.utils import secure_filename
from dotenv import load_dotenv
import requests
import face_recognition
import cv2
import numpy as np
import os
import logging


# Cargar variables de entorno desde el archivo .env
load_dotenv()

app = Flask(__name__)

logger = logging.getLogger()

ALLOWED_EXTENSIONS = {'mp4', 'avi', 'mov', 'gif'}
API_KEY = os.getenv("API_KEY")
API_BIO = os.getenv("API_BIO")
# Configuración de la carpeta de carga
UPLOAD_FOLDER = 'uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER



def connect_with_connector() -> sqlalchemy.engine.base.Engine:
    """
    Initializes a connection pool for a Cloud SQL instance of Postgres.

    Uses the Cloud SQL Python Connector package.
    """
    # Note: Saving credentials in environment variables is convenient, but not
    # secure - consider a more secure solution such as
    # Cloud Secret Manager (https://cloud.google.com/secret-manager) to help
    # keep secrets safe.

    instance_connection_name = os.environ[
        "INSTANCE_CONNECTION_NAME"
    ]  # e.g. 'project:region:instance'
    db_user = os.environ["DB_USER"]  # e.g. 'my-db_pool-user'
    db_pass = os.environ["DB_PASS"]  # e.g. 'my-db_pool-password'
    db_name = os.environ["DB_NAME"]  # e.g. 'my-database'

    ip_type = IPTypes.PRIVATE if os.environ.get("PRIVATE_IP") else IPTypes.PUBLIC

    # initialize Cloud SQL Python Connector object
    connector = Connector()

    def getconn() -> pg8000.dbapi.Connection:
        conn: pg8000.dbapi.Connection = connector.connect(
            instance_connection_name,
            "pg8000",
            user=db_user,
            password=db_pass,
            db=db_name,
            ip_type=ip_type,
        )
        return conn
    
    pool = sqlalchemy.create_engine(
    "postgresql+pg8000://",
    creator=getconn,
    # [START_EXCLUDE]
    # Pool size is the maximum number of permanent connections to keep.
    pool_size=5,
    # Temporarily exceeds the set pool_size if no connections are available.
    max_overflow=2,
    # The total number of concurrent connections for your application will be
    # a total of pool_size and max_overflow.
    # 'pool_timeout' is the maximum number of seconds to wait when retrieving a
    # new connection from the pool. After the specified amount of time, an
    # exception will be thrown.
    pool_timeout=30,  # 30 seconds
    # 'pool_recycle' is the maximum number of seconds a connection can persist.
    # Connections that live longer than the specified amount of time will be
    # re-established
    pool_recycle=1800,  # 30 minutes
    # [END_EXCLUDE]
    )
    return pool

def init_db () -> sqlalchemy.engine.base.Engine:
    global db_pool
    if db_pool is None:
        db_pool = connect_with_connector()
        migrate_db(db_pool)


def migrate_db(db_pool: sqlalchemy.engine.base.Engine) -> None:
    with db_pool.connect() as conn:
        tmp = conn.execute(sqlalchemy.text("SELECT EXISTS(SELECT 1 FROM pg_extension WHERE extname = 'cube');")).fetchone()
        extension_exists = tmp[0]
        if not extension_exists:
            conn.execute(sqlalchemy.text("CREATE EXTENSION cube;"))


        tmp = conn.execute(sqlalchemy.text("SELECT EXISTS(SELECT 1 FROM information_schema.tables WHERE table_name = 'vectors');")).fetchone()
        table_exists = tmp[0]
        if not table_exists:
            conn.execute(sqlalchemy.text("CREATE TABLE vectors (id serial, name varchar(50), vec_low cube, vec_high cube, UNIQUE(name));"))
            conn.execute(sqlalchemy.text("CREATE INDEX vectors_vec_idx ON vectors (vec_low, vec_high);"))

        conn.commit()

def insert_Actor(query) -> Response:
    # Intentar conectar a la base de datos
    try:
        with db_pool.connect() as conn:
            conn.execute(sqlalchemy.text(str(query)))
            conn.commit()

    except Exception as e:
        logger.exception(e)
        return Response(status=500, response="Unable to successfully add an actor Please check the "
            "application logs for more details.")
    
    return Response(status=200, response="Actor Agregado")





def get_ActorData(query):
    # Intentar conectar a la base de datos
    try:

        with db_pool.connect() as conn:
            tmp = conn.execute(sqlalchemy.text(str(query))).fetchone()

            if tmp != None:
                result = tmp[0]

            else:
                result = None

            conn.commit()
        return result

    except Exception as e:
        return jsonify({'error': 'Ocurrio un problema, intentalo de nuevo'})



def buscar_info(full_name):
    try:
        url = f"https://api.themoviedb.org/3/search/person?query={full_name}&include_adult=false&language=en-US&page=1"
        headers = {
            "accept": "application/json",
            "Authorization": f"Bearer {API_KEY}"
        }
        response = requests.get(url, headers=headers)
        data = response.json()

        if 'results' in data and data['results']:
            result = data['results'][0]
            actor_id = result.get('id')

            if actor_id:
                bio_info = buscar_bio(actor_id)
                if bio_info:
                    combined_info = {**result, **bio_info}
                    return combined_info
    except requests.RequestException as e:
        return(f"Error en la solicitud: {e}")
    except KeyError:
        return("Error: No se encontraron resultados.")
    except Exception as e:
        return(f"Error desconocido: {e}")
        
    return {}

def buscar_bio(id):
    try:
        url = f"https://api.themoviedb.org/3/person/{id}?api_key={API_BIO}&language=en-US"
        response = requests.get(url)
        data = response.json()
        return {'biography': data.get('biography', '')}
    except requests.RequestException as e:
        return(f"Error en la solicitud: {e}")
    except KeyError:
        return("Error: No se encontraron resultados.")
    except Exception as e:
        return(f"Error desconocido: {e}")
    
    return {}


def actor_info(results):
    if len(results) == 0:
        return []
    actor_info_list = []
    for res in results:
        actor_info = buscar_info(res)
        if actor_info: 
            actor_info_list.append(actor_info)
    return actor_info_list

def find_face(unknown_face_encodings):
            # Resultados del reconocimiento
    results = []
    threshold = 0.6
    matches = []
    for unknown_face_encoding in unknown_face_encodings:
        # Comparar rostro desconocido con los conocidos en la DB
        query = "SELECT name FROM public.vectors WHERE sqrt(power(CUBE(array[{}]) <-> vec_low, 2) + power(CUBE(array[{}]) <-> vec_high, 2)) <= {} ".format(
                ','.join(str(s) for s in unknown_face_encoding[0:64]),
                ','.join(str(s) for s in unknown_face_encoding[64:128]),
                threshold,
            ) + \
                    "ORDER BY sqrt(power(CUBE(array[{}]) <-> vec_low, 2) + power(CUBE(array[{}]) <-> vec_high, 2)) ASC".format(
                        ','.join(str(s) for s in unknown_face_encoding[0:64]),
                        ','.join(str(s) for s in unknown_face_encoding[64:128]),
                    )
        tmp = str(get_ActorData(query))
        if tmp != 'None':
            matches.append(tmp)
            print("Matches: ", matches)
                # Si encontramos una coincidencia, usar el nombre asociado al rostro conocido
            for match in matches:
                if match not in results:
                    results.append(str(match))
        #Evaluar si no se encuentra el actor


    return results

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def corregir_orientacion(image_data):
    try:
        # Abrir la imagen utilizando PIL
        image = Image.open(image_data)

        # Corregir la orientación
        if hasattr(image, '_getexif'):
            exif = image._getexif()
            if exif is not None:
                orientation = exif.get(0x0112)
                if orientation is not None:
                    if orientation == 3:
                        image = image.rotate(180, expand=True)
                    elif orientation == 6:
                        image = image.rotate(270, expand=True)
                    elif orientation == 8:
                        image = image.rotate(90, expand=True)

        image = image.convert('RGB')

        # Guardar la imagen en BytesIO para enviarla a face_recognition
        corrected_image_data = BytesIO()
        image.save(corrected_image_data, format='JPEG')
        corrected_image_data.seek(0)

        return corrected_image_data

    except Exception as e:
        return jsonify({'error': 'Error al procesar el video'}), 500


def process_frame(frame, results):
    small_frame = cv2.resize(frame, (0, 0), fx=0.25, fy=0.25)
    rgb_small_frame = np.ascontiguousarray(small_frame[:, :, ::-1])
    face_locations = face_recognition.face_locations(rgb_small_frame)
    face_encodings = face_recognition.face_encodings(rgb_small_frame, face_locations)

    if len(face_locations) == 0:
        return results

    tmp = find_face(face_encodings)
    for s in tmp:
        if s not in results:
            results.append(s)

    return results

def process_video_frames(video_path):
    try:
        capturar_frames = cv2.VideoCapture(video_path)
        total_frames = int(capturar_frames.get(cv2.CAP_PROP_FRAME_COUNT))

        results = []
        for fno in range(0, total_frames, int(total_frames * 0.15)):
            capturar_frames.set(cv2.CAP_PROP_POS_FRAMES, fno)
            _, image = capturar_frames.read()
            results = process_frame(image, results)
        print(results)
        return results
 
    except Exception as e:
        return jsonify({'error': 'Error al procesar el video'}), 500



# Ruta para agregar rostros conocidos
@app.route('/add_known_face', methods=['POST'])
def add_known_face():
    if 'file' not in request.files:
        return jsonify({'error': 'No se proporcionó ninguna imagen'}), 400

    file = request.files['file']
    name = request.form.get('name')

    # Asegúrate de que la imagen tenga una extensión válida
    if not file.filename.lower().endswith(('.png', '.jpg', '.jpeg')):
        return jsonify({'error': 'Formato de imagen no admitido'}), 400

    # Leer la imagen y convertirla a un formato adecuado para face_recognition
    image = face_recognition.load_image_file(file)
    face_encoding = face_recognition.face_encodings(image)[0]

    # Almacenar el rostro conocido con su nombre asociado
    if len(face_encoding) > 0:
        query = "INSERT INTO vectors (name, vec_low, vec_high) VALUES ('{}', CUBE(array[{}]), CUBE(array[{}])) RETURNING id".format(name,
                ','.join(str(s) for s in face_encoding[0:64]),
                ','.join(str(s) for s in face_encoding[64:128]),
            )

    return insert_Actor(query)


# Ruta para detectar y reconocer caras en una imagen
@app.route('/detect_and_recognize_faces', methods=['POST'])
def detect_and_recognize_faces():
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'No se proporcionó ninguna imagen'}), 400
        # Obtener datos del formulario multipart
        file = request.files['file']
        if not file.filename.lower().endswith(('.png', '.jpg', '.jpeg')):
            return jsonify({'error': 'Formato de imagen no admitido'}), 400
        # Verificar si se puede abrir la imagen correctamente
        try:
            image_data = BytesIO(file.read())
            # Corregir la orientación de la imagen
            corrected_image_data = corregir_orientacion(image_data)

            if corrected_image_data != None:
                # Detección y reconocimiento de caras
                unknown_image = face_recognition.load_image_file(corrected_image_data)
                unknown_face_locations = face_recognition.face_locations(unknown_image)
                unknown_face_encodings = face_recognition.face_encodings(unknown_image, unknown_face_locations)
            else:
                # Manejar el caso en que no se pudo corregir la orientación
                return jsonify({'error': 'Error al corregir la orientación de la imagen'}), 400
            
        except Exception as e:
            return jsonify({'error': {str(e)}}), 400  # Bad Request

        results = find_face(unknown_face_encodings)
        print("len res: ", len(results))
        print("Results:", results)
        res_info = actor_info(results)
        print("res_info: ", res_info)
        return res_info
    except Exception as e:
        return jsonify({'error': 'Error al procesar la imagen, intentelo de nuevo'}), 500

    
@app.route('/reconocimiento_video', methods=['POST'])
def detect_and_recognize_faces_in_video():
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'No se proporcionó ningún video'}), 400

        file = request.files['file']

        if file.filename == '':
            return jsonify({'error': 'Nombre de archivo vacío'}), 400

        if not file.filename.lower().endswith(('.mp4', '.avi', '.gif')):
            return jsonify({'error': 'Formato de imagen no admitido'}), 400

        if file and allowed_file(file.filename):
            # Extensión válida de video
            filename = secure_filename(file.filename)

            # Verificar y crear el directorio si no existe
            upload_folder = app.config['UPLOAD_FOLDER']
            os.makedirs(upload_folder, exist_ok=True)

            filepath = os.path.join(upload_folder, filename)
            file.save(filepath)
            # Verificar si el archivo existe después de guardarlo
            if not os.path.exists(filepath):
                return jsonify({'error': 'Error al guardar el archivo'}), 500

            # Procesar fotogramas del video
            results = process_video_frames(filepath)

            os.remove(filepath)

            return actor_info(results)
        
    except Exception as e:
        return jsonify({'error': 'Error al procesar el video, intentelo de nuevo'}), 500


    return jsonify({'error': 'Formato de video no admitido'}), 400


if __name__ == '__main__':
    init_db()
    app.run(host='127.0.0.1', port=8080, debug=False)
    

    
    