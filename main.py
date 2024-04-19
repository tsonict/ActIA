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
db_pool = None


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

init_db()

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
        return jsonify({'error': 'Something wrong happend, try again'}), 500



def search_info(full_name):
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
                bio_info = search_bio(actor_id)
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

def search_bio(id):
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
        actor_info = search_info(res)
        if actor_info: 
            actor_info_list.append(actor_info)
    return actor_info_list

def find_face(unknown_face_encodings):

    results = []
    threshold = 0.6
    matches = []
    for unknown_face_encoding in unknown_face_encodings:
        # Compare 128D face array of unknown person within threshold 
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
                # Avoid same names
            for match in matches:
                if match not in results:
                    results.append(str(match))


    return results

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def correct_image_rotation(image_data):
    try:
        # Open the image with PILLOW
        image = Image.open(image_data)

        # Correct image
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

        # Save image in bytes
        corrected_image_data = BytesIO()
        image.save(corrected_image_data, format='JPEG')
        corrected_image_data.seek(0)

        return corrected_image_data

    except Exception as e:
        return jsonify({'error': 'Error while processing video'}), 500


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
        return jsonify({'error': 'Error processing video'}), 500



# Ruta para agregar rostros conocidos
@app.route('/add_known_face', methods=['POST'])
def add_known_face():
    if 'file' not in request.files:
        return jsonify({'error': 'No file was attached'}), 400

    file = request.files['file']
    name = request.form.get('name')

    # Verify image format
    if not file.filename.lower().endswith(('.png', '.jpg', '.jpeg')):
        return jsonify({'error': 'Wrong image format'}), 400

    # Load image
    image = face_recognition.load_image_file(file)
    face_encoding = face_recognition.face_encodings(image)[0]

    # Save the face encoding to the db
    if len(face_encoding) > 0:
        query = "INSERT INTO vectors (name, vec_low, vec_high) VALUES ('{}', CUBE(array[{}]), CUBE(array[{}])) RETURNING id".format(name,
                ','.join(str(s) for s in face_encoding[0:64]),
                ','.join(str(s) for s in face_encoding[64:128]),
            )

    return insert_Actor(query)


# Ruta para detectar y reconocer caras en una imagen
@app.route('/photo_recognition', methods=['POST'])
def detect_and_recognize_faces():
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'No se proporcionó ninguna imagen'}), 400
        # Obtain request file
        file = request.files['file']
        if not file.filename.lower().endswith(('.png', '.jpg', '.jpeg')):
            return jsonify({'error': 'Formato de imagen no admitido'}), 400
        # Open file
        try:
            image_data = BytesIO(file.read())
            # Correct file if uploaded with rn_imagepicker
            corrected_image_data = correct_image_rotation(image_data)

            if corrected_image_data != None:
                # Detect and recognize faces in the image
                unknown_image = face_recognition.load_image_file(corrected_image_data)
                unknown_face_locations = face_recognition.face_locations(unknown_image)
                unknown_face_encodings = face_recognition.face_encodings(unknown_image, unknown_face_locations)
            else:
                return jsonify({'error': 'Error while verifying image rotation'}), 400
            
        except Exception as e:
            return jsonify({'error': {str(e)}}), 400 

        results = find_face(unknown_face_encodings)
        #Get actor info from tmdb
        res_info = actor_info(results)

        return res_info
    except Exception as e:
        return jsonify({'error': 'Error while processing image, try again'}), 500

    
@app.route('/video_recognition', methods=['POST'])
def detect_and_recognize_faces_in_video():
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'No file was attached'}), 400

        file = request.files['file']

        if file.filename == '':
            return jsonify({'error': 'Not valid filename'}), 400

        if not file.filename.lower().endswith(('.mp4', '.avi', '.gif')):
            return jsonify({'error': 'Wrong video format'}), 400

        if file and allowed_file(file.filename):
            # Valid video extension
            filename = secure_filename(file.filename)

            # Create upload folder if not exists
            upload_folder = app.config['UPLOAD_FOLDER']
            os.makedirs(upload_folder, exist_ok=True)

            filepath = os.path.join(upload_folder, filename)
            file.save(filepath)
            # Verify if the file exists
            if not os.path.exists(filepath):
                return jsonify({'error': 'Error saving file'}), 500

            # Process video frames
            results = process_video_frames(filepath)

            os.remove(filepath)

            return actor_info(results)
        
    except Exception as e:
        return jsonify({'error': 'Error while processing video, try again'}), 500


    return jsonify({'error': 'Wrong video format'}), 400


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080)), debug=True)
    

    
    