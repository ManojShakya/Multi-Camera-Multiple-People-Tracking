from flask import Flask, request, jsonify,send_from_directory
from flask_cors import CORS
import pickle
import pika
import logging
import datetime
import os


app = Flask(__name__)
CORS(app)

# Function to send logs to RabbitMQ
def send_log_to_rabbitmq(log_message):
    try:
        connection = pika.BlockingConnection(pika.ConnectionParameters(host='localhost', heartbeat=600))
        channel = connection.channel()
        channel.queue_declare(queue='anpr_logs')
        
        # Serialize the log message as JSON and send it to RabbitMQ
        channel.basic_publish(
            exchange='',
            routing_key='anpr_logs',
            body=pickle.dumps(log_message)
        )
        connection.close()
    except Exception as e:
        print(f"Failed to send log to RabbitMQ: {e}")

# Wrapper functions for different log levels
def log_info(message):
    logging.info(message)
    current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    message_data = {
        "log_level" : "INFO",
        "Event_Type":"Push RTSPULR into Queue by API",
        "Message":message,
        "datetime" : current_time,

    }
    send_log_to_rabbitmq(message_data)

def log_exception(message):
    logging.error(message)
    current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    message_data = {
        "log_level" : "EXCEPTION",
        "Event_Type":"Push RTSPULR into Queue by API",
        "Message":message,
        "datetime" :current_time,

    }
    send_log_to_rabbitmq(message_data)


# class RabbitMQLogger:
#     def __init__(self, host='localhost', queue='comman_api_logs'):
#         self.host = host
#         self.queue = queue
#         self.connection = None
#         self.channel = None
#         self._connect()

#     def _connect(self):
#         try:
#             self.connection = pika.BlockingConnection(
#                 pika.ConnectionParameters(host=self.host, heartbeat=600)
#             )
#             self.channel = self.connection.channel()
#             self.channel.queue_declare(queue=self.queue)
#             print("[RabbitMQ] Connection established.")
#         except Exception as e:
#             print(f"[RabbitMQ] Failed to connect: {e}")
#             self.connection = None
#             self.channel = None

#     def _is_connected(self):
#         return self.connection and self.connection.is_open and self.channel

#     def send_log(self, log_message):
#         try:
#             if not self._is_connected():
#                 print("[RabbitMQ] Reconnecting...")
#                 self._connect()

#             if self._is_connected():
#                 self.channel.basic_publish(
#                     exchange='',
#                     routing_key=self.queue,
#                     body=pickle.dumps(log_message)
#                     )
#                 print("This is log masseage :", log_message)    
#             else:
#                 print("[RabbitMQ] Unable to send log, connection not available.")
#         except Exception as e:
#             print(f"[RabbitMQ] Error sending log: {e}")
#             # Optionally reset the connection on error
#             self.connection = None
#             self.channel = None


# # Instantiate a single logger object to use throughout
# rabbitmq_logger = RabbitMQLogger()


# # Wrapper functions for different log levels
# def log_info(message):
#     logging.info(message)
#     current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
#     message_data = {
#         "log_level": "INFO",
#         "Event_Type": "Push RTSPULR into Queue by API",
#         "Message": message,
#         "datetime": current_time,
#     }
#     rabbitmq_logger.send_log(message_data)


# def log_exception(message):
#     logging.error(message)
#     current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
#     message_data = {
#         "log_level": "EXCEPTION",
#         "Event_Type": "Push RTSPULR into Queue by API",
#         "Message": message,
#         "datetime": current_time,
#     }
#     rabbitmq_logger.send_log(message_data)


@app.route('/CommanApiStart', methods=['POST'])
def update_camera_details():
    data = request.get_json()
    print("This is data:",data)

    cameras = data.get("cameras", [])
    if not cameras:
        log_exception("No cameras provided in the request.")
        return jsonify({"error": "No cameras provided!"}),

    for camera in cameras:
        required_fields = ["camera_id", "url"]

        if not all(field in camera for field in required_fields):
            missing_fields = [field for field in required_fields if field not in camera]
            log_exception(f"Missing required fields: {missing_fields} for camera {camera.get('camera_id', 'Unknown')}!")
            return jsonify({"error": f"Missing required fields in camera details for camera {camera.get('camera_id')}!"}), 400

        camera_id = camera["camera_id"]
        camera_url = camera["url"]
        running = camera.get("running", False)
        user_id = camera["user_id"]
        objectlist = camera.get("objectlist", "[]")
        objectlist_lower = objectlist.lower()
        print("This is object list :", objectlist, type(objectlist))

        # Connect to RabbitMQ
        try:
            connection = pika.BlockingConnection(pika.ConnectionParameters(host='localhost', heartbeat=600))
            channel = connection.channel()
            log_info(f"Connected to RabbitMQ for camera {camera_id}.")
            try:
                # # Declare the queue passively (will throw an exception if the queue doesn't exist)
                # channel.queue_declare(queue='rtspurl_for_rdas', passive=True)
                # Declare an exchange
                channel.exchange_declare(exchange='rtspurl_for_framer', exchange_type='fanout')
            except pika.exceptions.ChannelClosedByBroker:
                channel = connection.channel()
                channel.exchange_declare(exchange='rtspurl_for_framer', exchange_type='fanout')
                log_info(f"Queue 'rtspurl_from_api_db' declared successfully.")
        except Exception as e:
            log_exception(f"Failed to connect to RabbitMQ for camera {camera_id}: {e}")
            return jsonify({"error": "Failed to connect to RabbitMQ!"}), 500

        frame_data = {
            "CameraId": camera_id,
            "CameraUrl": camera_url,
            "Running": running,
            "UserId": user_id,
            "ObjectList": objectlist_lower
            
        }
        serialized_frame = pickle.dumps(frame_data)
        print("This is frame_data :", frame_data)

        # Send the frame to the queue
        try:
            channel.basic_publish(
                exchange="rtspurl_for_framer",
                routing_key="",
                body=serialized_frame
            )
            log_info(f"Sent a frame from camera {camera_id} to RabbitMQ queue.")
        except Exception as e:
            log_exception(f"Failed to publish message for camera {camera_id}: {e}")

    log_info("Cameras added/updated successfully.")
    return jsonify({"message": "Cameras added/updated successfully!"}), 201

@app.route('/app/<folder>/<camera_id>/<filename>')
def get_image(folder,camera_id, filename):
    print(camera_id,filename)
    camera_folder = os.path.join(os.path.join(os.getcwd(), folder),camera_id)
    print(camera_folder)
    return send_from_directory(camera_folder, filename)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=6565, debug=True)
