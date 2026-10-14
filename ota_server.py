import paho.mqtt.publish as publish
import run
import base64
import json

host = "localhost"

manifest_message = {'topic': "ota/pi5/manifest", 'payload': "", 'qos': 1, 'retain': True}

if __name__ == "__main__":
    # Get the manifest and chunks
    data = run.read_file(run.file_name)

    # ATTACK 2: simulate malicious firmware modification
    # data = data + b"\nMALICIOUS MODIFICATION FOR ATTACK 2\n"
    # print("ATTACK 2: firmware modified in memory")

    chunk_count = 4  # Number of chunks to split the data into
    data_chunks = run.split_data(data, chunk_count)

    for i, chunk in enumerate(data_chunks):
        with open(f"chunk_{i}.bin", "wb") as f:
            f.write(chunk)

    merkle_tree = run.MerkleTree(data_chunks)

    manifest = run.create_manifest(merkle_tree, data, chunk_count, data_chunks)

    with open("manifest.json", "w") as f:
        json.dump(manifest, f, indent=4)

    # Update the payloads for the MQTT messages
    manifest_message['payload'] = json.dumps(manifest).encode('utf-8')
    chunk_payloads = []
    for i, chunk in enumerate(data_chunks):
        # chunk_to_send = chunk
        # #TESTING TAMPERED CHUNK by modifying 1 byte in chunk 1
        # if i==1:
        #     chunk_to_send = bytes([chunk[0] ^ 1]) + chunk[1:]
        #     print(f"Test: Sending TAMPERED chunk 1")

        # print(f"Publishing chunk {i}, tampered={chunk_to_send != chunk}")
        chunk_payloads.append(
            {
                "firmware_version": manifest["firmware_version"],
                "chunk_index": i,
                "chunk_data": base64.b64encode(chunk).decode('utf-8')  # Encode the chunk data in base64 for transmission
            }
        )
    
    messages = [manifest_message]  # Start with the manifest message

    #Testing validation and integrity by sending only 3 chunks
    # for payload in chunk_payloads[:3]: 
    for payload in chunk_payloads:
        messages.append(
            {
                'topic': "ota/pi5/chunks",
                'payload': json.dumps(payload).encode('utf-8'),
                'qos': 1,
                'retain': False
            }
        )
        #Testing validation by sending a duplicate of chunk 1
        if payload["chunk_index"] == 1: 
            messages.append(
                {
                    'topic': "ota/pi5/chunks",
                    'payload': json.dumps(payload).encode('utf-8'),
                    'qos': 1,
                    'retain': False
                }
            )    
    
    publish.multiple(messages, hostname=host)