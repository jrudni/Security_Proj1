import paho.mqtt.client as mqtt
import json
import base64
from pathlib import Path
from file_prepare import MerkleTree
import time
import re
import binascii

#BROKER SETTINGS
BROKER_HOST = "localhost"
PORT = 1883
TIMEOUT = 30
CHUNK_COUNT = 4 # default
MANIFEST_TOPIC = "ota/pi5/manifest"
CHUNKS_TOPIC = "ota/pi5/chunks"
OUTPUT_FILE = Path("firmware_reconstructed.txt")

#Client Object class
class OTAClient:
    def __init__(self):
        self.broker_host = BROKER_HOST
        self.port = PORT
        self.timeout = TIMEOUT
        self.manifest_topic = MANIFEST_TOPIC
        self.chunk_topic = CHUNKS_TOPIC
        self.output_file = OUTPUT_FILE
        self.chunk_count = CHUNK_COUNT

        #creates the MQTT client
        self.client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id = "ota-pi5-client"
        )

        # Store received data
        self.manifest = None
        self.chunks = {}
        self.finished = False
        self.last_activity = time.monotonic()

        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message

        
    #Subscribes manifest and chunk topics
    def on_connect(self, client, userdata, flags, reason_code, properties):
        if reason_code.is_failure:
            self.reject(f"Connection failed: {reason_code}")
            return
        print("Connected to the MQTT broker")
        client.subscribe([
            (self.manifest_topic,1),
            (self.chunk_topic,1)
        ])
        print("Subscribed to manifest and chunk topics.")


    #Decides whether a message is a manifest or a chunk
    def on_message(self,client,userdata,msg):
        if self.finished:
            return
        self.last_activity = time.monotonic()

        try:
            print(f"Received message on topic {msg.topic}")
            payload = json.loads(msg.payload.decode("utf-8"))
        except(ValueError, UnicodeDecodeError):
            self.reject("Invalid JSON received.")
            return
            
        if not isinstance(payload, dict):
            self.reject("Message must be a JSON object.")
            return
            
        if msg.topic == self.manifest_topic:
            self.handle_manifest(payload)

        elif msg.topic == self.chunk_topic:
            self.handle_chunk(payload)

        #Validates and stores the manifest
    def handle_manifest(self,payload):
        if not self.validate_manifest(payload):
            self.reject("Invalid manifest or chunk data")
            return
            
        if self.manifest is not None:
            if payload != self.manifest:
                self.reject("Conflicting manifest recieved")
            else:
                print("Duplicate manifest")
            return
            
        self.manifest = payload

        print("Manifest recieved and validated:\n")
        print(self.manifest)



        #Decodes and then validates and stores each chunk
    def handle_chunk(self,payload):
        firmware_ver = payload.get("firmware_version")
        index = payload.get("chunk_index")
        encoded_chunk = payload.get("chunk_data")

        if self.manifest is None:
            print("Manifest not yet received. Cannot validate chunks.")
            return

        if firmware_ver != self.manifest["firmware_version"]:
            self.reject("Firmware version mismatch.")
            return

        if type(index) is not int or index not in range(self.chunk_count):
            self.reject("Invalid Chunk Index")
            return
        
            #checks whether the chunk index is in the manifest indexes
        manifest_indexes = {
            item["index"] for item in self.manifest["chunks"]
        }
        if index not in manifest_indexes:
            self.reject(f"Chunk {index} not listed in the manifest.")
            return
            
        if not isinstance(encoded_chunk, str) or not encoded_chunk:
            self.reject(f"Missing or Invalid data for chunk {index}.")
            return

        try:
            chunk = base64.b64decode(encoded_chunk, validate=True)
        except (ValueError, binascii.Error):
            self.reject(f"Could not decode chunk {index}.")
            return

        if not chunk:
            self.reject(f"Chunk {index} is empty")
            return

            #Handles duplicate indexes
        if index in self.chunks:
            if self.chunks[index] == chunk:
                print(f"Duplicate chunk {index} ignored.")
            else:
                self.reject(f"Conflicting chunk {index}")
            return
            
        self.chunks[index] = chunk
        print(f"Recieved chunk {index}.")

            #verifies when all the 4 chunks have arrived
        if len(self.chunks) == self.chunk_count:
            self.verify_firmware()

        #Verifies the Merkle Root and reconstructs the file
    def verify_firmware(self):
        if set(self.chunks) != set(range(self.chunk_count)):
            self.reject("Missing or Invalid chunk indexes.")
            return
        ordered_chunks = [
            self.chunks[index]
            for index in range(self.chunk_count)
        ]

        try:
            tree = MerkleTree(ordered_chunks)
        except (ValueError, TypeError) as error:
            self.reject(f"Not able to build the Merkle Tree: {error}")
            return

        expected_root = self.manifest["merkle_root"].lower()
        actual_root = tree.root.hash.lower()

        if actual_root != expected_root:
            self.reject("Mismatch in the Merkle Root, firmware possibly modified.")
            return

        firmware = b"".join(ordered_chunks)
        if len(firmware) != self.manifest["firmware_size"]:
            self.reject("Mismatch in the size of the firmware.")
            return

        try:
            self.output_file.write_bytes(firmware)
        except OSError as error:
            self.reject(f"Not able to write firmware file: {error}")
            return

        self.finished = True
        print("\nUPDATE ACCEPTED!!!")
        print("Merkle root verification: PASS")
        print("Firmware size verification: PASS")
        print(f"Reconstructed file: {self.output_file.resolve()}")
        
    def validate_manifest(self,payload):
        version = payload.get("firmware_version")
        size = payload.get("firmware_size")
        root = payload.get("merkle_root")
        chunk_files = payload.get("chunks")

        if not isinstance(version, str) or not version.strip():
            return False

        if type(size) is not int or size < self.chunk_count:
            return False

            #checks whether all the 64 characters in the merkle tree are hexadecimal
        if not isinstance(root, str) or not re.fullmatch(
            r"[0-9a-fA-F]{64}", root):
            return False

        if not isinstance(chunk_files, list):
            return False

        if len(chunk_files)!= self.chunk_count:
            return False

        indexes = []
        filenames = []

        for item in chunk_files:
            if not isinstance(item, dict):
                return False

            index = item.get("index")
            filename = item.get("filename")

            if type(index) is not int or index not in range(self.chunk_count):
                return False

            if not isinstance(filename, str) or not filename.strip():
                return False

            if Path(filename).name != filename:
                return False

            indexes.append(index)
            filenames.append(filename)

            #makes sure the indexes are 0,1,2,3
        if sorted(indexes) != list(range(self.chunk_count)):
            return False
            #makes sure that every chunk has a different file name
        if len(set(filenames)) != self.chunk_count:
            return False
            
        return True
        
        #stops update, clears chunks and removes the output file
    def reject(self,reject_reason):
        if self.finished:
            return
            
        self.finished = True
        self.chunks.clear()
        try:
            self.output_file.unlink(missing_ok=True)
        except OSError as error:
            print(f"Warning: could not remove output file: {error}")

        print(f"\nUPDATE REJECTED: {reject_reason}")
        print("Firmware was not accepted.")

        #Starts the MQTT and waits for the update,and handles timeout
    def run(self):
        try:
            self.output_file.unlink(missing_ok=True)
            self.client.connect(self.broker_host, self.port, 60)

            while not self.finished:
                self.client.loop(timeout=1.0)

                if time.monotonic() - self.last_activity > self.timeout:
                    if self.manifest is None:
                        self.reject("Session timed out while waiting for the manifest.")
                    else:
                        missing_chunks = sorted(
                            set(range(self.chunk_count)) - set(self.chunks)
                        )
                        self.reject(f"Session timed out while waiting for chunks: {missing_chunks}")
        except (OSError,ValueError) as error:
            self.reject(f"MQTT connection error: {error}")

        finally:
            if self.client.is_connected():
                self.client.disconnect()

