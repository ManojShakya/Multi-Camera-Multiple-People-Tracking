import pika
import cv2
import pickle  # To deserialize and serialize frames
import struct  # To handle frame size unpacking
from ultralytics import YOLO
import os
import datetime
import logging
import time
from reid_model import extract_reid_feature
import numpy as np

gallery = []  # List of (id, feature)
next_reid = 0

# Load YOLOv10 model
model_path = "yolov10n.pt"
model = YOLO(model_path)
# Function to send logs to RabbitMQ
def send_log_to_rabbitmq(log_message):
    try:
        connection = pika.BlockingConnection(pika.ConnectionParameters(host='localhost',heartbeat=600))
        channel = connection.channel()
        channel.queue_declare(queue='anpr_logs')  # Declare the queue for logs
        # Serialize the log message as JSON and send it to RabbitMQ
        channel.basic_publish(
            exchange='',
            routing_key='anpr_logs',
            body=pickle.dumps(log_message)
        )
        connection.close()
    except Exception as e:
        print(f"Failed to send log to RabbitMQ: {e}")

# Wrapper functions for logging and sending logs to RabbitMQ
def log_info(message):
    logging.info(message)
    current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    message_data = {
        "log_level" : "INFO",
        "Event_Type":"Numbper Plate detection event",
        "Message":message,
        "datetime" : current_time,

    }
    send_log_to_rabbitmq(message_data)

def log_error(message):
    logging.info(message)
    current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    message_data = {
        "log_level" : "ERROR",
        "Event_Type":"Numbper Plate detection event",
        "Message":message,
        "datetime" : current_time,

    }
    send_log_to_rabbitmq(message_data)    

def log_exception(message):
    logging.error(message)
    current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    message_data = {
        "log_level" : "EXCEPTION",
        "Event_Type":"Numbper Plate detection event",
        "Message":message,
        "datetime" : current_time,

    }
    send_log_to_rabbitmq(message_data)



def setup_rabbitmq_connection(queue_name, rabbitmq_host, retries=5, retry_delay=5):
    """
    Set up a RabbitMQ connection and declare the queue.
    """
    for attempt in range(retries):
        try:
            connection = pika.BlockingConnection(pika.ConnectionParameters(host=rabbitmq_host, heartbeat=600))
            channel = connection.channel()
            channel.exchange_declare(exchange=queue_name, exchange_type="fanout")
            log_info(f"Connected to RabbitMQ at {rabbitmq_host}")
            return connection, channel
        except pika.exceptions.AMQPConnectionError as e:
            log_error(f"RabbitMQ connection failed (attempt {attempt+1}/{retries}): {e}")
            time.sleep(retry_delay)
    raise log_exception(f"Could not connect to RabbitMQ after {retries} attempts")



def match_reid(feature, threshold=0.6):
    global next_reid
    best_id, best_dist = -1, float('inf')
    for pid, feat in gallery:
        dist = np.linalg.norm(feature - feat)
        if dist < best_dist:
            best_id, best_dist = pid, dist
    if best_dist < threshold:
        return best_id
    else:
        gallery.append((next_reid, feature))
        assigned_id = next_reid
        next_reid += 1
        return assigned_id

