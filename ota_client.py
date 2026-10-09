import paho.mqtt.client as mqtt
import json
import base64

chunk_count = 4 # default

manifest = None

chunks = {}


def on_connect(client, userdata, flags, res_code, properties):
    print(f"Connected with result code {res_code}")
    client.subscribe("ota/pi5/manifest", qos=1)
    client.subscribe("ota/pi5/chunks", qos=1)

def on_message(client, userdata, msg):
    print(f"Received message on topic {msg.topic}")
    payload = json.loads(msg.payload.decode('utf-8'))
    
    if msg.topic == "ota/pi5/manifest":
        print("Manifest received:")
        global manifest
        global chunk_count
        manifest = payload
        chunk_count = manifest.get("chunk_count", 4)
        print(manifest)
    
    elif msg.topic == "ota/pi5/chunks":
        if not validate_chunk(payload):
            print("Invalid chunk received, ignoring.")
            return
            chunk_index = payload.get("chunk_index")
        chunk_data = base64.b64decode(payload.get("chunk_data"), validate=True)
        if chunk_index not in chunks:
            chunks[chunk_index] = chunk_data
            print(f"Chunk {chunk_index} received, size: {len(chunk_data)} bytes")
        else:
            print(f"Chunk {chunk_index} already received, ignoring duplicate.")


def validate_chunk(payload) -> bool:
    if manifest is None:
        print("Manifest not received yet. Cannot validate chunks.")
        return False
    
    if payload.get("firmware_version") != manifest.get("firmware_version"):
        print("Firmware version mismatch.")
        return False

    if payload.get("chunk_index") is None or payload.get("chunk_data") is None:
        print("Invalid chunk message format.")
        return False

    if not isinstance(payload.get("chunk_index"), int):
        print("Chunk index is not an integer.")
        return False

    if payload.get("chunk_index") < 0 or payload.get("chunk_index") >= chunk_count:
        print("Chunk index out of bounds.")
        return False

    return True


mqttc = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
mqttc.on_connect = on_connect
mqttc.on_message = on_message
mqttc.connect("localhost", 1883, 60)

mqttc.loop_forever()