if __name__ == "__main__":
    ota_client = OTAClient()
    ota_client.run()
            
                

# def on_connect(client, userdata, flags, res_code, properties):
#     print(f"Connected with result code {res_code}")
#     client.subscribe("ota/pi5/manifest", qos=1)
#     client.subscribe("ota/pi5/chunks", qos=1)

# def on_message(client, userdata, msg):
#     print(f"Received message on topic {msg.topic}")
#     payload = json.loads(msg.payload.decode('utf-8'))
    
#     if msg.topic == "ota/pi5/manifest":
#         print("Manifest received:")
#         global manifest
#         global CHUNK_COUNT
#         manifest = payload
#         CHUNK_COUNT = manifest.get("CHUNK_COUNT", 4)
#         print(manifest)
    
#     elif msg.topic == "ota/pi5/chunks":
#         if not validate_chunk(payload):
#             print("Invalid chunk received, ignoring.")
#             return
        
#         chunk_index = payload.get("chunk_index")
#         chunk_data = base64.b64decode(payload.get("chunk_data"), validate=True)
#         if chunk_index not in chunks:
#             chunks[chunk_index] = chunk_data
#             print(f"Chunk {chunk_index} received, size: {len(chunk_data)} bytes")
#         else:
#             print(f"Chunk {chunk_index} already received, ignoring duplicate.")


# def validate_chunk(payload) -> bool:
#     if manifest is None:
#         print("Manifest not received yet. Cannot validate chunks.")
#         return False
    
#     if payload.get("firmware_version") != manifest.get("firmware_version"):
#         print("Firmware version mismatch.")
#         return False

#     if payload.get("chunk_index") is None or payload.get("chunk_data") is None:
#         print("Invalid chunk message format.")
#         return False

#     if not isinstance(payload.get("chunk_index"), int):
#         print("Chunk index is not an integer.")
#         return False

#     if payload.get("chunk_index") < 0 or payload.get("chunk_index") >= CHUNK_COUNT:
#         print("Chunk index out of bounds.")
#         return False

#     return True


# mqttc = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
# mqttc.on_connect = on_connect
# mqttc.on_message = on_message
# mqttc.connect("localhost", 1883, 60)
# mqttc.loop_forever()