def process_frame(ch, method, properties, body, processed_queue_name, rabbitmq_host):
    """
    Callback function to process the received frames from RabbitMQ.

    Args:
        ch, method, properties: RabbitMQ parameters.
        body: The serialized frame data received from the queue.
        processed_channel: RabbitMQ channel for sending processed frames.
    """
    global obj_list

    #processed_connection, processed_channel = setup_rabbitmq_connection(processed_queue_name, rabbitmq_host)
    # Load and print BoT-SORT config values
    tracker_config_path = "botsort.yaml"
    # if not os.path.exists(tracker_config_path):
    #     raise FileNotFoundError(f"Tracker config not found: {tracker_config_path}")

    # with open(tracker_config_path, 'r') as f:
    #     tracker_config = yaml.safe_load(f)

    # print("BoT-SORT Config:")
    # print(f"  with_reid       : {tracker_config.get('with_reid')}")
    # print(f"  track_buffer    : {tracker_config.get('track_buffer')}")
    # print(f"  new_track_thresh: {tracker_config.get('new_track_thresh')}")
    # print(f"  reid_weights    : {tracker_config.get('reid_weights')}")

    try:
        # Deserialize the frame and metadata
        frame_data = pickle.loads(body)
        camera_id = frame_data.get("camera_id", "Unknown")  # Default to 'Unknown' if not found
        frame = frame_data.get("frame", None)  # Ensure 'frame' is present
        user_id = frame_data.get("user_id", "Unknown") # Default to 'Unknown'
        date_time = frame_data.get("date_time", "Unknown") # Default
        object_list = frame_data.get("object_list",None)
        #print("This is payload data :", frame_data)
        
        if frame is None:
            raise log_error("Frame data is missing from the message")

        # Detect and classify objects in the frame
        if "person" in object_list:
            # Run tracking
            results = model.track(source=frame, classes=0, persist=True, tracker=tracker_config_path,verbose=False)[0]
            # Draw results
            boxes = results.boxes
            if boxes.id is not None:
                for box, cls_id, track_id, score in zip(boxes.xyxy, boxes.cls, boxes.id, boxes.conf):
                    if score > 0.4:
                        x1, y1, x2, y2 = map(int, box.tolist())
                        class_id = int(cls_id.item())
                        track_id = int(track_id.item())
                        class_name = results.names[class_id]
                        #person_crop = frame[y1:y2, x1:x2]
                        # === Extract ReID feature here ===
                        feature = extract_reid_feature(frame, (x1, y1, x2, y2))
                        print("THese are feature :", feature)
                        if feature is not None:
                            print(f"[ReID] Feature for Track ID {track_id}: {feature[:5]}...")  # Print first 5 dims
                        reid_id = match_reid(feature)
                        label = f"{class_name} (ReID:{reid_id})"


                        #label = f"{class_name} (ID:{track_id})"
                        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                        cv2.putText(frame, label, (x1, y1 + 10),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)
            # Resize and show
            frame = cv2.resize(frame, (900, 700))
            # Display in the correct window based on camera ID
            if camera_id == 20:
                cv2.imshow("win20", frame)
            elif camera_id == 21:
                cv2.imshow("win21", frame)
            else:
                cv2.imshow("win_unknown", frame)  # Optional: for unexpected IDs
            if cv2.waitKey(20) & 0xFF == ord("q"):
                cv2.destroyAllWindows()
                os._exit(0)      
            # Print metadata (camera ID)
            log_info(f"Received frame from Camera ID: {camera_id}")
    
    except Exception as e:
        log_exception(f"Error processing frame --=: {e}")

def main(receive_queue_name="all_frame", processed_queue_name="detect_person_object", rabbitmq_host="localhost"):
    """
    Main function to set up RabbitMQ connections for receiving and sending frames.

    Args:
        queue_name (str): The RabbitMQ queue to consume frames from. Defaults to 'video_frames'.
        processed_queue_name (str): The RabbitMQ queue to send processed frames to. Defaults to 'processed_frames'.
    """
    # Set up RabbitMQ connection and channel for receiving frames
    receiver_connection, receiver_channel = setup_rabbitmq_connection(receive_queue_name, rabbitmq_host)
    queue_name = "detected_vehicle"

    while True:
        try:
            if not receiver_channel.is_open:
                log_error("Receiver channel is closed. Attempting to reconnect.")
                time.sleep(25)
                receiver_connection, receiver_channel = setup_rabbitmq_connection(receive_queue_name, rabbitmq_host)
            receiver_channel.queue_declare(queue=queue_name, durable=True)
            receiver_channel.queue_bind(exchange=receive_queue_name, queue=queue_name)
            # Start consuming frames from the 'video_frames' queue
            receiver_channel.basic_consume(
                queue=queue_name, 
                on_message_callback=lambda ch, method, properties, body: process_frame(
                    ch, method, properties, body, processed_queue_name,rabbitmq_host 
                ),
                auto_ack=True
            )
            log_info("Waiting for video frames...")
            receiver_channel.start_consuming()
        except pika.exceptions.ConnectionClosedByBroker as e:
            log_error("Connection closed by broker, reconnecting...")
            time.sleep(25)
            receiver_connection, receiver_channel = setup_rabbitmq_connection(receive_queue_name, rabbitmq_host)

        except Exception as e:
            log_exception(f"Unexpected error: {e}")
            time.sleep(25)
            continue
    

if __name__ == "__main__":
    # Start the receiver and sender
    main()

